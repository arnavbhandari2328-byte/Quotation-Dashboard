import os
import asyncio
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

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


# ── API: Product catalog ──

@app.get("/api/products")
async def api_products():
    """
    Returns the full product catalog as a nested structure:
    {
      "SS 304": {
        "SCH-10 (ERW)": [
          {"product_id": "...", "product_name": "...", "material": "SS 304", "category": "SCH-10 (ERW)"},
          ...
        ],
        ...
      },
      "SS 316": { ... },
      ...
    }
    """
    catalog = database.get_product_catalog()
    return JSONResponse(content=catalog)


@app.get("/api/products/search")
async def api_products_search(q: str = Query(..., min_length=1, description="Search term")):
    """
    Search products by name substring.
    Example: /api/products/search?q=SCH-10
    Returns a flat list of matching {product_id, product_name, material, category}.
    """
    results = database.search_products(q)
    return JSONResponse(content=results)


@app.post("/api/products/backfill")
async def api_products_backfill():
    """
    One-time operation: reads every row in `products`, infers material + category
    from product_name, and PATCHes those values back into the DB.

    Prerequisites — run these SQL statements in Supabase SQL Editor first:
        ALTER TABLE products ADD COLUMN IF NOT EXISTS material text;
        ALTER TABLE products ADD COLUMN IF NOT EXISTS category text;

    Returns: { updated, skipped, errors }
    """
    result = await asyncio.to_thread(database.backfill_product_categories)
    return JSONResponse(content=result)
