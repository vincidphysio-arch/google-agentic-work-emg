import streamlit as st
import gspread
import pandas as pd
import json
from datetime import datetime, timedelta

# --- CONFIGURATION ---
SHEET_NAME = 'EMG Payments Kitchener'
CREDENTIALS_FILE = 'credentials.json'

# --- CONNECT TO GOOGLE ---
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

def get_all_data():
    gc = get_connection()
    sh = gc.open(SHEET_NAME)
    
    # 1. Get Payments (To calc average rate)
    ws_pay = sh.worksheet("Payments")
    pay_data = ws_pay.get_all_values()
    pay_headers = [h.strip() for h in pay_data[0]]
    df_pay = pd.DataFrame(pay_data[1:], columns=pay_headers)
    
    # 2. Get Work Log (To see future dates)
    ws_work = sh.worksheet("Work_Log")
    work_data = ws_work.get_all_values()
    work_headers = [h.strip() for h in work_data[0]]
    df_work = pd.DataFrame(work_data[1:], columns=work_headers)
    
    return df_pay, df_work

# --- DASHBOARD ---
def main():
    st.set_page_config(page_title="Future Income", layout="wide")
    
    if st.sidebar.button("⬅️ Back to Home"):
        st.switch_page("Home.py")
        
    st.title("🔮 Future Income Predictor")
    st.caption("Based on your Google Calendar & Historical Earning Rate")

    try:
        df_pay, df_work = get_all_data()
    except Exception as e:
        st.error(f"Error reading sheet: {e}")
        st.stop()

    if not df_pay.empty and not df_work.empty:
        # --- 1. CALCULATE HISTORICAL AVERAGE ---
        # Clean Payments
        df_pay['Amount'] = pd.to_numeric(df_pay['Amount'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce')
        total_earnings = df_pay['Amount'].sum()
        
        # Clean Work Log
        date_col = 'Date Worked' 
        if 'Date Worked' not in df_work.columns:
             date_col = df_work.columns[0] 

        df_work['Date Object'] = pd.to_datetime(df_work[date_col], errors='coerce')
        df_work = df_work.dropna(subset=['Date Object'])
        
        # Count PAST work days (Unique Dates Only!)
        today = datetime.now()
        past_work = df_work[df_work['Date Object'] < today]
        future_work = df_work[df_work['Date Object'] >= today]
        
        # *** FIX: Count UNIQUE dates so split days count as 1 ***
        days_worked = past_work['Date Object'].dt.date.nunique()
        
        # Calculate Real Average
        real_avg_rate = 0
        if days_worked > 0:
            real_avg_rate = total_earnings / days_worked

        # --- 2. SIDEBAR CONTROLS ---
        st.sidebar.header("⚙️ Forecast Settings")
        
        use_rate = st.sidebar.slider(
            "Estimated Daily Income ($)", 
            min_value=500, 
            max_value=3000, 
            value=int(real_avg_rate) if real_avg_rate > 0 else 1200,
            step=50,
            help="We calculated this baseline from your past payments."
        )
        
        months_forward = st.sidebar.slider("Look Forward (Months)", 1, 12, 6)

        # --- 3. CALCULATE PREDICTIONS ---
        end_date = today + timedelta(days=months_forward*30)
        scope_work = future_work[future_work['Date Object'] <= end_date]
        
        # *** FIX: Count UNIQUE future dates ***
        future_days_count = scope_work['Date Object'].dt.date.nunique()
        projected_income = future_days_count * use_rate
        
        # --- 4. VISUALS ---
        m1, m2, m3 = st.columns(3)
        m1.metric("📅 Future Work Days", f"{future_days_count} days", f"Next {months_forward} months")
        m2.metric("💰 Projected Income", f"${projected_income:,.2f}", f"@ ${use_rate}/day")
        m3.metric("📉 Historical Avg", f"${real_avg_rate:,.2f}/day", f"Based on {days_worked} past days")
        
        st.divider()
        
        # Group by Month for Chart
        scope_work['Month_Year'] = scope_work['Date Object'].dt.strftime('%Y-%m')
        
        # *** FIX: Group by Month, counting UNIQUE dates ***
        monthly_counts = scope_work.groupby('Month_Year')['Date Object'].apply(lambda x: x.dt.date.nunique()).reset_index(name='Days')
        monthly_counts['Estimated Income'] = monthly_counts['Days'] * use_rate
        
        st.subheader("📈 Monthly Forecast")
        st.bar_chart(monthly_counts.set_index('Month_Year')['Estimated Income'])
        
        with st.expander("See Future Schedule"):
            display_cols = [date_col, "Event Name", "Doctor"]
            final_cols = [c for c in display_cols if c in scope_work.columns]
            # Sort by date
            st.dataframe(
                scope_work.sort_values('Date Object')[final_cols], 
                use_container_width=True, 
                hide_index=True
            )

    else:
        st.info("Not enough data to forecast yet.")

if __name__ == "__main__":
    main()
