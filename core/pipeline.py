"""Runs the back-end tools in order for one claim. Used by the form, the batch test and try_tools.
The chat assistant calls the same tools one by one instead."""
import time
from concurrent.futures import ThreadPoolExecutor

from core import checklist, config, storage
from core.tools.assess_damage import assess_damage
from core.tools.check_fraud import check_fraud
from core.tools.decide import decide
from core.tools.estimate_cost import estimate_cost
from core.tools.file_claim import file_claim
from core.tools.lookup_policy import lookup_policy


def _silent(stage):
    pass


def assess_and_price(photos, description, deductible, usage):
    """The damage assessment and its price. Returns (damage, estimate).

    When the first estimate lands within EXTRA_LOOKS_MARGIN_EUR of the auto-settle limit, the photos are assessed
    twice more and the middle of the three is used: the parts and price of the middle estimate, and the middle
    confidence. A claim near the limit then gets the same decision run after run. The limit and the confidence bar
    themselves don't change."""
    damage = assess_damage(photos, description, usage)
    estimate = estimate_cost(damage["damaged_parts"], deductible)
    if not damage["ok"] or abs(estimate["gross_eur"] - config.AUTO_SETTLE_MAX_EUR) > config.EXTRA_LOOKS_MARGIN_EUR:
        return damage, estimate

    with ThreadPoolExecutor(max_workers=2) as pool:
        extra = list(pool.map(lambda _: assess_damage(photos, description, usage), range(2)))
    if not all(look["ok"] for look in extra):
        damage["looks_note"] = "A second look failed, so the first assessment is used."
        return damage, estimate
    looks = sorted(((d, estimate_cost(d["damaged_parts"], deductible)) for d in [damage, *extra]),
                   key=lambda pair: pair[1]["gross_eur"])
    middle_damage, middle_estimate = looks[1]
    confidences = sorted(d["confidence"] for d, _ in looks)
    middle_damage = {**middle_damage, "confidence": confidences[1],
                     "looks": [e["gross_eur"] for _, e in looks], "look_confidences": confidences}
    return middle_damage, middle_estimate


def assess_claim(claim, usage, progress=_silent):
    """Tools 1, 3, 4, 5 and 6. Returns everything file_claim needs.
    progress(stage) is called as each stage starts: policy, models, price, decide (the form's loader uses it)."""
    started = time.time()
    claim["claim_id"] = claim["claim_id"] or storage.new_claim_id()
    source_key = claim["source_key"] or claim["claim_id"]
    photos = checklist.usable_photos(claim)

    progress("policy")
    policy = lookup_policy(claim["policy_number"], claim["incident_date"])
    deductible = policy["deductible_eur"] if policy["found"] else 0
    progress("models")
    # The damage assessment and the fraud check don't depend on each other, so run them at the same time.
    with ThreadPoolExecutor(max_workers=2) as pool:
        damage_job = pool.submit(assess_and_price, photos, claim["what_happened"], deductible, usage)
        fraud_job = pool.submit(check_fraud, photos, claim["what_happened"], policy, source_key, usage)
        (damage, estimate), fraud = damage_job.result(), fraud_job.result()

    progress("price")

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
