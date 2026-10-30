import csv
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reports = []
for cpu in ("ibex_smoke", "picorv32_rv32i"):
    path = root / f"build/releases/v1-verified/advanced/{cpu}_reset/simulation/stalled_rvfi_trace.csv"
    initialized = {0}
    reads = 0
    for row in csv.DictReader(path.open()):
        insn = int(row["insn"], 16)
        opcode = insn & 127
        rs1, rs2, rd = (insn >> 15) & 31, (insn >> 20) & 31, (insn >> 7) & 31
        sources = [rs1, rs2] if opcode in (0x33, 0x23, 0x63) else [rs1] if opcode in (0x13, 3) else []
        if opcode not in (0x33, 0x23, 0x63, 0x13, 3, 0x37, 0x6f):
            raise SystemExit("Unknown instruction in reset dataflow audit")
        if any(source not in initialized for source in sources):
            raise SystemExit("Restart program reads retained/uninitialized RF state")
        reads += len(sources)
        if opcode not in (0x23, 0x63): initialized.add(rd)
    reports.append({"processor": cpu, "status": "pass", "register_reads": reads,
                    "trace": str(path), "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "scope": "selected restarted corners path reads only x0 or registers written since restart; not RF reset/retention proof"})
(root / "build/v1-bringup/reset-input-audit.json").write_text(json.dumps(reports, indent=2) + "\n")
print(json.dumps(reports, indent=2))
