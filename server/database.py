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
    # NB Pipes – SCH variants (SMLS) — keyword form
    (r"PIPE SMLS SCH-10", "SCH-10 (Seamless)"),
    (r"PIPE SMLS SCH-40", "SCH-40 (Seamless)"),
    # Seamless pipes with SCH written out (e.g. "SS 316 SEAMLESS PIPE SCH-40 150 NB")
    (r"SEAMLESS PIPE SCH-40", "SCH-40 (Seamless)"),
    (r"SEAMLESS PIPE SCH-10", "SCH-10 (Seamless)"),
    (r"SEAMLESS PIPE SCH-20", "SCH-20 (Seamless)"),
    # OD / Seamless misc (no SCH suffix)
    (r"SEAMLESS PIPE",    "Seamless"),
    # Structural / decorative pipes
    (r"PIPE ROUND",       "Round Pipe (OD)"),
    (r"PIPE RECTANGLE|PIPR RECTANGLE|PIPE RECTANGE", "Rectangle Pipe"),
    (r"POLISH PIPE",      "Polish Pipe"),
    # CS pipe
    (r"CS PIPE",          "CS Pipe"),
    # Rods & bars — MUST come before SQUARE PIPE rules
    (r"ROUND BRIGHT ROD", "Round Bright Rod"),
    (r"SQUARE ROD",       "Square Rod"),
    # Square / Rectangle pipes (after rod rules)
    (r"PIPE SQUARE",      "Square Pipe"),
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
# SIZE SORT KEY — extract numeric size info for ascending order
#
# Priority of extraction:
#   1. NB size        → "15 NB", "150NB"          → (size, 0, 0)
#   2. OD size (inch) → "2\" OD", "1.5\" OD"      → (size, 0, 0)
#   3. OD size (mm)   → "48.3 OD"                  → (size, 0, 0)
#   4. SWG            → "14SWG", "16 SWG"          → (primary_dim, swg, 0)
#                        primary_dim from OD/dim first number if present
#   5. Dimension      → "16 X 16", "25 X 50"       → (first_dim, second_dim, 0)
#   6. Fallback       → alphabetical via name
# ─────────────────────────────────────────────────────────────────

def _size_sort_key(product_name: str):
    name = product_name.upper()

    # 1. NB size  e.g. "15 NB", "150NB", "1/2 NB"
    nb = re.search(r'(\d+(?:\.\d+)?)\s*NB', name)
    if nb:
        nb_val = float(nb.group(1))
        # Also extract SWG as secondary within same NB size
        swg = re.search(r'(\d+)\s*SWG', name)
        swg_val = float(swg.group(1)) if swg else 0
        return (nb_val, swg_val, 0, name)

    # 2. OD size in inches  e.g. 2" OD, 1/2" OD
    od_inch = re.search(r'(\d+(?:\.\d+)?)\s*["\u2019\']\s*OD', name)
    if od_inch:
        od_val = float(od_inch.group(1))
        swg = re.search(r'(\d+)\s*SWG', name)
        swg_val = float(swg.group(1)) if swg else 0
        return (od_val, swg_val, 0, name)

    # 3. OD size in mm  e.g. 48.3 OD, 60.3OD
    od_mm = re.search(r'(\d+(?:\.\d+)?)\s*OD', name)
    if od_mm:
        od_val = float(od_mm.group(1))
        swg = re.search(r'(\d+)\s*SWG', name)
        swg_val = float(swg.group(1)) if swg else 0
        return (od_val, swg_val, 0, name)

    # 4. SWG only (no OD/NB prefix)  e.g. "14SWG", "16 SWG"
    swg = re.search(r'(\d+)\s*SWG', name)
    if swg:
        return (0, float(swg.group(1)), 0, name)

    # 5. Dimension  e.g. "16 X 16", "25 X 50", "2\" X 2\""
    dim = re.search(r'(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)', name)
    if dim:
        return (float(dim.group(1)), float(dim.group(2)), 0, name)

    # 6. Any leading number
    num = re.search(r'(\d+(?:\.\d+)?)', name)
    if num:
        return (float(num.group(1)), 0, 0, name)

    # 7. Pure alphabetical fallback
    return (float('inf'), 0, 0, name)


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
# Products within each category are sorted by size ascending:
#   NB size → OD size → SWG (primary size then SWG) → dimension
# ─────────────────────────────────────────────────────────────────

def get_product_catalog() -> dict:
    """
    Fetch all products from Supabase and return a nested dict:
    {
      "SS 304": {
        "SCH-10 (ERW)": [
          {"product_id": "...", "product_name": "...", "material": "SS 304", "category": "SCH-10 (ERW)"},
          ...   ← sorted 15 NB → 20 NB → 25 NB → ... → 150 NB
        ],
        ...
      },
      ...
    }
    Within each category products are sorted smallest → largest size.
    For SWG items: sorted by primary dimension first, then SWG ascending
    (so all 14 SWG sizes run smallest→largest, then all 16 SWG sizes, etc.)
    """
    # Fetch without DB-level ordering — we sort in Python by size
    rows = _get(
        f"{url}/rest/v1/products"
        f"?select=product_id,product_name,material,category"
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

    # Sort each category's product list by size ascending
    for mat in catalog:
        for cat in catalog[mat]:
            catalog[mat][cat].sort(key=lambda p: _size_sort_key(p["product_name"]))

    return catalog


def search_products(query: str) -> list:
    """Full-text search across product_name (case-insensitive substring), sorted by size."""
    encoded = requests.utils.quote(f"*{query.strip()}*")
    rows = _get(
        f"{url}/rest/v1/products"
        f"?product_name=ilike.{encoded}&select=product_id,product_name,material,category"
    )
    # Ensure material/category are always populated in results
    for row in rows:
        pname = (row.get("product_name") or "").strip()
        if not row.get("material"):
            row["material"] = _infer_material(pname)
        if not row.get("category"):
            row["category"] = _infer_category(pname)

    # Sort by size ascending
    rows.sort(key=lambda p: _size_sort_key(p.get("product_name", "")))
    return rows
