import os
import json
import re
from google import genai
from dotenv import load_dotenv

# load_dotenv() with no arguments automatically searches parent folders for the .env file
load_dotenv()

# Explicitly grab the key and hand it to the client to be absolutely sure
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def parse_enquiry_email(email_body: str) -> dict:
# ... (Keep the rest of your code exactly the same below this)
    prompt = f"""
    You are an assistant for a stainless steel supplier in India.
    Read the customer enquiry email and extract these fields:
    - customer_name   (company or person name, or null)
    - product_type    (pipe / elbow / flange / reducer / fitting)
    - material_grade  (SS 304 / SS 316 / SS 202 / SS 316L, or null)
    - size            (e.g. 2 inch SCH 40, DN50, 1.5 inch, or null)
    - quantity        (number only, or null)
    - unit            (pieces / kg / metres / sets, or null)
    
    Return ONLY a valid JSON object. No explanation. No markdown.
    Set any field you cannot find to null.
    
    Email: {email_body}
    """
    
    # Using the new SDK syntax and the 2.5 Flash model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    
    # Clean the output to ensure it is pure JSON
    text = re.sub(r'```json|```', '', response.text).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw": text}

# --- TEST SECTION ---
if __name__ == '__main__':
    dummy_email = """
    Dear Sir,
    Please give your best rate for SS 304 Seamless Pipe. 
    Size is 2 inch SCH 40. We need 150 pieces urgently for our site in Pune.
    Regards,
    Amit Patel
    Patel Fabricators
    """
    
    print("Sending email to the AI...")
    extracted_data = parse_enquiry_email(dummy_email)
    
    print("\n--- AI Extraction Result ---")
    print(json.dumps(extracted_data, indent=2))