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
    return _get(
        f"{url}/rest/v1/enquiries"
        f"?status=in.(EMAIL%20SENT,COMPLETED)&select=*,quotes(rate,grand_total,payment_terms,sent_at)&order=received_at.desc"
    )


def save_quote(quote_data: dict):
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
# SHARED CATEGORY / MATERIAL INFERENCE
# Used by BOTH warehouse and office stock
# ─────────────────────────────────────────────────────────────────

_CATEGORY_RULES = [
    (r"PIPE ERW SCH-05",  "SCH-05 (ERW)"),
    (r"PIPE ERW SCH-10",  "SCH-10 (ERW)"),
    (r"PIPE ERW SCH-20",  "SCH-20 (ERW)"),
    (r"PIPE ERW SCH-40",  "SCH-40 (ERW)"),
    (r"PIPE SMLS SCH-10", "SCH-10 (Seamless)"),
    (r"PIPE SMLS SCH-40", "SCH-40 (Seamless)"),
    (r"SEAMLESS PIPE SCH-40", "SCH-40 (Seamless)"),
    (r"SEAMLESS PIPE SCH-10", "SCH-10 (Seamless)"),
    (r"SEAMLESS PIPE SCH-20", "SCH-20 (Seamless)"),
    (r"SEAMLESS PIPE",    "Seamless"),
    (r"PIPE ROUND",       "Round Pipe (OD)"),
    (r"PIPE RECTANGLE|PIPR RECTANGLE|PIPE RECTANGE", "Rectangle Pipe"),
    (r"POLISH PIPE",      "Polish Pipe"),
    (r"CS PIPE",          "CS Pipe"),
    (r"ROUND BRIGHT ROD", "Round Bright Rod"),
    (r"SQUARE ROD",       "Square Rod"),
    (r"PIPE SQUARE",      "Square Pipe"),
    (r"NO\.8 SHEET",      "No.8 Mirror Sheet"),
    (r"NO\.4",            "No.4 Satin Sheet"),
    (r"2B SHEET",         "2B Sheet"),
    (r"ANGLE",            "Angle"),
    (r"FLAT",             "Flat Bar"),
    (r"SQUARE PIPE",      "Square Pipe (MS)"),
]

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


def _size_sort_key(product_name: str):
    name = product_name.upper()

    def _swg(n):
        m = re.search(r'(\d+)\s*SWG', n)
        return float(m.group(1)) if m else 0.0

    nb = re.search(r'(\d+(?:\.\d+)?)\s*NB', name)
    if nb:
        return (float(nb.group(1)), _swg(name), 0.0, name)

    od_inch = re.search(r'(\d+(?:\.\d+)?)\s*["\u2019\']\s*OD', name)
    if od_inch:
        return (float(od_inch.group(1)), _swg(name), 0.0, name)

    od_mm = re.search(r'(\d+(?:\.\d+)?)\s*OD', name)
    if od_mm:
        return (float(od_mm.group(1)), _swg(name), 0.0, name)

    dim = re.search(r'(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)', name)
    if dim:
        return (float(dim.group(1)), _swg(name), float(dim.group(2)), name)

    swg_m = re.search(r'(\d+)\s*SWG', name)
    if swg_m:
        swg_val = float(swg_m.group(1))
        nums = re.findall(r'(\d+(?:\.\d+)?)', name)
        other = next((float(n) for n in nums if float(n) != swg_val), 0.0)
        return (swg_val, other, 0.0, name)

    num = re.search(r'(\d+(?:\.\d+)?)', name)
    if num:
        return (float(num.group(1)), 0.0, 0.0, name)

    return (float('inf'), 0.0, 0.0, name)


# ─────────────────────────────────────────────────────────────────
# PRODUCT CATALOG — hierarchical: material → category → products
# products table: product_id, product_name, material, category, location
# ─────────────────────────────────────────────────────────────────

def backfill_product_categories() -> dict:
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


