"""Linux-side build driver. Writes only its owned build cache and output."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",required=True)
    parser.add_argument("--bridge",required=True)
    parser.add_argument("--config",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--jobs",type=int,default=8)
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    manifest=output/"build-manifest.json"
    state=output/"build-state.json"
    previous=json.loads(state.read_text()) if state.exists() else {}
    cache=Path(previous.get("linux_cache", "/nonexistent"))
    if (not cache.is_dir() or previous.get("archive_sha256")!=digest(args.archive)
            or previous.get("config_sha256")!=digest(args.config)):
        cache_root=Path.home()/".cache/rvverify-spike"
        cache_root.mkdir(parents=True,exist_ok=True)
        cache=Path(tempfile.mkdtemp(prefix="build-",dir=cache_root))
        with tarfile.open(args.archive) as archive:
            archive.extractall(cache/"source",filter="data")
    source,build=cache/"source",cache/"build"
    build.mkdir(exist_ok=True)
    state.write_text(json.dumps({"linux_cache":str(cache),"archive_sha256":digest(args.archive),
                                "config_sha256":digest(args.config)})+"\n")
    def run(command,name,timeout=1800):
        with (output/name).open("w") as log:
            result=subprocess.run(command,cwd=build,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Build command failed ({result.returncode}); see {output/name}")
    if not (build/"Makefile").exists():
        run([str(source/"configure"),*config["configure_options"],"CXXFLAGS="+config["cxxflags"]],"configure.log")
    run(["make",f"-j{args.jobs}","spike"],"make.log")
    libraries=["libriscv.a","libdisasm.a","libsoftfloat.a","libfesvr.a","libfdt.a"]
    command=["g++",*config["cxxflags"].split(),f'-DRVVERIFY_SPIKE_COMMIT="{config["commit"]}"']
    command += ["-I"+str(p) for p in (build,source,source/"riscv",source/"fesvr",source/"softfloat",source/"fdt")]
    command += [args.bridge,"-o",str(output/"spike_ref"),"-Wl,--start-group"]
    command += [str(build/name) for name in libraries]
    command += ["-Wl,--end-group","-ldl","-lpthread"]
    run(command,"bridge-build.log",timeout=180)
    shutil.copyfile(build/"spike",output/"spike")
    (output/"spike").chmod(0o755)
    (output/"spike_ref").chmod(0o755)
    version=subprocess.run([str(output/"spike_ref"),"--version"],capture_output=True,text=True,check=True).stdout.strip()
    result={"status":"built", "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "upstream":config,"platform":platform.platform(),"linux_cache":str(cache),
            "archive_sha256":digest(args.archive),"bridge_source_sha256":digest(args.bridge),
            "bridge_driver_sha256":digest(__file__),"config_sha256":digest(args.config),
            "spike_sha256":digest(output/"spike"),"bridge_sha256":digest(output/"spike_ref"),
            "version":version,"compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0],
            "link_command":command,"configure_options":config["configure_options"]}
    manifest.write_text(json.dumps(result,indent=2)+"\n")
    print("SPIKE_BUILD_PASS "+str(manifest),flush=True)


if __name__=="__main__":
    main()
