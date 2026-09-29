"""Assess the same photos several times and show how much the estimate moves.

    python scripts/estimate_spread.py small_clean --runs 5     # a demo set in data/demo_photos/
    python scripts/estimate_spread.py U1 --runs 5              # a case from data/test_photos/unsplash/

Only the damage assessment and the price run (no fraud check, nothing filed), so each run costs one assessment
call. For each run it prints the parts found, the estimate and the confidence, and whether price and confidence
alone would allow paying on the spot (the fraud check and policy rules can still send a claim to a person).
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import batch, checklist, config, llm  # noqa: E402
from core.pipeline import assess_and_price  # noqa: E402
from core.tools.lookup_policy import lookup_policy  # noqa: E402

UNSPLASH = config.DATA / "test_photos" / "unsplash"


def load(name):
    folder = config.DATA / "demo_photos" / name
    if folder.is_dir():
        claim = json.loads((folder / "claim.json").read_text())
        photos = [{"slot": checklist.guess_slot(p.name), "name": p.name, "path": str(p)}
                  for p in sorted(folder.glob("*.jpg"))]
        return photos, claim["what_happened"], claim["policy_number"]
    cases, _ = batch.load_cases(UNSPLASH / "test_cases.csv", UNSPLASH)
    case = next(c for c in cases if c["case_id"].lower() == name.lower())
    return case["photos"], case["description"], case["policy_number"]


def one_run(photos, description, deductible):
    usage = llm.Usage()
    damage, estimate = assess_and_price(photos, description, deductible, usage)
    return damage, estimate, usage.cost_eur


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", help="a demo set (small_clean, large, suspicious) or a case id (U1 to U8)")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    photos, description, policy_number = load(args.case)
    deductible = lookup_policy(policy_number, None)["deductible_eur"]
    print(f"{args.case}: {len(photos)} photo(s), {args.runs} runs on {config.MODEL_FOR['assess_damage']}\n")

    with ThreadPoolExecutor(max_workers=args.runs) as pool:
        results = list(pool.map(lambda _: one_run(photos, description, deductible), range(args.runs)))

    for number, (damage, estimate, cost) in enumerate(results, start=1):
        parts = ", ".join(f"{p['part']} {p['severity']} {p['action']}" for p in damage["damaged_parts"])
        pay = estimate["gross_eur"] < config.AUTO_SETTLE_MAX_EUR and damage["confidence"] >= config.MIN_CONFIDENCE_AUTO
        looks = damage.get("looks")
        extra = f"  (middle of {len(looks)} looks: {', '.join(f'€{e:,.2f}' for e in looks)})" if looks else ""
        print(f"Run {number}: €{estimate['gross_eur']:>9,.2f}  confidence {damage['confidence']:.2f}  "
              f"{'could pay on the spot' if pay else 'to a person'}  cost €{cost:.4f}{extra}")
        print(f"        {parts}")

    estimates = [estimate["gross_eur"] for _, estimate, _ in results]
    costs = [cost for *_, cost in results]
    print(f"\nEstimates €{min(estimates):,.2f} to €{max(estimates):,.2f} (spread €{max(estimates) - min(estimates):,.2f}). "
          f"{sum(e < config.AUTO_SETTLE_MAX_EUR for e in estimates)} of {len(estimates)} below the "
          f"€{config.AUTO_SETTLE_MAX_EUR:,} limit. Cost €{sum(costs):.3f} in total, €{sum(costs) / len(costs):.4f} per run.")


if __name__ == "__main__":
    main()