def get_product_catalog() -> dict:
    """
    Returns nested catalog: material → category → [products]
    Each product now includes 'location' field.
    """
    rows = _get(
        f"{url}/rest/v1/products"
        f"?select=product_id,product_name,material,category,location"
    )

    catalog: dict = {}
    for row in rows:
        pid   = row.get("product_id", "")
        pname = (row.get("product_name") or "").strip()

        mat = row.get("material") or _infer_material(pname)
        cat = row.get("category") or _infer_category(pname)

        catalog.setdefault(mat, {}).setdefault(cat, []).append({
            "product_id":   pid,
            "product_name": pname,
            "material":     mat,
            "category":     cat,
            "location":     row.get("location") or "",
        })

    for mat in catalog:
        for cat in catalog[mat]:
            catalog[mat][cat].sort(key=lambda p: _size_sort_key(p["product_name"]))

    return catalog


def add_product(product_data: dict) -> bool:
    """
    Adds a new product to the products table.
    Expected fields: product_id, product_name, material, category, location (optional)
    Auto-infers material/category if not provided.
    """
    pname = (product_data.get("product_name") or "").strip()
    if not product_data.get("material"):
        product_data["material"] = _infer_material(pname)
    if not product_data.get("category"):
        product_data["category"] = _infer_category(pname)

    try:
        r = requests.post(
            f"{url}/rest/v1/products",
            json=product_data,
            headers={**_headers(), "Prefer": "return=minimal"}
        )
        if not r.ok:
            print(f"❌ Add product failed {r.status_code}: {r.text}")
            return False
        print(f"✅ Product added: {pname}")
        return True
    except Exception as e:
        print(f"❌ Add product error: {e}")
        return False


def search_products(query: str) -> list:
    encoded = requests.utils.quote(f"*{query.strip()}*")
    rows = _get(
        f"{url}/rest/v1/products"
        f"?product_name=ilike.{encoded}&select=product_id,product_name,material,category,location"
    )
    for row in rows:
        pname = (row.get("product_name") or "").strip()
        if not row.get("material"):
            row["material"] = _infer_material(pname)
        if not row.get("category"):
            row["category"] = _infer_category(pname)

    rows.sort(key=lambda p: _size_sort_key(p.get("product_name", "")))
    return rows


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE STOCK
# Table: warehouse_stock
#   id (uuid), product_id (text, FK→products), product_name (text),
#   material (text), category (text),
#   type (text: 'IN'|'OUT'), qty (numeric), unit (text),
#   rate (numeric), entry_date (date), remarks (text),
#   is_hero (bool), created_at (timestamptz)
# ═══════════════════════════════════════════════════════════════════

def add_warehouse_entry(entry: dict) -> bool:
    try:
        r = requests.post(
            f"{url}/rest/v1/warehouse_stock",
            json=entry,
            headers={**_headers(), "Prefer": "return=minimal"}
        )
        if not r.ok:
            print(f"❌ Warehouse entry failed {r.status_code}: {r.text}")
            return False
        return True
    except Exception as e:
        print(f"❌ Warehouse entry error: {e}")
        return False


def get_warehouse_entries(product_id: str = None) -> list:
    if product_id:
        encoded = requests.utils.quote(product_id, safe="")
        return _get(f"{url}/rest/v1/warehouse_stock?product_id=eq.{encoded}&select=*&order=entry_date.desc,created_at.desc")
    return _get(f"{url}/rest/v1/warehouse_stock?select=*&order=entry_date.desc,created_at.desc")


def get_warehouse_stock_levels() -> dict:
    """
    Returns current stock level per product_id.
    Level = SUM(qty where type=IN) - SUM(qty where type=OUT)
    Returns: { product_id: { product_name, material, category, qty, unit, is_hero } }
    """
    rows = _get(f"{url}/rest/v1/warehouse_stock?select=*&order=entry_date.asc")
    levels = {}
    for row in rows:
        pid = row.get("product_id", "")
        if not pid:
            continue
        if pid not in levels:
            levels[pid] = {
                "product_id":   pid,
                "product_name": row.get("product_name", ""),
                "material":     row.get("material", ""),
                "category":     row.get("category", ""),
                "qty":          0.0,
                "unit":         row.get("unit", "Pcs"),
                "is_hero":      row.get("is_hero", False),
            }
        delta = float(row.get("qty") or 0)
        if row.get("type") == "IN":
            levels[pid]["qty"] += delta
        else:
            levels[pid]["qty"] -= delta
        if row.get("is_hero"):
            levels[pid]["is_hero"] = True
    return levels


