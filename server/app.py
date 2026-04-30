import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from server.pdf_generator import create_quotation_pdf
from server.main import process_inbox
from server.email_reader import send_quotation_email
from server import database

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))


# ── Bug Fix 2: Background inbox poller (every 5 min, not 60s) ──
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
        await asyncio.sleep(300)  # Check every 5 minutes


app = FastAPI(title="Quotify Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Home: Pending enquiries ──
@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    enquiries = database.list_pending()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"enquiries": enquiries}
    )


# ── History: All sent quotes ──
@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    all_enquiries = database.list_all()
    sent = [e for e in all_enquiries if e.get("status") not in ("PENDING", "FAILED")]
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
    # ── Bug Fix 3: Use database.get_enquiry() instead of inline Supabase call ──
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

    # 3. Update status in Supabase
    final_status = "EMAIL SENT" if email_sent else "PDF GENERATED"
    database.mark_quoted(enquiry_id, final_status)

    return RedirectResponse(url="/", status_code=303)


# ── API endpoints (for future use / testing) ──
@app.get("/api/enquiries")
async def api_enquiries():
    return database.list_pending()


@app.get("/api/all")
async def api_all():
    return database.list_all()
