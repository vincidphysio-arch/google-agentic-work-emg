import streamlit as st
import gspread
import json
import traceback

def main():
    try:
        with open("debug_audit.txt", "w") as f:
            f.write("DEBUG_START\n")
            if "gcpjson" in st.secrets:
                creds_dict = json.loads(st.secrets["gcpjson"])
                gc = gspread.service_account_from_dict(creds_dict)
                
                # Use name 
                sh = gc.open("EMG Payments Kitchener")
                ws = sh.worksheet("Payments")
                
                # Get all data
                data = ws.get_all_values()
                f.write(f"Total Rows: {len(data)}\n")
                
                if len(data) > 0:
                    f.write(f"Headers: {data[0]}\n")
                
                start_row = max(0, len(data) - 10)
                f.write(f"Dumping rows from {start_row} to end:\n")
                
                for i in range(start_row, len(data)):
                    f.write(f"Row {i+1}: {data[i]}\n")
            else:
                f.write("ERROR: st.secrets['gcpjson'] not found.\n")
            
            f.write("DEBUG_END\n")
    except Exception as e:
        with open("debug_audit.txt", "w") as f:
            f.write(f"DEBUG_ERROR: {repr(e)}\n")
            f.write(traceback.format_exc())

if __name__ == "__main__":
    main()
