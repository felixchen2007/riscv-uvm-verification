class riscv_control_item extends uvm_sequence_item;
  `uvm_object_utils(riscv_control_item)
  // Commands: 0 reset pulse, 1 IRQ level. Observations: 2 reset, 3 IRQ high, 4 low.
  int kind,cycles=8;
  bit level,pending_data,accepted_data;
  function new(string name="riscv_control_item"); super.new(name); endfunction
endclass
