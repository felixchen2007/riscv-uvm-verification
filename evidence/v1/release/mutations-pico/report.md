# RTL mutation report

Status: completed; all targeted detected: True.

| Mutant | Outcome | Intended UVM checker | Spike prefix observation |
| --- | --- | --- | --- |
| pico_add_flip_bit0 | killed | RVFI_RD | architectural_mismatch |
| pico_beq_inverted | killed | RVFI_PC | architectural_mismatch |
| pico_sll_flip_bit0 | killed | RVFI_RD | architectural_mismatch |
| pico_store_flip_bit0 | killed | MEM_STORE_DATA | architectural_mismatch |

Compile-invalid and infrastructure failures are excluded from the detection denominator.
A matching stopped prefix is not a full architectural pass. One actual clean Spike execution is reused only for identical input images.
This targeted campaign does not establish a broad mutation score.
