import os
import base64
import re
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# NEW SCOPE: This gives Quotify permission to Read AND Send emails!
SCOPES = ['https://mail.google.com/']

def get_gmail_service():
    creds = None
    base_dir = os.path.dirname(__file__)
    token_path = os.path.join(base_dir, 'token.json')
    cred_path = os.path.join(base_dir, 'credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def fetch_unread_emails():
    service = get_gmail_service()
    results = service.users().messages().list(userId='me', q='is:unread').execute()
    messages = results.get('messages', [])
    
    email_data = []
    for msg in messages:
        msg_full = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        
        # Get Sender
        headers = msg_full['payload'].get('headers', [])
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        
        # Get Body
        body = ""
        if 'parts' in msg_full['payload']:
            for part in msg_full['payload']['parts']:
                if part['mimeType'] == 'text/plain' and part.get('body', {}).get('data'):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        elif msg_full['payload'].get('body', {}).get('data'):
            body = base64.urlsafe_b64decode(msg_full['payload']['body']['data']).decode('utf-8')

        email_data.append({'from_address': sender, 'body': body})
        
        # Mark as read
        service.users().messages().modify(userId='me', id=msg['id'], body={'removeLabelIds': ['UNREAD']}).execute()
        
    return email_data

def send_quotation_email(to_email: str, customer_name: str, pdf_path: str):
    """Builds an email with the PDF attached and sends it to the customer."""
    service = get_gmail_service()
    
    # Clean up the email address (extracts pure email if it's formatted weirdly)
    extracted_email = re.findall(r'<([^>]+)>', to_email)
    clean_email = extracted_email[0] if extracted_email else to_email

    message = EmailMessage()
    message['To'] = clean_email
    message['Subject'] = f"Your Quotation from Nivee Metal Products - {customer_name}"
    message.set_content(
        f"Dear {customer_name},\n\n"
        f"Thank you for your enquiry.\n\n"
        f"Please find attached the official quotation for the stainless steel products you requested.\n\n"
        f"Best regards,\n"
        f"Quotify Automated System\n"
        f"Nivee Metal Products Pvt. Ltd."
    )

    # Attach the PDF
    with open(pdf_path, 'rb') as f:
        pdf_data = f.read()
        
    message.add_attachment(
        pdf_data, 
        maintype='application', 
        subtype='pdf', 
        filename=os.path.basename(pdf_path)
    )

    # Send it
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    try:
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        print(f"📧 Auto-Reply successfully sent to {clean_email}")
        return True  # <-- NEW: Tell the server it worked!
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False # <-- NEW: Tell the server it failed!