import streamlit as st
import gspread
import pandas as pd
import json

# Page Config
st.set_page_config(page_title="Data Maintenance", layout="wide")
st.title("🧹 Data Maintenance")

# Load Data
def get_worksheet():
    if "gcpjson" in st.secrets:
        creds_dict = json.loads(st.secrets["gcpjson"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("EMG Payments Kitchener")
        return sh.worksheet("Payments")
    return None

ws = get_worksheet()
if not ws:
    st.error("Could not connect to Google Sheet.")
    st.stop()

data = ws.get_all_values()
if len(data) < 2:
    st.warning("No data found.")
    st.stop()

headers = data[0]
df = pd.DataFrame(data[1:], columns=headers)

# Convert for analysis
df['AmountNum'] = pd.to_numeric(df['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').fillna(0)
df['DateObj'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
df['SenderNorm'] = df['Sender'].astype(str).str.lower().str.strip()

st.info(f"Loaded {len(df)} rows from Google Sheet.")

# --- Cleaning Options ---
st.divider()
st.subheader("1. Remove '0.00' Entries")
zero_rows = df[df['AmountNum'] == 0]
st.write(f"Found **{len(zero_rows)}** rows with 0.00 amount.")
if not zero_rows.empty:
    with st.expander("View 0.00 Rows"):
        st.dataframe(zero_rows)
    if st.button("🗑️ Delete all 0.00 Rows"):
        # Filter keep > 0
        df_clean = df[df['AmountNum'] != 0]
        # Reconstruct list
        new_data = [headers] + df_clean[headers].values.tolist()
        ws.clear()
        ws.update(new_data)
        st.success("Deleted!")
        st.rerun()

st.divider()
st.subheader("2. Remove 'Unknown' Doctors")
unknown_rows = df[df['Doctor'] == "Unknown"]
st.write(f"Found **{len(unknown_rows)}** rows with 'Unknown' doctor (e.g. Personal payments).")
if not unknown_rows.empty:
    with st.expander("View Unknown Rows"):
        st.dataframe(unknown_rows)
    if st.button("🗑️ Delete 'Unknown' Doctor Rows"):
        df_clean = df[df['Doctor'] != "Unknown"]
        new_data = [headers] + df_clean[headers].values.tolist()
        ws.clear()
        ws.update(new_data)
        st.success("Deleted!")
        st.rerun()

st.divider()
st.subheader("3. Remove Duplicates")
# Duplicate logic: Same Date(Day), Amount, and Sender
# Create a Day column for comparison
df['Day'] = df['DateObj'].dt.date
duplicates = df[df.duplicated(subset=['Day', 'AmountNum', 'SenderNorm'], keep='first')]

st.write(f"Found **{len(duplicates)}** duplicate rows (Same Sender, Amount, and Day).")
if not duplicates.empty:
    with st.expander("View Duplicates (To be deleted)"):
        st.dataframe(duplicates)
    if st.button("🗑️ Delete Duplicates (Keep First)"):
        df_clean = df.drop_duplicates(subset=['Day', 'AmountNum', 'SenderNorm'], keep='first')
        new_data = [headers] + df_clean[headers].values.tolist()
        ws.clear()
        ws.update(new_data)
        st.success("Deleted!")
        st.rerun()
