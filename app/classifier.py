from dataclasses import dataclass
from typing import Optional


AFFILIATIONS = (
    "CCF Main",
    "Local Satellite",
    "International Satellite",
    "Non-CCF",
    "Unknown",
)


def clean(value):
    return (value or "").strip()


@dataclass(frozen=True)
class Classification:
    affiliation: str
    satellite_name: Optional[str]
    contradictory: bool = False
    invalid_ccf_details: bool = False


def classify_affiliation(row):
    if any(
        field in row
        for field in ("B1g Satellite Hub", "B1g Satellite", "Specify B1g Satellite")
    ):
        return classify_b1g_affiliation(row)

    attending_raw = clean(row.get("Are You Attending Ccf"))
    scope_raw = clean(row.get("Are You From A Local Or International Satellite"))
    local_raw = clean(row.get("Which Local Satellite"))
    international_raw = clean(row.get("Which International Satellite"))

    attending = attending_raw.casefold()
    scope = scope_raw.casefold()

    if attending == "no":
        contradictory = bool(scope_raw or local_raw or international_raw)
        return Classification("Non-CCF", None, contradictory=contradictory)

    if attending != "yes":
        return Classification("Unknown", None)

    if scope == "local satellite":
        if not local_raw:
            return Classification("Unknown", None, invalid_ccf_details=True)
        if local_raw.casefold() == "ccf main":
            return Classification("CCF Main", local_raw)
        return Classification("Local Satellite", local_raw)

    if scope == "international satellite":
        if not international_raw:
            return Classification("Unknown", None, invalid_ccf_details=True)
        return Classification("International Satellite", international_raw)

    return Classification("Unknown", None, invalid_ccf_details=True)


def classify_b1g_affiliation(row):
    hub_raw = clean(row.get("B1g Satellite Hub"))
    satellite_raw = clean(row.get("B1g Satellite"))
    specified_raw = clean(row.get("Specify B1g Satellite"))

    hub = hub_raw.casefold()
    satellite = satellite_raw.casefold()

    if satellite == "b1g main":
        return Classification("CCF Main", satellite_raw)

    satellite_name = specified_raw if satellite == "others" else satellite_raw
    if not hub_raw or not satellite_name:
        return Classification("Unknown", None, invalid_ccf_details=True)

    if hub == "icp":
        return Classification("International Satellite", satellite_name)

    return Classification("Local Satellite", satellite_name)
