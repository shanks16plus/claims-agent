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

Opens at http://localhost:8501. The team password (`APP_PASSWORD`) only applies to the deployed link, not to local runs. In the claim form, "Demo: fill in a ready-made claim" loads a claim with photos, so no uploads are needed.

## The chat assistant

The Chat page is the claims assistant: a conversation on the left and, on the right, what the agent is doing (the claim checklist, every tool call and every guardrail), so an audience can watch it work. "Send ready-made photos" posts the demo photo sets into the chat, so a live demo needs no uploads.

The model decides what to ask and how to phrase it (`prompts/assistant_system.md`). Everything that matters is enforced in code (`core/agent.py`):
- It can only call five tools: `lookup_policy`, `check_photo_quality`, `record_answer`, `hand_over_to_human` and `file_claim`. The last one runs the fixed pipeline (assess, price, fraud check, decide, file).
- Answers only go into the checklist fields, and each value is checked: dates can't be in the future, and yes/no must be yes or no.
- The claim is filed only after the customer presses "Confirm and file" themselves.
- An injury, theft, a dispute, an upset customer or a request for a person hands the claim to a claims handler.
- After 25 customer messages a person takes over. After two messages in a row that don't move the claim forward, the app offers a person.
- Amounts of money are removed from replies until the claim is decided, and so are the prompt's own markers and tool names.

## Insurer dashboard

The Dashboard page (under Insurer in the top menu) reads the claims log. It shows:
- The share settled automatically, the share sent to a person, and the average time from filing to decision.
- How many claims are waiting for a handler, the time to check a claim, and the model cost per claim.
- Charts of the outcome by channel, fraud flags by reason and claims per day, each with a table view.
- Form and chat compared, and every claim with a link to its status page.

One filter row at the top (period and channels) applies to everything below it. Batch tests are left out unless you select them. The insurer pages are built for a laptop screen.

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

## Demo video

The home page shows a screen recording of a claim filed through the chat (`static/demo.mp4`). The current one uses the small-claim demo set (a scraped rear bumper, from a CC0 photo on Wikimedia Commons that still carries its camera metadata) and was settled on the spot: estimate €1,326.76, payout €1,076.76. To record a new one, start the app and run:

```bash
python scripts/record_demo.py --set small_clean   # needs Playwright (pip install playwright) and Google Chrome
```

It drives Chrome like a customer, with real model calls (a few cents), so the outcome is whatever the rules decide.

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
- **Variable estimates.** The same photos can get a different estimate on another run (we saw €826 and €1,327 for one claim), so the auto-settle limit and confidence threshold have to be set with that in mind.
- **Weak fraud checks.** The fraud signals flag claims for a person to look at; they prove nothing. Missing camera metadata is common in honest photos too (messaging apps strip it).
- **No claims-handler tools yet.** Routed claims wait in the log; there is no queue page to approve, change or reject them yet.
- **Local, temporary data.** Claims are stored in local files. On Streamlit Cloud they disappear when the app restarts.
- **No accounts.** One shared team password protects the deployed link; there are no customer logins.
- **Guardrail tests not run yet.** `data/guardrail_tests.csv` (17 messages) and `core/guardrails.py` are ready but haven't been run.

