"""Tool 1: look up a policy in policies.json. Read-only: nothing here can change a policy."""
import json
import re
from datetime import date, timedelta

from core import config


def _key(policy_number):
    return re.sub(r"[^A-Z0-9]", "", str(policy_number or "").upper())


def _policies():
    data = json.loads((config.DATA / "policies.json").read_text(encoding="utf-8"))
    return {_key(p["policy_number"]): p for p in data["policies"]}


def lookup_policy(policy_number, incident_date=None):
    policy = _policies().get(_key(policy_number))
    if policy is None:
        return {"found": False, "policy_number": str(policy_number or "").strip()}

    result = {
        "found": True,
        "policy_number": policy["policy_number"],
        "holder_first_name": policy["holder_first_name"],
        "active": policy["active"],
        "coverage_type": policy["coverage_type"],
        "own_damage_covered": policy["own_damage_covered"],
        "deductible_eur": policy["deductible_eur"],
        "start_date": _start_date(policy).isoformat(),
        "vehicle": policy["vehicle"],
        "vehicle_value_eur": policy["vehicle_value_eur"],
        "registration": policy.get("registration", ""),
        "date_issues": [],
    }
    if incident_date:
        result["date_issues"] = _date_issues(incident_date, _start_date(policy))
    return result


def _start_date(policy):
    """A demo policy that must always look brand new gives its age in days instead of a fixed date."""
    if "started_days_ago" in policy:
        return date.today() - timedelta(days=policy["started_days_ago"])
    return date.fromisoformat(policy["start_date"])


def _date_issues(incident_date, start):
    try:
        incident = date.fromisoformat(str(incident_date))
    except ValueError:
        return [{"code": "invalid_date", "detail": f"Incident date '{incident_date}' is not a valid date"}]

    issues = []
    if incident < start:
        issues.append({"code": "incident_before_policy_start",
                       "detail": f"Incident on {incident} is before the policy started on {start}"})
    elif (incident - start).days < config.RECENT_POLICY_DAYS:
        issues.append({"code": "policy_started_recently",
                       "detail": f"Policy started {(incident - start).days} days before the incident"})
    if incident > date.today():
        issues.append({"code": "incident_in_future", "detail": f"Incident date {incident} is in the future"})
    return issues
