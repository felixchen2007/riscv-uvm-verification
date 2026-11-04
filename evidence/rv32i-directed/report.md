# Directed RV32I verification

**40 of 40 base RV32I instructions passed on each core.** Vivado XSim 2025.2
ran 12 positive UVM 1.2 simulations with seed 20261029. Each core ran a
sequence covering 38 distinct instructions and two separate trap programs at both
memory timings. All positive runs had zero UVM errors, fatals, and assertion
failures. Both injected writeback controls triggered the expected checker error.

The SystemVerilog scoreboard checked the ordered instruction path, register
results, and data transactions. All six conditional branches exercised taken
and untaken paths. The jump cases checked the target and link register. Byte
and halfword cases checked store lanes and load sign and zero extension.
FENCE was tested between stores and loads in the serialized memory model.

Ibex took both synchronous traps and its handler reported the expected
cause and faulting PC. PicoRV32 raised its configured terminal trap for both
instructions. The directed suite used explicit expected results in SystemVerilog.
The separate Spike campaigns cover their original RV32I subset.

The table gives checked observations across both timing profiles. Support
instructions in the trap setup and handler are excluded from the table.

| Base RV32I instruction | Ibex | PicoRV32 |
| --- | ---: | ---: |
| ADD | Pass (2) | Pass (2) |
| ADDI | Pass (20) | Pass (20) |
| AND | Pass (2) | Pass (2) |
| ANDI | Pass (2) | Pass (2) |
| AUIPC | Pass (2) | Pass (2) |
| BEQ | Pass (4) | Pass (4) |
| BGE | Pass (4) | Pass (4) |
| BGEU | Pass (4) | Pass (4) |
| BLT | Pass (4) | Pass (4) |
| BLTU | Pass (4) | Pass (4) |
| BNE | Pass (4) | Pass (4) |
| EBREAK | Pass (2) | Pass (2) |
| ECALL | Pass (2) | Pass (2) |
| FENCE | Pass (2) | Pass (2) |
| JAL | Pass (2) | Pass (2) |
| JALR | Pass (2) | Pass (2) |
| LB | Pass (2) | Pass (2) |
| LBU | Pass (2) | Pass (2) |
| LH | Pass (2) | Pass (2) |
| LHU | Pass (2) | Pass (2) |
| LUI | Pass (2) | Pass (2) |
| LW | Pass (2) | Pass (2) |
| OR | Pass (2) | Pass (2) |
| ORI | Pass (2) | Pass (2) |
| SB | Pass (2) | Pass (2) |
| SH | Pass (2) | Pass (2) |
| SLL | Pass (2) | Pass (2) |
| SLLI | Pass (2) | Pass (2) |
| SLT | Pass (2) | Pass (2) |
| SLTI | Pass (2) | Pass (2) |
| SLTIU | Pass (2) | Pass (2) |
| SLTU | Pass (2) | Pass (2) |
| SRA | Pass (2) | Pass (2) |
| SRAI | Pass (2) | Pass (2) |
| SRL | Pass (2) | Pass (2) |
| SRLI | Pass (2) | Pass (2) |
| SUB | Pass (2) | Pass (2) |
| SW | Pass (2) | Pass (2) |
| XOR | Pass (2) | Pass (2) |
| XORI | Pass (2) | Pass (2) |

[Machine-readable results and source hashes](results.json) · [RV32I specification](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)
