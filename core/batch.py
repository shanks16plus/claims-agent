"""Batch test: run test cases without the chat.

- run_pipeline: tools 1, 3, 4, 5 and 6 on every case, like a real claim (logged as channel "batch").
- run_comparison: only the damage assessment, once per model, to compare accuracy and cost.
"""
import csv
import io
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

from core import checklist, config, llm
from core.pipeline import assess_claim
from core.tools.assess_damage import assess_damage
from core.tools.estimate_cost import estimate_cost
from core.tools.file_claim import file_claim

RESULTS_DIR = config.RUNTIME / "batch_results"
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp")


# --- Loading test cases ------------------------------------------------------

def extract_zip(zip_bytes):
    """Unpack an uploaded zip. Returns (csv path, folder with the photos)."""
    config.RUNTIME.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="batch_upload_", dir=config.RUNTIME))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        archive.extractall(folder)
    csv_files = [p for p in folder.rglob("*.csv") if "__MACOSX" not in p.parts]
    if not csv_files:
        raise ValueError("The zip file has no CSV file in it.")
    return csv_files[0], folder


def _number(text):
    text = str(text or "").replace("€", "").replace(" ", "").strip()
    if text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _yes_no(text):
    text = str(text or "").strip().lower()
    if text in ("yes", "y", "true", "1", "ja"):
        return True
    if text in ("no", "n", "false", "0", "nee"):
        return False
    return None


def _true_parts(text):
    """'rear_bumper:minor;tail_light_left:severe' -> {'rear_bumper': 'minor', ...}. None when empty."""
    parts = {}
    for item in str(text or "").replace(",", ";").split(";"):
        if item.strip():
            part, _, severity = item.strip().partition(":")
            parts[part.strip()] = severity.strip() or None
    return parts or None


def load_cases(csv_path, photo_folder):
    """Read test cases and match photo names to files. Returns (cases, problems)."""
    photos_by_name = {p.name.lower(): p for p in Path(photo_folder).rglob("*")
                      if p.suffix.lower() in IMAGE_TYPES and "__MACOSX" not in p.parts}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    header = text.splitlines()[0] if text else ""
    delimiter = ";" if header.count(";") > header.count(",") else ","  # Dutch Excel saves with ;

    cases, problems = [], []
    for row in csv.DictReader(io.StringIO(text), delimiter=delimiter):
        case_id = (row.get("claim_id") or "").strip()
        if not case_id:
            continue
        if None in row:
            problems.append(f"{case_id}: skipped because the row has more columns than the header "
                            "(put the photo names in quotes)")
            continue
        names = [n.strip() for n in str(row.get("photo_filenames") or "").replace(",", ";").split(";") if n.strip()]
        photos = [{"slot": checklist.guess_slot(n), "name": n, "path": str(photos_by_name[n.lower()])}
                  for n in names if n.lower() in photos_by_name]
        missing = [n for n in names if n.lower() not in photos_by_name]
        if missing:
            problems.append(f"{case_id}: photo not found: {', '.join(missing)}")
        if not photos:
            problems.append(f"{case_id}: skipped because none of its photos were found")
            continue
        cases.append({
            "case_id": case_id,
            "photos": photos,
            "description": (row.get("description") or "").strip(),
            "policy_number": (row.get("policy_number") or "").strip(),
            "incident_date": (row.get("incident_date") or "").strip(),
            "true_cost": _number(row.get("true_repair_cost_eur")),
            "is_fraud": _yes_no(row.get("is_fraud")),
            "true_parts": _true_parts(row.get("true_parts")),
            "notes": (row.get("notes") or "").strip(),
        })
    return cases, problems


# --- Scoring -----------------------------------------------------------------

def _pct_error(estimate, true_cost):
    if not true_cost:
        return None
    return abs(estimate - true_cost) / true_cost


