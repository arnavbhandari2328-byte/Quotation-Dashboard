import os
import requests
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from server.pdf_generator import create_quotation_pdf
from server.main import process_inbox
from server.email_reader import send_quotation_email

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# --- The Automated Background Loop ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🤖 Starting Quotify Auto-Inbox Watcher...")
    task = asyncio.create_task(background_inbox_check())
    yield
    task.cancel() # Turns off when you stop the server

async def background_inbox_check():
    while True:
        try:
            # Runs your main.py function in the background
            await asyncio.to_thread(process_inbox) 
        except Exception as e:
            print(f"❌ Inbox check failed: {e}")
        
        # Wait 60 seconds before checking Gmail again
        await asyncio.sleep(60) 
# ------------------------------------------

app = FastAPI(title="Quotify Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    endpoint = f"{url}/rest/v1/enquiries?select=*"
    
    enquiries = []
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        enquiries = response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")

    return templates.TemplateResponse(
        request=request, name="index.html", context={"enquiries": enquiries}
    )

# Changed from .get to .post!
@app.post("/generate/{enquiry_id}")
async def generate_quote(
    enquiry_id: str,
    rate: str = Form(...),
    payment_terms: str = Form(...),
    pickup_location: str = Form(...),
    gst: str = Form(...)
):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    get_endpoint = f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}&select=*"
    response = requests.get(get_endpoint, headers=headers)
    
    if response.status_code == 200 and len(response.json()) > 0:
        enquiry_data = response.json()[0]
        
        # 1. Pass the 4 manual inputs to the PDF builder!
        pdf_filepath = create_quotation_pdf(enquiry_data, rate, payment_terms, pickup_location, gst)
        
        # 2. Email the PDF directly to the customer
        customer_email = enquiry_data.get('customer_email')
        customer_name = enquiry_data.get('customer_name', 'Customer')
        
        email_sent = False
        if customer_email:
            email_sent = send_quotation_email(customer_email, customer_name, pdf_filepath)
        
        # 3. Update the database status
        final_status = "EMAIL SENT" if email_sent else "FAILED"
        patch_endpoint = f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}"
        requests.patch(patch_endpoint, json={"status": final_status}, headers=headers)

    return RedirectResponse(url="/", status_code=303)