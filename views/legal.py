"""Privacy notice and terms of use for the prototype. Plain statements of what the code actually does."""
from core import config, provenance
from ui import theme
from ui.theme import band, show


def model_name(model_id):
    return config.COMPARISON_MODELS.get(model_id) or (model_id or "not set").split("/")[-1]


with band("hero-page", "legal"):
    theme.hero_media("canal_trees", even=True)
    theme.heading("Privacy and terms", "Privacy notice and terms of use", size="page-title")

with band("paper", "legal-body"), theme.lift("legal"), theme.card("legal"):
    show(f"""<div class='ca-legal'>
<p class='ca-small'>Last updated 25 September 2026. This page covers the {theme.APP_NAME} prototype, built by a
student team for the RSM AI Strategy Lab. It is not an insurance product.</p>

<h2>What this prototype is</h2>
<p>A demonstration of how car damage claims could be reported and checked with the help of AI models. The policies
in it are fictional, no insurance cover exists, and no money is paid. Please use the demo policies and test photos,
not your own personal details or a real claim.</p>

<h2>What we collect</h2>
<ul>
<li>What you type into the form or the chat: policy number, date, place and what happened.</li>
<li>Photos and documents you add.</li>
<li>For the insurer dashboard: timings, the number of messages and photo retakes, and the cost of the model calls.</li>
</ul>

<h2>Photos</h2>
<p>Before a photo is stored, we read three pieces of its metadata: the editing software, the camera make and model,
and the time it was taken, and we check whether the file says it was made with AI (Content Credentials or IPTC
metadata). We use these only to check whether a photo may have been edited or generated. We then save a copy
without any metadata, so location (GPS) data is never stored.</p>

<h2>How AI models are used</h2>
<p>Your text and photos are sent to AI models through OpenRouter:</p>
<ul>
<li>{model_name(config.MODEL_FOR["chat"])} runs the chat assistant and checks whether photos are usable.</li>
<li>{model_name(config.MODEL_FOR["assess_damage"])} assesses the damage in the photos.</li>
<li>{model_name(config.MODEL_FOR["fraud_review"])} checks whether the photos match the description.</li>
{"<li>Sightengine checks whether a photo looks AI-generated.</li>" if provenance.detector_configured() else ""}
</ul>
<p>The models give an assessment. They do not decide whether a claim is paid.</p>

<h2>Automated decisions</h2>
<p>A claim is settled automatically only when every rule in code is met: a valid policy, a low-risk check, a
confident damage assessment and an estimate below {theme.esc(f"€{config.AUTO_SETTLE_MAX_EUR:,}")}. No claim is
rejected automatically. Every claim that does not meet all the rules goes to a person, and you can ask for a person
at any time in the chat.</p>

<h2>Where data is kept, and for how long</h2>
<p>Claims are stored as local files on the computer or server running the prototype. They are kept for the course
and deleted when it ends. Ask the project team through the course and we will delete your data sooner.</p>

<h2>Terms of use</h2>
<ul>
<li>The prototype is provided as is, for teaching and testing. It may be changed or taken offline at any time.</li>
<li>Decisions and amounts shown are simulations. They are not offers, and prices are placeholders.</li>
<li>Don't upload photos of other people, or anything you don't have the right to share.</li>
<li>Photos on the site are from Unsplash and the hero video is from Mixkit, used under their licences.</li>
</ul>
</div>""")

theme.footer()
