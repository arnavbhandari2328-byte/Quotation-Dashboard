import os
import re
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


# ─────────────────────────────────────────────────────────────────
# PRODUCT CATALOG — hierarchical: material → category → products
# ─────────────────────────────────────────────────────────────────

# Category inference rules: ordered by specificity.
# Each entry is (regex_pattern, display_label)
_CATEGORY_RULES = [
    # NB Pipes – SCH variants (ERW)
    (r"PIPE ERW SCH-05",  "SCH-05 (ERW)"),
    (r"PIPE ERW SCH-10",  "SCH-10 (ERW)"),
    (r"PIPE ERW SCH-20",  "SCH-20 (ERW)"),
    (r"PIPE ERW SCH-40",  "SCH-40 (ERW)"),
    # NB Pipes – SCH variants (SMLS)
    (r"PIPE SMLS SCH-10", "SCH-10 (Seamless)"),
    (r"PIPE SMLS SCH-40", "SCH-40 (Seamless)"),
    # OD / Seamless misc
    (r"SEAMLESS PIPE",    "Seamless Pipe"),
    # Structural / decorative pipes
    (r"PIPE ROUND",       "Round Pipe (OD)"),
    (r"PIPE SQUARE",      "Square Pipe"),
    (r"PIPE RECTANGLE|PIPR RECTANGLE|PIPE RECTANGE", "Rectangle Pipe"),
    (r"POLISH PIPE",      "Polish Pipe"),
    # CS pipe
    (r"CS PIPE",          "CS Pipe"),
    # Rods & bars
    (r"ROUND BRIGHT ROD", "Round Bright Rod"),
    (r"SQUARE ROD",       "Square Rod"),
    # Sheets
    (r"NO\.8 SHEET",      "No.8 Mirror Sheet"),
    (r"NO\.4",            "No.4 Satin Sheet"),
    (r"2B SHEET",         "2B Sheet"),
    # Structurals
    (r"ANGLE",            "Angle"),
    (r"FLAT",             "Flat Bar"),
    (r"SQUARE PIPE",      "Square Pipe (MS)"),
]

# Material extraction: map product_name keyword → top-level material key
_MATERIAL_PATTERNS = [
    (r"\bSS\s+304\b",  "SS 304"),
    (r"\bSS\s+316\b",  "SS 316"),
    (r"\bSS\s+202\b",  "SS 202"),
    (r"\bCS\b",        "CS (Carbon Steel)"),
    (r"\bMS\b",        "MS (Mild Steel)"),
]


def _infer_material(name: str) -> str:
    for pattern, label in _MATERIAL_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return label
    return "Other"


def _infer_category(name: str) -> str:
    for pattern, label in _CATEGORY_RULES:
        if re.search(pattern, name, re.IGNORECASE):
            return label
    return "Miscellaneous"


# ─────────────────────────────────────────────────────────────────
# BACKFILL — write material + category back into each products row
# Run once after adding the columns in Supabase:
#   ALTER TABLE products ADD COLUMN IF NOT EXISTS material text;
#   ALTER TABLE products ADD COLUMN IF NOT EXISTS category text;
# Then call POST /api/products/backfill
# ─────────────────────────────────────────────────────────────────

def backfill_product_categories() -> dict:
    """
    Reads every row from `products`, infers material + category from
    product_name, then PATCHes each row to store those values directly
    in the DB.  Returns a summary { updated, skipped, errors }.
    """
    rows = _get(f"{url}/rest/v1/products?select=product_id,product_name&order=product_name.asc")

    updated = 0
    skipped = 0
    errors  = 0

    for row in rows:
        pid   = row.get("product_id", "")
        pname = (row.get("product_name") or "").strip()
        if not pid or not pname:
            skipped += 1
            continue

        mat = _infer_material(pname)
        cat = _infer_category(pname)

        try:
            encoded_pid = requests.utils.quote(pid, safe="")
            r = requests.patch(
                f"{url}/rest/v1/products?product_id=eq.{encoded_pid}",
                json={"material": mat, "category": cat},
                headers=_headers()
            )
            if r.ok:
                updated += 1
            else:
                print(f"❌ Patch failed for {pid}: {r.status_code} {r.text}")
                errors += 1
        except Exception as e:
            print(f"❌ Exception patching {pid}: {e}")
            errors += 1

    print(f"✅ Backfill done — updated={updated}, skipped={skipped}, errors={errors}")
    return {"updated": updated, "skipped": skipped, "errors": errors}


# ─────────────────────────────────────────────────────────────────
# CATALOG READ — uses stored material/category columns if present,
# falls back to runtime inference if columns are null/missing.
# ─────────────────────────────────────────────────────────────────

def get_product_catalog() -> dict:
    """
    Fetch all products from Supabase and return a nested dict:
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
    Prefers the stored `material` and `category` columns; infers on the
    fly for any row where those columns are still null.
    """
    rows = _get(
        f"{url}/rest/v1/products"
        f"?select=product_id,product_name,material,category&order=product_name.asc"
    )

    catalog: dict = {}
    for row in rows:
        pid   = row.get("product_id", "")
        pname = (row.get("product_name") or "").strip()

        # Use stored values if available, otherwise infer
        mat = row.get("material") or _infer_material(pname)
        cat = row.get("category") or _infer_category(pname)

        catalog.setdefault(mat, {}).setdefault(cat, []).append({
            "product_id":   pid,
            "product_name": pname,
            "material":     mat,
            "category":     cat,
        })

    return catalog


def search_products(query: str) -> list:
    """Full-text search across product_name (case-insensitive substring)."""
    encoded = requests.utils.quote(f"*{query.strip()}*")
    rows = _get(
        f"{url}/rest/v1/products"
        f"?product_name=ilike.{encoded}&select=product_id,product_name,material,category&order=product_name.asc"
    )
    # Ensure material/category are always populated in results
    for row in rows:
        pname = (row.get("product_name") or "").strip()
        if not row.get("material"):
            row["material"] = _infer_material(pname)
        if not row.get("category"):
            row["category"] = _infer_category(pname)
    return rows
