"""Shared, dependency-free Questa discovery and bounded process execution."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def find_questa():
    candidates = []
    if os.environ.get("QUESTA_BIN"):
        candidates.append(Path(os.environ["QUESTA_BIN"]))
    executable = shutil.which("vsim")
    if executable:
        candidates.append(Path(executable).parent)
    if os.name == "nt":
        for location in (Path("C:/altera_lite"), Path("C:/intelFPGA_lite")):
            if location.exists():
                candidates.extend(sorted(location.glob("*/questa_fse/win64"), reverse=True))
    suffix = ".exe" if os.name == "nt" else ""
    for candidate in candidates:
        if all((candidate / (tool + suffix)).is_file() for tool in ("vlib", "vlog", "vsim")):
            return candidate.resolve()
    raise RuntimeError("Questa not found; set QUESTA_BIN to the directory containing vsim, vlog and vlib")


def uvm_paths(tool_dir):
    source = tool_dir.parent / "verilog_src/uvm-1.2/src"
    dpi = tool_dir.parent / ("uvm-1.2/win64/uvm_dpi" if os.name == "nt" else "uvm-1.2/linux_x86_64/uvm_dpi")
    suffix = ".dll" if os.name == "nt" else ".so"
    if not (source / "uvm_pkg.sv").is_file() or not dpi.with_suffix(suffix).is_file():
        raise RuntimeError("UVM 1.2 package and DPI not found beside Questa; this runner expects the Intel installation layout")
    return source, dpi


def call_tool(tool_dir, tool, arguments, cwd, log_name, timeout=180, env=None):
    suffix = ".exe" if os.name == "nt" else ""
    command = [str(tool_dir / (tool + suffix)), *map(str, arguments)]
    try:
        result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        (cwd / log_name).write_text(output + "\nPROCESS_TIMEOUT\n", encoding="utf-8")
        raise RuntimeError(f"{tool} timed out after {timeout}s; see {cwd / log_name}") from exc
    (cwd / log_name).write_text(result.stdout, encoding="utf-8")
    return result


def require_success(result, context):
    if result.returncode or "** Error:" in result.stdout or "** Fatal:" in result.stdout:
        raise RuntimeError(f"{context} failed (exit {result.returncode}):\n{result.stdout[-7000:]}")
