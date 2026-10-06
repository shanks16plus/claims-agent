# Claims Agent

AI claims agent prototype for car damage claims. RSM Information Strategy, AI Strategy Lab (Track B).

**Governance split:** the AI does the talking, understanding, looking and judging. Plain code does the money and the rules: prices, deductibles, thresholds and the settle-or-route decision live in code (`core/tools/estimate_cost.py`, `core/tools/decide.py`, `core/config.py`). The system never rejects a claim on its own; anything that fails a rule goes to a human.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your API keys
```

| Setting | What it is |
|---|---|
| `OPENROUTER_API_KEY` | From openrouter.ai. All models run through it. Set a credit limit on the key. |
| `CLAUDE_MODEL` | Strong model for damage assessment and fraud review (`anthropic/claude-opus-5.5`) |
| `CLAUDE_MODEL_FAST` | Cheaper model for the photo checks (`anthropic/claude-haiku-4.5`) |
| `CHAT_MODEL` | The chat assistant (`google/gemini-3.7-flash`, chosen after the chat model comparison) |
| `ASSESS_MODEL` | Damage assessment (`moonshotai/kimi-k3`, chosen after the model comparison) |
| `ANTHROPIC_API_KEY` | Optional: only to call Claude directly at Anthropic (use model IDs without a "/") |

Business rules, fraud points and prices per model are in `core/config.py`. Part prices are in `data/parts_prices.csv` (placeholders for now).

## Run the app

```bash
streamlit run app.py
```

Opens at http://localhost:8501. The team password (`APP_PASSWORD`) only applies to the deployed link, not to local runs. To test, use the details and photos in `test_kit/` (see below).

## Test kit

`test_kit/` is what testers get: five scenario folders with photos (small claim, large claim, suspicious claim, an AI-generated photo, a photo with a hidden instruction) and `READ ME FIRST.txt` with the details to type in and what should happen. Zip it and share it. The app itself has no demo shortcuts: testers type and upload like a customer would. (The screen recorder uses a hidden `?demo=1` switch that brings back the ready-made demo claims.)

## The chat assistant

The Chat page is the claims assistant: a conversation on the left and, on the right, what the agent is doing (the claim checklist, every tool call and every guardrail), so an audience can watch it work.

The model decides what to ask and how to phrase it (`prompts/assistant_system.md`). Everything that matters is enforced in code (`core/agent.py`):
- It can only call five tools: `lookup_policy`, `check_photo_quality`, `record_answer`, `hand_over_to_human` and `file_claim`. The last one runs the fixed pipeline (assess, price, fraud check, decide, file).
- Answers only go into the checklist fields, and each value is checked: dates can't be in the future, and yes/no must be yes or no.
- The claim is filed only after the customer presses "Confirm and file" themselves.
- A theft, a dispute, an upset customer or a request for a person hands the claim to a claims handler. So does an injury, and that one is handled in code before the model sees the message (see When someone was hurt).
- The assistant says it is an AI in its first message, and the model is told to say so whenever it is asked.
- After 25 customer messages a person takes over. After two messages in a row that don't move the claim forward, the app offers a person.
- Amounts of money are removed from replies until the claim is decided, and so are the prompt's own markers and tool names.

## Saying where AI is used

Wherever AI does the work, the page says so, with one marker: a few words followed by "AI" in a filled block, alone beside a result or leading a short notice (`theme.ai_tag` and `theme.ai_note` in `ui/theme.py`). The notice links to the privacy page, which opens without the team password:
- **Home:** the second section is the workflow diagram: AI checks and assesses, fixed rules decide, a person takes everything else.
- **Form:** a notice at the top of the first step, "Checked by AI" beside every photo result, and a notice before the Send button.
- **Checking your claim:** the steps that are AI say so ("AI is assessing the damage").
- **Chat:** the header, the first message, the name above every reply and a line under the message box all say it is an AI assistant, not a person.
- **Status page:** a line under the decision says how it was made: by AI and fixed rules with no person involved, or by a claims handler. A claim that was decided automatically has a way to ask a claims handler to review it, with room to explain; the claim then goes back to the handlers.
- **Privacy page:** which models are used for what, how automatic decisions work, and what a customer can ask for.

The reasons are the EU AI Act (Article 50: people must be told when they deal with an AI system) and the GDPR (Articles 13 and 22: decisions made without a person). The prototype has not been assessed against either.

## When someone was hurt

Claims that involve an injury are for a claims handler, and the AI models are kept out of them (`core/screen.py`):
- A word list in English and Dutch runs on the customer's text before any model sees it. In the chat, a message that mentions an injury is withheld from the model and the chat is handed over. In the form, the story or the "Someone was injured" box sends the claim to a handler: no photo checks, no damage assessment and no fraud review by AI, and no model cost.
- The list catches the usual wording ("hurt her neck", "went to hospital", "gewond", "ziekenhuis") and skips "nobody was hurt". On 225 test sentences written to probe it, it caught all 70 plain statements that someone was hurt and about half of the unusual or misspelt ones, with 4 false alarms in 107 sentences where nobody was hurt. As a second layer, the chat model is told to hand over, and the fraud review reports `injury_mentioned`, which also sends the claim to a handler. In that case a model has read the text.

## Steadier estimates

The model only reports which parts are damaged and how badly. Repair or replace is a rule in code (`REPLACE_FROM` in `core/config.py`): parts the price table can't repair (lights, side and rear windows, the grille) are replaced, the windscreen and mirrors from moderate damage, body panels and bumpers only when severe. Before this rule the model flipped between repair and replace for the same bumper, which moved the estimate by €306.

When the first estimate lands within €500 of the €1,500 auto-settle limit (`EXTRA_LOOKS_MARGIN_EUR`), the photos are assessed twice more and the middle estimate and the middle confidence of the three are used. Claims further from the limit get one assessment, as before. The limit and the 80% confidence bar don't change.

```bash
python scripts/estimate_spread.py small_clean --runs 5    # the same photos, five times: estimates, confidence, cost
```

## Photos from the internet

The fraud review is told the make, model and year of the insured car and reads the number plate in the photos, without being told the registration. Code then compares the plate with the policy (`registration` in `data/policies.json`). A different car or plate counts as the existing "photos don't match" signal (3 points, goes to a person), so the fraud scoring is unchanged. On 28 September it caught 6 of the 7 internet photos that don't show the insured car; the miss was a close-up of a light where the car can't be seen.

```bash
python scripts/check_insured_car.py      # the demo sets and the 8 internet photos, fraud check only
```

What still gets through: a photo of the same model without a readable plate, and photos that were never online. A reverse image search (Google Cloud Vision web detection) would add a direct check but isn't built.

## AI-generated photos

The fraud check looks for AI-generated photos in three ways (`core/provenance.py`):
1. **Content Credentials (C2PA):** a signed record that tools like ChatGPT and Adobe Firefly attach to the images they make. Read with the official `c2pa-python` library. A photo that says it was made with AI adds 4 points, which is high risk, so it goes to a person.
2. **IPTC metadata:** the "digital source type" tag that Google and others write into generated images. Same result.
3. **AI-image detector (optional):** Sightengine's model judges the pixels. It catches screenshots and re-saved copies, which lose their metadata. A score of 90% or more adds 3 points (medium risk, goes to a person); 60% or more adds 1. To switch it on, create a free account at sightengine.com and add `SIGHTENGINE_API_USER` and `SIGHTENGINE_API_SECRET` to `.env` (or the Streamlit secrets).

The fraud model also looks for visible signs of editing or generation (a weak signal, 1 point). Google's SynthID watermark can't be checked automatically: there is no public API yet. When a claim has an AI-related flag, the adjuster file says how to check it by hand in the Gemini app.

Test photos: `data/guardrail_assets/ai_generated_c2pa.jpg` (Content Credentials signed with the C2PA project's public test certificate) and `ai_generated_iptc.jpg` (IPTC tag). Both are our own synthetic drawing, labelled as AI-made.

## Insurer dashboard

The Dashboard page (under Insurer in the top menu) reads the claims log. It shows:
- The share settled automatically, the share sent to a person, and the average time from filing to decision.
- How many claims are waiting for a handler, the time to check a claim, and the model cost per claim.
- Charts of the outcome by channel, fraud flags by reason and claims per day, each with a table view.
- Form and chat compared, and every claim with a link to its status page.

The claims table has a **Why** column (which rules sent a claim to a person), and under it a **Claim file**: pick a claim to see what the customer sent, every rule with its result, each fraud signal with what was found, the plate the AI read, and the damage and price. It is read from the claims log, so it works for every claim.

One filter row at the top (period and channels) applies to everything below it. Batch tests are left out unless you select them. The insurer pages are built for a laptop screen.

## Guardrail tests

```bash
python scripts/run_guardrails.py --runs 3        # the 19 messages in data/guardrail_tests.csv, three times (about €0.10)
python scripts/test_code_guardrails.py           # the code guardrails alone, with fake model replies (free)
```

The first sends each test message (off-topic, advice, amounts, prompt injection, a photo with a hidden instruction, injury, theft, asking for a person, an upset customer, other customers, Dutch) to a fresh chat in dry-run mode. On 28 September 2026 Gemini 3.7 Flash passed 17 of 17 in each of three runs, every time without a code guardrail stepping in. On 5 October, with two tests added ("am I talking to a person?" and an injury worded so the word list misses it), it passed 19 of 19: the plain injury message is handled by the code rule before the model sees it, and the other 18 by the model alone.

The second replaces the model with scripted replies, so it tests the code layer on its own. It catches amounts before a decision (€1,250, 1.250 euro, EUR 800, 900 EUR), the prompt's own markers and tool names, the 25-message limit, the offer of a person after two off-topic messages, unknown tools, future dates, and filing without the customer's button. Known gaps, on record in the script: amounts written in words or without a currency, the prompt retold in other words, and false statements (the model can say "your claim is filed" when it isn't; the code blocks the action, not the words).

## Chat model comparison

```bash
python scripts/compare_chat_models.py            # Gemini 3.7 Flash, GLM 5.3 Flash, MiMo-V2.6-Flash, Haiku 4.5
```

It plays the same customer through each model: the full claim with the demo photos, plus five guardrail probes (off-topic, prompt injection, a request for advice, an injury, Dutch). On 25 September 2026:

| Model | Full claim | Guardrails | Median reply | Cost per chat |
|---|---|---|---|---|
| Gemini 3.7 Flash (chosen) | 8/8 | 5/5 | 4.2 s | €0.030 |
| GLM 5.3 Flash | 8/8 | 5/5 | 4.2 s | €0.011 |
| MiMo-V2.6-Flash | 7/8 (never showed the confirm step) | 5/5 | 2.4 s | €0.006 |
| Claude Haiku 4.5 | 8/8 | 5/5 | 2.3 s | €0.068 |

Costs include the photo checks. The advice probe for GLM and Haiku was re-scored by reading the replies: the first version of the check counted "I can't say whether it's covered" as advice. Gemini 3.7 Flash also leads the public τ²-bench airline leaderboard for tool-calling agents (80.6% vs 67.0% for Haiku 4.5). GLM and MiMo wrote em dashes, which the reply check now removes.

## Demo videos

The home page shows three screen recordings, one per part of the product (`static/demo_<flow>.mp4`), recorded on 6 October 2026:
- **Chat** (1 min 59 s): a claim filed through the chat assistant, settled on the spot (estimate €1,021.24, payout €771.24).
- **Form** (1 min 1 s): the same kind of claim through the form, settled on the spot (estimate €1,021.24, payout €771.24).
- **Insurer dashboard** (33 s): the dashboard with those claims in it, ending on the Claim file of a large claim that went to a claims handler.

In both runs the model listed a light scuff next to the bumper. When it doesn't, the same claim prices at €520.30 (payout €270.30).

The claims use the small-claim demo set: a scraped rear bumper, from a CC0 photo on Wikimedia Commons that still carries its camera metadata. To record them again, start the app and run:

```bash
python scripts/record_demo.py --flow chat        # or form, or dashboard; needs Playwright and Google Chrome
```

The recorder drives Chrome like a person would, with real model calls (about €0.10 for the chat and €0.07 for the form), so the outcome is whatever the rules decide.

For slides, the chat run can also save stills of single parts of the screens (PNG, at twice the screen resolution) and `run.json`, the numbers of that claim read from the claims log. They go into a folder git ignores:

```bash
python scripts/record_demo.py --flow chat --stills data/runtime/deck_assets                    # the video and the stills
python scripts/record_demo.py --flow chat --set large --stills data/runtime/deck_assets/large_claim --no-video --parts status,file
python scripts/record_demo.py --flow stills --claim CLM-... --stills data/runtime/deck_assets  # a claim already in the log
```

## Deploying

The app runs on Streamlit Community Cloud, which applies a push by reloading changed files in place, without restarting. `fresh.py` makes that safe: before app.py imports our own packages, it drops them if any source file changed, so pages never run new code against old helpers. A sleeping app is rebuilt from scratch when it wakes, which resets the claims log to the seeded test runs.

## Look and feel

The look lives in `ui/`: `theme.css` (styles), `motion.js` (scroll animations with GSAP), `loader3d.js` (the three.js "checking your claim" screen) and `loaders.py` (the photo scan and the claim loader, which follows the real pipeline steps). Photos come from Unsplash, the hero video from Mixkit, and GSAP and three.js from jsDelivr, so the page needs internet for those. Without it the app still works, just without the photos and animation.

## Try the tools (step 1)

```bash
python scripts/make_test_assets.py   # synthetic sample photos, only needed once
python scripts/try_tools.py          # runs all seven tools on one sample claim
```

## Batch test

Put photos in `data/test_photos/` and list the cases in `data/test_cases.csv`:

| Column | Example |
|---|---|
| `claim_id` | `TC001` |
| `photo_filenames` | `tc001_wide.jpg;tc001_close.jpg;tc001_plate.jpg` (names with "wide" or "plate" fill those slots) |
| `description` | What the customer says happened |
| `policy_number`, `incident_date` | `NL-100001`, `2026-09-12` |
| `true_repair_cost_eur` | Optional: the real repair cost |
| `is_fraud` | Optional: `yes` / `no` |
| `true_parts` | Optional: `rear_bumper:moderate;tail_light_left:severe` (part names from `parts_prices.csv`) |
| `notes` | Anything |

```bash
python scripts/run_batch.py                      # full pipeline: estimate, fraud and decision per case
python scripts/run_batch.py --compare --limit 10 # Kimi K3 vs Opus 5.5 on 10 cases
python scripts/run_batch.py --compare --models anthropic/claude-opus-5.5 qwen/qwen3.8-flash moonshotai/kimi-k3
```

Every run shows how many model calls it will make and asks before spending anything. Results are saved in `data/runtime/batch_results/`.

The comparison scores each model on **parts found** (F1 against `true_parts`), **severity accuracy**, **cost error** against `true_repair_cost_eur`, and **cost per claim**. Without `true_parts` it reports each model's agreement with the first model instead. Cost error also depends on the price table, so it only becomes meaningful once `parts_prices.csv` has real prices.

## Prompts

Every prompt sent to a model is a file in `prompts/`.

## Limitations

What the prototype does not do:
- **No real insurance.** Policies are fictional, no money is paid, and part prices are placeholders until sourced Dutch figures are in.
- **One kind of claim.** Car damage under an existing policy only. Injury, theft, disputes and total losses go to a person.
- **Photos only.** Damage is judged from photos, so hidden damage (behind panels, mechanical) can't be seen. The model says when it suspects it.
- **Variable estimates.** The same photos can still get a different estimate on another run: the model lists a light scuff on the next panel about two times in three, so the small demo claim prices at €520 or €1,021. Near the limit, three assessments keep the decision steady (see Steadier estimates). Confidence also varies (0.75 to 0.90 for the same photos), so a claim just above the 80% bar can occasionally go to a person.
- **Weak fraud checks.** The fraud signals flag claims for a person to look at; they prove nothing. Missing camera metadata is common in honest photos too (messaging apps strip it).
- **AI photos are only partly caught.** Content Credentials and metadata are lost in screenshots and re-saves; the optional detector is the backstop but can be wrong both ways; SynthID can only be checked by hand.
- **No claims-handler tools yet.** Routed claims wait in the log. A handler can read the full claim file on the dashboard, but there is no queue page to approve, change or reject a claim yet. A customer's request to review an automatic decision puts the claim back in the log as waiting for a handler.
- **Local, temporary data.** Claims are stored in local files. On Streamlit Cloud they disappear when the app restarts.
- **No accounts.** One shared team password protects the deployed link; there are no customer logins.
- **Guardrails tested on single messages only.** Each test is one message at the start of a chat; attacks in the middle of a claim or spread over several messages aren't tested. See the known gaps under Guardrail tests.

