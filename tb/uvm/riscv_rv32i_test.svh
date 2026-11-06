// Builds directed programs and expected results for all 40 base RV32I instructions.
// Checks each core's behavior for ordinary instructions and the two trap instructions.

// Each directed step supplies its expected result independently of the encoding.
typedef struct {
  string mnemonic;
  bit [31:0] pc, result, bus_address, bus_data;
  bit [4:0] rd;
  bit [3:0] bus_mask;
  bit store, trap, halt, handler_entry;
} rv32i_step;

class rv32i_program extends ibex_program;
  `uvm_object_utils(rv32i_program)
  rv32i_step steps[$];
  bit pico;
  int trap_case;
  function new(string name="rv32i_program"); super.new(name); endfunction

  function void step(string mnemonic, bit [31:0] insn, bit [4:0] rd=0, bit [31:0] result=0,
                     bit [3:0] mask=0, bit store=0, bit [31:0] data=0);
    rv32i_step expected;
    expected.mnemonic = mnemonic;
    expected.pc = cursor;
    expected.result = result;
    expected.rd = rd;
    expected.bus_address = 32'h1000;
    expected.bus_data = data;
    expected.bus_mask = mask;
    expected.store = store;
    expected.trap = 0;
    expected.halt = 0;
    expected.handler_entry = 0;
    steps.push_back(expected);
    emit(insn);
  endfunction

  function void branch_pair(string mnemonic, int funct3, int taken_rs1, int taken_rs2,
                            int untaken_rs1, int untaken_rs2);
    step(mnemonic,enc_b(8,taken_rs2,taken_rs1,funct3));
    emit(enc_i(99,0,0,31,'h13)); // Must be skipped.
    step(mnemonic,enc_b(8,untaken_rs2,untaken_rs1,funct3));
    step("ADDI",enc_i(7,0,0,31,'h13),31,7); // Must execute.
  endfunction

  virtual function void build_image(int unsigned seed,int program_id=0);
    bit [31:0] target;
    program_seed=seed;
    profile_id=4;
    cursor='h80;
    if(trap_case!=0) begin
      step("ADDI",enc_i(1,0,0,1,'h13),1,1);
      step(trap_case==1?"ECALL":"EBREAK",trap_case==1?'h00000073:'h00100073);
      steps[1].trap=1;
      steps[1].halt=pico;
      emit(enc_i(99,0,0,31,'h13)); // Trap must prevent fallthrough.
      if(!pico) begin
        cursor=0; // Synchronous exception entry at the boot-derived mtvec base.
        step("MCAUSE",enc_i('h342,0,2,5,'h73),5,trap_case==1?11:3);
        steps[2].handler_entry=1;
        step("MEPC",enc_i('h341,0,2,6,'h73),6,'h84);
        emit(enc_j(0,0));
      end
      return;
    end

    step("ADDI",enc_i(-8,0,0,1,'h13),1,32'hfffffff8);
    step("ADDI",enc_i(3,0,0,2,'h13),2,3);
    step("LUI",'h00001337,6,'h1000);
    step("AUIPC",'h00001397,7,'h108c);
    step("ADD", enc_r(0,2,1,0,10),10,32'hfffffffb);
    step("SUB", enc_r(32,2,1,0,10),10,32'hfffffff5);
    step("SLL", enc_r(0,2,1,1,10),10,32'hffffffc0);
    step("SLT", enc_r(0,2,1,2,10),10,1);
    step("SLTU",enc_r(0,2,1,3,10),10,0);
    step("XOR", enc_r(0,2,1,4,10),10,32'hfffffffb);
    step("SRL", enc_r(0,2,1,5,10),10,32'h1fffffff);
    step("SRA", enc_r(32,2,1,5,10),10,32'hffffffff);
    step("OR",  enc_r(0,2,1,6,10),10,32'hfffffffb);
    step("AND", enc_r(0,2,1,7,10),10,0);
    step("SLLI", enc_i(3,1,1,10,'h13),10,32'hffffffc0);
    step("SLTI", enc_i(3,1,2,10,'h13),10,1);
    step("SLTIU",enc_i(-1,1,3,10,'h13),10,1);
    step("XORI", enc_i(3,1,4,10,'h13),10,32'hfffffffb);
    step("SRLI", enc_i(3,1,5,10,'h13),10,32'h1fffffff);
    step("SRAI", enc_i('h403,1,5,10,'h13),10,32'hffffffff);
    step("ORI",  enc_i(3,1,6,10,'h13),10,32'hfffffffb);
    step("ANDI", enc_i(15,1,7,10,'h13),10,8);

    // Write -8, then replace byte lane 1 and halfword lanes 2/3.
    step("SW",enc_s(0,1,6),0,0,4'b1111,1,32'hfffffff8);
    step("SB",32'h002300a3,0,0,4'b0010,1,32'h00000300);
    step("SH",32'h00131123,0,0,4'b1100,1,32'hfff80000);
    step("FENCE",32'h0330000f); // fence rw,rw
    step("LW", enc_i(0,6,2,11,'h03),11,32'hfff803f8,4'b1111,0,32'hfff803f8);
    step("LB", enc_i(3,6,0,11,'h03),11,32'hffffffff,4'b1000,0,32'hfff803f8);
    step("LBU",enc_i(3,6,4,11,'h03),11,'hff,4'b1000,0,32'hfff803f8);
    step("LH", enc_i(2,6,1,11,'h03),11,32'hfffffff8,4'b1100,0,32'hfff803f8);
    step("LHU",enc_i(2,6,5,11,'h03),11,'hfff8,4'b1100,0,32'hfff803f8);

    branch_pair("BEQ",0,1,1,1,2);
    branch_pair("BNE",1,1,2,1,1);
    branch_pair("BLT",4,1,2,2,1);
    branch_pair("BGE",5,2,1,1,2);
    branch_pair("BLTU",6,2,1,1,2);
    branch_pair("BGEU",7,1,2,2,1);
    step("JAL",enc_j(8,12),12,cursor+4);
    emit(enc_i(98,0,0,31,'h13));
    target=cursor+12;
    step("ADDI",enc_i(int'(target)+1,0,0,13,'h13),13,target+1);
    step("JALR",enc_i(0,13,0,12,'h67),12,cursor+4);
    emit(enc_i(97,0,0,31,'h13));
    step("ADDI",enc_i(1,0,0,31,'h13),31,1);
    emit(enc_j(0,0));
  endfunction
endclass

class rv32i_directed_scoreboard extends riscv_scoreboard;
  `uvm_component_utils(rv32i_directed_scoreboard)
  rv32i_program directed;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(!$cast(directed,image)) `uvm_fatal("RV32I_CONFIG","Missing directed program")
  endfunction

  function void check_transfer(rv32i_step expected);
    ibex_mem_txn req,rsp;
    bit [31:0] data_mask;
    bit [3:0] request_mask;
    bit wrong_request, wrong_response, wrong_data;
    if(requests.size()==0 || responses.size()==0)
      `uvm_fatal("RV32I_BUS","Missing accepted data transaction")
    req=requests.pop_front();
    rsp=responses.pop_front();
    request_mask = expected.bus_mask;
    if (directed.pico && !expected.store) request_mask = 4'hf;

    // Compare only the bytes the store is supposed to write.
    data_mask = 0;
    for (int lane = 0; lane < 4; lane++) begin
      if (expected.bus_mask[lane]) data_mask[8*lane+:8] = 8'hff;
    end
    wrong_request = req.address !== expected.bus_address ||
                    req.write !== expected.store || req.be !== request_mask;
    wrong_response = rsp.address !== req.address || rsp.write !== req.write || rsp.err !== 0;
    if (expected.store)
      wrong_data = (req.data & data_mask) !== expected.bus_data;
    else
      wrong_data = rsp.data !== expected.bus_data;

    if (wrong_request || wrong_response || wrong_data)
      `uvm_fatal("RV32I_BUS",$sformatf("%s addr=%08x write=%b mask=%x write_data=%08x read_data=%08x",
        expected.mnemonic,req.address,req.write,req.be,req.data,rsp.data))
    if (expected.store)
      stores++;
    else
      loads++;
  endfunction

  virtual function void write_retire(ibex_retirement t);
    rv32i_step expected;
    if(done) return;
    expected=directed.steps[retired];
    if(t.order!==64'(retired+order_base) || t.pc!==expected.pc || t.insn!==image.instruction(expected.pc))
      `uvm_fatal("RV32I_FLOW",$sformatf("%s expected PC %08x, saw %08x insn=%08x order=%0d",
        expected.mnemonic,expected.pc,t.pc,t.insn,t.order))
    if(t.trap!==expected.trap || t.halt!==expected.halt || t.intr!==expected.handler_entry)
      `uvm_fatal("RV32I_TRAP",$sformatf("%s trap=%b halt=%b handler_entry=%b",
        expected.mnemonic,t.trap,t.halt,t.intr))
    if(t.rd!==expected.rd || (expected.rd!=0 && t.rd_data!==expected.result))
      `uvm_error("RVFI_RD",$sformatf("%s expected x%0d=%08x, saw x%0d=%08x",
        expected.mnemonic,expected.rd,expected.result,t.rd,t.rd_data))
    if(expected.bus_mask!=0) check_transfer(expected);
    `uvm_info("RV32I_CHECKED",$sformatf("%s pc=%08x insn=%08x",expected.mnemonic,t.pc,t.insn),UVM_LOW)
    retired++;
    done=retired==directed.steps.size();
  endfunction

  function void check_phase(uvm_phase phase);
    if(!done || requests.size()!=0 || responses.size()!=0)
      `uvm_error("RV32I_COMPLETION","Expected instruction sequence or data transaction checks did not complete")
  endfunction
