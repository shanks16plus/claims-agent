"""Step 1 check: run every tool on one sample claim and print what each returns.

    python scripts/try_tools.py                       # uses data/sample_claim/
    python scripts/try_tools.py path/to/photo_folder  # wide*, close*, plate* photos

Writes to a separate test database, so nothing shows up in the dashboard.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import checklist, config, llm, storage  # noqa: E402

storage.DB_PATH = config.RUNTIME / "try_tools" / "claims.db"

from core.tools import file_claim as file_claim_module  # noqa: E402
from core.tools.assess_damage import assess_damage  # noqa: E402
from core.tools.check_fraud import check_fraud  # noqa: E402
from core.tools.check_photo_quality import check_photo_quality  # noqa: E402
from core.tools.decide import decide  # noqa: E402
from core.tools.estimate_cost import estimate_cost  # noqa: E402
from core.tools.file_claim import file_claim  # noqa: E402
from core.tools.lookup_policy import lookup_policy  # noqa: E402

file_claim_module.CLAIMS_DIR = config.RUNTIME / "try_tools" / "claims"


def show(title, data):
    print(f"\n=== {title} ===")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else config.DATA / "sample_claim"
    photo_files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not photo_files:
        sys.exit(f"No photos in {folder}. Run: python scripts/make_test_assets.py")
    if not (config.OPENROUTER_API_KEY or config.ANTHROPIC_API_KEY):
        print("NOTE: no API key in .env, so the AI tools will report an error and "
              "the claim will be routed to a human. That's the intended fallback.")

    claim = checklist.new_claim("form")
    claim.update({
        "policy_number": "NL-100001",
        "what_happened": "I reversed into a bollard in a parking garage. The rear bumper is dented and scratched.",
        "incident_date": "2026-09-20",
        "incident_place": "Rotterdam, parking garage",
        "other_party_involved": False,
        "drivable": True,
        "confirmed": True,
        "source_key": "sample:try_tools",
    })
    usage = llm.Usage()

    show("1. lookup_policy", policy := lookup_policy(claim["policy_number"], claim["incident_date"]))

    for path in photo_files:
        slot = checklist.guess_slot(path.name)
        quality = check_photo_quality(path, slot, claim["language"], usage)
        show(f"2. check_photo_quality: {path.name} as {slot}", quality)
        claim["photos"].append({"slot": slot, "name": path.name, "path": str(path),
                                "usable": quality["usable"]})

    photos = checklist.usable_photos(claim)
    show("3. assess_damage", damage := assess_damage(photos, claim["what_happened"], usage))
    show("4. estimate_cost", estimate := estimate_cost(damage["damaged_parts"], policy["deductible_eur"]))
    fraud = check_fraud(photos, claim["what_happened"], policy, claim["source_key"], usage)
    show("5. check_fraud", {k: v for k, v in fraud.items() if k != "photo_hashes"})
    show("6. decide", decision := decide(policy, damage, estimate, fraud, claim["scope_flags"]))

    results = {"policy": policy, "damage": damage, "estimate": estimate, "fraud": fraud,
               "decision": decision, "processing_seconds": 0}
    show("7. file_claim", file_claim(claim, results, usage))

    print(f"\nClaude calls: {usage.calls} | tokens in/out: {usage.input_tokens}/{usage.output_tokens} "
          f"| cost: €{usage.cost_eur:.4f}")


if __name__ == "__main__":
    main()
