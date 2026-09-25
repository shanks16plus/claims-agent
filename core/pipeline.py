"""Runs the back-end tools in order for one claim. Used by the form, the batch test and try_tools.
The chat assistant calls the same tools one by one instead."""
import time
from concurrent.futures import ThreadPoolExecutor

from core import checklist, storage
from core.tools.assess_damage import assess_damage
from core.tools.check_fraud import check_fraud
from core.tools.decide import decide
from core.tools.estimate_cost import estimate_cost
from core.tools.file_claim import file_claim
from core.tools.lookup_policy import lookup_policy


def _silent(stage):
    pass


def assess_claim(claim, usage, progress=_silent):
    """Tools 1, 3, 4, 5 and 6. Returns everything file_claim needs.
    progress(stage) is called as each stage starts: policy, models, price, decide (the form's loader uses it)."""
    started = time.time()
    claim["claim_id"] = claim["claim_id"] or storage.new_claim_id()
    source_key = claim["source_key"] or claim["claim_id"]
    photos = checklist.usable_photos(claim)

    progress("policy")
    policy = lookup_policy(claim["policy_number"], claim["incident_date"])
    progress("models")
    # The two Claude calls don't depend on each other, so run them at the same time.
    with ThreadPoolExecutor(max_workers=2) as pool:
        damage_job = pool.submit(assess_damage, photos, claim["what_happened"], usage)
        fraud_job = pool.submit(check_fraud, photos, claim["what_happened"], policy, source_key, usage)
        damage, fraud = damage_job.result(), fraud_job.result()

    progress("price")
    deductible = policy["deductible_eur"] if policy["found"] else 0
    estimate = estimate_cost(damage["damaged_parts"], deductible)

    progress("decide")
    decision = decide(policy, damage, estimate, fraud, claim["scope_flags"], claim["language"])

    return {"policy": policy, "damage": damage, "estimate": estimate, "fraud": fraud,
            "decision": decision, "processing_seconds": round(time.time() - started, 1)}


def process_claim(claim, usage, progress=_silent):
    """Assess, decide and file. Returns (results, filing)."""
    results = assess_claim(claim, usage, progress)
    progress("file")
    filing = file_claim(claim, results, usage)
    progress("done")
    return results, filing
