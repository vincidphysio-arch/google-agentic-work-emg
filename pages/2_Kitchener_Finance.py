import streamlit as st
import gspread
import pandas as pd
import json
import io

@st.cache_data(ttl=60)
def get_google_sheet_df(sheet_name, worksheet_name):
    """
    Fetch data from Google Sheet with proper credential handling
    """
    try:
        # Load credentials from Streamlit secrets
        creds_dict = json.loads(st.secrets["gcpjson"])
        
        # Create gspread client with service account
        gc = gspread.service_account_from_dict(creds_dict)
        
        # Open the spreadsheet and worksheet
        sh = gc.open(sheet_name)
        worksheet = sh.worksheet(worksheet_name)
        
        # Get all data
        data = worksheet.get_all_values()
        
        # Create DataFrame
        if len(data) > 0:
            headers = data[0]
            df = pd.DataFrame(data[1:], columns=headers)
            return df
        else:
            return pd.DataFrame()
            
    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API Error: {str(e)}")
        st.info("Please refresh the page or contact support if the issue persists.")
        return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.info("Please check your credentials and try again.")
        return pd.DataFrame()

SHEET_NAME = "EMG Payments Kitchener"
WORKSHEET_NAME = "Payments"

st.title("Kitchener Finance Dashboard")
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# --- CSS Styling ---
st.markdown("""
<style>
/* General page styling */
.main {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}

/* Standard metric cards */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    padding: 20px;
    border-radius: 15px;
    color: white;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
div[data-testid="stMetricLabel"] {
    color: rgba(255,255,255,0.9);
    font-size: 14px;
    font-weight: 500;
}
div[data-testid="stMetricValue"] {
    color: white;
    font-size: 28px;
    font-weight: bold;
}

/* Custom highlighted card for This Month */
.highlight-card {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    border-radius: 20px;
    padding: 30px;
    box-shadow: 0 8px 25px rgba(245, 87, 108, 0.4);
    text-align: center;
    margin-bottom: 20px;
}
.highlight-label {
    color: white;
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.highlight-value {
    color: white;
    font-size: 48px;
    font-weight: bold;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
}
</style>
""", unsafe_allow_html=True)

df = get_google_sheet_df(SHEET_NAME, WORKSHEET_NAME)

# --- Data Cleaning & Filtering ---
if not df.empty:
    # 1. Filter out Dr. Tugalov
    if 'Doctor' in df.columns:
        df = df[~df['Doctor'].str.contains('Tugalov', case=False, na=False)]
    
    # 2. Convert Amount to Numeric
    if 'Amount' in df.columns:
        df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').fillna(0)
        
    # 3. Parse Dates
    if 'Date' in df.columns:
        df['Date Object'] = pd.to_datetime(df['Date'], errors='coerce, dayfirst=True)
        df = df.dropna(subset=['Date Object'])
        
        # Calculate Metrics
        current_date = pd.Timestamp.now(), dayfirst=True
        current_month = current_date.month
        current_year = current_date.year
        
        total_earnings = df['Amount'].sum()
        
        monthly_earnings = df[
            (df['Date Object'].dt.month == current_month) & 
            (df['Date Object'].dt.year == current_year)
        ]['Amount'].sum()
        
        yearly_earnings = df[
            (df['Date Object'].dt.year == current_year)
        ]['Amount'].sum()
        
        # --- Display Metrics ---
        st.markdown("### 📊 Earnings Overview")
        
        left_col, right_col = st.columns([2, 1])
        
        with left_col:
            c1, c2 = st.columns(2)
            c1.metric("💰 Total Earnings", f"${total_earnings:,.2f}")
            c2.metric("📈 This Year", f"${yearly_earnings:,.2f}")
            
        with right_col:
             # Highlighted "This Month" card
            st.markdown(f"""
            <div class="highlight-card">
                <div class="highlight-label">🌟 This Month</div>
                <div class="highlight-value">${monthly_earnings:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        # --- Styled Table ---
        st.divider()
        st.subheader("📋 Detailed Records")
        
        def highlight_amount(val):
            return 'color: green; font-weight: bold'
            
        styled_df = df.style.format({"Amount": "${:,.2f}"})\
                            .map(highlight_amount, subset=['Amount'])
                            
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        # Downloads
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "KitchenerFinance.csv", "text/csv")
        
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)
        st.download_button("Download Excel", buffer, "KitchenerFinance.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("No data available.")
