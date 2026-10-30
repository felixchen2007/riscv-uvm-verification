"""Pinned Spike execution and offline architectural comparison within layer 2."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from verification.traces import compare_traces, validate_trace, write_trace

ROOT = Path(__file__).resolve().parents[2]
PIN = "530af85d83781a3dae31a4ace84a573ec255fefa"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wsl_path(path):
    path = Path(path).resolve()
    if not path.drive.endswith(":"):
        raise ValueError("Spike WSL backend requires a Windows drive path")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def read_program_image(path, memory_bytes=65536):
    """Convert the shared readmemh word image to explicit byte addresses.

    Fail on undefined bits, overlaps and overflow instead of changing input
    meaning. No DUT trace or expected result participates in this conversion.
    """
    words, cursor = {}, None
    text = Path(path).read_text(encoding="ascii")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    for token in text.split():
        if token.startswith("@"):
            if not re.fullmatch(r"@[0-9a-fA-F]{1,8}", token):
                raise ValueError("Malformed program image address")
            cursor = int(token[1:], 16) * 4
            continue
        if cursor is None or not re.fullmatch(r"[0-9a-fA-F]{1,8}", token):
            raise ValueError("Undefined/malformed program image word or missing address")
        if cursor in words or cursor + 4 > memory_bytes:
            raise ValueError("Overlapping/out-of-range program image")
        words[cursor] = int(token, 16)
        cursor += 4
    if not words:
        raise ValueError("Empty program image")
    return words


def verify_spike_build(root=ROOT):
    config_path = root / "config/spike.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (config.get("schema_version") != 1 or config.get("commit") != PIN or
            config.get("bridge_api") != 1 or config.get("backend") != "wsl" or
            config.get("memory_bytes") != 65536 or config.get("privilege") != "M"):
        raise ValueError("Unsupported/unpinned Spike build configuration")
    folder = root / config["build_directory"]
    manifest_path = folder / "build-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Spike build missing; run scripts/build_spike.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = f"rvverify-spike-ref api=1 spike=1.1.0 commit={PIN}"
    if manifest.get("status") != "built" or manifest.get("upstream") != config or manifest.get("version") != version:
        raise RuntimeError("Spike build identity is stale or unsupported; rebuild required")
    checks = {
        "config_sha256": config_path,
        "archive_sha256": folder / "source.tar",
        "bridge_source_sha256": root / "verification/reference/spike_bridge.cc",
        "bridge_driver_sha256": root / "verification/reference/build_spike_linux.py",
        "spike_sha256": folder / "spike",
        "bridge_sha256": folder / "spike_ref",
    }
    for field, path in checks.items():
        if not path.is_file() or manifest.get(field) != digest(path):
            raise RuntimeError(f"Spike build source/binary hash changed: {field}; rebuild required")
    return config, manifest


def parse_spike_records(text, program_path, processor):
    try:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed Spike JSONL output") from exc
    if not records or any(not isinstance(row, dict) for row in records):
        raise ValueError("Empty/invalid Spike retirement records")
    trace = validate_trace({"schema_version": 1, "processor_config": processor["id"],
        "producer": "spike", "isa": processor["program_isa"], "complete": True,
        "program_profile": processor.get("program_profile", "smoke"),
        "program_sha256": digest(program_path), "records": records})
    if len(records) != processor["expected_retirements"] or records[0]["pc"] != processor["entry_pc"]:
        raise ValueError("Spike retirement count/entry differs from configuration")
    if "terminal_pc" in processor and records[-1]["pc"] != processor["terminal_pc"]:
        raise ValueError("Spike terminal PC differs from program contract")
    if any(row[k] for row in records for k in ("trap", "halt", "interrupt")):
        raise ValueError("Spike smoke scope excludes trap/halt/interrupt events")
    terminal = {"kind": "store", "address": processor["signature_address"],
                "mask": 15, "data": processor["signature_value"]}
    if records[-1]["memory"] != terminal:
        raise ValueError("Spike trace lacks the terminal signature store")
    return trace


def run_reference(program_path, processor, output):
    config, build = verify_spike_build()
    if processor["spike_isa"] not in ("rv32i", "rv32ic"):
        raise ValueError("Unsupported Spike ISA configuration")
    program_path, output = Path(program_path).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = output / "reference-result.json"
    result = {"schema_version": 1, "status": "failed", "executed": False,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "processor_config": processor["id"], "spike_isa": processor["spike_isa"],
              "program_profile": processor.get("program_profile", "smoke"),
              "program_sha256": digest(program_path), "build": build,
              "scope": "offline single-hart machine-mode RV32I smoke; zero registers/RAM; no external events"}
    try:
        words = read_program_image(program_path, config["memory_bytes"])
        if processor["entry_pc"] not in words:
            raise ValueError("Reference entry is absent from image")
        converted = output / "program-byte-addresses.txt"
        converted.write_text("".join(f"{address:08x} {word:08x}\n" for address, word in sorted(words.items())), encoding="ascii")
        command = ["wsl", "-d", config["distribution"], "--exec",
                   wsl_path(ROOT / config["build_directory"] / "spike_ref"),
                   processor["spike_isa"], wsl_path(converted), str(processor["entry_pc"]),
                   str(processor["expected_retirements"]), str(config["memory_bytes"]),
                   str(processor["signature_address"]), str(processor["signature_value"])]
        result["command"] = command
        result["input_words_sha256"] = digest(converted)
        proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=180)
        result.update(executed=True, returncode=proc.returncode)
        (output / "retirements.jsonl").write_text(proc.stdout, encoding="utf-8")
        (output / "commit.log").write_text(proc.stderr, encoding="utf-8")
        markers = re.findall(r"^SPIKE_REFERENCE_PASS retired=(\d+) next_pc=(\d+) signature=(\d+)$", proc.stderr, re.M)
        if proc.returncode or len(markers) != 1 or "SPIKE_REFERENCE_FAILED" in proc.stderr:
            raise RuntimeError("Spike execution failed or lacked completion marker; see commit.log")
        trace = parse_spike_records(proc.stdout, program_path, processor)
        retired, next_pc, signature = map(int, markers[0])
        if (retired != len(trace["records"]) or signature != processor["signature_value"] or
                next_pc != trace["records"][-1]["pc"] + 4):
            raise ValueError("Spike completion marker contradicts its terminal store")
        # Reject source or executable changes while the external process ran.
        if verify_spike_build()[1] != build or digest(program_path) != result["program_sha256"]:
            raise RuntimeError("Spike build/program source changed during execution")
        write_trace(output / "retirement-v1.json", trace)
        result.update(status="pass", retirements=len(trace["records"]),
                      trace_sha256=digest(output / "retirement-v1.json"))
    except subprocess.TimeoutExpired as exc:
        result.update(error="Spike reference timed out after 180 seconds", timed_out=True)
        for name, value in (("retirements.jsonl", exc.stdout), ("commit.log", exc.stderr)):
            if isinstance(value, bytes):
                value = value.decode(errors="replace")
            (output / name).write_text(value or "", encoding="utf-8")
        raise RuntimeError(result["error"]) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        result["error"] = str(exc)
        raise
    finally:
        manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return trace, result


def qualify_comparison(actual, reference):
    """An observation corruption control, never an RTL/ISS mutation claim."""
    corrupt = copy.deepcopy(actual)
    index = next((i for i, row in enumerate(corrupt["records"]) if row["rd_address"]), None)
    if index is None:
        raise ValueError("No writeback available for comparison corruption control")
    corrupt["records"][index]["rd_data"] ^= 1
    try:
        compare_traces(corrupt, reference)
    except ValueError as exc:
        diagnostic = str(exc)
        if not diagnostic.startswith(f"Architectural mismatch at record {index}: rd_data:"):
            raise RuntimeError("Comparison corruption control failed for an unintended reason") from exc
        return {"status": "detected", "record": index, "field": "rd_data", "diagnostic": diagnostic}, corrupt
    raise RuntimeError("Comparison corruption control survived")


def compare_case_with_spike(folder, processor, traces):
    folder = Path(folder)
    reference, execution = run_reference(folder / "no_added_delay_program.hex", processor, folder / "spike")
    comparisons = {name: compare_traces(trace, reference) for name, trace in traces.items()}
    control, corrupt = qualify_comparison(traces["no_added_delay"], reference)
    write_trace(folder / "spike/corrupted-observation.json", corrupt)
    result = {"status": "pass", "executed": execution["executed"],
              "reference_manifest": str(folder / "spike/reference-result.json"),
              "profiles": comparisons, "corruption_control": control}
    (folder / "spike/comparison-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