def get_warehouse_catalog_with_stock() -> dict:
    """
    Returns product catalog merged with live stock levels.
    Structure: { material: { category: [ {product + stock fields} ] } }
    """
    catalog = get_product_catalog()
    levels  = get_warehouse_stock_levels()

    result = {}
    for mat, cats in catalog.items():
        for cat, products in cats.items():
            for p in products:
                pid = p["product_id"]
                stock = levels.get(pid, {})
                entry = {
                    **p,
                    "qty":     stock.get("qty", 0.0),
                    "unit":    stock.get("unit", "Pcs"),
                    "is_hero": stock.get("is_hero", False),
                }
                result.setdefault(mat, {}).setdefault(cat, []).append(entry)

    # Also include items in stock that aren't in the products catalog
    for pid, stock in levels.items():
        mat = stock.get("material") or "Other"
        cat = stock.get("category") or "Miscellaneous"
        existing = result.get(mat, {}).get(cat, [])
        if not any(e["product_id"] == pid for e in existing):
            result.setdefault(mat, {}).setdefault(cat, []).append(stock)

    return result


def toggle_warehouse_hero(product_id: str, is_hero: bool) -> bool:
    try:
        encoded = requests.utils.quote(product_id, safe="")
        r = requests.patch(
            f"{url}/rest/v1/warehouse_stock?product_id=eq.{encoded}",
            json={"is_hero": is_hero},
            headers=_headers()
        )
        return r.ok
    except Exception as e:
        print(f"❌ Toggle hero error: {e}")
        return False


