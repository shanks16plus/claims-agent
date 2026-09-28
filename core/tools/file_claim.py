"""Tool 7: save the claim and, when it is routed, build the adjuster file."""
import json
import time
from pathlib import Path

from core import checklist, config, images, storage
from core.tools.decide import ROUTE, money

CLAIMS_DIR = config.RUNTIME / "claims"
AI_SIGNALS = {"ai_content_credentials", "ai_detector_likely", "ai_detector_possible", "possible_manipulation"}


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
        name = Path(photo["path"]).name
        name = name if name.startswith(photo["slot"]) else f"{photo['slot']}_{name}"
        photo["path"] = str(images.save_clean_copy(photo["path"], folder / "photos" / name))
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
    detector = fraud.get("ai_detector") or {}
    if detector.get("configured"):
        scores = ", ".join(f"{name} {score:.0%}" for name, score in detector["scores"].items())
        lines += [f"AI-image detector (Sightengine): {scores or 'no score'}"]
    else:
        lines += ["AI-image detector: not switched on"]
    if any(s["code"] in AI_SIGNALS for s in fraud["signals"]):
        lines += ["To check for a SynthID watermark (images from Google's AI tools and other SynthID adopters), "
                  "upload the photo to the Gemini app and ask whether it was made with AI. There is no public "
                  "API for this check yet."]
    lines += ["", "## Photos", *[f"- {p['slot']}: {p['name']}" for p in claim["photos"]]]
    return "\n".join(lines) + "\n"


HANDOVER_MESSAGES = {
    "en": "A claims handler will take over your claim and contact you. They can see everything you have told us "
          "so far, so you won't need to repeat it.",
    "nl": "Een schadebehandelaar neemt uw claim over en neemt contact met u op. De behandelaar ziet alles wat u "
          "ons al hebt verteld, dus u hoeft het niet te herhalen.",
}


def file_handover(claim, reason, conversation, usage):
    """File a claim that a person takes over before it is complete (injury, theft, a request for a person,
    the message limit...). No assessment runs: the claims handler gets what was collected plus the chat."""
    claim["claim_id"] = claim["claim_id"] or storage.new_claim_id()
    claim["scope_flags"] = sorted(set(claim["scope_flags"]) | {reason})
    reason_label = checklist.SCOPE_FLAGS.get(reason, reason)
    claim["summary"] = checklist.plain_summary(claim)
    decision = {
        "decision": ROUTE, "payout_eur": None, "gross_eur": None, "checks": [],
        "reasons": [f"Handed over during the chat: {reason_label}"],
        "next_step": "Contact the customer personally. The assessment has not run yet.",
        "customer_message": HANDOVER_MESSAGES.get(claim.get("language"), HANDOVER_MESSAGES["en"]),
    }
    filed_at = storage.now()
    folder = CLAIMS_DIR / claim["claim_id"]
    folder.mkdir(parents=True, exist_ok=True)
    transcript = "\n".join(f"**{turn['role']}:** {turn['text']}" for turn in conversation if turn.get("text"))
    (folder / "adjuster_file.md").write_text(
        f"# Adjuster file: {claim['claim_id']}\nChannel: {claim['channel']} | Policy: {claim['policy_number']}\n\n"
        f"## Why it was routed\n- {reason_label} (handed over during the chat)\n\n"
        f"## Suggested next step\n{decision['next_step']}\n\n## What was collected\n{claim['summary']}\n\n"
        f"## Conversation\n{transcript}\n", encoding="utf-8")
    metrics = claim["metrics"]
    storage.save_claim({
        "claim_id": claim["claim_id"], "filed_at": filed_at, "decided_at": None, "channel": claim["channel"],
        "policy_number": claim["policy_number"], "status": "awaiting_adjuster", "decision": ROUTE,
        "estimate_eur": None, "payout_eur": None, "fraud_risk": None, "fraud_reasons": [], "confidence": None,
        "chat_turns": metrics.get("chat_turns", 0),
        "seconds_to_file": round(time.time() - metrics["started_at"], 1),
        "photo_retakes": metrics.get("photo_retakes", 0), "processing_seconds": 0,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
        "api_cost_eur": round(usage.cost_eur, 4),
        "details": {"claim": {k: v for k, v in claim.items() if k != "metrics"}, "policy": None, "damage": None,
                    "estimate": None, "fraud": None, "decision": decision,
                    "handover": {"reason": reason, "conversation": conversation}},
    })
    return {"filed": True, "claim_id": claim["claim_id"], "status": "awaiting_adjuster",
            "customer_message": decision["customer_message"]}
