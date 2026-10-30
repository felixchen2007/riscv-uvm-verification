`timescale 1ns/1ps
// Targeted component harness. It does not duplicate the CPU UVM environment.
module ibex_regfile_wrapper #(parameter bit RV32E=0) (
  input logic clk, rst_n, write_enable,
  input logic [4:0] read_a, read_b, write_address,
  input logic [31:0] write_data,
  output logic [31:0] data_a, data_b,
  output logic error
);
  ibex_register_file_ff #(.RV32E(RV32E)) dut (
    .clk_i(clk),.rst_ni(rst_n),.test_en_i(1'b0),
    .dummy_instr_id_i(1'b0),.dummy_instr_wb_i(1'b0),
    .raddr_a_i(read_a),.rdata_a_o(data_a),.raddr_b_i(read_b),.rdata_b_o(data_b),
    .waddr_a_i(write_address),.wdata_a_i(write_data),.we_a_i(write_enable),.err_o(error)
  );
endmodule
