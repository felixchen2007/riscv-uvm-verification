`include "uvm_macros.svh"
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
