import time
from server.email_reader import fetch_unread_emails
from server.ai_parser import parse_enquiry_email
from server.database import save_enquiry

def process_inbox():
    print("Checking inbox for new enquiries...")
    new_emails = fetch_unread_emails()
    
    if not new_emails:
        return

    for email in new_emails:
        # 🛑 NEW: Completely ignore bounce-backs and spam system emails
        if "mailer-daemon" in email['from_address'].lower() or "noreply" in email['from_address'].lower():
            print(f"🗑️ Ignored automated email from: {email['from_address']}")
            continue
            
        print(f"\nProcessing email from {email['from_address']}...")
        
        parsed_data = parse_enquiry_email(email['body'])
        
        if parsed_data and parsed_data.get('product_type'):
            db_record = {
                'customer_name': parsed_data.get('customer_name'),
                'customer_email': email['from_address'],
                'product_type': parsed_data.get('product_type'),
                'material_grade': parsed_data.get('material_grade'),
                'size': parsed_data.get('size'),
                'quantity': parsed_data.get('quantity'),
                'unit': parsed_data.get('unit'),
                'raw_email': email['body'],
                'status': 'PENDING'
            }
            save_enquiry(db_record)
        else:
            print("⏭️ Skipped: No stainless steel products found in this email.")
            
        # 🛑 SPEED LIMIT: Increased to 15 seconds so Gemini never blocks you
        time.sleep(15)

if __name__ == '__main__':
    process_inbox()