def _part_scores(predicted, truth):
    """F1 on which parts are damaged, and severity accuracy on the parts both agree on."""
    pred, true = set(predicted) - {"other"}, set(truth) - {"other"}
    if not pred and not true:
        return 1.0, None
    both = pred & true
    precision = len(both) / len(pred) if pred else 0.0
    recall = len(both) / len(true) if true else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    judged = [p for p in both if truth.get(p)]
    severity = sum(predicted[p] == truth[p] for p in judged) / len(judged) if judged else None
    return round(f1, 3), None if severity is None else round(severity, 3)


def _save(df, kind):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{kind}.csv"
    df.to_csv(path, index=False)
    return path


# --- Full pipeline batch -----------------------------------------------------

def run_pipeline(cases, progress=None):
    """Run tools 1, 3, 4, 5 and 6 on every case. Returns (results table, saved csv path)."""
    rows = []
    for number, case in enumerate(cases, start=1):
        claim = checklist.new_claim("batch")
        claim.update(policy_number=case["policy_number"], what_happened=case["description"],
                     incident_date=case["incident_date"], photos=case["photos"],
                     source_key=f"batch:{case['case_id']}")
        usage = llm.Usage()
        try:
            results = assess_claim(claim, usage)
            file_claim(claim, results, usage)
            rows.append(_pipeline_row(case, results, usage))
        except Exception as exc:  # one broken case shouldn't stop the whole batch
            rows.append({"case_id": case["case_id"], "error": str(exc)})
        if progress:
            progress(number, len(cases), case["case_id"])
    df = pd.DataFrame(rows)
    return df, _save(df, "pipeline")


def _pipeline_row(case, results, usage):
    estimate, fraud = results["estimate"], results["fraud"]
    decision, damage = results["decision"], results["damage"]
    flagged = fraud["risk"] in ("medium", "high")
    if case["is_fraud"] is None:
        fraud_outcome = ""
    elif case["is_fraud"]:
        fraud_outcome = "caught" if flagged else "missed"
    else:
        fraud_outcome = "false alarm" if flagged else "correct clear"
    error = _pct_error(estimate["gross_eur"], case["true_cost"])
    return {
        "case_id": case["case_id"],
        "policy_number": case["policy_number"],
        "estimate_eur": estimate["gross_eur"],
        "true_cost_eur": case["true_cost"],
        "abs_pct_error": None if error is None else round(error, 3),
        "within_20pct": None if error is None else error <= 0.20,
        "decision": decision["decision"],
        "payout_eur": decision["payout_eur"],
        "route_reasons": " | ".join(decision["reasons"]),
        "fraud_risk": fraud["risk"],
        "fraud_signals": " | ".join(s["code"] for s in fraud["signals"]),
        "is_fraud": case["is_fraud"],
        "fraud_outcome": fraud_outcome,
        "confidence": damage["confidence"],
        "parts_found": "; ".join(f"{p['part']}:{p['severity']}" for p in damage["damaged_parts"]),
        "seconds": results["processing_seconds"],
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "api_cost_eur": round(usage.cost_eur, 4),
        "error": damage.get("error") or fraud.get("error") or "",
        "notes": case["notes"],
    }


def pipeline_summary(df):
    ok = df[df["decision"].notna()] if "decision" in df else df.iloc[0:0]
    if not len(ok):
        return {"cases": len(df), "failed": len(df), "errors": df.get("error", pd.Series()).tolist()}
    priced = ok.dropna(subset=["abs_pct_error"])
    outcomes = ok["fraud_outcome"].value_counts()
    worst = priced.sort_values("abs_pct_error", ascending=False).head(5)
    return {
        "cases": len(df),
        "failed": len(df) - len(ok),
        "mape": round(priced["abs_pct_error"].mean(), 3) if len(priced) else None,
        "within_20pct_share": round(priced["within_20pct"].astype(float).mean(), 3) if len(priced) else None,
        "fraud_caught": int(outcomes.get("caught", 0)),
        "fraud_missed": int(outcomes.get("missed", 0)),
        "fraud_false_alarms": int(outcomes.get("false alarm", 0)),
        "auto_settled_share": round((ok["decision"] == "auto_settle").mean(), 3),
        "avg_seconds": round(ok["seconds"].mean(), 1),
        "avg_cost_eur": round(ok["api_cost_eur"].mean(), 4),
        "worst_misses": worst[["case_id", "estimate_eur", "true_cost_eur", "abs_pct_error", "notes"]]
        .to_dict("records"),
    }


