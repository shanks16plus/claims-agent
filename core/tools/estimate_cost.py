"""Tool 4: price the damage from parts_prices.csv. Plain code, no AI."""
import csv

from core import config

SEVERITY_RANK = {"minor": 0, "moderate": 1, "severe": 2}


def load_prices():
    with open(config.DATA / "parts_prices.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    prices = {}
    for row in rows:
        prices[row["part"]] = {key: (value if key in ("part", "source") else float(value))
                               for key, value in row.items()}
    return prices


def repair_or_replace(part, severity, prices=None):
    """The business rule for repair or replace (config.REPLACE_FROM). The model only reports part and severity."""
    row = (prices or load_prices()).get(part)
    if row is None:
        return "replace"                              # unpriced parts go to a person anyway
    if row["repair_materials_eur"] == 0 and row["labour_hours_repair"] == 0:
        return "replace"                              # the price table has no repair for this part
    threshold = config.REPLACE_FROM.get(part, config.REPLACE_FROM_DEFAULT)
    return "replace" if SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold] else "repair"


def _deduplicate(damaged_parts):
    """If a part is listed twice, keep the most severe entry."""
    by_part = {}
    for item in damaged_parts:
        current = by_part.get(item["part"])
        if current is None or SEVERITY_RANK[item["severity"]] > SEVERITY_RANK[current["severity"]]:
            by_part[item["part"]] = item
    return list(by_part.values())


def estimate_cost(damaged_parts, deductible_eur):
    prices = load_prices()
    lines, unpriced = [], []

    for item in _deduplicate(damaged_parts):
        row = prices.get(item["part"])
        if row is None:
            unpriced.append(item.get("evidence") or item["part"])
            continue
        factor = config.SEVERITY_FACTOR[item["severity"]]
        action = repair_or_replace(item["part"], item["severity"], prices)
        if action == "replace":
            parts_eur = row["replace_part_eur"]
            paint_eur = row["paint_eur"]
            hours = row["labour_hours_replace"]
        else:
            parts_eur = row["repair_materials_eur"] * factor
            paint_eur = row["paint_eur"] * factor
            hours = row["labour_hours_repair"] * factor
        labour_eur = hours * row["hourly_rate_eur"]
        lines.append({
            "part": item["part"],
            "action": action,
            "severity": item["severity"],
            "parts_eur": round(parts_eur, 2),
            "paint_eur": round(paint_eur, 2),
            "labour_hours": round(hours, 2),
            "labour_eur": round(labour_eur, 2),
            "line_total_eur": round(parts_eur + paint_eur + labour_eur, 2),
            "placeholder_price": "placeholder" in row["source"].lower(),
        })

    subtotal = sum(line["line_total_eur"] for line in lines)
    vat = subtotal * config.VAT_RATE
    gross = subtotal + vat
    return {
        "lines": lines,
        "unpriced_parts": unpriced,
        "subtotal_ex_vat_eur": round(subtotal, 2),
        "vat_eur": round(vat, 2),
        "gross_eur": round(gross, 2),
        "deductible_eur": deductible_eur,
        "payout_eur": round(max(0.0, gross - deductible_eur), 2),
        "uses_placeholder_prices": any(line["placeholder_price"] for line in lines),
    }
