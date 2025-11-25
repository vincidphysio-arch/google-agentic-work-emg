import streamlit as st
import gspread
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
SHEET_LONDON = 'Tugolov combined questionnaire(Responses)'
SHEET_KITCHENER = 'EMG Payments Kitchener'
CREDENTIALS_FILE = 'credentials.json'

CRA_MAP = {
    "🚗 Travel/Parking": "Line 9281 - Motor vehicle expenses",
    "🏥 Medical Supplies": "Line 8810 - Office stationery and supplies",
    "📜 Professional Fees/Licenses": "Line 8760 - Business taxes, licences and memberships",
    "🎓 Continuing Education": "Line 8710 - Seminars/Conventions (or Tuition)",
    "💻 Software/Office": "Line 8810 - Office stationery and supplies",
    "🥣 Meals/Entertainment": "Line 8523 - Meals and entertainment (50%)",
    "Other": "Line 9270 - Other expenses"
}

@st.cache_resource
def get_connection():
    try:
        if "gcpjson" in st.secrets:
            creds_dict = json.loads(st.secrets["gcpjson"])
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            st.error("Secrets 'gcpjson' not found.")
            st.stop()
        return gc
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.stop()

def clean_and_convert_dates(df, date_col_name):
    """Helper function to safely convert dates and remove bad rows"""
    if df.empty or date_col_name not in df.columns:
        return df
    
    # Force conversion, turn errors into NaT (Not a Time)
    df['Date Object'] = pd.to_datetime(df[date_col_name], dayfirst=True, errors='coerce')
    
    # Drop rows where date conversion failed
    df = df.dropna(subset=['Date Object'])
    
    return df