# --- Model head-to-head --------------------------------------------------------

def _assess_with(case, model):
    usage = llm.Usage()
    started = time.time()
    damage = assess_damage(case["photos"], case["description"], usage, model=model)
    estimate = estimate_cost(damage["damaged_parts"], 0)
    return {"damage": damage, "estimate": estimate, "usage": usage, "seconds": round(time.time() - started, 1)}


def run_comparison(cases, models, progress=None):
    """Damage assessment only, once per model, same photos. Returns (results table, saved csv path)."""
    rows = []
    reference = models[0]
    for number, case in enumerate(cases, start=1):
        with ThreadPoolExecutor(max_workers=len(models)) as pool:
            jobs = {model: pool.submit(_assess_with, case, model) for model in models}
            outputs = {model: job.result() for model, job in jobs.items()}
        reference_damage = outputs[reference]["damage"]
        reference_parts = ({p["part"]: p["severity"] for p in reference_damage["damaged_parts"]}
                           if reference_damage["ok"] else None)
        for model in models:
            rows.append(_comparison_row(case, model, outputs[model],
                                        None if model == reference else reference_parts))
        if progress:
            progress(number, len(cases), case["case_id"])
    df = pd.DataFrame(rows)
    return df, _save(df, "comparison")


def _comparison_row(case, model, output, reference_parts):
    damage, estimate, usage = output["damage"], output["estimate"], output["usage"]
    predicted = {p["part"]: p["severity"] for p in damage["damaged_parts"]}
    f1 = severity = agreement = error = None
    if damage["ok"]:  # a failed call is counted as failed, not scored as a wrong answer
        if case["true_parts"]:
            f1, severity = _part_scores(predicted, case["true_parts"])
        if reference_parts is not None:
            agreement = _part_scores(predicted, reference_parts)[0]
        error = _pct_error(estimate["gross_eur"], case["true_cost"])
    return {
        "case_id": case["case_id"],
        "model": model,
        "model_name": config.COMPARISON_MODELS.get(model, model),
        "ok": damage["ok"],
        "error": damage.get("error", ""),
        "parts_found": "; ".join(f"{p}:{s}" for p, s in predicted.items()),
        "true_parts": "; ".join(f"{p}:{s}" for p, s in (case["true_parts"] or {}).items()),
        "parts_f1": f1,
        "severity_accuracy": severity,
        "agreement_with_reference": agreement,
        "estimate_eur": estimate["gross_eur"],
        "true_cost_eur": case["true_cost"],
        "abs_pct_error": None if error is None else round(error, 3),
        "within_20pct": None if error is None else error <= 0.20,
        "confidence": damage["confidence"],
        "json_retries": usage.json_retries,
        "seconds": output["seconds"],
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_eur": round(usage.cost_eur, 5),
    }


def comparison_summary(df):
    """One row per model: accuracy, speed and cost."""
    rows = []
    for model, group in df.groupby("model", sort=False):
        ok = group[group["ok"]]
        rows.append({
            "model": config.COMPARISON_MODELS.get(model, model),
            "cases": len(group),
            "failed": int((~group["ok"]).sum()),
            "json_retries": int(group["json_retries"].sum()),
            "parts_f1": ok["parts_f1"].mean(),
            "severity_accuracy": ok["severity_accuracy"].mean(),
            "mape": ok["abs_pct_error"].mean(),
            "within_20pct": ok["within_20pct"].dropna().astype(float).mean(),
            "agreement_with_reference": ok["agreement_with_reference"].mean(),
            "avg_confidence": ok["confidence"].mean(),
            "avg_seconds": group["seconds"].mean(),
            "cost_per_case_eur": group["cost_eur"].mean(),
            "cost_per_1000_claims_eur": group["cost_eur"].mean() * 1000,
        })
    return pd.DataFrame(rows).round(3)
