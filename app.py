"""Entry point: theme, team password (deployed link only) and page navigation."""
import streamlit as st

from ui import theme

st.set_page_config(page_title=theme.APP_NAME, page_icon=":material/directions_car:", layout="wide")
theme.apply()

if not theme.password_gate():
    st.stop()

pages = [
    st.Page("views/start.py", title="Home", url_path="home", default=True),
    st.Page("views/claim_form.py", title="File a claim", url_path="claim"),
    st.Page("views/claim_status.py", title="Claim status", url_path="status"),
]
st.navigation(pages, position="top").run()
