// Sends each observed retirement to the live DPI-C checker.
// Confirms that Spike completed the expected instruction sequence.

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
  // These values match the launcher's SPIKE_LIVE_CORRUPT plusarg.
  localparam int NO_CORRUPTION = 0;
  localparam int CORRUPT_REGISTER = 1;
  localparam int CORRUPT_PC = 2;
  localparam int CORRUPT_STORE = 3;
  int compared = 0;
  int corruption_mode = NO_CORRUPTION;
  bit failed=0,injected=0,opened=0;
  string config_path;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void start_of_simulation_phase(uvm_phase phase);
    int matched;
    if(!$value$plusargs("SPIKE_LIVE_CONFIG=%s",config_path))
      `uvm_fatal("SPIKE_LIVE_CONFIG","Missing launch configuration")
    matched=$value$plusargs("SPIKE_LIVE_CORRUPT=%d",corruption_mode);
    if(corruption_mode < NO_CORRUPTION || corruption_mode > CORRUPT_STORE)
      `uvm_fatal("SPIKE_LIVE_CONFIG","Invalid observation control")
    if(rv_spike_open(config_path)!=0) `uvm_fatal("SPIKE_LIVE_START",rv_spike_error())
    opened=1;
    `uvm_info("SPIKE_LIVE_READY","Pinned Spike process ready for retirement-triggered stepping",UVM_NONE)
  endfunction
  function void write(ibex_retirement t);
    int unsigned pc,data,wdata;
    bit is_load, is_store;
    bit unknown_retirement, unknown_load, unknown_store;
    bit corrupt_register, corrupt_pc, corrupt_store;
    if (failed) return;

    is_load = t.insn[6:0] == 7'h03;
    is_store = t.insn[6:0] == 7'h23;
    unknown_retirement = $isunknown({t.order,t.pc,t.insn,t.rd,t.rd_data,t.trap,t.halt,t.intr});
    unknown_load = is_load && $isunknown({t.mem_addr,t.mem_rmask,t.mem_rdata});
    unknown_store = is_store && $isunknown({t.mem_addr,t.mem_wmask,t.mem_wdata});
    if (unknown_retirement || unknown_load || unknown_store) begin
      failed = 1;
      rv_spike_close();
      `uvm_error("SPIKE_LIVE_X","Unknown meaningful RVFI observation")
      return;
    end

    pc = t.pc;
    data = t.rd_data;
    wdata = t.mem_wdata;
    // Corrupt only this subscriber's local copy. SV checker and DUT are unchanged.
    corrupt_register = corruption_mode == CORRUPT_REGISTER && t.rd != 0;
    corrupt_pc = corruption_mode == CORRUPT_PC;
    corrupt_store = corruption_mode == CORRUPT_STORE && is_store;
    if (!injected && (corrupt_register || corrupt_pc || corrupt_store)) begin
      if (corrupt_register) data^=1;
      else if (corrupt_pc) pc^=4;
      else wdata^=1;
      injected=1;
      `uvm_info("SPIKE_LIVE_INJECTED",$sformatf("control=%0d order=%0d",corruption_mode,compared),UVM_NONE)
    end
    if(rv_spike_check(pc,t.insn,int'(t.rd),data,t.mem_addr,int'(t.mem_rmask),int'(t.mem_wmask),
        t.mem_rdata,wdata,int'(t.trap),int'(t.halt),int'(t.intr))!=0) begin
      failed = 1;
      `uvm_error("SPIKE_LIVE_MISMATCH",rv_spike_error())
    end else begin
      compared++;
    end
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
