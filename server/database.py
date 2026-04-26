import os
import requests
from dotenv import load_dotenv

# Safely load the .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

def save_enquiry(enquiry_data: dict):
    """Pushes the clean JSON data into the Supabase 'enquiries' table via REST API."""
    
    # Supabase API requires these headers
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    endpoint = f"{url}/rest/v1/enquiries"
    
    try:
        response = requests.post(endpoint, json=enquiry_data, headers=headers)
        response.raise_for_status() # Check for errors
        
        print(f"✅ Successfully saved to database: {enquiry_data.get('customer_name', 'Unknown Customer')}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        return None