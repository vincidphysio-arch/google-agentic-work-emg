import streamlit as st
import gspread
import pandas as pd
import json
import io

@st.cache_data(ttl=60)
def get_google_sheet_df(sheet_name, worksheet_name):
    """Fetch data from Google Sheet with proper credential handling"""
    try:
        creds_dict = json.loads(st.secrets["gcpjson"])
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open(sheet_name)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        
        if len(data) > 0:
            headers = data[0]
            df = pd.DataFrame(data[1:], columns=headers)
            return df
        return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

SHEET_NAME = "EMG Payments Kitchener"
WORKSHEET_NAME = "Payments"

st.set_page_config(page_title="Kitchener Finance Dashboard", layout="wide")
st.title("Kitchener Finance Dashboard")

if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# --- CSS Styling ---
st.markdown("""
<style>
.main { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none; padding: 20px; border-radius: 15px; color: white;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.highlight-card {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    border-radius: 20px; padding: 30px; text-align: center; margin-bottom: 20px;
    box-shadow: 0 8px 25px rgba(245, 87, 108, 0.4);
}
.highlight-label { color: white; font-size: 18px; font-weight: 600; text-transform: uppercase; }
.highlight-value { color: white; font-size: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

df = get_google_sheet_df(SHEET_NAME, WORKSHEET_NAME)

# --- Data Cleaning & Filtering ---
if not df.empty:
    # 1. FIX: Remove duplicate column names immediately (Required for Streamlit/Arrow)
    df = df.loc[:, ~df.columns.duplicated()]

    # 2. Filter and RESET INDEX
    # (Removed Tugalov filter as per user request to include all doctors)
    # if 'Doctor' in df.columns:
    #     df = df[~df['Doctor'].str.contains('Tugalov', case=False, na=False)].reset_index(drop=True)
    
    # 3. Convert Amount to Numeric
    if 'Amount' in df.columns:
        df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').fillna(0)
        
    # 4. Parse Dates
    if 'Date' in df.columns:
        df['Date Object'] = pd.to_datetime(df['Date'], errors='coerce', dayfirst=True)
        # Log warning if dates are dropped
        n_dropped = df['Date Object'].isna().sum() 
        if n_dropped > 0:
            st.warning(f"⚠️ {n_dropped} rows had invalid dates and were excluded.")
            
        df = df.dropna(subset=['Date Object']).reset_index(drop=True)
        
        # 5. Sort by Date Descending (Newest First)
        df = df.sort_values(by='Date Object', ascending=False).reset_index(drop=True)
        
        current_date = pd.Timestamp.now()
        current_month = current_date.month
        current_year = current_date.year
        
        total_earnings = df['Amount'].sum()
        monthly_earnings = df[(df['Date Object'].dt.month == current_month) & (df['Date Object'].dt.year == current_year)]['Amount'].sum()
        yearly_earnings = df[(df['Date Object'].dt.year == current_year)]['Amount'].sum()
        
        # Check for potential duplicates (Same Date, Same Amount, Same Sender)
        duplicates = df[df.duplicated(subset=['Date', 'Amount', 'Sender'], keep=False)]
        if not duplicates.empty:
            st.warning(f"⚠️ Warning: Found {len(duplicates)} potential duplicate entries! This might explain why your income looks too high.")
            with st.expander("Show Duplicates"):
                st.dataframe(duplicates)
        
        st.markdown("### 📊 Earnings Overview")
        l_col, r_col = st.columns([2, 1])
        with l_col:
            c1, c2 = st.columns(2)
            c1.metric("💰 Total Earnings", f"${total_earnings:,.2f}")
            c2.metric("📈 This Year", f"${yearly_earnings:,.2f}")
        with r_col:
            st.markdown(f'<div class="highlight-card"><div class="highlight-label">🌟 This Month</div><div class="highlight-value">${monthly_earnings:,.2f}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("📋 Detailed Records")
        
        try:
            # Use map for cell-wise styling
            styled_df = df.style.format({"Amount": "${:,.2f}"}).map(lambda x: 'color: green; font-weight: bold', subset=['Amount'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Downloads
        col_down1, col_down2 = st.columns(2)
        with col_down1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", csv, "KitchenerFinance.csv", "text/csv")
        with col_down2:
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            buffer.seek(0)
            st.download_button("📥 Download Excel", buffer, "KitchenerFinance.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("No data available.")
