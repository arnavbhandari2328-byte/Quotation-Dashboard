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

def _get(endpoint):
    """Safe GET with detailed error printing."""
    try:
        r = requests.get(endpoint, headers=_headers())
        if not r.ok:
            print(f"❌ Supabase error {r.status_code}: {r.text}")
            r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []


def save_enquiry(enquiry_data: dict):
    """Save a new enquiry to Supabase."""
    try:
        r = requests.post(
            f"{url}/rest/v1/enquiries",
            json=enquiry_data,
            headers=_headers()
        )
        if not r.ok:
            print(f"❌ Save failed {r.status_code}: {r.text}")
            return False
        print(f"✅ Saved: {enquiry_data.get('customer_name', 'Unknown')}")
        return True
    except Exception as e:
        print(f"❌ Save error: {e}")
        return False


def get_enquiry(enquiry_id: str):
    """Fetch a single enquiry by ID."""
    data = _get(f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}&select=*")
    return data[0] if data else None


def list_pending():
    """Return all PENDING enquiries."""
    return _get(f"{url}/rest/v1/enquiries?status=eq.PENDING&select=*")


def list_all():
    """Return ALL enquiries for history tab."""
    return _get(f"{url}/rest/v1/enquiries?select=*")


def mark_quoted(enquiry_id: str, status: str = "EMAIL SENT"):
    """Update enquiry status after quote is sent."""
    try:
        r = requests.patch(
            f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}",
            json={"status": status},
            headers=_headers()
        )
        if not r.ok:
            print(f"❌ Mark failed {r.status_code}: {r.text}")
            return False
        print(f"✅ Enquiry {enquiry_id} → {status}")
        return True
    except Exception as e:
        print(f"❌ Mark error: {e}")
        return False


def email_already_imported(raw_body: str) -> bool:
    """Prevent duplicate emails from being processed twice."""
    try:
        # Check using first 80 chars of email body as a fingerprint
        snippet = (raw_body or "").strip()[:80]
        encoded = requests.utils.quote(snippet)
        data = _get(f"{url}/rest/v1/enquiries?raw_email=like.{encoded}*&select=id")
        return len(data) > 0
    except Exception:
        return False
