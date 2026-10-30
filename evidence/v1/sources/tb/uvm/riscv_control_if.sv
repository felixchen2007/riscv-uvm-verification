`timescale 1ns/1ps
interface riscv_control_if(input logic clk);
  logic reset_request=0, irq_external=0;
  wire effective_rst_n;
  wire data_request,data_accept,data_inflight;
endinterface