def get_combined_data():
    gc = get_connection()
    
    # 1. GET LONDON DATA
    try:
        sh_lon = gc.open(SHEET_LONDON)
        ws_lon = sh_lon.get_worksheet(0)
        data_lon = ws_lon.get_all_records()
        df_lon = pd.DataFrame(data_lon)
        
        # Find the Date Column
        lon_date_col = 'Timestamp' if 'Timestamp' in df_lon.columns else 'Date'
        
        # Safe Date Conversion
        df_lon = clean_and_convert_dates(df_lon, lon_date_col)
        
        # Calculate Amounts if missing
        if 'Amount' not in df_lon.columns:
            df_lon['Amount'] = 0.0
            for index, row in df_lon.iterrows():
                t = str(row.get("Type of encounter", "")).lower()
                if "new consult" in t: df_lon.at[index, 'Amount'] = 85.00
                elif "non cts" in t: df_lon.at[index, 'Amount'] = 65.00
                elif "follow up" in t: df_lon.at[index, 'Amount'] = 65.00
                
    except Exception:
        df_lon = pd.DataFrame(columns=['Date Object', 'Amount'])

    # 2. GET KITCHENER DATA
    try:
        sh_kit = gc.open(SHEET_KITCHENER)
        ws_kit = sh_kit.worksheet("Payments")
        data_kit = ws_kit.get_all_values()
        # Force headers from row 1
        headers = [h.strip() for h in data_kit[0]]
        df_kit = pd.DataFrame(data_kit[1:], columns=headers)
        
        # Safe Date Conversion
        df_kit = clean_and_convert_dates(df_kit, 'Date')
        
        # Clean Amount
        df_kit['Amount'] = pd.to_numeric(df_kit['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').fillna(0)
        
    except Exception:
        df_kit = pd.DataFrame(columns=['Date Object', 'Amount'])

    # 3. GET EXPENSES
    try:
        sh_exp = gc.open(SHEET_KITCHENER)
        # Try both names just in case
        try:
            ws_exp = sh_exp.worksheet("Expenses_Form") 
        except:
            ws_exp = sh_exp.worksheet("Expenses")
            
        data_exp = ws_exp.get_all_values()
        
        # Manual mapping for safety
        structured_exp = []
        if len(data_exp) > 1:
            for row in data_exp[1:]:
                # Ensure row has enough cols
                if len(row) >= 3: 
                    # Check if we are using the Form layout (Timestamp is Col A) or Manual (Date is Col A)
                    # Simple heuristic: If Col A looks like a timestamp (long string), treat Col B as Date
                    # But to be safe, let's try to parse Col B first (Form style), if fail, try Col A
                    
                    # DEFAULT: Assume Form Layout (Col B = Date, Col C = Category, Col D = Amount)
                    date_val = row[1] if len(row) > 1 else ""
                    cat_val = row[2] if len(row) > 2 else ""
                    amt_val = row[3] if len(row) > 3 else 0
                    
                    # Fallback for Manual Layout (Col A = Date, Col B = Category, Col C = Amount)
                    # If the header was 'Date', use Col A
                    if "Date" in data_exp[0][0]: 
                        date_val = row[0]
                        cat_val = row[1]
                        amt_val = row[2]

                    structured_exp.append({
                        "Date": date_val,
                        "Category": cat_val,
                        "Amount": amt_val
                    })

        df_exp = pd.DataFrame(structured_exp)
        df_exp = clean_and_convert_dates(df_exp, 'Date')
        df_exp['Amount'] = pd.to_numeric(df_exp['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').fillna(0)
            
    except Exception as e:
        # If it fails, return empty
        df_exp = pd.DataFrame(columns=['Date Object', 'Amount', 'Category'])

    return df_lon, df_kit, df_exp

def main():
    st.set_page_config(page_title="Tax Center", layout="wide")
    
    if st.sidebar.button("⬅️ Back to Home"):
        st.switch_page("Home.py")
        
    st.title("🏛️ Tax Command Center")
    st.caption("Consolidated Financials (London + Kitchener)")

    if st.sidebar.button("🔄 FORCE REFRESH"):
        st.cache_data.clear()
        st.rerun()

    try:
        df_lon, df_kit, df_exp = get_combined_data()
    except Exception as e:
        st.error(f"Data Error: {e}")
        st.stop()

    # --- TIME FILTER ---
    current_year = datetime.now().year
    selected_year = st.sidebar.selectbox("Select Tax Year", [current_year, current_year-1, current_year-2])

    # Filter
    # Check if empty before filtering to avoid crash
    if not df_lon.empty: df_lon = df_lon[df_lon['Date Object'].dt.year == selected_year]
    if not df_kit.empty: df_kit = df_kit[df_kit['Date Object'].dt.year == selected_year]
    if not df_exp.empty: df_exp = df_exp[df_exp['Date Object'].dt.year == selected_year]

    # --- CALCS ---
    london_total = df_lon['Amount'].sum() if not df_lon.empty else 0
    kitchener_total = df_kit['Amount'].sum() if not df_kit.empty else 0
    gross_income = london_total + kitchener_total
    
    total_expenses = df_exp['Amount'].sum() if not df_exp.empty else 0
    net_income = gross_income - total_expenses

    # Tax Estimator
    st.sidebar.divider()
    st.sidebar.header("⚖️ Tax Settings")
    tax_rate = st.sidebar.slider("Est. Tax Rate (%)", 15, 50, 30)
    estimated_tax = net_income * (tax_rate / 100)
    safe_to_spend = net_income - estimated_tax

    # --- DISPLAY ---
    st.subheader(f"Financials for {selected_year}")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Gross Revenue", f"${gross_income:,.2f}", help="London + Kitchener")
    c2.metric("📉 Expenses", f"${total_expenses:,.2f}")
    c3.metric("💵 Net Income", f"${net_income:,.2f}")
    c4.metric("🏛️ Est. Tax Due", f"${estimated_tax:,.2f}", f"@ {tax_rate}%")

    st.markdown(f"""
    <div style="background-color: #d4edda; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #c3e6cb;">
        <h2 style="color: #155724; margin:0;">✅ Safe to Spend: ${safe_to_spend:,.2f}</h2>
        <p style="color: #155724; margin:0;">(Profit - Estimated Taxes)</p>
    </div>
    <br>
    """, unsafe_allow_html=True)

    # CRA Categorization
    st.subheader("📂 CRA Expense Categories (T2125)")
    
    if not df_exp.empty:
        df_exp['CRA Line'] = df_exp['Category'].map(CRA_MAP).fillna("Other")
        cra_summary = df_exp.groupby('CRA Line')['Amount'].sum().reset_index().sort_values(by='Amount', ascending=False)
        
        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.dataframe(cra_summary, use_container_width=True, hide_index=True, column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")})
        with col_b:
            # Income Split Chart
            source_df = pd.DataFrame({
                "Source": ["London Fees", "Kitchener Payments"],
                "Amount": [london_total, kitchener_total]
            })
            st.markdown("**Revenue Sources**")
            st.bar_chart(source_df.set_index("Source"))
    else:
        st.info("No expenses logged for this year.")

if __name__ == "__main__":
    main()
