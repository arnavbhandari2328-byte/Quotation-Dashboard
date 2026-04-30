import time
import logging
from server.email_reader import fetch_unread_emails
from server.ai_parser import parse_enquiry_email
from server.database import save_enquiry, email_already_imported

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def process_inbox():
    """Fetch unread emails, parse with AI, save new enquiries to Supabase."""
    print("📬 Checking inbox...")
    new_emails = fetch_unread_emails()

    if not new_emails:
        print("📭 No new emails.")
        return

    AUTO_SKIP = ["mailer-daemon", "noreply", "no-reply",
                 "postmaster", "bounce", "donotreply", "notifications@"]

    for email in new_emails:
        from_addr = email.get('from_address', '').lower()
        body = email.get('body', '')

        # Skip automated/system emails
        if any(p in from_addr for p in AUTO_SKIP):
            print(f"🗑️  Skipped automated email from: {from_addr}")
            continue

        # Skip duplicate emails already in database
        if email_already_imported(body):
            print(f"♻️  Duplicate skipped: {from_addr}")
            continue

        print(f"\n🔍 Processing email from {email['from_address']}...")
        parsed = parse_enquiry_email(body)

        if parsed and parsed.get('product_type'):
            save_enquiry({
                **parsed,
                'customer_email': email['from_address'],
                'raw_email': body,
                'status': 'PENDING'
            })
            print(f"✅ Saved enquiry from {email['from_address']}")
        else:
            print(f"⏭️  No SS product found — skipped: {email['from_address']}")

        time.sleep(2)  # Avoid Gemini rate limits


if __name__ == '__main__':
    process_inbox()
