"""Does the fraud check notice when the photos don't show the insured car? Runs only the fraud check (one
fraud review call per case, nothing filed) on photo sets filed against a chosen policy.

    python scripts/check_insured_car.py                      # the standard set below
    python scripts/check_insured_car.py large:NL-100001      # one photo set on one policy

A photo set is a demo set in data/demo_photos/ or a case from data/test_photos/unsplash/ (U1 to U8).
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import llm  # noqa: E402
from core.tools.check_fraud import check_fraud  # noqa: E402
from core.tools.lookup_policy import lookup_policy  # noqa: E402
from estimate_spread import load  # noqa: E402

# (photo set, policy, whether the photos show the insured car)
STANDARD = [
    ("small_clean", "NL-100001", True),     # the Škoda Roomster on its own policy
    ("large", "NL-100002", True),           # the VW Tiguan on its own policy
    ("large", "NL-100001", False),          # the VW Tiguan filed on the Škoda policy
    ("suspicious", "NL-100003", False),     # an old blue saloon on a Peugeot 208 policy
    *[(f"U{n}", None, None) for n in range(1, 9)],   # internet photos, on the policy in their test case
]


def run(case, policy_number):
    photos, description, case_policy = load(case)
    policy = lookup_policy(policy_number or case_policy, None)
    usage = llm.Usage()
    fraud = check_fraud(photos, description, policy, source_key=f"insured-car-test-{case}", usage=usage)
    return policy, fraud, usage.cost_eur


def main():
    cases = [(c.split(":")[0], c.split(":")[1] if ":" in c else None, None) for c in sys.argv[1:]] or STANDARD
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda c: run(c[0], c[1]), cases))

    caught_total, cost_total = 0, 0.0
    for (case, _, expected), (policy, fraud, cost) in zip(cases, results):
        review = fraud["review"] or {}
        car_signal = [s for s in fraud["signals"] if s["code"] == "story_photo_mismatch"
                      and ("insured" in s["detail"] or "registration" in s["detail"])]
        caught = bool(car_signal) or review.get("insured_car") == "different"
        caught_total += caught
        cost_total += cost
        verdict = "NOT THE INSURED CAR" if caught else "insured car / can't tell"
        if expected is None:
            note = ""
        else:
            note = "  (as expected)" if caught != expected else "  <-- not what we expected"
        print(f"{case:<11} on {policy['policy_number']} ({policy['vehicle']}, {policy['registration']})")
        print(f"            {verdict}{note}: model says {review.get('insured_car')}, plate read "
              f"'{review.get('plate_in_photos', '')}'. Risk {fraud['risk']}: {[s['code'] for s in fraud['signals']]}")
        for signal in car_signal:
            print(f"            {signal['detail'][:260]}")
    print(f"\nNot the insured car: {caught_total} of {len(cases)}. Cost €{cost_total:.3f} "
          f"(€{cost_total / len(cases):.4f} per fraud check).")


if __name__ == "__main__":
    main()
