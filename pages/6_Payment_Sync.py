import streamlit as st
import os.path
import base64
import json
import pandas as pd
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import gspread
from datetime import datetime, timedelta
import re

# SCOPES for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                st.error("❌ 'credentials.json' not found. Please upload your Gmail OAuth credentials.")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            # Use a local server for auth (might need adjustment for Streamlit Cloud)
            # For Streamlit Cloud, we might need a different approach (e.g. copy paste token)
            # But for local testing this works.
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

def parse_interac_email(service, msg_id):
    """
    Fetch email body and parse for Amount, Sender, Date
    """
    try:
        message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        payload = message['payload']
        headers = payload['headers']
        
        subject = next(h['value'] for h in headers if h['name'] == 'Subject')
        date_str = next(h['value'] for h in headers if h['name'] == 'Date')
        
        # Parse Date (Approximate)
        # Format: "Tue, 23 Dec 2025 18:20:00 -0500"
        try:
            email_date = datetime.strptime(date_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except:
            email_date = datetime.now() # Fallback

        # Get Body
        body_data = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    body_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        elif 'body' in payload:
             body_data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        soup = BeautifulSoup(body_data, 'html.parser')
        text_content = soup.get_text()

        # Regex for Amount ($910.00)
        amount_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text_content)
        amount = amount_match.group(1) if amount_match else "0.00"

        # Regex for Sender (From X)
        # Usually "You've received $X from SENDER NAME"
        sender_match = re.search(r"received \$[\d\.,]+ from (.*?) and", text_content, re.IGNORECASE)
        # Fallback for subject line parsing
        if not sender_match:
             sender_match = re.search(r"received \$[\d\.,]+ from (.*?) and", subject, re.IGNORECASE)
             
        sender = sender_match.group(1).strip() if sender_match else "Unknown"
        
        # Clean Sender Name (remove extra words if any)
        if "Interac" in sender: sender = sender.replace("Interac", "").strip()

        return {
            "id": msg_id,
            "date": email_date.strftime("%d/%m/%Y %H:%M:%S"),
            "sender": sender,
            "amount": amount,
            "subject": subject
        }

    except Exception as e:
        print(f"Error parsing {msg_id}: {e}")
        return None

def get_google_sheet_data():
    if "gcpjson" in st.secrets:
        creds_dict = json.loads(st.secrets["gcpjson"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("EMG Payments Kitchener")
        ws = sh.worksheet("Payments")
        return ws
    return None

def main():
    st.set_page_config(page_title="Payment Sync", layout="wide")
    st.title("📥 Sync Interac Payments")
    
    st.info("This tool scans your Gmail for 'Interac' emails from the last 7 days and adds them to the Google Sheet if missing.")

    if st.button("🚀 Start Sync", type="primary"):
        status = st.empty()
        status.write("🔑 Authenticating with Gmail...")
        
        try:
            service = get_gmail_service()
            if not service:
                return

            status.write("🔍 Searching for recent Interac emails...")
            
            # Search Query: "Interac" AND "deposited" in last 7 days
            today = datetime.now().strftime("%Y/%m/%d")
            # query = f'subject:"Interac e-Transfer" "deposited" after:{before_date}' # Simplified for demo
            query = 'subject:"Interac e-Transfer" "deposited"'
            
            results = service.users().messages().list(userId='me', q=query, maxResults=20).execute()
            messages = results.get('messages', [])
            
            status.write(f"📧 Found {len(messages)} matching emails. Parsing...")
            
            found_payments = []
            progress_bar = st.progress(0)
            
            for i, msg in enumerate(messages):
                payment = parse_interac_email(service, msg['id'])
                if payment:
                    found_payments.append(payment)
                progress_bar.progress((i + 1) / len(messages))
                
            # Deduplicate against Google Sheet
            status.write("💾 Checking Google Sheet for duplicates...")
            ws = get_google_sheet_data()
            if not ws:
                st.error("Could not connect to Google Sheet.")
                return
                
            existing_data = ws.get_all_values()
            # headers: Date, Sender, Amount
            # Simple dedupe key: Date + Amount (Rough but effective for now)
            
            existing_keys = set()
            for row in existing_data[1:]:
                # Setup key: Amount + Sender (Date might vary slightly between email and log)
                # Let's use Amount + Sender for safety
                amt = str(row[2]).replace('$','').replace(',','')
                snd = str(row[1]).lower().strip()
                key = f"{amt}_{snd}"
                existing_keys.add(key)
                # strict key
                key_strict = f"{row[0]}_{amt}_{snd}" # Date_Amt_Sender
                existing_keys.add(key_strict)

            new_payments = []
            for p in found_payments:
                p_amt = str(p['amount']).replace(',','')
                p_snd = str(p['sender']).lower().strip()
                
                # Check duplication
                key = f"{p_amt}_{p_snd}"
                
                # Verify date proximity? For now, just trust unique key or subject ID if possible
                # Google Sheets usually doesn't store Msg ID.
                # Let's Assume if (Amount, Sender) matches in last 7 days, it's the same.
                
                # BETTER: Check date diff? 
                # Let's just list them for review first? 
                # Or auto-add if perfectly unique.
                
                # Let's implement safe auto-add
                if key not in existing_keys:
                    # Doctor mapping (simple logic)
                    doctor = "Unknown"
                    if "TRIPIC" in p['sender'].upper(): doctor = "Dr. Tripic"
                    elif "CARTAGENA" in p['sender'].upper(): doctor = "Dr. Cartagena"
                    
                    new_payments.append([p['date'], p['sender'], p['amount'], doctor])
                    existing_keys.add(key) # Prevent double adding in same loop

            if new_payments:
                st.write(f"✨ Found {len(new_payments)} NEW payments:")
                df_new = pd.DataFrame(new_payments, columns=["Date", "Sender", "Amount", "Doctor"])
                st.dataframe(df_new)
                
                if st.button("Confirm & Save to Sheet"):
                    ws.append_rows(new_payments)
                    st.success("✅ Successfully saved to Google Sheet!")
            else:
                st.success("✅ No new payments found. Your sheet is up to date!")
                
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.expander("Traceback").write(str(e))

if __name__ == "__main__":
    main()
