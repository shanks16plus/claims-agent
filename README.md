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
| `CLAUDE_MODEL_FAST` | Cheaper model for the chat and photo checks (`anthropic/claude-haiku-4.5`) |
| `ASSESS_MODEL` | Damage assessment (`moonshotai/kimi-k3`, chosen after the model comparison) |
| `ANTHROPIC_API_KEY` | Optional: only to call Claude directly at Anthropic (use model IDs without a "/") |

Business rules, fraud points and prices per model are in `core/config.py`. Part prices are in `data/parts_prices.csv` (placeholders for now).

## Run the app

```bash
streamlit run app.py
```

Opens at http://localhost:8501. The team password (`APP_PASSWORD`) only applies to the deployed link, not to local runs. In the claim form, "Demo: fill in a ready-made claim" loads a claim with photos, so no uploads are needed.

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
