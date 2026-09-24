"""Tool 7: save the claim and, when it is routed, build the adjuster file."""
import json
import time

from core import checklist, config, images, storage
from core.tools.decide import ROUTE, money

CLAIMS_DIR = config.RUNTIME / "claims"


def file_claim(claim, results, usage):
    """`results` holds policy, damage, estimate, fraud, decision and processing_seconds."""
    if claim["channel"] != "batch":
        missing = checklist.missing_items(claim)
        if missing:
            return {"filed": False, "error": "The checklist is not complete.", "missing": missing}
        if not claim["confirmed"]:
            return {"filed": False, "error": "The customer has not confirmed the summary yet."}

    decision = results["decision"]
    routed = decision["decision"] == ROUTE
    claim["claim_id"] = claim["claim_id"] or storage.new_claim_id()
    claim["summary"] = claim.get("summary") or checklist.plain_summary(claim)
    filed_at = storage.now()

    if claim["channel"] == "batch":
        status = "batch_test"
    else:
        status = "awaiting_adjuster" if routed else "settled"
        _save_files(claim, results, routed)

    fraud = {k: v for k, v in results["fraud"].items() if k != "photo_hashes"}
    details = {
        "claim": {k: v for k, v in claim.items() if k != "metrics"},
        "policy": results["policy"],
        "damage": results["damage"],
        "estimate": results["estimate"],
        "fraud": fraud,
        "decision": decision,
    }
    metrics = claim["metrics"]
    storage.save_claim({
        "claim_id": claim["claim_id"],
        "filed_at": filed_at,
        "decided_at": None if routed else filed_at,
        "channel": claim["channel"],
        "policy_number": claim["policy_number"],
        "status": status,
        "decision": decision["decision"],
        "estimate_eur": results["estimate"]["gross_eur"],
        "payout_eur": decision["payout_eur"],
        "fraud_risk": fraud["risk"],
        "fraud_reasons": [s["code"] for s in fraud["signals"]],
        "confidence": results["damage"]["confidence"],
        "chat_turns": metrics.get("chat_turns", 0),
        "seconds_to_file": None if claim["channel"] == "batch" else round(time.time() - metrics["started_at"], 1),
        "photo_retakes": metrics.get("photo_retakes", 0),
        "processing_seconds": results["processing_seconds"],
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "api_cost_eur": round(usage.cost_eur, 4),
        "details": details,
    })
    storage.save_photo_hashes(claim["claim_id"], claim["source_key"] or claim["claim_id"],
                              results["fraud"]["photo_hashes"])
    return {"filed": True, "claim_id": claim["claim_id"], "status": status}


def _save_files(claim, results, routed):
    """Copy the photos (without metadata) into the claim folder, plus claim.json and the adjuster file."""
    folder = CLAIMS_DIR / claim["claim_id"]
    for photo in claim["photos"]:
        photo["path"] = str(images.save_clean_copy(photo["path"], folder / "photos" / f"{photo['slot']}_{photo['name']}"))
        photo.pop("metadata", None)
    (folder / "claim.json").write_text(json.dumps(
        {"claim": {k: v for k, v in claim.items() if k != "metrics"},
         **{k: v for k, v in results.items() if k != "fraud"},
         "fraud": {k: v for k, v in results["fraud"].items() if k != "photo_hashes"}},
        indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if routed:
        (folder / "adjuster_file.md").write_text(adjuster_file(claim, results), encoding="utf-8")


def adjuster_file(claim, results):
    policy, damage, estimate = results["policy"], results["damage"], results["estimate"]
    fraud, decision = results["fraud"], results["decision"]
    lines = [
        f"# Adjuster file: {claim['claim_id']}",
        f"Channel: {claim['channel']} | Policy: {claim['policy_number']}",
        "",
        "## Why it was routed",
        *[f"- {reason}" for reason in decision["reasons"]],
        "",
        "## Suggested next step",
        decision["next_step"],
        "",
        "## Claim summary",
        claim["summary"],
        "",
        "## Policy",
    ]
    if policy.get("found"):
        lines += [f"{policy['vehicle']} | coverage {policy['coverage_type']} | deductible "
                  f"{money(policy['deductible_eur'])} | active: {policy['active']} | since {policy['start_date']}"]
    else:
        lines += ["Policy not found."]

    lines += ["", "## Damage", f"Confidence {damage['confidence']:.2f}: {damage['confidence_reason']}"]
    if damage.get("hidden_damage_risk"):
        lines += [f"Hidden damage risk: {damage['hidden_damage_risk']}"]
    lines += ["", "| Part | Severity | Action | Mentioned by customer | Evidence |", "|---|---|---|---|---|"]
    lines += [f"| {p['part']} | {p['severity']} | {p['action']} | {'yes' if p['mentioned_by_customer'] else 'no'} "
              f"| {p['evidence']} |" for p in damage["damaged_parts"]]

    lines += ["", "## Cost breakdown", "| Part | Action | Parts | Paint | Labour | Total |", "|---|---|---|---|---|---|"]
    lines += [f"| {l['part']} | {l['action']} | {money(l['parts_eur'])} | {money(l['paint_eur'])} | "
              f"{money(l['labour_eur'])} | {money(l['line_total_eur'])} |" for l in estimate["lines"]]
    lines += [f"Subtotal {money(estimate['subtotal_ex_vat_eur'])} + VAT {money(estimate['vat_eur'])} = "
              f"**{money(estimate['gross_eur'])}**, deductible {money(estimate['deductible_eur'])}"]
    if estimate["uses_placeholder_prices"]:
        lines += ["_Prices are placeholders, not sourced figures._"]
    if estimate["unpriced_parts"]:
        lines += [f"Not priced: {'; '.join(estimate['unpriced_parts'])}"]

    lines += ["", f"## Fraud check: {fraud['risk']} risk ({fraud['points']} points)"]
    lines += [f"- {s['detail']} (+{s['points']})" for s in fraud["signals"]] or ["- No signals"]
    lines += ["", "## Photos", *[f"- {p['slot']}: {p['name']}" for p in claim["photos"]]]
    return "\n".join(lines) + "\n"
