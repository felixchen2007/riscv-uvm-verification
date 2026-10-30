// Passive architectural observation boundary. No stimulus drives these signals.
interface ibex_rvfi_if(input logic clk, input logic rst_n);
  logic valid, trap, halt, intr;
  logic [63:0] order;
  logic [31:0] insn, pc, pc_next, rd_data, rs1_data, rs2_data;
  logic [4:0] rd, rs1, rs2;
  logic [31:0] mem_addr, mem_rdata, mem_wdata;
  logic [3:0] mem_rmask, mem_wmask;

  a_valid_known: assert property (@(posedge clk) disable iff (!rst_n)
    !$isunknown(valid)) else $error("RVFI valid unknown");
  a_retire_known: assert property (@(posedge clk) disable iff (!rst_n)
    valid |-> !$isunknown({order,insn,pc,trap,halt,intr,rd,rd_data}))
    else $error("RVFI retirement contains unknown values");
endinterface
