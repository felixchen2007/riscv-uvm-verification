// Thin adapter to the pinned, unmodified Spike processor implementation.
// Instruction semantics execute inside Spike. No DUT trace is an input here.
#include "config.h"
#include "processor.h"
#include "mmu.h"
#include "simif.h"
#include "VERSION"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef RVVERIFY_SPIKE_COMMIT
#error "Build must identify the pinned Spike revision"
#endif

struct reference_ram : simif_t {
  std::vector<char> bytes;
  explicit reference_ram(size_t size) : bytes(size, 0) {}
  char* addr_to_mem(reg_t addr) override { return addr < bytes.size() ? bytes.data()+addr : nullptr; }
  bool mmio_load(reg_t, size_t, uint8_t*) override { return false; }
  bool mmio_store(reg_t, size_t, const uint8_t*) override { return false; }
  void proc_reset(unsigned) override {}
  const char* get_symbol(uint64_t) override { return nullptr; }
  uint32_t read_word(uint64_t address) const {
    if (address+4 > bytes.size() || (address & 3)) throw std::runtime_error("Unaligned/out-of-range reference memory");
    uint32_t value=0;
    for(unsigned i=0;i<4;i++) value |= uint32_t(uint8_t(bytes[address+i])) << (8*i);
    return value;
  }
  void write_word(uint64_t address,uint32_t value) {
    if (address+4 > bytes.size() || (address & 3)) throw std::runtime_error("Invalid image address");
    for(unsigned i=0;i<4;i++) bytes[address+i]=char(value >> (8*i));
  }
};

int main(int argc,char** argv) {
  try {
    if(argc==2 && std::string(argv[1])=="--version") {
      std::cout << "rvverify-spike-ref api=1 spike=" SPIKE_VERSION " commit=" RVVERIFY_SPIKE_COMMIT "\n";
      return 0;
    }
    if(argc!=8) throw std::runtime_error("Usage: spike_ref ISA words-file entry steps memory-bytes signature-address signature-value");
    const std::string isa=argv[1];
    if(isa!="rv32i" && isa!="rv32ic") throw std::runtime_error("Unsupported reference ISA profile");
    const auto entry=std::stoull(argv[3],nullptr,0), steps=std::stoull(argv[4],nullptr,0);
    const auto memory_size=std::stoull(argv[5],nullptr,0), sig_addr=std::stoull(argv[6],nullptr,0);
    const auto sig_value=std::stoull(argv[7],nullptr,0);
    if(memory_size!=65536 || steps==0 || steps>1000 || sig_value>0xffffffff)
      throw std::runtime_error("Invalid bounded reference configuration");
    reference_ram memory(memory_size);
    std::ifstream image(argv[2]);
    if(!image) throw std::runtime_error("Cannot open shared program image");
    uint64_t address,word;
    unsigned words=0;
    while(image >> std::hex >> address >> word) {
      if(word>0xffffffff) throw std::runtime_error("Invalid image word");
      memory.write_word(address,uint32_t(word)); words++;
    }
    if(!image.eof() || words==0) throw std::runtime_error("Malformed/empty image");
    processor_t core(isa.c_str(),"M","vlen:128,elen:64",&memory,0,false,stderr,std::cerr);
    core.enable_log_commits();
    state_t* state=core.get_state();
    state->pc=entry; // Exact DUT execution window; no reset-ROM instructions.
    for(unsigned r=0;r<32;r++)
      if(state->XPR[r]!=0) throw std::runtime_error("Spike reset register state is not zero");
    bool terminal=false;
    for(uint64_t index=0;index<steps;index++) {
      const uint32_t pc=uint32_t(state->pc);
      auto fetch=core.get_mmu()->load_insn(state->pc);
      const uint32_t insn=uint32_t(fetch.insn.bits());
      const unsigned opcode=insn & 127, funct3=(insn >> 12)&7;
      // A scope guard only; execution and result calculation stay in Spike.
      if(fetch.insn.length()!=4 || !(opcode==0x13 || opcode==0x33 || opcode==0x37 ||
          opcode==0x03 || opcode==0x23 || opcode==0x63 || opcode==0x6f) ||
         ((opcode==0x03 || opcode==0x23) && funct3!=2))
        throw std::runtime_error("Instruction outside supported reference smoke scope");
      const uint64_t before=state->minstret->read();
      core.step(1);
      if(state->minstret->read()!=before+1 || state->debug_mode || state->prv!=3)
        throw std::runtime_error("Unexpected trap/halt/privilege transition; no reference pass");
      unsigned rd=0,writes=0;
      uint32_t rd_value=0;
      for(const auto& item:state->log_reg_write) {
        if(item.first==0) continue; // x0 is not an architectural write.
        if((item.first & 15)!=0 || ++writes>1) throw std::runtime_error("Unexpected noninteger/multiple writebacks");
        rd=unsigned(item.first >> 4); rd_value=uint32_t(item.second.v[0]);
      }
      if(state->log_mem_read.size()+state->log_mem_write.size()>1)
        throw std::runtime_error("Unexpected multiple memory effects");
      std::cout << "{\"order\":" << index << ",\"hart\":0,\"pc\":" << pc
                << ",\"insn\":" << insn << ",\"rd_address\":" << rd << ",\"rd_data\":" << rd_value
                << ",\"trap\":false,\"halt\":false,\"interrupt\":false,\"memory\":";
      terminal=false;
      if(!state->log_mem_read.empty()) {
        const auto& access=state->log_mem_read[0];
        const uint64_t addr=std::get<0>(access);
        if(opcode!=3 || std::get<2>(access)!=4) throw std::runtime_error("Unexpected load effect");
        std::cout << "{\"kind\":\"load\",\"address\":" << addr << ",\"mask\":15,\"data\":" << memory.read_word(addr) << "}";
      } else if(!state->log_mem_write.empty()) {
        const auto& access=state->log_mem_write[0];
        const uint64_t addr=std::get<0>(access), value=std::get<1>(access)&0xffffffff;
        if(opcode!=0x23 || std::get<2>(access)!=4) throw std::runtime_error("Unexpected store effect");
        std::cout << "{\"kind\":\"store\",\"address\":" << addr << ",\"mask\":15,\"data\":" << value << "}";
        terminal=addr==sig_addr && value==sig_value;
      } else {
        if(opcode==3 || opcode==0x23) throw std::runtime_error("Missing Spike memory effect");
        std::cout << "null";
      }
      std::cout << "}\n";
      if(terminal && index+1!=steps) throw std::runtime_error("Premature terminal store");
    }
    if(!terminal || memory.read_word(sig_addr)!=sig_value) throw std::runtime_error("Missing terminal reference store");
    std::cerr << "SPIKE_REFERENCE_PASS retired=" << steps << " next_pc=" << state->pc << " signature=" << sig_value << "\n";
    return 0;
  } catch(const std::exception& error) {
    std::cerr << "SPIKE_REFERENCE_FAILED: " << error.what() << "\n";
    return 1;
  }
}
