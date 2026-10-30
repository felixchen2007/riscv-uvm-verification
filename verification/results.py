"""Shared outcome classification and honest coverage summaries."""
import re


def classify_failure(message):
    text = message.lower()
    for category, pattern in (
        ("license", r"license|svverification"),
        ("timeout", r"timed out|timeout|watchdog"),
        ("source_integrity", r"source.*chang|source.*hash|vendor snapshot|source drift"),
        ("architectural_mismatch", r"rvfi_|architectural mismatch|scoreboard"),
        ("compile_or_elaboration", r"compil|elaborat|vrfc"),
        ("unsupported_configuration", r"not executable|no executable.*adapter|unsupported|not implemented"),
    ):
        if re.search(pattern, text):
            return category
    return "infrastructure"


def validate_case(case):
    required = {"schema_version", "case_id", "layer", "scope", "processor_config", "seed", "status", "artifacts"}
    if not required.issubset(case) or case["schema_version"] != 1:
        raise ValueError("Invalid shared result envelope")
    if case["layer"] not in ("uvm", "python") or case["scope"] not in ("cpu", "component", "utility"):
        raise ValueError("Invalid verification layer/scope")
    if case["status"] not in ("pass", "failed", "unavailable"):
        raise ValueError("Unresolved case cannot enter a completed regression")
    if type(case["seed"]) is not int or not 0 < case["seed"] <= 0xffffffff:
        raise ValueError("Invalid result seed")
    if case["status"] == "pass" and not case.get("executed"):
        raise ValueError("Preparation/compilation alone is not a pass")
    return case


def aggregate(cases, requested):
    if len(cases) != requested or not cases:
        raise ValueError("Missing requested regression cases")
    for case in cases:
        validate_case(case)
    ids = [case["case_id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate case IDs inflate result counts")
    coverage = []
    for case in cases:
        coverage.extend(case.get("coverage_observations", []))
    return {"status": "pass" if all(c["status"] == "pass" for c in cases) else "failed",
            "requested_cases": requested, "passed_cases": sum(c["status"] == "pass" for c in cases),
            "failed_cases": sum(c["status"] != "pass" for c in cases),
            # Percentages from independent runs cannot be arithmetically merged.
            "coverage": {"observations": coverage, "merged_bin_coverage": None,
                         "note": "Per-run percentages only. Merge simulator bin databases before claiming combined coverage."}}
