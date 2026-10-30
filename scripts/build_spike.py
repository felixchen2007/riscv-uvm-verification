"""Build the pinned upstream Spike and thin state-observation adapter in WSL."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from tool_common import ROOT


def wsl_path(path):
    path=Path(path).resolve()
    if not path.drive or not path.drive.endswith(":"):
        raise ValueError("Expected an absolute Windows drive path")
    return "/mnt/"+path.drive[0].lower()+path.as_posix()[2:]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs",type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.jobs<=16:
        parser.error("jobs must be in 1..16")
    config_path=ROOT/"config/spike.json"
    config=json.loads(config_path.read_text())
    source=ROOT/"build/spike-upstream"
    if not source.exists():
        subprocess.run(["git","clone","--depth","1","--branch",config["tag"],config["repository"],str(source)],check=True)
    revision=subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()
    if revision!=config["commit"]:
        raise RuntimeError("Spike checkout differs from pinned revision")
    if subprocess.check_output(["git","-C",str(source),"status","--porcelain"],text=True).strip():
        raise RuntimeError("Spike checkout is modified; refusing reference build")
    output=ROOT/config["build_directory"]
    output.mkdir(parents=True,exist_ok=True)
    archive=output/"source.tar"
    # Git for Windows may otherwise apply the host's CRLF export conversion.
    subprocess.run(["git","-c","core.autocrlf=false","-c","core.eol=lf","-C",str(source),
                    "archive","--format=tar","--output",str(archive),config["commit"]],check=True)
    command=["wsl","-d",config["distribution"],"--exec","python3",
             wsl_path(ROOT/"verification/reference/build_spike_linux.py"),
             "--archive",wsl_path(archive),"--bridge",wsl_path(ROOT/"verification/reference/spike_bridge.cc"),
             "--config",wsl_path(config_path),"--output",wsl_path(output),"--jobs",str(args.jobs)]
    (output/"build-command.json").write_text(json.dumps(command,indent=2)+"\n")
    return subprocess.run(command).returncode


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        print("SPIKE_BUILD_FAILED: "+str(exc),file=sys.stderr)
        raise SystemExit(1)
