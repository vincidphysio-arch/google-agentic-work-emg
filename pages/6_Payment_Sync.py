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
    # 1. Try to load token from secrets or file
    if os.path.exists('token.json'):
         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 2. If valid, return service
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)

    # 3. Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            return build('gmail', 'v1', credentials=creds)
        except Exception:
            st.warning("Token expired and refresh failed. Please re-authenticate.")
            creds = None

    # 4. New Authentication
    if not creds:
        # Check session state first
        creds_content = st.session_state.get('creds_json_content', None)
        
        # UI to get credentials if missing
        if not creds_content:
            if os.path.exists('credentials.json'):
                # Legacy check
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            elif "gmail" in st.secrets:
                 creds_info = json.loads(st.secrets["gmail"]["client_secret_json"])
                 flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
            else:
                st.warning("⚠️ Credentials not found.")
                with st.expander("⚙️ Setup Gmail Access", expanded=True):
                    tab1, tab2 = st.tabs(["📂 Upload File", "📝 Paste JSON"])
                    
                    with tab1:
                        uploaded_file = st.file_uploader("Upload credentials.json", type="json", key="u1")
                        if uploaded_file:
                            creds_content = json.load(uploaded_file)
                            st.session_state['creds_json_content'] = creds_content
                            st.success("Loaded!")
                            st.rerun()
                            
                    with tab2:
                        json_str = st.text_area("Paste credentials.json content here")
                        if st.button("Save JSON"):
                            try:
                                creds_content = json.loads(json_str)
                                st.session_state['creds_json_content'] = creds_content
                                st.success("Loaded!")
                                st.rerun()
                            except:
                                st.error("Invalid JSON")
                st.stop()
                return None
        else:
            # We have content in session state
            flow = InstalledAppFlow.from_client_config(creds_content, SCOPES)

        # Cloud-friendly Auth Flow (OOB)
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        auth_url, _ = flow.authorization_url(prompt='consent')

        st.markdown(f"### 🔗 [Click here to Authorize Gmail Access]({auth_url})")
        st.info("Since this app runs in the cloud, we need to copy-paste the code manually.")
        
        code = st.text_input("Paste the Authorization Code here:", type="password")
        
        if code:
            try:
                flow.fetch_token(code=code)
                creds = flow.credentials
                # Save token locally (ephemeral in cloud, but works for session)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                st.success("✅ Authenticated! click Start Sync again.")
                st.session_state['creds_json_content'] = None # Clear after success
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {e}")
                return None
        else:
            st.stop() # Wait for input

    return build('gmail', 'v1', credentials=creds)

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
        # Recursive function to find body
        def get_body_from_payload(payload):
            if 'body' in payload and 'data' in payload['body']:
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
            
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/html':
                        return get_body_from_payload(part)
                    if part['mimeType'] == 'text/plain': # Fallback
                        return get_body_from_payload(part)
                    if 'parts' in part: # Nested parts
                         res = get_body_from_payload(part)
                         if res: return res
            return ""

        body_data = get_body_from_payload(payload)
        
        if not body_data:
             # Last ditch effort: extracted snippet from list
             body_data = message.get('snippet', '')

        soup = BeautifulSoup(body_data, 'html.parser')
        # Use separator to avoid joining text like "Amount:$500" into "Amount:$500" without space if hidden in divs
        text_content = soup.get_text(separator=' ')

        # Regex for Amount
        # Pattern 1: $1,234.50
        amount_match = re.search(r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', text_content)
        
        # Pattern 2: "910.00 (CAD)" or "910.00 CAD"
        if not amount_match:
             amount_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*(?:CAD|CDN)', text_content, re.IGNORECASE)

        # Pattern 3: "sent you 910.00"
        if not amount_match:
             amount_match = re.search(r'sent you\s+\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', text_content, re.IGNORECASE)

        # Pattern 4: "Amount: 910.00"
        if not amount_match:
             amount_match = re.search(r'Amount:?\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', text_content, re.IGNORECASE)

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
            "subject": subject,
            "raw_text": text_content[0:2000] # Save snippet for debug
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

    # Initialize Session State for Flow Control
    if 'sync_active' not in st.session_state:
        st.session_state['sync_active'] = False

    if st.button("🚀 Start Sync", type="primary"):
        st.session_state['sync_active'] = True

    # Main Logic Block (Runs if active, avoiding nested button issues)
    if st.session_state['sync_active']:
        if st.button("❌ Cancel / Reset"):
            st.session_state['sync_active'] = False
            st.rerun()
            
        status = st.empty()
        status.write("🔑 Authenticating with Gmail...")
        
        try:
            service = get_gmail_service()
            if not service:
                # get_gmail_service handles the UI for auth. 
                # If it returns None, it means we are waiting for user action.
                return

            status.write("🔍 Searching for recent Interac emails...")
            
            # Search Query: "Interac" AND "deposited" in last 7 days
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
            
            existing_keys = set()
            for row in existing_data[1:]:
                if len(row) > 2:
                    amt = str(row[2]).replace('$','').replace(',','')
                    snd = str(row[1]).lower().strip()
                    key = f"{amt}_{snd}"
                    existing_keys.add(key)
                    # strict key
                    key_strict = f"{row[0]}_{amt}_{snd}" 
                    existing_keys.add(key_strict)

            new_payments = []
            for p in found_payments:
                p_amt = str(p['amount']).replace(',','')
                p_snd = str(p['sender']).lower().strip()
                key = f"{p_amt}_{p_snd}"
                
                if key not in existing_keys:
                    doctor = "Unknown"
                    if "TRIPIC" in p['sender'].upper(): doctor = "Dr. Tripic"
                    elif "CARTAGENA" in p['sender'].upper(): doctor = "Dr. Cartagena"
                    
                    # Store full dict for debugging, add computed doctor field
                    p_entry = p.copy()
                    p_entry['doctor'] = doctor
                    new_payments.append(p_entry)
                    
                    existing_keys.add(key)

            if new_payments:
                st.write(f"✨ Found {len(new_payments)} NEW payments:")
                st.warning("⚠️ Please review and EDIT the table below if amounts are 0.00!")
                
                # Create DataFrame from dicts
                df_new = pd.DataFrame(new_payments)
                # Select and reorder columns for display
                df_display = df_new[["date", "sender", "amount", "doctor"]]
                df_display.columns = ["Date", "Sender", "Amount", "Doctor"]
                
                # Use Data Editor to allow manual corrections
                edited_df = st.data_editor(df_display, num_rows="dynamic")
                
                # --- DEBUG SECTION ---
                # Show raw text for the first 0.00 amount to help debug
                zero_rows = [p for p in new_payments if p['amount'] == "0.00"]
                if zero_rows:
                    st.divider()
                    st.error("🐞 Debug Info: I can't read the amount for these emails. Here is what I see:")
                    st.text_area("Raw Email Text (Copy/Paste this to the AI)", zero_rows[0].get('raw_text', 'No raw text saved'), height=200)
                # ---------------------

                if st.button("Confirm & Save to Sheet", key="confirm_save"):
                    # Convert edited DF back to list
                    final_data = edited_df.values.tolist()
                    ws.append_rows(final_data)
                    st.success("✅ Successfully saved to Google Sheet!")
                    st.balloons()
            else:
                st.success("✅ No new payments found. Your sheet is up to date!")
                st.balloons()
                
            # --- Secrets Export for GitHub Automation ---
            st.divider()
            with st.expander("🤖 Configure Automatic Robot (GitHub Actions)"):
                st.markdown("""
                To make this run **automatically every hour** on GitHub, you need to add these two secrets 
                to your GitHub Repository Settings (`Settings` -> `Secrets and variables` -> `Actions`).
                """)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("1. GMAIL_TOKEN")
                    # Try to get token from current session or file
                    token_content = None
                    if os.path.exists('token.json'):
                        with open('token.json', 'r') as f:
                            token_content = f.read()
                    
                    if token_content:
                        st.code(token_content, language="json")
                        st.caption("Copy this and paste it as `GMAIL_TOKEN` in GitHub Secrets.")
                    else:
                        st.warning("⚠️ Please 'Start Sync' and Login first to generate this token.")

                with col2:
                    st.subheader("2. GCP_JSON")
                    if "gcpjson" in st.secrets:
                        # Reconstruct JSON string from secrets toml object or string
                        # st.secrets returns an AttrDict for TOML tables, or string if raw.
                        # Assuming it's a string structure in toml like gcpjson = '...' or [gcpjson]
                        # Based on typical usage, it might be a dictionary if parsed from TOML table.
                        try:
                            # If it handles as a dict in secrets.toml
                            gcp_data = st.secrets["gcpjson"]
                            if isinstance(gcp_data, str):
                                st.code(gcp_data, language="json")
                            else:
                                st.code(json.dumps(dict(gcp_data)), language="json")
                            st.caption("Copy this and paste it as `GCP_JSON` in GitHub Secrets.")
                        except:
                            st.error("Could not read gcpjson from secrets.")
                    else:
                        st.error("gcpjson missing from secrets.")
        
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.expander("Traceback").write(str(e))


if __name__ == "__main__":
    main()
