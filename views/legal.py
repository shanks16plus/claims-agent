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
<p class='ca-small'>Last updated 5 October 2026. This page covers the {theme.APP_NAME} prototype, built by a
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

<h2>How AI is used</h2>
<p>Every page says where AI does the work. The chat assistant is an AI system, not a person. Your text and photos
are sent to these AI models:</p>
<ul>
<li>{model_name(config.MODEL_FOR["chat"])} runs the chat assistant.</li>
<li>{model_name(config.MODEL_FOR["photo_quality"])} checks whether each photo is clear enough to use.</li>
<li>{model_name(config.MODEL_FOR["assess_damage"])} assesses the damage in the photos.</li>
<li>{model_name(config.MODEL_FOR["fraud_review"])} checks whether the photos match the description and show the car on the policy.</li>
{"<li>Sightengine checks whether a photo looks AI-generated.</li>" if provenance.detector_configured() else ""}
</ul>
<p>The models give an assessment. They do not decide whether a claim is paid, and AI can make mistakes.</p>

<h2>When someone was hurt</h2>
<p>If you tick that someone was injured, or your description says so, a claims handler handles the claim. Your
description is not sent to the AI models and your photos are not assessed by AI. In the chat, a message that says
someone was hurt is not sent to the AI model, and the chat stops there. We find these claims with a word list in
English and Dutch, which can miss unusual wording. If an AI model still comes across an injury, the claim goes to
a claims handler as well.</p>

<h2>Automated decisions</h2>
<p>Small, clear claims are decided automatically, and no person looks at them. A claim is settled automatically
only when it passes every fixed check. The main ones: a valid policy that covers the damage, a low result on the
risk check, an AI damage assessment that is at least {round(config.MIN_CONFIDENCE_AUTO * 100)}% sure, every damaged
part in our price list, and an estimate below {theme.esc(f"€{config.AUTO_SETTLE_MAX_EUR:,}")} that is not close to
the value of the car. The result is a payment, or no payment when the repair costs less than your deductible.
The rules never reject a claim: a claim that fails any check goes to a claims handler, who decides.</p>

<h2>What you can ask for</h2>
<ul>
<li>If your claim was decided automatically, you can ask for a person to review it. You can also give your side
and tell us you disagree. Open your claim status page and choose "Do you disagree, or do you want to explain
something?".</li>
<li>In the chat, you can ask for a claims handler at any point, in words or with the button under the chat.
The chat then stops and the claims handler contacts you.</li>
<li>If you have a complaint about how we use AI, tell the project team through the course. We will explain how your
claim was handled.</li>
</ul>
<p>The rules behind this are the EU AI Act (Article 50), which asks that people are told when they deal with an AI
system, and the GDPR (Articles 13 and 22), which covers decisions made without a person. This prototype is a
student project. Nobody has assessed it against these rules.</p>

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
