`timescale 1ns/1ps
// Ibex's request/grant interface has no response backpressure. The responder
// below returns every accepted request exactly once, at least one cycle later.
interface ibex_mem_if(input logic clk, input logic rst_n);
  logic req, gnt, rvalid, we;
  logic [3:0] be;
  logic [31:0] addr, wdata, rdata;
  logic err;

  clocking mon @(posedge clk);
    default input #1step;
    input rst_n, req, gnt, rvalid, we, be, addr, wdata, rdata, err;
  endclocking

  property request_stays_until_grant;
    @(posedge clk) disable iff (!rst_n)
      req && !gnt |=> req && $stable({addr, we, be, wdata});
  endproperty
  a_request_stays_until_grant: assert property(request_stays_until_grant)
    else $error("IBEX_MEM_STABILITY: request changed before grant");

  a_grant_has_request: assert property(
    @(posedge clk) disable iff (!rst_n) gnt |-> req)
    else $error("IBEX_MEM_GRANT: grant without request");

  a_controls_known: assert property(
    @(posedge clk) disable iff (!rst_n) !$isunknown({req, gnt, rvalid}))
    else $error("IBEX_MEM_CONTROL_X: unknown request/grant/response control");

  a_response_known: assert property(
    @(posedge clk) disable iff (!rst_n)
      rvalid |-> !$isunknown({rdata, err}))
    else $error("IBEX_MEM_RESPONSE_X: unknown response payload");
endinterface
