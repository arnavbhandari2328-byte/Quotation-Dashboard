import os
import asyncio
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from typing import Optional

from server.pdf_generator import create_quotation_pdf
from server.main import process_inbox
from server.email_reader import send_quotation_email
from server import database

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🤖 Quotify Dashboard started — inbox watcher running...")
    task = asyncio.create_task(background_inbox_check())
    yield
    task.cancel()


async def background_inbox_check():
    while True:
        try:
            await asyncio.to_thread(process_inbox)
        except Exception as e:
            print(f"❌ Inbox check failed: {e}")
        await asyncio.sleep(300)


app = FastAPI(title="Quotify Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Home: Pending enquiries ──
@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    enquiries = database.list_pending()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"enquiries": enquiries, "view": "pending"}
    )


# ── History: All sent quotes ──
@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    sent = database.list_sent()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"enquiries": sent, "view": "history"}
    )


# ── Generate & Send Quote ──
@app.post("/generate/{enquiry_id}")
async def generate_quote(
    enquiry_id: str,
    rate: str = Form(...),
    payment_terms: str = Form(...),
    pickup_location: str = Form(...),
    gst: str = Form(...)
):
    enquiry_data = database.get_enquiry(enquiry_id)

    if not enquiry_data:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    # 1. Generate PDF
    pdf_filepath = create_quotation_pdf(
        enquiry_data, rate, payment_terms, pickup_location, gst
    )

    # 2. Send email to customer
    customer_email = enquiry_data.get('customer_email')
    customer_name = enquiry_data.get('customer_name', 'Customer')
    email_sent = False

    if customer_email:
        email_sent = send_quotation_email(customer_email, customer_name, pdf_filepath)

    # 3. Calculate financials for quotes table
    try:
        rate_clean = float(str(rate).replace('/kg','').replace('/pc','').replace('/m','').replace(',','').strip())
    except (ValueError, TypeError):
        rate_clean = 0.0

    try:
        qty = float(enquiry_data.get('quantity') or 0)
    except (ValueError, TypeError):
        qty = 0.0

    try:
        gst_pct = float(str(gst).replace('%','').strip())
    except (ValueError, TypeError):
        gst_pct = 18.0

    subtotal = round(rate_clean * qty, 2)
    gst_amount = round(subtotal * gst_pct / 100, 2)
    grand_total = round(subtotal + gst_amount, 2)

    # 4. Save to quotes table
    database.save_quote({
        "id": str(uuid.uuid4()),
        "enquiry_id": enquiry_id,
        "rate": rate_clean,
        "subtotal": subtotal,
        "gst_rate": gst_pct,
        "gst_amount": gst_amount,
        "grand_total": grand_total,
        "payment_terms": payment_terms,
        "validity_days": 5,
        "notes": f"F.O.R: {pickup_location}",
        "pdf_path": pdf_filepath,
        "sent_at": datetime.utcnow().isoformat()
    })

    # 5. Update enquiry status
    final_status = "EMAIL SENT" if email_sent else "PDF GENERATED"
    database.mark_quoted(enquiry_id, final_status)

    return RedirectResponse(url="/", status_code=303)


# ── API: enquiry endpoints ──
@app.get("/api/enquiries")
async def api_enquiries():
    return database.list_pending()


@app.get("/api/all")
async def api_all():
    return database.list_all()


@app.get("/api/history")
async def api_history():
    return database.list_sent()


# ════════════════════════════════════════════════
# PRODUCT CATALOG ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/api/products")
async def api_products():
    """
    Returns the full product catalog as a nested structure:
    { material: { category: [ {product_id, product_name, material, category, location} ] } }
    """
    catalog = database.get_product_catalog()
    return JSONResponse(content=catalog)


@app.get("/api/products/search")
async def api_products_search(q: str = Query(..., min_length=1)):
    """
    Search products by name substring.
    Returns a flat list of matching products including location.
    """
    results = database.search_products(q)
    return JSONResponse(content=results)


