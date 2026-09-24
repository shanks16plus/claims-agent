"""Start screen: the customer picks the chat or the form."""
import streamlit as st

from ui import theme

left, _, right = st.columns([11, 1, 10])

with left:
    theme.eyebrow("Car damage claim")
    st.markdown("# Report car damage in a few minutes")
    theme.lede("Tell us what happened and add a few photos. We check your claim straight away, and if "
               "anything needs a closer look, a claims handler takes it from there.")
    st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)

    st.markdown("<div class='ca-option'><h3>Fill in a short form</h3>"
                "<p>A few questions and three photos. About five minutes.</p></div>", unsafe_allow_html=True)
    if st.button("Start the form", type="primary"):
        st.switch_page("views/claim_form.py")

    st.markdown("<div class='ca-option' style='margin-top:1.4rem'><h3>Chat with the assistant</h3>"
                "<p>It asks one question at a time and checks your photos as you go.</p></div>",
                unsafe_allow_html=True)
    st.button("Arrives in the next build", disabled=True)

with right:
    theme.photo("start", height=620)

st.markdown("<div class='ca-rule'></div>", unsafe_allow_html=True)
st.markdown("## How it works")
columns = st.columns(3, gap="large")
how = [
    ("Tell us what happened", "Your policy number, when and where it happened, and whether another car "
                              "was involved."),
    ("Add photos", "A wide shot, close-ups of the damage and the number plate. If a photo needs a retake, "
                   "you'll know straight away."),
    ("Get a decision", "Simple claims are settled on the spot. Anything else goes to a claims handler with "
                       "your file already prepared."),
]
for column, (title, body) in zip(columns, how):
    with column:
        st.markdown(f"<div class='ca-option'><h3>{title}</h3><p>{body}</p></div>", unsafe_allow_html=True)

theme.footer()
