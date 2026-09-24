"""Run the batch test from the terminal. Results are saved to data/runtime/batch_results/.

    python scripts/run_batch.py                      # full pipeline on data/test_cases.csv + data/test_photos/
    python scripts/run_batch.py --compare            # damage-assessment head-to-head, default models
    python scripts/run_batch.py --compare --models anthropic/claude-opus-5.5 moonshotai/kimi-k3
    python scripts/run_batch.py --compare --limit 10 # first 10 cases only (cheap first run)
    python scripts/run_batch.py --zip my_tests.zip   # test cases + photos in one zip
    python scripts/run_batch.py --compare --csv data/test_photos/unsplash/test_cases.csv
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402

from core import batch, config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compare", action="store_true", help="compare models on damage assessment only")
    parser.add_argument("--models", nargs="+", default=config.COMPARISON_DEFAULT,
                        help="model IDs; the first is the reference")
    parser.add_argument("--limit", type=int, help="only run the first N cases")
    parser.add_argument("--zip", help="zip file with test_cases.csv and the photos")
    parser.add_argument("--csv", help="test cases CSV (default data/test_cases.csv)")
    parser.add_argument("--photos", help="photo folder (default: the CSV's folder, or data/test_photos)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation question")
    args = parser.parse_args()

    if args.zip:
        csv_path, photo_folder = batch.extract_zip(Path(args.zip).read_bytes())
    elif args.csv:
        csv_path = Path(args.csv)
        photo_folder = Path(args.photos) if args.photos else csv_path.parent
    else:
        csv_path, photo_folder = config.DATA / "test_cases.csv", Path(args.photos or config.DATA / "test_photos")
    cases, problems = batch.load_cases(csv_path, photo_folder)
    for problem in problems:
        print(f"  ! {problem}")
    cases = cases[: args.limit] if args.limit else cases
    if not cases:
        sys.exit("No runnable test cases. Put photos in data/test_photos/ and list them in data/test_cases.csv.")

    calls = len(cases) * (len(args.models) if args.compare else 2)
    what = f"compare {', '.join(args.models)}" if args.compare else "run the full pipeline"
    print(f"\nAbout to {what} on {len(cases)} cases: about {calls} model calls.")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        sys.exit("Stopped. Nothing was spent.")

    def progress(done, total, case_id):
        print(f"  {done}/{total} {case_id}")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    if args.compare:
        df, path = batch.run_comparison(cases, args.models, progress)
        print("\n" + batch.comparison_summary(df).to_string(index=False))
    else:
        df, path = batch.run_pipeline(cases, progress)
        print("\n" + json.dumps(batch.pipeline_summary(df), indent=2, default=str))
    print(f"\nFull results: {path}")


if __name__ == "__main__":
    main()
