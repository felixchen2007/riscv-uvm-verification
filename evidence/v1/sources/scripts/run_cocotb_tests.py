"""Run complementary register-file tests through Questa's actual VPI interface."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from tool_common import ROOT, find_questa, call_tool, require_success
from run_uvm_tests import snapshot_hashes, verify_vendor_lock


def run_suite(seed=20261029, output=None):
    output = Path(output or ROOT / "build/cocotb" / f"seed_{seed}").resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "status": "incomplete", "verification_pass": False,
              "layer": "python", "scope": "targeted RTL component; not CPU acceptance",
              "simulator": "Questa VPI", "seed": seed,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "variants": {}}
    (output / "results.json").unlink(missing_ok=True)
    try:
        import cocotb
        import cocotb_tools.config
        import find_libpython
        result["cocotb_version"] = cocotb.__version__
        result["vendor_commit_verified"] = verify_vendor_lock()["commit"]
        hashes = snapshot_hashes()
        result["source_sha256"] = hashes
        tool_dir = find_questa()
        libpython = find_libpython.find_libpython()
        if not libpython:
            raise RuntimeError("Matching libpython was not found")
        env = dict(os.environ)
        env.update(LIBPYTHON_LOC=libpython, PYGPI_PYTHON_BIN=sys.executable,
                   PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "tb/cocotb"), *sys.path)),
                   COCOTB_TOPLEVEL="ibex_regfile_wrapper", COCOTB_TEST_MODULES="test_register_file",
                   TOPLEVEL_LANG="verilog", COCOTB_RANDOM_SEED=str(seed), RF_TEST_SEED=str(seed))
        env["PATH"] = os.pathsep.join((str(tool_dir), str(cocotb_tools.config.libs_dir), env.get("PATH", "")))
        version = call_tool(tool_dir,"vsim",["-version"],output,"version.log")
        require_success(version,"Questa version")
        result["tool_version"] = version.stdout.strip()
        for rv32e in (0, 1):
            case = output / f"rv32e_{rv32e}"
            case.mkdir(parents=True, exist_ok=True)
            # Invoke native CLI arguments directly. cocotb 2.0.1's generic
            # Questa runner Tcl-escapes these Windows paths before subprocess,
            # causing paths containing spaces to be rejected by vlog.
            if not (case / "work").exists():
                require_success(call_tool(tool_dir,"vlib",["work"],case,"library.log"),"component library")
            require_success(call_tool(tool_dir,"vlog",["-sv",str(ROOT / "vendor/ibex/rtl/ibex_register_file_ff.sv"),
                             str(ROOT / "tb/cocotb/ibex_regfile_wrapper.sv")],case,"build.log"),"component compile")
            xml = case / "results.xml"
            xml.unlink(missing_ok=True)
            env.update(RF_RV32E=str(rv32e), COCOTB_RESULTS_FILE=str(xml))
            library = cocotb_tools.config.lib_name_path("vpi", "questa")
            # -pli is a Tcl list inside one CLI argument. Keep the original
            # wheel directory so its DLL assembly is loaded only once.
            pli_list = "{" + library.as_posix() + "}"
            (case / "run.do").write_text("onerror {quit -code 1}\nrun -all\nquit -code 0\n")
            simulation=call_tool(tool_dir,"vsim",["-c","-onfinish","exit","-voptargs=+acc",
                                 "-pli",pli_list,f"-gRV32E={rv32e}","work.ibex_regfile_wrapper",
                                 "-do","do run.do"],case,"simulation.log",env=env)
            require_success(simulation,"cocotb component simulation")
            if "RF_COMPONENT_PASS" not in simulation.stdout:
                raise RuntimeError("Component simulation lacks executed completion marker")
            tests = list(ET.parse(xml).getroot().iter("testcase"))
            if len(tests) != 1 or any(t.find("failure") is not None or t.find("error") is not None or t.find("skipped") is not None for t in tests):
                raise RuntimeError(f"Component test did not execute cleanly: {xml}")
            result["variants"][f"rv32e_{rv32e}"] = {"status": "pass", "registers": 16 if rv32e else 32,
                                                    "random_cycles": 128, "tests": len(tests),
                                                    "results_xml": str(xml), "uvm_counts": None}
        if snapshot_hashes() != hashes:
            raise RuntimeError("Sources changed during component tests")
        result.update(status="pass", verification_pass=True)
        print(f"COCOTB_COMPONENT_SUITE_PASS: {output / 'results.json'}", flush=True)
        return result
    except (Exception, SystemExit) as exc:
        result.update(status="failed", error=str(exc))
        raise RuntimeError(str(exc)) from exc
    finally:
        (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 < args.seed <= 0xffffffff:
        parser.error("seed must be a nonzero unsigned 32-bit integer")
    run_suite(args.seed, args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"COCOTB_COMPONENT_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
