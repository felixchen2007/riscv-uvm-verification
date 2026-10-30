`timescale 1ns/1ps
interface picorv32_mem_if(input logic clk,input logic rst_n);
  logic valid,instr,ready;
  logic [31:0] addr,wdata,rdata;
  logic [3:0] wstrb;
  clocking mon @(posedge clk);
    default input #1step;
    input rst_n,valid,instr,ready,addr,wdata,rdata,wstrb;
  endclocking
  a_held_request: assert property (@(posedge clk) disable iff(!rst_n)
    valid && !ready |=> valid && $stable({instr,addr,wstrb}))
    else $error("PICO_MEM_STABILITY: held request changed");
  a_held_write: assert property (@(posedge clk) disable iff(!rst_n)
    valid && !ready && |wstrb |=> $stable(wdata))
    else $error("PICO_WRITE_STABILITY: held write data changed");
  a_ready_valid: assert property (@(posedge clk) disable iff(!rst_n) ready |-> valid)
    else $error("PICO_READY: completion without request");
  a_known_controls: assert property (@(posedge clk) disable iff(!rst_n) !$isunknown({valid,ready}))
    else $error("PICO_CONTROL_X: unknown control");
  a_known_request: assert property (@(posedge clk) disable iff(!rst_n)
    valid |-> !$isunknown({instr,addr,wstrb})) else $error("PICO_REQUEST_X: unknown request");
  a_read_known: assert property (@(posedge clk) disable iff(!rst_n)
    valid && ready && wstrb==0 |-> !$isunknown(rdata)) else $error("PICO_READ_X: unknown response");
endinterface
