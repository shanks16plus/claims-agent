"""Entry point: theme, team password (deployed link only) and page navigation."""
import streamlit as st

from core import storage
from ui import theme


@st.cache_resource
def seed_claims_log():
    """Once per server start: an empty claims log gets our recorded test runs."""
    return storage.seed_if_empty()


st.set_page_config(page_title=theme.APP_NAME, page_icon=":material/directions_car:", layout="wide")
theme.apply()
seed_claims_log()

if not theme.password_gate():
    st.stop()

pages = {
    "Customer": [
        st.Page("views/start.py", title="Home", url_path="home", default=True),
        st.Page("views/claim_form.py", title="File a claim", url_path="claim"),
        st.Page("views/chat.py", title="Chat", url_path="chat"),
        st.Page("views/claim_status.py", title="Claim status", url_path="status"),
        st.Page("views/legal.py", title="Privacy and terms", url_path="privacy", visibility="hidden"),
    ],
    "Insurer": [
        st.Page("views/dashboard.py", title="Dashboard", url_path="dashboard"),
    ],
}
st.navigation(pages, position="top").run()
