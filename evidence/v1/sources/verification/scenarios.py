"""Passive event/epoch checks, separate from the native independent predictor."""
import csv
from pathlib import Path
import shutil


def extract_reset_epoch(path):
    path=Path(path)
    with path.open(newline="") as stream:
        reader=csv.DictReader(stream); columns=reader.fieldnames; rows=list(reader)
    if "epoch" not in (columns or []) or not rows:
        raise ValueError("Reset trace lacks explicit epoch observations")
    epochs=[int(row["epoch"]) for row in rows]
    if sorted(set(epochs))!=[0,1] or epochs!=sorted(epochs):
        raise ValueError("Reset requires one ordered aborted prefix and restart epoch")
    shutil.copyfile(path,path.with_name(path.stem.replace("_rvfi_trace","_all_epochs_rvfi_trace")+".csv"))
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,columns);writer.writeheader();writer.writerows(r for r in rows if int(r["epoch"])==1)
    return {"epochs":2,"aborted_prefix_retirements":epochs.count(0),"final_retirements":epochs.count(1)}


def audit_irq_trace(path,control_path,order_base=1):
    with Path(path).open(newline="") as stream: rows=list(csv.DictReader(stream))
    pcs=[int(r["pc"],16) for r in rows]
    handler=pcs.index(0x22c) if 0x22c in pcs else -1
    if handler<8 or pcs[:7]!=list(range(0x80,0x9c,4)) or any(pc!=0x9c for pc in pcs[7:handler]):
        raise ValueError("IRQ setup/parking path differs from contract")
    if pcs[handler:]!=[0x22c,0x230,0x234,0x238,0x9c,0xa0,0xa4]:
        raise ValueError("IRQ handler/MRET/mainline path differs from contract")
    for index,row in enumerate(rows):
        if int(row["order"])!=index+order_base or int(row.get("epoch",0))!=0 or int(row["trap"]) or int(row["halt"]):
            raise ValueError("IRQ order/reset/trap mismatch")
        if int(row["intr"])!=int(index==handler): raise ValueError("IRQ entry flag mismatch")
    if int(rows[handler]["rd"])!=11 or int(rows[handler]["rd_data"],16)!=0x8000000b:
        raise ValueError("Incorrect machine-external mcause")
    if int(rows[handler+1]["rd"])!=12 or int(rows[handler+1]["rd_data"],16)!=0x9c:
        raise ValueError("Incorrect interrupted mepc")
    if int(rows[handler+3]["insn"],16)!=0x30200073: raise ValueError("Missing MRET")
    last=rows[-1]
    if int(last["mem_addr"],16)!=0x1004 or int(last["mem_wmask"],16)!=15 or int(last["mem_wdata"],16)!=1:
        raise ValueError("IRQ completion store missing")
    with Path(control_path).open(newline="") as stream: events=[r["event"] for r in csv.DictReader(stream)]
    if events!=["irq_1","irq_0"]: raise ValueError("IRQ input pulse observations differ")
    return {"status":"pass","retirements":len(rows),"parking_retirements":handler-7,
        "mcause":0x8000000b,"mepc":0x9c,"mret":1,"spike_comparison_executed":False,
        "scope":"native independent CSR/event/return contract; no asynchronous Spike comparison"}
