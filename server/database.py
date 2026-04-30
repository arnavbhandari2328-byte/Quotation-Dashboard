import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

def _headers():
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

# ── Bug Fix 1: Added all missing functions that app.py was calling ──

def save_enquiry(enquiry_data: dict):
    """Save a new enquiry to Supabase."""
    try:
        response = requests.post(
            f"{url}/rest/v1/enquiries",
            json=enquiry_data,
            headers=_headers()
        )
        response.raise_for_status()
        print(f"✅ Saved enquiry: {enquiry_data.get('customer_name', 'Unknown')}")
        return True
    except Exception as e:
        print(f"❌ Error saving enquiry: {e}")
        return False


def get_enquiry(enquiry_id: str):
    """Fetch a single enquiry by ID from Supabase."""
    try:
        response = requests.get(
            f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}&select=*",
            headers=_headers()
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        print(f"❌ Error fetching enquiry {enquiry_id}: {e}")
        return None


def list_pending():
    """Return all PENDING enquiries, newest first."""
    try:
        response = requests.get(
            f"{url}/rest/v1/enquiries?status=eq.PENDING&select=*&order=created_at.desc",
            headers=_headers()
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error listing pending enquiries: {e}")
        return []


def list_all():
    """Return ALL enquiries for the history tab, newest first."""
    try:
        response = requests.get(
            f"{url}/rest/v1/enquiries?select=*&order=created_at.desc",
            headers=_headers()
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error listing all enquiries: {e}")
        return []


def mark_quoted(enquiry_id: str, status: str = "EMAIL SENT"):
    """Update status of an enquiry after quote is sent."""
    try:
        response = requests.patch(
            f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}",
            json={"status": status},
            headers=_headers()
        )
        response.raise_for_status()
        print(f"✅ Enquiry {enquiry_id} marked as {status}")
        return True
    except Exception as e:
        print(f"❌ Error updating enquiry status: {e}")
        return False


def email_already_imported(raw_body: str) -> bool:
    """Prevent duplicate processing — checks if this email body is already saved."""
    try:
        snippet = (raw_body or "")[:200]
        # Supabase full text match on first 200 chars
        response = requests.get(
            f"{url}/rest/v1/enquiries?raw_email=like.{requests.utils.quote(snippet[:50])}*&select=id",
            headers=_headers()
        )
        data = response.json()
        return len(data) > 0
    except Exception:
        return False
