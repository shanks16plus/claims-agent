"""Run the guardrail tests in data/guardrail_tests.csv against the chat assistant and print a report.

    python scripts/run_guardrails.py             # one run
    python scripts/run_guardrails.py --runs 3    # three runs, to see how steady the model is

Each message goes to a fresh chat in dry-run mode (nothing is filed). Every test gets two verdicts:
passed (what the customer saw) and model alone (passed without a code guardrail stepping in).
Results are saved to data/runtime/guardrail_results/, one CSV per run.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, guardrails  # noqa: E402


def report(df):
    for row in df.to_dict("records"):
        verdict = "PASS" if row["passed"] else "FAIL"
        helped = "" if row["model_alone"] or not row["passed"] else "  (code guardrail stepped in)"
        print(f"{row['test_id']}  {verdict}  {row['category']:<18} expected {row['expected']}{helped}")
        print(f"     reply: {str(row['reply'])[:150].replace(chr(10), ' ')}")
        extras = [f"handover: {row['handover']}" if row.get("handover") else "",
                  f"guardrails: {row['guardrails_fired']}" if row.get("guardrails_fired") else "",
                  f"tools: {row['tools']}" if row.get("tools") else ""]
        if any(extras):
            print("     " + " | ".join(e for e in extras if e))
    passed, alone = int(df["passed"].sum()), int(df["model_alone"].sum())
    print(f"\nPassed: {passed}/{len(df)}. The model alone: {alone}/{len(df)}. "
          f"Code guardrails stepped in on {passed - alone}. Cost €{df['cost_eur'].sum():.3f}.")
    return passed, alone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    tests = guardrails.load_tests()
    print(f"Running {len(tests)} guardrail tests on {config.MODEL_FOR['chat']}, {args.runs} run(s)\n")

    def progress(done, total, test_id):
        print(f"  {done}/{total} {test_id}", flush=True)

    runs = []
    for number in range(1, args.runs + 1):
        print(f"--- Run {number} ---")
        df = guardrails.run_all(tests, progress)
        print()
        runs.append((df, *report(df)))
        print()

    if len(runs) > 1:
        print("--- All runs ---")
        for number, (df, passed, alone) in enumerate(runs, start=1):
            print(f"Run {number}: passed {passed}/{len(df)}, the model alone {alone}/{len(df)}, "
                  f"cost €{df['cost_eur'].sum():.3f}")
        for test in tests:
            results = [bool(df.loc[df["test_id"] == test["test_id"], "passed"].iloc[0]) for df, *_ in runs]
            if not all(results):
                print(f"{test['test_id']} passed {sum(results)} of {len(results)} runs")


if __name__ == "__main__":
    main()
