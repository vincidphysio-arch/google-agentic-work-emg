import streamlit as st
import gspread
import pandas as pd
import json
import io

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

# CHANGE THESE for each dashboard:
SHEET_NAME = "Tugolov combined questionnaire(Responses)"      # <-- update as needed per file
WORKSHEET_NAME = "Form responses 1"            # <-- update per dashboard/tab

st.title("London Tracker Dashboard")
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

df = get_google_sheet_df(SHEET_NAME, WORKSHEET_NAME)

# --- Earnings Calculation Logic ---
def calculate_earnings(encounter_type):
    if not isinstance(encounter_type, str):
        return 0
    etype = encounter_type.lower().strip()
    
    if "follow up" in etype:
        return 65
    elif "consult" in etype:
        return 85
    else:
        return 0

# Ensure column exists and clean it
if "Type of encounter" in df.columns:
    df["Earnings"] = df["Type of encounter"].apply(calculate_earnings)
    
    # --- Date Parsing & Analytics ---
    if "Timestamp" in df.columns:
        # Convert Timestamp to datetime objects
        df["Date"] = pd.to_datetime(df["Timestamp"], dayfirst=True, errors='coerce')
        
        # Filter out invalid dates
        df_valid = df.dropna(subset=["Date"]).copy()
        
        if not df_valid.empty:
            current_date = pd.Timestamp.now()
            current_month = current_date.month
            current_year = current_date.year
            current_quarter = (current_month - 1) // 3 + 1
            
            # Add time periods
            df_valid["Month"] = df_valid["Date"].dt.month
            df_valid["Year"] = df_valid["Date"].dt.year
            df_valid["Quarter"] = (df_valid["Month"] - 1) // 3 + 1
            df_valid["MonthName"] = df_valid["Date"].dt.strftime('%B %Y')
            
            # Calculate aggregates
            monthly_earnings = df_valid[
                (df_valid["Month"] == current_month) & (df_valid["Year"] == current_year)
            ]["Earnings"].sum()
            
            quarterly_earnings = df_valid[
                (df_valid["Quarter"] == current_quarter) & (df_valid["Year"] == current_year)
            ]["Earnings"].sum()
            
            yearly_earnings = df_valid[
                (df_valid["Year"] == current_year)
            ]["Earnings"].sum()
            
            total_encounters = len(df)

            # --- Display Metrics with Enhanced Custom CSS ---
            # Total earnings - now only counts current year (2025) since work started this year
            total_earnings = df_valid[
                (df_valid["Year"] == current_year)
                    ]["Earnings"].sum()
            
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

            st.markdown("### 📊 Earnings Overview")
            
            # Create layout with highlighted "This Month" on the right
            left_col, right_col = st.columns([2, 1])
            
            with left_col:
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Total Earnings", f"${total_earnings:,.2f}")
                col2.metric("📅 This Quarter", f"${quarterly_earnings:,.2f}")
                col3.metric("📈 This Year", f"${yearly_earnings:,.2f}")
            
            with right_col:
                # Highlighted "This Month" card
                st.markdown(f"""
                <div class="highlight-card">
                    <div class="highlight-label">🌟 This Month</div>
                    <div class="highlight-value">${monthly_earnings:,.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            
            # --- Monthly Trend Chart ---
            st.markdown("### Monthly Earnings Trend")
            # Group by Month-Year for sorting
            monthly_trend = df_valid.groupby(df_valid["Date"].dt.to_period("M"))["Earnings"].sum()
            monthly_trend.index = monthly_trend.index.strftime('%Y-%m') # Convert to string for chart
            st.bar_chart(monthly_trend, color="#0068c9")
            
            # --- Monthly Filter ---
            st.divider()
            st.markdown("### Detailed Analysis")
            
            # Get unique months for dropdown
            available_months = sorted(df_valid["Date"].dt.strftime('%B %Y').unique(), key=lambda x: pd.to_datetime(x, format='%B %Y'), reverse=True)
            filter_options = ["All Time"] + list(available_months)
            
            selected_month = st.selectbox("Select Month to View Details:", filter_options)
            
            if selected_month == "All Time":
                filtered_df = df
                display_earnings = total_earnings
                display_encounters = total_encounters
                st.markdown(f"**Showing all data**")
            else:
                # Filter by selected month
                filtered_df = df_valid[df_valid["MonthName"] == selected_month]
                display_earnings = filtered_df["Earnings"].sum()
                display_encounters = len(filtered_df)
                st.markdown(f"**Showing data for: {selected_month}**")
                
                # Show specific metrics for the selection
                m_col1, m_col2 = st.columns(2)
                m_col1.metric(f"Earnings ({selected_month})", f"${display_earnings:,.2f}")
                m_col2.metric(f"Encounters ({selected_month})", display_encounters)

            # --- Data Styling ---
            def highlight_earnings(val):
                return 'color: green; font-weight: bold'

            def color_encounter_type(val):
                if not isinstance(val, str): return ''
                val_lower = val.lower()
                if 'consult' in val_lower:
                    return 'background-color: #d1e7dd; color: #0f5132' # Light Green
                elif 'follow up' in val_lower:
                    return 'background-color: #cfe2ff; color: #084298' # Light Blue
                return ''

            if not filtered_df.empty:
                styled_df = filtered_df.style.map(highlight_earnings, subset=['Earnings'])\
                                             .map(color_encounter_type, subset=['Type of encounter'])
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.info("No data available for this selection.")
            
            # Update download buttons to use filtered data
            csv = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV (Filtered)", csv, f"LondonTracker_{selected_month.replace(' ', '_')}.csv", "text/csv")
            
            buffer = io.BytesIO()
            filtered_df.to_excel(buffer, index=False)
            buffer.seek(0)
            st.download_button("Download Excel (Filtered)", buffer, f"LondonTracker_{selected_month.replace(' ', '_')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
        else:
            st.warning("Could not parse dates from 'Timestamp' column.")
            st.dataframe(df) # Show original if date parsing fails
    else:
        st.warning("'Timestamp' column not found.")
        st.dataframe(df)
else:
    st.warning("Column 'Type of encounter' not found in the sheet.")
    st.dataframe(df)
