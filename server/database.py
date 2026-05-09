import os
import requests
from datetime import datetime
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
    try:
        r = requests.post(
            f"{url}/rest/v1/enquiries",
            json=enquiry_data,
            headers={**_headers(), "Prefer": "return=representation"}
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
    data = _get(f"{url}/rest/v1/enquiries?id=eq.{enquiry_id}&select=*")
    return data[0] if data else None


def list_pending():
    return _get(f"{url}/rest/v1/enquiries?status=eq.PENDING&select=*&order=received_at.desc")


def list_all():
    return _get(f"{url}/rest/v1/enquiries?select=*&order=received_at.desc")


def list_sent():
    """Return enquiries that have been quoted, joined with quote details."""
    return _get(
        f"{url}/rest/v1/enquiries"
        f"?status=in.(EMAIL%20SENT,COMPLETED)&select=*,quotes(rate,grand_total,payment_terms,sent_at)&order=received_at.desc"
    )


def save_quote(quote_data: dict):
    """Insert a new row into the quotes table with all commercial details."""
    try:
        r = requests.post(
            f"{url}/rest/v1/quotes",
            json=quote_data,
            headers={**_headers(), "Prefer": "return=minimal"}
        )
        if not r.ok:
            print(f"❌ Save quote failed {r.status_code}: {r.text}")
            return False
        print(f"✅ Quote saved for enquiry {quote_data.get('enquiry_id')}")
        return True
    except Exception as e:
        print(f"❌ Save quote error: {e}")
        return False


def mark_quoted(enquiry_id: str, status: str = "EMAIL SENT"):
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
    try:
        snippet = (raw_body or "").strip()[:80]
        encoded = requests.utils.quote(snippet)
        data = _get(f"{url}/rest/v1/enquiries?raw_email=like.{encoded}*&select=id")
        return len(data) > 0
    except Exception:
        return False
