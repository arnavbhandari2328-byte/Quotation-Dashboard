import os
import json
import re
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

CANDIDATE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
]

# ── Stainless Steel keyword pre-filter (runs BEFORE AI — zero API cost) ──
SS_KEYWORDS = [
    # products
    "pipe", "pipes", "elbow", "elbows", "flange", "flanges",
    "reducer", "reducers", "tee", "cap", "fitting", "fittings",
    "sheet", "sheets", "plate", "bar", "bars", "tube", "tubes",
    "valve", "valves", "ball valve", "gate valve", "coupling",
    "nipple", "stub end", "ferrule", "union",
    # materials
    "ss ", "stainless", "s.s.", "s.s",
    "304", "316", "202", "316l", "310", "321",
    "seamless", "erw", "sch 40", "sch40", "schedule",
    # buying intent words
    "enquiry", "inquiry", "quotation", "quote", "rate",
    "best rate", "price", "supply", "requirement", "require",
    "purchase", "order", "procure",
]

def is_ss_enquiry(email_body: str) -> bool:
    """Fast keyword check — returns True only if email looks like an SS product enquiry."""
    body_lower = email_body.lower()
    matches = sum(1 for kw in SS_KEYWORDS if kw in body_lower)
    return matches >= 2  # needs at least 2 hits to avoid false positives


PROMPT = """
You are an AI assistant for a stainless steel metal supplier in India.
Your ONLY job is to extract structured data from genuine customer enquiry emails about stainless steel products.

RULES (strictly follow):
1. If the email is NOT about buying/enquiring for stainless steel products → return exactly: {"product_type": null}
2. Ignore promotional emails, newsletters, delivery alerts, BSE/NSEI alerts, auto-replies, and spam.
3. Do NOT guess product if it is not clearly about metal/steel.

If it IS a genuine SS enquiry, extract these fields:
- customer_name   (company or person name, or null)
- product_type    (pipe / elbow / flange / reducer / tee / cap / fitting / sheet / bar / valve / other)
- material_grade  (SS 304 / SS 316 / SS 202 / SS 316L / SS 310 / SS 321, or null)
- size            (e.g. "2 inch SCH 40", "DN50", "1.5 inch", or null)
- quantity        (NUMBER only, no units, or null)
- unit            (pieces / kg / metres / sets / sheets, or null)

Return ONLY a valid JSON object. No markdown. No explanation. No code fences.
Set any field you cannot find to null.

Email:
---
{email_body}
---
"""

SAFE_EMPTY = {
    "customer_name": None, "product_type": None, "material_grade": None,
    "size": None, "quantity": None, "unit": None
}


def _strip_fences(text: str) -> str:
    return re.sub(r'```[\w]*\n?', '', text).replace('```', '').strip()


def parse_enquiry_email(email_body: str) -> dict:
    if not email_body or not email_body.strip():
        return SAFE_EMPTY

    # ── STAGE 1: Free keyword pre-filter — skip AI entirely for non-SS emails ──
    if not is_ss_enquiry(email_body):
        print("⏭️  Skipped by keyword filter — not an SS enquiry (0 API calls used)")
        return SAFE_EMPTY

    # ── STAGE 2: AI parse — only runs for emails that passed keyword filter ──
    prompt = PROMPT.format(email_body=email_body[:3000])

    for model_name in CANDIDATE_MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"temperature": 0.0, "max_output_tokens": 256}
                )
                text = _strip_fences(response.text)
                data = json.loads(text)

                if not isinstance(data, dict):
                    raise ValueError("Not a JSON object")

                for k in SAFE_EMPTY:
                    data.setdefault(k, None)

                if data["quantity"] is not None:
                    try:
                        data["quantity"] = float(
                            re.sub(r"[^\d.]", "", str(data["quantity"]))
                        )
                    except (ValueError, TypeError):
                        data["quantity"] = None

                print(f"✅ AI parsed — model={model_name}, product={data.get('product_type')}")
                return data

            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️ JSON error model={model_name} attempt={attempt+1}: {e}")
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"⚠️ Quota hit on {model_name}, trying next model...")
                    break
                print(f"⚠️ API error model={model_name} attempt={attempt+1}: {e}")
                time.sleep(1.5 * (attempt + 1))

    print("❌ All AI parse attempts failed")
    return SAFE_EMPTY


# --- TEST ---
if __name__ == '__main__':
    tests = [
        # Should PASS keyword filter → goes to AI
        "Dear Sir, Please give best rate for SS 304 Seamless Pipe 2 inch SCH 40, qty 150 pcs. Regards, Amit Patel",
        # Should be BLOCKED by keyword filter → 0 AI calls
        "BSE Corporate Actions Alert: Dividend declared by XYZ Ltd",
        "Your Amazon order has been shipped. Track your package here.",
        # Edge case — should pass (contains 316 + fitting)
        "We need SS 316 ball valves 3inch - 5 nos from cms pvt",
    ]
    for i, body in enumerate(tests, 1):
        print(f"\n--- Test {i} ---")
        print(f"Email: {body[:60]}...")
        result = parse_enquiry_email(body)
        print(f"Result: {json.dumps(result, indent=2)}")
