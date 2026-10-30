"""Architectural register semantics for targeted component tests, not a CPU ISS."""
class RegisterFileModel:
    def __init__(self, count=32):
        if count not in (16, 32):
            raise ValueError("RV32 register count must be 16 or 32")
        self.count = count
        self.reset()

    def reset(self):
        self.registers = [0] * self.count

    def _check(self, address):
        if type(address) is not int or not 0 <= address < self.count:
            raise ValueError("Register address outside selected ISA")

    def read(self, address):
        self._check(address)
        return self.registers[address]

    def write(self, address, value, enable=True):
        self._check(address)
        if enable and address:
            self.registers[address] = value & 0xffffffff
