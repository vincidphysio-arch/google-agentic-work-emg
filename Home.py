import streamlit as st

st.set_page_config(page_title="EMG Portal", page_icon="🏥", layout="wide")

st.title("🏥 EMG Business Portal")
st.write("Select a clinic location:")

col1, col2 = st.columns(2)

with col1:
    # Changed from GB flag to City Building icon
    st.header("🏙️ London, ON") 
    st.write("Patient Tracker & Earnings")
    if st.button("Go to London Dashboard", type="primary"):
        st.switch_page("pages/1_London_Tracker.py")

with col2:
    # Kept consistent style
    st.header("📍 Kitchener, ON") 
    st.write("Interac Payments & Doctors")
    if st.button("Go to Kitchener Dashboard", type="primary"):
        st.switch_page("pages/2_Kitchener_Finance.py")
