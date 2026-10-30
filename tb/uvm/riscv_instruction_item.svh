// Preload stimulus only. The architectural scoreboard never uses these fields.
class riscv_instruction_item extends uvm_sequence_item;
  `uvm_object_utils(riscv_instruction_item)
  // 0=register ALU, 1=ADDI, 2=LUI, 3=LW, 4=SW.
  int unsigned kind,previous_rd;
  rand int unsigned alu_kind,rd,rs1,rs2,slot,dependency;
  rand int signed immediate;
  rand bit [19:0] upper;
`ifdef IBEX_UVM_FULL
  constraint legal_instruction {
    alu_kind inside {[0:9]};
    rd inside {[0:31]}; rd!=6; rd!=27;
    rs1 inside {[0:31]}; rs2 inside {[0:31]};
    immediate inside {[-2048:2047]};
    slot inside {[8:15]}; // 0x1020..0x103c; never code or terminal signature.
    dependency inside {[0:2]};
    solve dependency before rs1,rs2;
    if(kind==3 || kind==4) rs1==6;
    if(kind!=0 && kind!=1) dependency==0;
    if(kind==1) dependency inside {[0:1]};
    if(previous_rd==0) dependency==0;
    if(dependency==1) rs1==previous_rd;
    if(dependency==2) rs2==previous_rd;
  }
`endif
  function new(string name="riscv_instruction_item"); super.new(name); endfunction
endclass

class riscv_instruction_schedule extends uvm_object;
  `uvm_object_utils(riscv_instruction_schedule)
  rand int unsigned order[8];
`ifdef IBEX_UVM_FULL
  constraint permutation {
    foreach(order[i]) order[i] inside {[0:7]};
    foreach(order[i]) foreach(order[j]) if(i!=j) order[i]!=order[j];
  }
`endif
  function new(string name="riscv_instruction_schedule"); super.new(name); endfunction
endclass
