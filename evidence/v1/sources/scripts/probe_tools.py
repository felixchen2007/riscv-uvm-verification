"""Probe Questa's UVM/SV capabilities and inventory local host tools."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from tool_common import ROOT, call_tool, find_questa, require_success, uvm_paths

PROBES = {
    "uvm_base": '''`include "uvm_macros.svh"
package probe_pkg;
  import uvm_pkg::*;
  class capability_test extends uvm_test;
    `uvm_component_utils(capability_test)
    function new(string name="capability_test", uvm_component parent=null);
      super.new(name,parent);
    endfunction
    task run_phase(uvm_phase phase);
      phase.raise_objection(this);
      `uvm_info("UVM_BASE_EXECUTED", "UVM class factory and phases executed", UVM_NONE)
      phase.drop_objection(this);
    endtask
  endclass
endpackage
module probe_uvm_base;
  import uvm_pkg::*;
  import probe_pkg::*;
  initial run_test("capability_test");
endmodule
''',
    "randomize": '''module probe_randomize;
  class item;
    rand int unsigned value;
    constraint legal { value inside {[1:7]}; }
  endclass
  initial begin
    item request = new();
    if (!request.randomize()) $fatal(1,"randomize returned false");
    if (!(request.value inside {[1:7]})) $fatal(1,"constraint not honored");
    $display("RANDOMIZE_EXECUTED value=%0d",request.value);
    $finish;
  end
endmodule
''',
    "covergroups": '''module probe_covergroups;
  int value;
  covergroup cg;
    value_cp: coverpoint value { bins observed = {1}; }
  endgroup
  cg coverage;
  initial begin
    coverage = new(); value = 1; coverage.sample();
    if (coverage.get_inst_coverage() < 100.0) $fatal(1,"coverage did not sample");
    $display("COVERGROUP_EXECUTED coverage=%0f",coverage.get_inst_coverage());
    $finish;
  end
endmodule
''',
}


def external_version(executable, args):
    if not executable:
        return {"available": False, "status": "not-found-on-path"}
    try:
        run = subprocess.run([str(executable), *args], text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=30, errors="replace")
        return {"available": run.returncode == 0, "path": str(executable),
                "exit_code": run.returncode, "output": run.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "path": str(executable), "error": str(exc)}


def probe(output):
    output.mkdir(parents=True, exist_ok=True)
    tool_dir = find_questa()
    uvm_source, dpi = uvm_paths(tool_dir)
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "python": {"path": sys.executable, "version": sys.version},
              "simulator_under_capability_probe": "Questa Intel Starter", "questa_bin": str(tool_dir), "uvm_version": "1.2",
              "uvm_package_sha256": hashlib.sha256((uvm_source / "uvm_pkg.sv").read_bytes()).hexdigest(),
              "probes": {}, "tools": {}}
    for tool in ("vsim", "vlog"):
        run = call_tool(tool_dir, tool, ["-version"], output, tool + "_version.log")
        report["tools"][tool] = {"exit_code": run.returncode, "version": run.stdout.strip()}
        require_success(run, tool + " version")
    quartus = shutil.which("quartus_sh")
    if not quartus and os.name == "nt":
        candidate = tool_dir.parent.parent / "quartus/bin64/quartus_sh.exe"
        if candidate.is_file():
            quartus = candidate
    report["tools"]["quartus"] = external_version(quartus, ["--version"])
    report["tools"]["git"] = external_version(shutil.which("git"), ["--version"])
    try:
        from run_xsim_tests import find_vivado
        xsim_bin=find_vivado()
        report["tools"]["xsim"] = external_version(xsim_bin / ("xvlog.bat" if os.name=="nt" else "xvlog"), ["--version"])
        report["tools"]["xsim"]["feature_execution_evidence"] = "Separate build/xsim/*/results.json; Questa license denials do not apply to XSim"
    except RuntimeError as exc:
        report["tools"]["xsim"] = {"available": False, "reason": str(exc)}
    for tool in ("spike", "riscv64-unknown-elf-gcc", "riscv32-unknown-elf-gcc"):
        report["tools"][tool] = external_version(shutil.which(tool), ["--version"])
    for library in ("work", "uvm12"):
        if not (output / library).exists():
            require_success(call_tool(tool_dir, "vlib", [library], output, library + "_library.log"), "library creation")
    require_success(call_tool(tool_dir, "vlog", ["-sv", "-work", "uvm12", "+incdir+" + str(uvm_source),
                                               uvm_source / "uvm_pkg.sv"], output, "uvm_compile.log"), "UVM package compilation")
    (output / "run.do").write_text("onerror {quit -code 1}\nrun -all\nquit -code 0\n", encoding="ascii")
    for name, source in PROBES.items():
        path = output / ("probe_" + name + ".sv")
        path.write_text(source, encoding="ascii")
        compile_run = call_tool(tool_dir, "vlog", ["-sv", "-L", "uvm12", "+incdir+" + str(uvm_source), path],
                                output, name + "_compile.log")
        result = {"compiled": compile_run.returncode == 0, "executed": False,
                  "source_sha256": hashlib.sha256(source.encode("ascii")).hexdigest(),
                  "compile_exit_code": compile_run.returncode}
        transcript = compile_run.stdout
        if compile_run.returncode == 0:
            args = ["-c", "-onfinish", "stop", "-L", "uvm12", "-sv_lib", str(dpi),
                    "work.probe_" + name, "-do", "do run.do"]
            if name == "covergroups":
                args.insert(1, "-coverage")
            simulation = call_tool(tool_dir, "vsim", args, output, name + "_simulation.log")
            transcript += simulation.stdout
            result["simulation_exit_code"] = simulation.returncode
            marker = {"uvm_base": "[UVM_BASE_EXECUTED]", "randomize": "RANDOMIZE_EXECUTED", "covergroups": "COVERGROUP_EXECUTED"}[name]
            result["executed"] = (simulation.returncode == 0 and marker in simulation.stdout
                                  and "** Error:" not in simulation.stdout and "** Fatal:" not in simulation.stdout)
            if name == "uvm_base":
                result["uvm_counts"] = {}
                for severity in ("UVM_INFO", "UVM_WARNING", "UVM_ERROR", "UVM_FATAL"):
                    matches = re.findall(rf"\b{severity}\s*:\s*(\d+)", simulation.stdout)
                    result["uvm_counts"][severity] = int(matches[-1]) if matches else None
                result["executed"] = result["executed"] and all(result["uvm_counts"][severity] == 0
                                      for severity in ("UVM_ERROR", "UVM_FATAL"))
        result["verification_license_denied"] = bool(re.search(r"svverification|Unable to checkout verification license", transcript, re.I))
        result["status"] = "executed-pass" if result["executed"] else ("license-denied" if result["verification_license_denied"] else "failed")
        report["probes"][name] = result
        print(f"CAPABILITY {name}: {result['status']}", flush=True)
    report["status"] = "uvm-base-available" if report["probes"]["uvm_base"]["executed"] else "uvm-base-unavailable"
    report["full_sv_verification_available"] = all(report["probes"][name]["executed"] for name in PROBES)
    (output / "tool-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/probe")
    args = parser.parse_args()
    report = probe(args.output.resolve())
    print("TOOL_REPORT: " + str(args.output.resolve() / "tool-report.json"))
    return 0 if report["probes"]["uvm_base"]["executed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print("TOOL_PROBE_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
