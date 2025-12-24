import streamlit as st
import gspread
import json
import traceback

def main():
    try:
        with open("debug_output_headers.txt", "w") as f:
            f.write("DEBUG_START\n")
            creds_dict = json.loads(st.secrets["gcpjson"])
            gc = gspread.service_account_from_dict(creds_dict)
            
            # url = "https://docs.google.com/spreadsheets/d/..."
            # sh = gc.open_by_url(url)
            # Use name instead of URL for safety/consistency with other files
            sh = gc.open("EMG Payments Kitchener")
            ws = sh.worksheet("Payments")
            
            headers = ws.row_values(1)
            f.write(f"Headers: {headers}\n")
            
            # Also print first few rows of data to see values
            data = ws.get_all_values()
            f.write(f"Total Rows: {len(data)}\n")
            if len(data) > 0:
                f.write(f"Row 1 (Headers): {data[0]}\n")
            if len(data) > 1:
                f.write(f"Last Row: {data[-1]}\n")
                # Check recent rows for '910' or 'Tripic'
                for row in data[-5:]:
                    f.write(f"Recent Row: {row}\n")
            
            f.write("DEBUG_END\n")
    except Exception as e:
        with open("debug_output_headers.txt", "w") as f:
            f.write(f"DEBUG_ERROR: {repr(e)}\n")
            f.write(traceback.format_exc())

if __name__ == "__main__":
    main()
