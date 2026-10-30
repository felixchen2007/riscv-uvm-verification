// XSim 2025.2 produces invalid C++ names for the unused DPI exports inside
// ibex_if_stage.gen_prefetch_buffer (e.g. int gen_prefetch_buffer.function()).
// Select STANDARD assertion macros before suppressing those SYNTHESIS-guarded
// exports. No vendor source is edited; the RTL ASSERT macros stay enabled.
// This scope also omits V2S coverage signals, already disabled by DV_FCOV_DISABLE.
`include "prim_assert.sv"
`define SYNTHESIS
`include "ibex_if_stage.sv"
`undef SYNTHESIS
