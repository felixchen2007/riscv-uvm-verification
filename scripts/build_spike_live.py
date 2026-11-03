"""Build the interactive Spike service from the already verified pinned cache."""
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from verification.reference.spike import verify_spike_build, digest, wsl_path, PIN

SOURCE = ROOT / "verification/reference/spike_live.cc"
OUTPUT = ROOT / "build/spike-live"


def verify_live_build():
    verify_spike_build()
    manifest = json.loads((OUTPUT / "build-manifest.json").read_text())
    if (manifest.get("status") != "built" or manifest.get("commit") != PIN or
            manifest.get("source_sha256") != digest(SOURCE) or
            manifest.get("driver_sha256") != digest(Path(__file__)) or
            manifest.get("executable_sha256") != digest(OUTPUT / "spike_live")):
        raise RuntimeError("Live Spike build changed; run scripts/build_spike_live.py")
    return manifest


def build():
    config, upstream = verify_spike_build()
    cache = PurePosixPath(upstream["linux_cache"])
    # Paths here are Linux paths, passed to g++ as individual argv entries.
    source, libraries = cache / "source", cache / "build"
    OUTPUT.mkdir(exist_ok=True, parents=True)
    (OUTPUT / "build-manifest.json").unlink(missing_ok=True)
    command = ["wsl", "-d", config["distribution"], "--exec", "g++",
               *config["cxxflags"].split(), f'-DRVVERIFY_SPIKE_COMMIT="{PIN}"']
    command += ["-I" + str(p) for p in (libraries, source, source / "riscv", source / "fesvr", source / "softfloat", source / "fdt")]
    command += [wsl_path(SOURCE), "-o", wsl_path(OUTPUT / "spike_live"), "-Wl,--start-group"]
    command += [str(libraries / name) for name in ("libriscv.a", "libdisasm.a", "libsoftfloat.a", "libfesvr.a", "libfdt.a")]
    command += ["-Wl,--end-group", "-ldl", "-lpthread"]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (OUTPUT / "build.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError("Live Spike build failed; see build/spike-live/build.log")
    version = subprocess.check_output(["wsl", "-d", config["distribution"], "--exec",
                                     wsl_path(OUTPUT / "spike_live"), "--version"], text=True).strip()
    if version != f"rvverify-spike-live api=1 spike=1.1.0 commit={PIN}":
        raise RuntimeError("Unexpected interactive Spike identity")
    data = {"status": "built", "commit": PIN, "version": version, "command": command,
            "upstream_build": upstream, "source_sha256": digest(SOURCE),
            "driver_sha256": digest(Path(__file__)), "executable_sha256": digest(OUTPUT / "spike_live")}
    (OUTPUT / "build-manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    print("SPIKE_LIVE_BUILD_PASS")
    return data


if __name__ == "__main__":
    build()
