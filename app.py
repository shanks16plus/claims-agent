"""Entry point: theme, team password (deployed link only) and page navigation."""
import streamlit as st

import fresh

fresh.use_latest_code()        # before our own imports: after a push they must be the new versions

from core import storage  # noqa: E402
from ui import theme  # noqa: E402


@st.cache_resource
def seed_claims_log():
    """Once per server start: an empty claims log gets our recorded test runs."""
    return storage.seed_if_empty()


st.set_page_config(page_title=theme.APP_NAME, page_icon=":material/directions_car:", layout="wide")
theme.apply()
seed_claims_log()

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
# The pages are registered before the password screen, so a link to a page (say /status?claim=...) is still
# that page after signing in. The menu only shows once signed in.
page = st.navigation(pages, position="top" if theme.signed_in() else "hidden")
if not theme.signed_in() and page.url_path != "privacy":     # the privacy notice is public
    theme.password_gate()
    st.stop()
page.run()
