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

# Sender-level spam filter — these never reach AI
AUTO_SKIP = [
    "mailer-daemon", "noreply", "no-reply",
    "postmaster", "bounce", "donotreply",
    "notifications@", "alert", "bseindia",
    "torbel.com", "undelivered", "delivery subsystem",
    "mail delivery", "auto-reply", "autoreply",
    "daemon", "system@", "support@google",
    "accounts@google", "no.reply", "newsletter",
    "nse", "bse", "sebi", "moneycontrol",
    "info@amazon", "flipkart", "swiggy", "zomato",
]


def process_inbox():
    """Fetch unread emails → keyword filter → AI parse → save SS enquiries only."""
    print("📬 Checking inbox...")
    new_emails = fetch_unread_emails()

    if not new_emails:
        print("🔴 No new emails.")
        return

    print(f"📥 {len(new_emails)} unread email(s) found")
    skipped = 0
    saved = 0

    for email in new_emails:
        from_addr = email.get('from_address', '').lower()
        body = email.get('body', '')

        # ── Layer 1: Sender-level skip ──
        if any(p in from_addr for p in AUTO_SKIP):
            print(f"🗑️  Sender blocked: {from_addr}")
            skipped += 1
            continue

        # ── Layer 2: Empty body skip ──
        if not body or len(body.strip()) < 20:
            print(f"🗑️  Empty email from: {from_addr}")
            skipped += 1
            continue

        # ── Layer 3: Duplicate skip ──
        if email_already_imported(body):
            print(f"♻️  Duplicate skipped: {from_addr}")
            skipped += 1
            continue

        # ── Layer 4: AI parse (keyword pre-filter runs inside ai_parser) ──
        print(f"\n🔍 Processing: {email['from_address']}")
        parsed = parse_enquiry_email(body)

        if parsed and parsed.get('product_type'):
            save_enquiry({
                **parsed,
                'customer_email': email['from_address'],
                'raw_email': body,
                'status': 'PENDING'
            })
            saved += 1
            print(f"✅ Saved: {email['from_address']}")
        else:
            print(f"⏭️  Not an SS enquiry: {email['from_address']}")
            skipped += 1

        time.sleep(1)

    print(f"\n📊 Done — {saved} saved, {skipped} skipped")


if __name__ == '__main__':
    process_inbox()
