`timescale 1ns/1ps
module tb_picorv32_uvm;
  import uvm_pkg::*;
  import ibex_uvm_pkg::*;
  logic clk=0,boot_rst_n=0,trap;
  wire rst_n;
  riscv_control_if control(clk);
  assign rst_n=boot_rst_n && !control.reset_request;
  assign control.effective_rst_n=rst_n;
  assign control.data_request=memory.valid && !memory.instr;
  assign control.data_accept=memory.valid && !memory.instr && memory.ready;
  assign control.data_inflight=1'b0; // Native acceptance and response are atomic.
  always #5ns clk=~clk;
  initial begin repeat(8) @(negedge clk); boot_rst_n=1; end
  picorv32_mem_if memory(clk,rst_n);
  ibex_rvfi_if rvfi(clk,rst_n);
  picorv32 #(
    .ENABLE_COUNTERS(0),.ENABLE_COUNTERS64(0),.ENABLE_REGS_16_31(1),.ENABLE_REGS_DUALPORT(1),
    .LATCHED_MEM_RDATA(0),.TWO_STAGE_SHIFT(1),.BARREL_SHIFTER(0),
    .TWO_CYCLE_COMPARE(0),.TWO_CYCLE_ALU(0),.COMPRESSED_ISA(0),
    .CATCH_MISALIGN(1),.CATCH_ILLINSN(1),.ENABLE_PCPI(0),.ENABLE_MUL(0),
    .ENABLE_FAST_MUL(0),.ENABLE_DIV(0),.ENABLE_IRQ(0),.ENABLE_IRQ_QREGS(0),
    .ENABLE_IRQ_TIMER(0),.ENABLE_TRACE(0),.REGS_INIT_ZERO(1),
    .PROGADDR_RESET(32'h80),.STACKADDR(32'hffffffff)
  ) dut (
    .clk(clk),.resetn(rst_n),.trap(trap),
    .mem_valid(memory.valid),.mem_instr(memory.instr),.mem_ready(memory.ready),
    .mem_addr(memory.addr),.mem_wdata(memory.wdata),.mem_wstrb(memory.wstrb),.mem_rdata(memory.rdata),
    .mem_la_read(),.mem_la_write(),.mem_la_addr(),.mem_la_wdata(),.mem_la_wstrb(),
    .pcpi_valid(),.pcpi_insn(),.pcpi_rs1(),.pcpi_rs2(),
    .pcpi_wr(1'b0),.pcpi_rd(32'b0),.pcpi_wait(1'b0),.pcpi_ready(1'b0),
    .irq(32'b0),.eoi(),.trace_valid(),.trace_data(),
    .rvfi_valid(rvfi.valid),.rvfi_order(rvfi.order),.rvfi_insn(rvfi.insn),
    .rvfi_trap(rvfi.trap),.rvfi_halt(rvfi.halt),.rvfi_intr(rvfi.intr),.rvfi_mode(),.rvfi_ixl(),
    .rvfi_rs1_addr(rvfi.rs1),.rvfi_rs2_addr(rvfi.rs2),
    .rvfi_rs1_rdata(rvfi.rs1_data),.rvfi_rs2_rdata(rvfi.rs2_data),
    .rvfi_rd_addr(rvfi.rd),.rvfi_rd_wdata(rvfi.rd_data),
    .rvfi_pc_rdata(rvfi.pc),.rvfi_pc_wdata(rvfi.pc_next),
    .rvfi_mem_addr(rvfi.mem_addr),.rvfi_mem_rmask(rvfi.mem_rmask),.rvfi_mem_wmask(rvfi.mem_wmask),
    .rvfi_mem_rdata(rvfi.mem_rdata),.rvfi_mem_wdata(rvfi.mem_wdata),
    .rvfi_csr_mcycle_rmask(),.rvfi_csr_mcycle_wmask(),.rvfi_csr_mcycle_rdata(),.rvfi_csr_mcycle_wdata(),
    .rvfi_csr_minstret_rmask(),.rvfi_csr_minstret_wmask(),.rvfi_csr_minstret_rdata(),.rvfi_csr_minstret_wdata()
  );
  a_no_trap: assert property (@(posedge clk) disable iff(!rst_n) trap===1'b0)
    else $error("PICO_TRAP: unexpected CPU trap");
  initial begin
    uvm_config_db#(virtual riscv_control_if)::set(null,"uvm_test_top.env.control_agent.*","vif",control);
    uvm_config_db#(virtual riscv_control_if)::set(null,"uvm_test_top.env","control_vif",control);
    uvm_config_db#(int)::set(null,"uvm_test_top","cpu_id",1);
    uvm_config_db#(virtual picorv32_mem_if)::set(null,"uvm_test_top.env.memory_agent.*","vif",memory);
    uvm_config_db#(virtual ibex_rvfi_if)::set(null,"uvm_test_top.env.rvfi_monitor","vif",rvfi);
    run_test();
  end
endmodule
