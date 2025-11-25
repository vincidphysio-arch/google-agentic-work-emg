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
            
            url = "https://docs.google.com/spreadsheets/d/1QAlr_R7nbXmFK15vASOKsYb5TylvgV11OA7ijEyHHPY/edit?usp=sharing"
            sh = gc.open_by_url(url)
            ws = sh.worksheet("Form responses 1")
            
            headers = ws.row_values(1)
            f.write(f"Headers: {headers}\n")
            
            # Also print first few rows of data to see values
            data = ws.get_all_values()
            if len(data) > 1:
                f.write(f"Row 1: {data[1]}\n")
            
            f.write("DEBUG_END\n")
    except Exception as e:
        with open("debug_output_headers.txt", "w") as f:
            f.write(f"DEBUG_ERROR: {repr(e)}\n")
            f.write(traceback.format_exc())

if __name__ == "__main__":
    main()