@app.post("/api/products")
async def api_add_product(payload: dict = Body(...)):
    """
    Add a new product.
    Body: { product_id, product_name, material?, category?, location? }
    material and category are auto-inferred from product_name if omitted.

    Run this SQL in Supabase first if location column doesn't exist:
        ALTER TABLE products ADD COLUMN IF NOT EXISTS location text;
    """
    required = ["product_id", "product_name"]
    for field in required:
        if not payload.get(field):
            raise HTTPException(status_code=422, detail=f"Missing required field: {field}")

    ok = await asyncio.to_thread(database.add_product, payload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add product")
    return JSONResponse(content={"success": True, "product_id": payload["product_id"]})


@app.post("/api/products/backfill")
async def api_products_backfill():
    """
    One-time: infer material+category for all products from product_name and PATCH back.
    Prerequisites:
        ALTER TABLE products ADD COLUMN IF NOT EXISTS material text;
        ALTER TABLE products ADD COLUMN IF NOT EXISTS category text;
    """
    result = await asyncio.to_thread(database.backfill_product_categories)
    return JSONResponse(content=result)


# ════════════════════════════════════════════════
# WAREHOUSE STOCK ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/api/warehouse/stock")
async def api_warehouse_stock():
    """Current stock levels per product (qty = IN - OUT)."""
    levels = await asyncio.to_thread(database.get_warehouse_stock_levels)
    return JSONResponse(content=levels)


@app.get("/api/warehouse/catalog")
async def api_warehouse_catalog():
    """Full product catalog merged with live warehouse stock levels."""
    catalog = await asyncio.to_thread(database.get_warehouse_catalog_with_stock)
    return JSONResponse(content=catalog)


@app.get("/api/warehouse/entries")
async def api_warehouse_entries(product_id: Optional[str] = Query(None)):
    """
    Ledger rows for warehouse.
    ?product_id=<id> → filtered by product
    No param → all rows
    """
    entries = await asyncio.to_thread(database.get_warehouse_entries, product_id)
    return JSONResponse(content=entries)


@app.post("/api/warehouse/entries")
async def api_add_warehouse_entry(payload: dict = Body(...)):
    """
    Add a warehouse stock movement (IN or OUT).
    Body: { product_id, product_name, material, category, type, qty, unit, rate?, entry_date, remarks?, is_hero? }
    """
    required = ["product_id", "type", "qty", "entry_date"]
    for field in required:
        if payload.get(field) is None:
            raise HTTPException(status_code=422, detail=f"Missing required field: {field}")
    if payload["type"] not in ("IN", "OUT"):
        raise HTTPException(status_code=422, detail="type must be 'IN' or 'OUT'")

    ok = await asyncio.to_thread(database.add_warehouse_entry, payload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save warehouse entry")
    return JSONResponse(content={"success": True})


@app.delete("/api/warehouse/entries/{entry_id}")
async def api_delete_warehouse_entry(entry_id: str):
    """Delete a single warehouse stock row by its UUID."""
    ok = await asyncio.to_thread(database.delete_warehouse_entry, entry_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Delete failed")
    return JSONResponse(content={"success": True})


@app.patch("/api/warehouse/hero")
async def api_warehouse_toggle_hero(payload: dict = Body(...)):
    """
    Toggle is_hero flag for a warehouse product.
    Body: { product_id, is_hero }
    """
    product_id = payload.get("product_id")
    is_hero    = payload.get("is_hero")
    if product_id is None or is_hero is None:
        raise HTTPException(status_code=422, detail="product_id and is_hero required")
    ok = await asyncio.to_thread(database.toggle_warehouse_hero, product_id, is_hero)
    if not ok:
        raise HTTPException(status_code=500, detail="Toggle failed")
    return JSONResponse(content={"success": True})


# ════════════════════════════════════════════════
# OFFICE STOCK ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/api/office/stock")
async def api_office_stock():
    """
    Current office stock levels.
    Returns: { "mat||cat||item": { item_name, material, category, qty, unit, is_hero } }
    """
    levels = await asyncio.to_thread(database.get_office_stock_levels)
    return JSONResponse(content=levels)


@app.get("/api/office/catalog")
async def api_office_catalog():
    """
    Office stock as nested catalog: { material: { category: [ items ] } }
    Categories follow the same rules as warehouse stock.
    """
    catalog = await asyncio.to_thread(database.get_office_catalog_with_stock)
    return JSONResponse(content=catalog)


@app.get("/api/office/entries")
async def api_office_entries(
    item_name: Optional[str] = Query(None),
    material:  Optional[str] = Query(None),
    category:  Optional[str] = Query(None),
):
    """
    Ledger rows for office stock.
    Filter by ?item_name=, ?material=, ?category= (all optional, combinable).
    No params → all rows.
    """
    entries = await asyncio.to_thread(
        database.get_office_entries, item_name, material, category
    )
    return JSONResponse(content=entries)


@app.post("/api/office/entries")
async def api_add_office_entry(payload: dict = Body(...)):
    """
    Add an office stock movement (IN or OUT).
    Body: { item_name, type, qty, unit, entry_date, rate?, material?, category?, remarks?, is_hero? }

    material and category are auto-inferred from item_name if not provided,
    using the same rules as warehouse stock — so categories stay consistent.
    """
    required = ["item_name", "type", "qty", "entry_date"]
    for field in required:
        if payload.get(field) is None:
            raise HTTPException(status_code=422, detail=f"Missing required field: {field}")
    if payload["type"] not in ("IN", "OUT"):
        raise HTTPException(status_code=422, detail="type must be 'IN' or 'OUT'")

    ok = await asyncio.to_thread(database.add_office_entry, payload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save office entry")
    return JSONResponse(content={"success": True})


@app.delete("/api/office/entries/{entry_id}")
async def api_delete_office_entry(entry_id: str):
    """Delete a single office stock row by its UUID."""
    ok = await asyncio.to_thread(database.delete_office_entry, entry_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Delete failed")
    return JSONResponse(content={"success": True})


@app.patch("/api/office/hero")
async def api_office_toggle_hero(payload: dict = Body(...)):
    """
    Toggle is_hero flag for an office item.
    Body: { item_name, material, category, is_hero }
    """
    item_name = payload.get("item_name")
    material  = payload.get("material")
    category  = payload.get("category")
    is_hero   = payload.get("is_hero")
    if not all([item_name, material, category, is_hero is not None]):
        raise HTTPException(status_code=422, detail="item_name, material, category, is_hero all required")
    ok = await asyncio.to_thread(database.toggle_office_hero, item_name, material, category, is_hero)
    if not ok:
        raise HTTPException(status_code=500, detail="Toggle failed")
    return JSONResponse(content={"success": True})


# ════════════════════════════════════════════════
# TRANSACTIONS (combined)
# ════════════════════════════════════════════════

@app.get("/api/transactions")
async def api_transactions(limit: int = Query(200, ge=1, le=1000)):
    """Combined warehouse + office ledger, sorted by date desc."""
    txns = await asyncio.to_thread(database.get_all_transactions, limit)
    return JSONResponse(content=txns)


# ════════════════════════════════════════════════
# DASHBOARD ANALYTICS
# ════════════════════════════════════════════════

@app.get("/api/dashboard")
async def api_dashboard():
    """Full dashboard analytics payload."""
    data = await asyncio.to_thread(database.get_dashboard_analytics)
    return JSONResponse(content=data)