def delete_warehouse_entry(entry_id: str) -> bool:
    try:
        r = requests.delete(
            f"{url}/rest/v1/warehouse_stock?id=eq.{entry_id}",
            headers=_headers()
        )
        return r.ok
    except Exception as e:
        print(f"❌ Delete warehouse entry error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# OFFICE STOCK
# Table: office_stock
#   id (uuid), item_name (text), material (text), category (text),
#   type (text: 'IN'|'OUT'), qty (numeric), unit (text),
#   rate (numeric), entry_date (date), remarks (text),
#   is_hero (bool), created_at (timestamptz)
#
# NOTE: material & category use the SAME _infer_material / _infer_category
#       rules as warehouse stock so categories are identical across both.
# ═══════════════════════════════════════════════════════════════════

def add_office_entry(entry: dict) -> bool:
    """
    Saves a new office stock row.
    Auto-infers material & category from item_name if not provided,
    using the same rules as warehouse stock.
    """
    item_name = (entry.get("item_name") or "").strip()

    # Auto-infer material/category if missing — same rules as warehouse
    if not entry.get("material"):
        entry["material"] = _infer_material(item_name)
    if not entry.get("category"):
        entry["category"] = _infer_category(item_name)

    try:
        r = requests.post(
            f"{url}/rest/v1/office_stock",
            json=entry,
            headers={**_headers(), "Prefer": "return=minimal"}
        )
        if not r.ok:
            print(f"❌ Office entry failed {r.status_code}: {r.text}")
            return False
        print(f"✅ Office entry saved: {item_name}")
        return True
    except Exception as e:
        print(f"❌ Office entry error: {e}")
        return False


def get_office_entries(item_name: str = None, material: str = None, category: str = None) -> list:
    """
    Fetch office stock ledger rows.
    - No args → all rows
    - item_name only → filter by exact item_name
    - material + category → filter by both
    - all three → filter by all three
    """
    filters = []
    if item_name:
        filters.append(f"item_name=eq.{requests.utils.quote(item_name, safe='')}")
    if material:
        filters.append(f"material=eq.{requests.utils.quote(material, safe='')}")
    if category:
        filters.append(f"category=eq.{requests.utils.quote(category, safe='')}")

    qs = "&".join(filters)
    suffix = f"&{qs}" if qs else ""
    return _get(
        f"{url}/rest/v1/office_stock"
        f"?select=*&order=entry_date.desc,created_at.desc{suffix}"
    )


def get_office_stock_levels() -> dict:
    """
    Returns current stock level per (item_name, material, category).
    key = f"{material}||{category}||{item_name}"

    material and category are inferred via the same rules as warehouse
    if not already set on the row.
    """
    rows = _get(f"{url}/rest/v1/office_stock?select=*&order=entry_date.asc")
    levels = {}
    for row in rows:
        item_name = (row.get("item_name") or "").strip()
        if not item_name:
            continue

        # Use stored values; fall back to inference (same rules as warehouse)
        mat = (row.get("material") or "").strip() or _infer_material(item_name)
        cat = (row.get("category") or "").strip() or _infer_category(item_name)
        key = f"{mat}||{cat}||{item_name}"

        if key not in levels:
            levels[key] = {
                "item_name": item_name,
                "material":  mat,
                "category":  cat,
                "qty":       0.0,
                "unit":      row.get("unit", "Pcs"),
                "is_hero":   row.get("is_hero", False),
            }
        delta = float(row.get("qty") or 0)
        if row.get("type") == "IN":
            levels[key]["qty"] += delta
        else:
            levels[key]["qty"] -= delta
        if row.get("is_hero"):
            levels[key]["is_hero"] = True
    return levels


def get_office_catalog_with_stock() -> dict:
    """
    Returns office stock as nested dict:
    { material: { category: [ { item_name, qty, unit, is_hero } ] } }
    Categories match warehouse stock categories.
    """
    levels = get_office_stock_levels()
    result = {}
    for key, stock in levels.items():
        mat = stock.get("material", "Other")
        cat = stock.get("category", "Miscellaneous")
        result.setdefault(mat, {}).setdefault(cat, []).append(stock)
    return result


def toggle_office_hero(item_name: str, material: str, category: str, is_hero: bool) -> bool:
    try:
        enc_item = requests.utils.quote(item_name, safe="")
        enc_mat  = requests.utils.quote(material, safe="")
        enc_cat  = requests.utils.quote(category, safe="")
        r = requests.patch(
            f"{url}/rest/v1/office_stock"
            f"?item_name=eq.{enc_item}&material=eq.{enc_mat}&category=eq.{enc_cat}",
            json={"is_hero": is_hero},
            headers=_headers()
        )
        return r.ok
    except Exception as e:
        print(f"❌ Toggle office hero error: {e}")
        return False


def delete_office_entry(entry_id: str) -> bool:
    try:
        r = requests.delete(
            f"{url}/rest/v1/office_stock?id=eq.{entry_id}",
            headers=_headers()
        )
        return r.ok
    except Exception as e:
        print(f"❌ Delete office entry error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# TRANSACTIONS — combined view of warehouse + office movements
# ═══════════════════════════════════════════════════════════════════

def get_all_transactions(limit: int = 200) -> list:
    """
    Returns combined warehouse + office stock movements, sorted by date desc.
    Each row has: source, type, item_name/product_name, material, category,
                  qty, unit, rate, entry_date, remarks, is_hero
    """
    w_rows = _get(
        f"{url}/rest/v1/warehouse_stock"
        f"?select=id,product_id,product_name,material,category,type,qty,unit,rate,entry_date,remarks,is_hero,created_at"
        f"&order=entry_date.desc,created_at.desc&limit={limit}"
    )
    o_rows = _get(
        f"{url}/rest/v1/office_stock"
        f"?select=id,item_name,material,category,type,qty,unit,rate,entry_date,remarks,is_hero,created_at"
        f"&order=entry_date.desc,created_at.desc&limit={limit}"
    )

    transactions = []
    for r in w_rows:
        transactions.append({
            "id":           r.get("id"),
            "source":       "Warehouse",
            "product_name": r.get("product_name", r.get("product_id", "")),
            "material":     r.get("material", ""),
            "category":     r.get("category", ""),
            "type":         r.get("type", ""),
            "qty":          r.get("qty", 0),
            "unit":         r.get("unit", ""),
            "rate":         r.get("rate", 0),
            "entry_date":   r.get("entry_date", ""),
            "remarks":      r.get("remarks", ""),
            "created_at":   r.get("created_at", ""),
        })
    for r in o_rows:
        transactions.append({
            "id":           r.get("id"),
            "source":       "Office",
            "product_name": r.get("item_name", ""),
            "material":     r.get("material", ""),
            "category":     r.get("category", ""),
            "type":         r.get("type", ""),
            "qty":          r.get("qty", 0),
            "unit":         r.get("unit", ""),
            "rate":         r.get("rate", 0),
            "entry_date":   r.get("entry_date", ""),
            "remarks":      r.get("remarks", ""),
            "created_at":   r.get("created_at", ""),
        })

    transactions.sort(key=lambda x: (x.get("entry_date") or "", x.get("created_at") or ""), reverse=True)
    return transactions[:limit]


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD ANALYTICS
# ═══════════════════════════════════════════════════════════════════

def get_dashboard_analytics() -> dict:
    """
    Returns all data needed for the dashboard:
    - enquiry counts (today, this week, total)
    - revenue stats from quotes
    - warehouse stock summary (top items, hero, dead)
    - office stock summary (hero, dead)
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()

    # Enquiries
    all_enquiries = list_all()
    today_enq   = [e for e in all_enquiries if (e.get("received_at") or "")[:10] == today]
    week_enq    = [e for e in all_enquiries if (e.get("received_at") or "")[:10] >= week_ago]
    pending_enq = [e for e in all_enquiries if e.get("status") == "PENDING"]

    # Revenue from quotes
    all_sent = list_sent()
    total_revenue = sum(
        float((q.get("quotes") or [{}])[0].get("grand_total") or 0)
        for q in all_sent if q.get("quotes")
    )

    # Warehouse stock levels
    w_levels = get_warehouse_stock_levels()
    w_hero   = [v for v in w_levels.values() if v.get("is_hero")]
    w_dead   = [v for v in w_levels.values() if v.get("qty", 0) <= 0]
    w_low    = [v for v in w_levels.values() if 0 < v.get("qty", 0) <= 10]
    w_ok     = [v for v in w_levels.values() if v.get("qty", 0) > 10]

    # Top 8 warehouse items by qty
    w_top = sorted(w_levels.values(), key=lambda x: x.get("qty", 0), reverse=True)[:8]

    # Office stock levels
    o_levels = get_office_stock_levels()
    o_hero   = [v for v in o_levels.values() if v.get("is_hero")]
    o_dead   = [v for v in o_levels.values() if v.get("qty", 0) <= 0]
    o_low    = [v for v in o_levels.values() if 0 < v.get("qty", 0) <= 5]

    # Recent transactions (last 30 days) for sparkline
    all_tx = get_all_transactions(limit=500)
    recent_tx = [t for t in all_tx if (t.get("entry_date") or "") >= month_ago]

    return {
        "enquiries": {
            "today":   len(today_enq),
            "week":    len(week_enq),
            "total":   len(all_enquiries),
            "pending": len(pending_enq),
        },
        "revenue": {
            "total": round(total_revenue, 2),
            "quotes_sent": len(all_sent),
        },
        "warehouse": {
            "total_skus": len(w_levels),
            "ok":         len(w_ok),
            "low":        len(w_low),
            "dead":       len(w_dead),
            "hero":       w_hero,
            "top_items":  w_top,
        },
        "office": {
            "total_skus": len(o_levels),
            "low":        len(o_low),
            "dead":       len(o_dead),
            "hero":       o_hero,
            "by_category": _group_by_category(o_levels),
        },
        "recent_transactions": recent_tx[:50],
    }


def _group_by_category(levels: dict) -> list:
    cats = {}
    for v in levels.values():
        cat = v.get("category", "Other")
        cats[cat] = cats.get(cat, 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])]
