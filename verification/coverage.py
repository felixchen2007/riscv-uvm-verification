"""Read simulator bin counts; percentages are never averaged across tests."""
import csv
import io

POINTS = {
    "retire_cg": {"op": 7, "branch_direction": 2, "branch_kind": 2, "branch_cross": 4},
    "corner_cg": dict.fromkeys(("add_wrap", "sign_boundary", "sub_underflow", "immediate_min", "immediate_max",
        "x0_discard", "rd_rs1_alias", "rd_rs2_alias", "load_use", "negative_memory_offset", "high_register",
        "masked_shift_count"), 1) | {"alu_kind": 10},
    "random_kind_cg": {"kind": 5}, "random_alu_cg": {"operation": 10}, "random_memory_cg": {"words": 8},
}


def parse_xcrg_report(text):
    groups = {name: {} for name in POINTS}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6:
            continue
        row = [part.strip() for part in row]
        for group, points in POINTS.items():
            if row[1].startswith(group + "_") and row[0] in points:
                if row[0] in groups[group]:
                    raise ValueError("Duplicate coverage point in native report")
                expected, uncovered, covered = map(int, row[2:5])
                if expected != points[row[0]] or covered + uncovered != expected or min(covered, uncovered) < 0:
                    raise ValueError("Native coverage bin counts contradict the declared model")
                groups[group][row[0]] = {"expected": expected, "covered": covered, "uncovered": uncovered,
                                         "percent": float(row[5])}
    if any(set(groups[g]) != set(POINTS[g]) for g in groups):
        raise ValueError("Native report lacks required coverpoints/crosses")
    return {g: {"points": points, "expected": sum(p["expected"] for p in points.values()),
                "covered": sum(p["covered"] for p in points.values()),
                "closed": all(p["uncovered"] == 0 for p in points.values())} for g, points in groups.items()}
