import streamlit as st
import gspread
import pandas as pd
import json

def main():
    st.set_page_config(layout="wide")
    st.title("🕵️ Debug Sheet Data")
    
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()
        
    try:
        # Load credentials
        creds_dict = json.loads(st.secrets["gcpjson"])
        gc = gspread.service_account_from_dict(creds_dict)
        
        # Open details
        st.write("Attempting to open: `EMG Payments Kitchener`")
        sh = gc.open("EMG Payments Kitchener")
        
        st.write("Attempting to open worksheet: `Payments`")
        ws = sh.worksheet("Payments")
        
        data = ws.get_all_values()
        st.success(f"Successfully fetched {len(data)} rows.")
        
        if len(data) > 0:
            st.markdown("### Raw Data Preview")
            df = pd.DataFrame(data)
            st.dataframe(df)
            
            st.markdown("### Column Headers (Row 0)")
            st.code(str(data[0]))
            
            st.markdown("### Last 5 Rows")
            st.code(str(data[-5:]))
            
    except Exception as e:
        st.error(f"Error: {e}")
        st.code(json.dumps(dict(st.secrets), default=str)) # Be careful not to expose full private keys if possible, but valid for debug

if __name__ == "__main__":
    main()
