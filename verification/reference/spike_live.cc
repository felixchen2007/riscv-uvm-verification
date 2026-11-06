// Runs Spike as a service that advances one instruction per request.
// Returns Spike's register and memory effects to the DPI-C bridge.

// Interactive adapter around unmodified pinned Spike, never fed DUT results.
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
#error "Pin the upstream Spike revision"
#endif

struct live_ram : simif_t {
  std::vector<char> bytes = std::vector<char>(65536, 0);
  char* addr_to_mem(reg_t a) override { return a < bytes.size() ? bytes.data()+a : nullptr; }
  bool mmio_load(reg_t, size_t, uint8_t*) override { return false; }
  bool mmio_store(reg_t, size_t, const uint8_t*) override { return false; }
  void proc_reset(unsigned) override {}
  const char* get_symbol(uint64_t) override { return nullptr; }
  uint32_t word(uint64_t a) const {
    if ((a & 3) || a > bytes.size()-4) throw std::runtime_error("memory-range");
    uint32_t v=0;
    for (unsigned i=0;i<4;i++) v |= uint32_t(uint8_t(bytes[a+i])) << (8*i);
    return v;
  }
  void load(const char* path) {
    std::ifstream image(path);
    if (!image) throw std::runtime_error("image-open");
    std::string address, value;
    std::vector<bool> seen(16384, false);
    unsigned count=0;
    while (image >> address) {
      if(!(image >> value)) throw std::runtime_error("image-missing-word");
      if (address.size()<2 || address[0]!='@' || address.size()>9 || value.size()>8 ||
          address.substr(1).find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos ||
          value.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
        throw std::runtime_error("image-format");
      uint64_t a=std::stoull(address.substr(1),nullptr,16)*4;
      uint64_t v=std::stoull(value,nullptr,16);
      if (a>bytes.size()-4 || seen[a/4]) throw std::runtime_error("image-overlap-range");
      seen[a/4]=true;
      for(unsigned i=0;i<4;i++) bytes[a+i]=char(v>>(8*i));
      count++;
    }
    if (!image.eof() || !count) throw std::runtime_error("image-empty-malformed");
  }
};

int main(int argc, char** argv) {
  try {
    if (argc==2 && std::string(argv[1])=="--version") {
      std::cout << "rvverify-spike-live api=1 spike=" SPIKE_VERSION " commit=" RVVERIFY_SPIKE_COMMIT "\n";
      return 0;
    }
    if(argc!=8) throw std::runtime_error("arguments");
    std::string isa=argv[1];
    unsigned entry=std::stoul(argv[3]), steps=std::stoul(argv[4]),
             terminal_pc=std::stoul(argv[5]), sig_addr=std::stoul(argv[6]), sig_value=std::stoul(argv[7]);
    if((isa!="rv32i" && isa!="rv32ic") || steps<1 || steps>1000 || entry!=128 ||
        terminal_pc>65532 || (terminal_pc&3) || sig_addr!=4100 || sig_value!=1)
      throw std::runtime_error("configuration");
    live_ram ram; ram.load(argv[2]);
    processor_t core(isa.c_str(),"M","vlen:128,elen:64",&ram,0,false,stderr,std::cerr);
    core.enable_log_commits();
    state_t* state=core.get_state(); state->pc=entry;
    for(unsigned r=0;r<32;r++) if(state->XPR[r]) throw std::runtime_error("reset-state");
    std::cout << "READY 1 " RVVERIFY_SPIKE_COMMIT " " << steps << std::endl;
    unsigned count=0; bool terminal=false;
    std::string command;
    while(std::getline(std::cin,command)) {
      if(!command.empty() && command.back()=='\r') command.pop_back();
      if(command=="FINISH") {
        if(count!=steps || !terminal || ram.word(sig_addr)!=sig_value || state->pc!=terminal_pc+4)
          throw std::runtime_error("incomplete-terminal");
        std::cout << "PASS " << count << std::endl;
        return 0;
      }
      if(command!="STEP " + std::to_string(count) || count>=steps || terminal)
        throw std::runtime_error("step-order");
      uint32_t pc=uint32_t(state->pc);
      auto fetch=core.get_mmu()->load_insn(state->pc);
      uint32_t insn=uint32_t(fetch.insn.bits()), op=insn&127, f3=(insn>>12)&7;
      if(fetch.insn.length()!=4 || !(op==0x13 || op==0x33 || op==0x37 || op==3 || op==0x23 || op==0x63 || op==0x6f) ||
          ((op==3 || op==0x23) && f3!=2)) throw std::runtime_error("unsupported-instruction");
      uint64_t before=state->minstret->read();
      core.step(1);
      if(state->minstret->read()!=before+1 || state->debug_mode || state->prv!=3)
        throw std::runtime_error("trap-halt-privilege");
      unsigned rd=0, writes=0; uint32_t data=0;
      for(const auto& v:state->log_reg_write) {
        if(!v.first) continue;
        if((v.first&15) || ++writes>1) throw std::runtime_error("register-write");
        rd=unsigned(v.first>>4); data=uint32_t(v.second.v[0]);
      }
      if(state->log_mem_read.size()+state->log_mem_write.size()>1) throw std::runtime_error("memory-count");
      unsigned kind=0; uint64_t address=0; uint32_t value=0;
      if(!state->log_mem_read.empty()) {
        const auto& a=state->log_mem_read[0]; address=std::get<0>(a);
        if(op!=3 || std::get<2>(a)!=4) throw std::runtime_error("load-effect");
        kind=1; value=ram.word(address);
      } else if(!state->log_mem_write.empty()) {
        const auto& a=state->log_mem_write[0]; address=std::get<0>(a); value=uint32_t(std::get<1>(a));
        if(op!=0x23 || std::get<2>(a)!=4 || ram.word(address)!=value) throw std::runtime_error("store-effect");
        kind=2; terminal=(address==sig_addr && value==sig_value);
      } else if(op==3 || op==0x23) throw std::runtime_error("missing-memory");
      if(terminal && (count+1!=steps || pc!=terminal_pc)) throw std::runtime_error("early-terminal");
      std::cout << "RET " << count << ' ' << pc << ' ' << insn << ' ' << rd << ' ' << data
                << ' ' << kind << ' ' << address << ' ' << value << ' ' << uint32_t(state->pc)
                << ' ' << unsigned(terminal) << std::endl;
      count++;
    }
    throw std::runtime_error("closed-without-finish");
  } catch(const std::exception& e) {
    std::cout << "FAIL " << e.what() << std::endl;
    return 1;
  }
}
