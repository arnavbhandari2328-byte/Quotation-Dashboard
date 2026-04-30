import os
import json
import re
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Model free tier limits (requests per day):
# gemini-2.5-flash     → only 20/day  ❌ too low
# gemini-2.0-flash     → 1,500/day    ✅ use as primary
# gemini-2.0-flash-lite→ 1,500/day    ✅ fallback
# gemini-2.5-flash     → kept as last resort if others fail
CANDIDATE_MODELS = [
    "gemini-2.0-flash",      # Primary — 1500/day free, fast
    "gemini-2.0-flash-lite", # Fallback 1 — 1500/day free, lightest
    "gemini-2.5-flash",      # Fallback 2 — only if others fail
]

PROMPT = """
You are an assistant for a stainless steel supplier in India.
Read the customer enquiry email and extract ONLY these fields:
- customer_name   (company or person name, or null)
- product_type    (pipe / elbow / flange / reducer / tee / cap / fitting / sheet / bar / other)
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

                print(f"✅ AI parsed email — model={model_name}")
                return data

            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️ JSON error model={model_name} attempt={attempt+1}: {e}")
            except Exception as e:
                error_str = str(e)
                # If quota exhausted on this model, skip to next immediately
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"⚠️ Quota hit on {model_name}, trying next model...")
                    break
                print(f"⚠️ API error model={model_name} attempt={attempt+1}: {e}")
                time.sleep(1.5 * (attempt + 1))

    print("❌ All AI parse attempts failed")
    return SAFE_EMPTY


# --- TEST ---
if __name__ == '__main__':
    dummy = """
    Dear Sir,
    Please give your best rate for SS 304 Seamless Pipe.
    Size is 2 inch SCH 40. We need 150 pieces urgently.
    Regards, Amit Patel, Patel Fabricators
    """
    print(json.dumps(parse_enquiry_email(dummy), indent=2))
