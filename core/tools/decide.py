"""Tool 6: settle automatically or route to a human. Plain code, no AI.
The system never rejects a claim: anything that fails a rule goes to a person."""
from core import checklist, config

AUTO_SETTLE, ROUTE = "auto_settle", "route_to_human"

NEXT_STEPS = {
    "Policy found": "Verify the policy number with the customer.",
    "Policy active": "Check the policy status and payment history.",
    "Own damage covered": "Confirm coverage: the policy does not list own-damage cover.",
    "Incident date within policy": "Verify the incident date with the customer.",
    "Damage assessment completed": "Assess the photos manually.",
    "Damage found in photos": "Check the photos: the AI found no damage.",
    "Fraud check completed": "Complete the fraud review manually.",
    "Fraud risk low": "Review the fraud signals before paying; consider asking for the original photos or an inspection.",
    "Model confidence high": "Check the damage assessment; consider a garage quote or an inspection.",
    "All parts priced": "Price the parts that are not in the price table.",
    "Estimate below auto-settle limit": "Review the estimate; consider a garage quote or an inspection.",
    "Not a possible total loss": "Arrange a total-loss valuation.",
    "No out-of-scope situation": "Contact the customer personally.",
}

MESSAGES = {
    "en": {
        "paid": ("Your claim is approved. The repair estimate is {gross}, and after your {deductible} "
                 "deductible we will pay {payout}. You'll receive a confirmation with the payment details."),
        "below_deductible": ("Your claim is registered. The estimated repair cost ({gross}) is below your "
                             "deductible of {deductible}, so there is no payment on this claim. If a garage "
                             "quotes a higher amount, you can send us the quote."),
        "routed": ("Your claim has been filed and passed to a claims adjuster, who already has your photos "
                   "and details. The adjuster will contact you about the next steps. This is not a "
                   "rejection: a person just needs to review your claim."),
    },
    "nl": {
        "paid": ("Uw schade is goedgekeurd. De geschatte reparatiekosten zijn {gross}. Na aftrek van uw eigen "
                 "risico van {deductible} betalen wij {payout} uit. U ontvangt een bevestiging met de "
                 "betalingsgegevens."),
        "below_deductible": ("Uw schade is geregistreerd. De geschatte reparatiekosten ({gross}) liggen onder "
                             "uw eigen risico van {deductible}, dus er volgt geen uitkering op deze claim. "
                             "Heeft een garage een hogere offerte gemaakt? Stuur ons die offerte dan toe."),
        "routed": ("Uw schademelding is ingediend en doorgestuurd naar een schadebehandelaar, die uw foto's "
                   "en gegevens al heeft. De behandelaar neemt contact met u op over de volgende stappen. "
                   "Dit is geen afwijzing: een medewerker bekijkt uw claim alleen persoonlijk."),
    },
}


def money(amount, language="en"):
    text = f"€{amount:,.2f}"
    if language == "nl":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def decide(policy, damage, estimate, fraud, scope_flags=(), language="en"):
    checks = []

    def check(rule, passed, detail=""):
        checks.append({"rule": rule, "passed": bool(passed), "detail": detail})

    gross = estimate["gross_eur"]
    check("Policy found", policy.get("found"), policy.get("policy_number", ""))
    if policy.get("found"):
        check("Policy active", policy["active"])
        check("Own damage covered", policy["own_damage_covered"], f"Coverage: {policy['coverage_type']}")
        bad_dates = [i["detail"] for i in policy["date_issues"]
                     if i["code"] in ("incident_before_policy_start", "incident_in_future", "invalid_date")]
        check("Incident date within policy", not bad_dates, "; ".join(bad_dates))
    check("Damage assessment completed", damage.get("ok"), damage.get("error", ""))
    if damage.get("ok"):
        check("Damage found in photos", damage["damaged_parts"])
    check("Fraud check completed", fraud.get("complete"), fraud.get("error") or "")
    check("Fraud risk low", fraud["risk"] == "low", f"Risk: {fraud['risk']}")
    check("Model confidence high", damage.get("confidence", 0) >= config.MIN_CONFIDENCE_AUTO,
          f"{damage.get('confidence', 0):.2f} (needs {config.MIN_CONFIDENCE_AUTO:.2f})")
    check("All parts priced", not estimate["unpriced_parts"], "; ".join(estimate["unpriced_parts"]))
    check("Estimate below auto-settle limit", gross < config.AUTO_SETTLE_MAX_EUR,
          f"{money(gross)} (limit {money(config.AUTO_SETTLE_MAX_EUR)})")
    if policy.get("found"):
        limit = config.TOTAL_LOSS_SHARE * policy["vehicle_value_eur"]
        check("Not a possible total loss", gross <= limit,
              f"{money(gross)} vs {config.TOTAL_LOSS_SHARE:.0%} of vehicle value = {money(limit)}")
    check("No out-of-scope situation", not scope_flags,
          "; ".join(checklist.SCOPE_FLAGS.get(flag, flag) for flag in scope_flags))

    failed = [c for c in checks if not c["passed"]]
    texts = MESSAGES.get(language, MESSAGES["en"])
    amounts = {"gross": money(gross, language), "deductible": money(estimate["deductible_eur"], language),
               "payout": money(estimate["payout_eur"], language)}

    if not failed:
        key = "paid" if estimate["payout_eur"] > 0 else "below_deductible"
        return {"decision": AUTO_SETTLE, "payout_eur": estimate["payout_eur"], "gross_eur": gross,
                "checks": checks, "reasons": [], "next_step": "None: settled automatically.",
                "customer_message": texts[key].format(**amounts)}

    return {"decision": ROUTE, "payout_eur": None, "gross_eur": gross, "checks": checks,
            "reasons": [f"{c['rule']}: {c['detail']}" if c["detail"] else c["rule"] for c in failed],
            "next_step": " ".join(dict.fromkeys(NEXT_STEPS[c["rule"]] for c in failed)),
            "customer_message": texts["routed"]}