endclass

class riscv_rv32i_test extends riscv_smoke_test;
  `uvm_component_utils(riscv_rv32i_test)
  rv32i_program directed;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction

  virtual function void configure_program();
    if(!$cast(directed,image)) `uvm_fatal("RV32I_CONFIG","Missing directed stimulus")
    directed.pico=cpu_id==1;
    void'($value$plusargs("RV32I_TRAP=%d",directed.trap_case));
    if(!(directed.trap_case inside {0,1,2}))
      `uvm_fatal("RV32I_CONFIG","Unknown trap scenario")
  endfunction

  function void build_phase(uvm_phase phase);
    ibex_program::type_id::set_type_override(rv32i_program::get_type());
    riscv_scoreboard::type_id::set_type_override(rv32i_directed_scoreboard::get_type());
    super.build_phase(phase);
  endfunction

  function void report_phase(uvm_phase phase);
    uvm_report_server server=uvm_report_server::get_server();
    if(server.get_severity_count(UVM_ERROR)==0 && server.get_severity_count(UVM_FATAL)==0 && env.scoreboard.done)
      `uvm_info("RV32I_UVM_PASS",$sformatf("retired=%0d loads=%0d stores=%0d instr_stalls=%0d data_stalls=%0d instr_waits=%0d data_waits=%0d seed=%0d max_delay=%0d cpu_id=%0d trap_case=%0d",
        env.scoreboard.retired,env.scoreboard.loads,env.scoreboard.stores,env.instr_stalls(),env.data_stalls(),
        env.instr_waits(),env.data_waits(),seed,max_delay,cpu_id,directed.trap_case),UVM_NONE)
  endfunction
endclass
