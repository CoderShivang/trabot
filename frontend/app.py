import streamlit as st
st.set_page_config(layout="wide", page_title="Scalper Dashboard")
st.title("BTC/ETH Scalper Bot - Dashboard (Simplified)")
st.markdown("This is a simplified Streamlit UI. For full functionality, run the bot service.")
if st.button("Ping bot"):
    st.success("Bot pinged (placeholder)")
