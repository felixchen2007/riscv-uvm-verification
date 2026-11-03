// Optional live reference subscriber. The existing SV predictor remains active.
`ifdef RV_SPIKE_DPI
import "DPI-C" function int rv_spike_open(input string config_path);
import "DPI-C" function int rv_spike_check(input int unsigned pc,insn,rd,data,
  address,rmask,wmask,rdata,wdata,trap,halt,intr);
import "DPI-C" function int rv_spike_finish();
import "DPI-C" function string rv_spike_error();
import "DPI-C" function void rv_spike_close();

class riscv_spike_checker extends uvm_subscriber #(ibex_retirement);
  `uvm_component_utils(riscv_spike_checker)
  int compared=0,corrupt=0;
  bit failed=0,injected=0,opened=0;
  string config_path;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void start_of_simulation_phase(uvm_phase phase);
    int matched;
    if(!$value$plusargs("SPIKE_LIVE_CONFIG=%s",config_path))
      `uvm_fatal("SPIKE_LIVE_CONFIG","Missing launch configuration")
    matched=$value$plusargs("SPIKE_LIVE_CORRUPT=%d",corrupt);
    if(corrupt<0 || corrupt>3) `uvm_fatal("SPIKE_LIVE_CONFIG","Invalid observation control")
    if(rv_spike_open(config_path)!=0) `uvm_fatal("SPIKE_LIVE_START",rv_spike_error())
    opened=1;
    `uvm_info("SPIKE_LIVE_READY","Pinned Spike process ready for retirement-triggered stepping",UVM_NONE)
  endfunction
  function void write(ibex_retirement t);
    int unsigned pc,data,wdata;
    if(failed) return;
    if($isunknown({t.order,t.pc,t.insn,t.rd,t.rd_data,t.trap,t.halt,t.intr}) ||
      (t.insn[6:0]==7'h03 && $isunknown({t.mem_addr,t.mem_rmask,t.mem_rdata})) ||
      (t.insn[6:0]==7'h23 && $isunknown({t.mem_addr,t.mem_wmask,t.mem_wdata}))) begin
      failed=1; rv_spike_close(); `uvm_error("SPIKE_LIVE_X","Unknown meaningful RVFI observation")
      return;
    end
    pc=t.pc; data=t.rd_data; wdata=t.mem_wdata;
    // Corrupt only this subscriber's local copy. SV checker and DUT are unchanged.
    if(!injected && ((corrupt==1 && t.rd!=0) || corrupt==2 || (corrupt==3 && t.insn[6:0]==7'h23))) begin
      if(corrupt==1) data^=1;
      else if(corrupt==2) pc^=4;
      else wdata^=1;
      injected=1;
      `uvm_info("SPIKE_LIVE_INJECTED",$sformatf("control=%0d order=%0d",corrupt,compared),UVM_NONE)
    end
    if(rv_spike_check(pc,t.insn,int'(t.rd),data,t.mem_addr,int'(t.mem_rmask),int'(t.mem_wmask),
        t.mem_rdata,wdata,int'(t.trap),int'(t.halt),int'(t.intr))!=0) begin
      failed=1; `uvm_error("SPIKE_LIVE_MISMATCH",rv_spike_error())
    end else compared++;
  endfunction
  function void check_phase(uvm_phase phase);
    if(!failed) begin
      if(rv_spike_finish()!=0) begin
        failed=1; `uvm_error("SPIKE_LIVE_FINISH",rv_spike_error())
      end else `uvm_info("SPIKE_LIVE_PASS",$sformatf("compared=%0d",compared),UVM_NONE)
    end
  endfunction
  function void final_phase(uvm_phase phase); if(opened) rv_spike_close(); endfunction
endclass
`endif
