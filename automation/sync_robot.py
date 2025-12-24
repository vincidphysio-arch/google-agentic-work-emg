import os
import json
import base64
import re
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import gspread

# Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Authenticates using Environment Variables (GitHub Secrets)"""
    creds = None
    
    # In GitHub Actions, we will pass the token content as an env var
    token_json = os.environ.get('GMAIL_TOKEN')
    
    if token_json:
        try:
            # If it's passed as a string representation of the JSON
            creds_data = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        except Exception as e:
            print(f"Error loading token from env: {e}")

    # If valid, return service
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)

    # If expired, try to refresh
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Note: We can't save the new token back to GitHub Secrets easily from here, 
            # but it allows the run to proceed.
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            print(f"Token expired and refresh failed: {e}")
            return None
            
    print("No valid credentials found.")
    return None

def parse_interac_email(service, msg_id):
    try:
        msg = service.users().messages().get(userId='me', id=msg_id).execute()
        payload = msg['payload']
        headers = payload.get("headers")
        
        subject = "Unknown"
        sender = "Unknown"
        email_date = datetime.now()

        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': sender = h['value']
            if h['name'] == 'Date': 
                # Basic parsing, might need adjustment for strict formats
                try:
                    # E.g. "Fri, 23 Dec 2025 14:00:00 -0500"
                    # Simplified parsing or usage of dateutil would be better but keeping deps low
                    pass 
                except:
                    pass

        # Get Body
        if 'parts' in payload:
            parts = payload.get('parts')[0]
            data = parts['body']['data']
        else:
            data = payload['body']['data']
            
        decoded_data = base64.urlsafe_b64decode(data).decode('utf-8')
        
        # Simple extraction (Text based, ignoring HTML tags for regex)
        # Using the same logic as the Sync App
        
        # Simple extraction (Text based, ignoring HTML tags for regex)
        # Using the same logic as the Sync App
        # Remove HTML tags logic (rudimentary but avoiding bs4 dependency if not needed? Actually bs4 is better)
        # Since we added bs4 to requirements, let's use it or stick to decoded_data if simple.
        # But for consistency, let's upgrade regex here too.
        
        # Pattern 1: $1,234.50
        amount_match = re.search(r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', decoded_data)
        
        # Pattern 2: "910.00 (CAD)" or "910.00 CAD"
        if not amount_match:
             amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*(?:CAD|CDN)', decoded_data, re.IGNORECASE)

        # Pattern 3: "sent you 910.00"
        if not amount_match:
             amount_match = re.search(r'sent you\s+\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', decoded_data, re.IGNORECASE)

        # Pattern 4: "Amount: 910.00"
        if not amount_match:
             amount_match = re.search(r'Amount:?\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', decoded_data, re.IGNORECASE)
        
        amount = amount_match.group(1) if amount_match else "0.00"

        # Regex for Sender
        sender_match = re.search(r"received \$[\d\.,]+ from (.*?) and", decoded_data, re.IGNORECASE)
        if not sender_match:
             sender_match = re.search(r"received \$[\d\.,]+ from (.*?) and", subject, re.IGNORECASE)
             
        sender_name = sender_match.group(1).strip() if sender_match else "Unknown"
        if "Interac" in sender_name: sender_name = sender_name.replace("Interac", "").strip()

        # Date from InternalDate (more reliable than header for sorting)
        internal_date = int(msg['internalDate']) / 1000
        dt_object = datetime.fromtimestamp(internal_date)
        formatted_date = dt_object.strftime("%d/%m/%Y %H:%M:%S")

        print(f"Parsed: {formatted_date} | {sender_name} | ${amount}")

        return {
            "date": formatted_date,
            "sender": sender_name,
            "amount": amount,
            "doctor": "Unknown" # Placeholder logic
        }

    except Exception as e:
        print(f"Error parsing {msg_id}: {e}")
        return None

def get_google_sheet_worksheet():
    """Connects using GCP Service Account JSON from Env Var"""
    gcp_json = os.environ.get('GCP_JSON')
    if gcp_json:
        try:
            creds_dict = json.loads(gcp_json)
            gc = gspread.service_account_from_dict(creds_dict)
            sh = gc.open("EMG Payments Kitchener")
            ws = sh.worksheet("Payments")
            return ws
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
    return None

def main():
    print("🤖 Starting Payment Sync Robot...")
    
    # 1. Auth Gmail
    service = get_gmail_service()
    if not service:
        print("❌ Gmail Auth Failed. Exiting.")
        # We don't exit(1) to avoid failing the workflow if it's just a credential issue? 
        # Actually we should fail so user knows.
        exit(1)

    # 2. Search
    query = 'subject:"Interac e-Transfer" "deposited"'
    print(f"🔍 Searching: {query}")
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=20).execute()
        messages = results.get('messages', [])
        print(f"📧 Found {len(messages)} emails.")
        
        found_payments = []
        for msg in messages:
            p = parse_interac_email(service, msg['id'])
            if p:
                found_payments.append(p)

        # 3. Auth Sheets
        ws = get_google_sheet_worksheet()
        if not ws:
            print("❌ Sheets Auth Failed. Exiting.")
            exit(1)

        existing_data = ws.get_all_values()
        existing_keys = set()
        
        # Deduplication Map
        for row in existing_data[1:]:
            if len(row) > 2:
                # Key: Amount_Sender (Rough)
                amt = str(row[2]).replace('$','').replace(',','')
                snd = str(row[1]).lower().strip()
                key = f"{amt}_{snd}"
                existing_keys.add(key)

        new_rows = []
        for p in found_payments:
            p_amt = str(p['amount']).replace(',','')
            p_snd = str(p['sender']).lower().strip()
            key = f"{p_amt}_{p_snd}"
            
            if key not in existing_keys:
                # Logic for Doctor
                doctor = "Unknown"
                if "TRIPIC" in p['sender'].upper(): doctor = "Dr. Tripic"
                elif "CARTAGENA" in p['sender'].upper(): doctor = "Dr. Cartagena"
                
                new_rows.append([p['date'], p['sender'], p['amount'], doctor])
                existing_keys.add(key) # Prevent internal dupes
                print(f"✨ NEW ENTRY: {p['sender']} - ${p['amount']}")
            else:
                # print(f"Skipping duplicate: {p['sender']}")
                pass

        if new_rows:
            ws.append_rows(new_rows)
            print(f"✅ Automatically added {len(new_rows)} payments to Sheet.")
        else:
            print("✅ No new payments found.")

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
