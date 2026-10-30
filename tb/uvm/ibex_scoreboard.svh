`uvm_analysis_imp_decl(_retire)
`uvm_analysis_imp_decl(_data_req)
`uvm_analysis_imp_decl(_data_rsp)
`uvm_analysis_imp_decl(_instr_rsp)
`uvm_analysis_imp_decl(_control)

class ibex_retirement extends uvm_sequence_item;
  `uvm_object_utils(ibex_retirement)
  logic [63:0] order;
  logic [31:0] insn,pc,rd_data,rs1_data,rs2_data;
  logic [4:0] rd,rs1,rs2;
  logic trap,halt,intr;
  logic [31:0] mem_addr,mem_rdata,mem_wdata;
  logic [3:0] mem_rmask,mem_wmask;
  function new(string name="ibex_retirement"); super.new(name); endfunction
endclass

class ibex_rvfi_monitor extends uvm_monitor;
  `uvm_component_utils(ibex_rvfi_monitor)
  virtual ibex_rvfi_if vif;
  uvm_analysis_port #(ibex_retirement) ap;
  bit corrupt, corrupted;
  int trace_fd;
  int epoch=0;
  bit epoch_active;
  function new(string name,uvm_component parent);
    super.new(name,parent); ap=new("ap",this);
  endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(!uvm_config_db#(virtual ibex_rvfi_if)::get(this,"","vif",vif))
      `uvm_fatal("CONFIG","Missing RVFI interface")
    corrupt=$test$plusargs("IBEX_CORRUPT_RVFI");
  endfunction
  task run_phase(uvm_phase phase);
    ibex_retirement t;
    trace_fd=$fopen("rvfi_trace.csv","w");
    if(!trace_fd) `uvm_fatal("TRACE_FILE","Cannot open retirement trace")
    $fdisplay(trace_fd,"order,pc,insn,rd,rd_data,mem_addr,mem_rmask,mem_wmask,mem_rdata,mem_wdata,trap,halt,intr,epoch");
    forever begin
      @(posedge vif.clk);
      if(!vif.rst_n && epoch_active) begin epoch++; epoch_active=0; end
      if(vif.rst_n) epoch_active=1;
      // Sample pre-edge values just as the processor's synchronous observers do.
      if(vif.rst_n && vif.valid) begin
        t=ibex_retirement::type_id::create("retirement");
        t.order=vif.order; t.pc=vif.pc; t.insn=vif.insn;
        t.rd=vif.rd; t.rd_data=vif.rd_data;
        t.rs1=vif.rs1; t.rs2=vif.rs2;
        t.rs1_data=vif.rs1_data; t.rs2_data=vif.rs2_data;
        t.trap=vif.trap; t.halt=vif.halt; t.intr=vif.intr;
        t.mem_addr=vif.mem_addr; t.mem_rmask=vif.mem_rmask;
        t.mem_wmask=vif.mem_wmask; t.mem_rdata=vif.mem_rdata;
        t.mem_wdata=vif.mem_wdata;
        // Checker qualification only: DUT, expected state and bus stay intact.
        if(corrupt && !corrupted && t.rd!=0) begin
          t.rd_data^=32'h1; corrupted=1;
          `uvm_info("CORRUPTION_INJECTED","Flipped bit 0 in one sampled RVFI writeback",UVM_LOW)
        end
        $fdisplay(trace_fd,"%0d,%08x,%08x,%0d,%08x,%08x,%x,%x,%08x,%08x,%0d,%0d,%0d,%0d",
          t.order,t.pc,t.insn,t.rd,t.rd_data,t.mem_addr,t.mem_rmask,t.mem_wmask,t.mem_rdata,t.mem_wdata,
          t.trap,t.halt,t.intr,epoch);
        $fflush(trace_fd);
        ap.write(t);
      end
    end
  endtask
  function void final_phase(uvm_phase phase);
    if(trace_fd) $fclose(trace_fd);
  endfunction
endclass

class riscv_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(riscv_scoreboard)
  uvm_analysis_imp_retire #(ibex_retirement,riscv_scoreboard) retire_export;
  uvm_analysis_imp_data_req #(ibex_mem_txn,riscv_scoreboard) data_req_export;
  uvm_analysis_imp_data_rsp #(ibex_mem_txn,riscv_scoreboard) data_rsp_export;
  uvm_analysis_imp_instr_rsp #(ibex_mem_txn,riscv_scoreboard) instr_rsp_export;
  uvm_analysis_imp_control #(riscv_control_item,riscv_scoreboard) control_export;
  ibex_program image;
  // No DUT values ever enter these expected-state arrays.
  protected bit [31:0] regs[32];
  protected bit [31:0] memory[bit [31:0]];
  protected bit [31:0] expected_pc='h80;
  ibex_mem_txn requests[$],responses[$];
  int unsigned retired,loads,stores,branches_taken,branches_not_taken,jumps,signature;
  int unsigned branch_hits[4],corner_hits[12];
  int last_rd;
  bit last_load;
  bit done;
  int order_base=1;
  int irq_count=0,mret_count=0;
  bit irq_input_active,parking_seen,global_mie;
  bit [31:0] csr_mie,csr_mtvec,csr_mcause,csr_mepc;
`ifdef IBEX_UVM_FULL
  covergroup retire_cg with function sample(bit [6:0] opcode,bit taken,bit [2:0] funct3);
    option.per_instance=1;
    op: coverpoint opcode {
      bins alu_imm={7'h13}; bins alu_reg={7'h33}; bins lui={7'h37};
      bins load={7'h03}; bins store={7'h23}; bins branch={7'h63}; bins jump={7'h6f};
    }
    branch_direction: coverpoint taken iff(opcode==7'h63);
    branch_kind: coverpoint funct3 iff(opcode==7'h63) {
      bins beq={0}; bins bne={1};
    }
    branch_cross: cross branch_kind,branch_direction;
  endgroup
  covergroup random_memory_cg with function sample(bit [3:0] slot);
    option.per_instance=1;
    words: coverpoint slot { bins scratch[8]={[8:15]}; }
  endgroup
  covergroup random_kind_cg with function sample(bit [6:0] opcode);
    option.per_instance=1;
    kind: coverpoint opcode {
      bins alu={7'h33}; bins addi={7'h13}; bins lui={7'h37}; bins lw={7'h03}; bins sw={7'h23};
    }
  endgroup
  covergroup random_alu_cg with function sample(bit [9:0] alu_key);
    option.per_instance=1;
    operation: coverpoint alu_key {
      bins add={10'b0000000_000}; bins sub={10'b0100000_000};
      bins sll={10'b0000000_001}; bins slt={10'b0000000_010}; bins sltu={10'b0000000_011};
      bins xor_op={10'b0000000_100}; bins srl={10'b0000000_101}; bins sra={10'b0100000_101};
      bins or_op={10'b0000000_110}; bins and_op={10'b0000000_111};
    }
  endgroup
  covergroup corner_cg with function sample(bit [11:0] events,bit is_alu,bit [9:0] alu_key);
    option.per_instance=1;
    add_wrap: coverpoint events[0] { bins hit={1}; ignore_bins other={0}; }
    sign_boundary: coverpoint events[1] { bins hit={1}; ignore_bins other={0}; }
    sub_underflow: coverpoint events[2] { bins hit={1}; ignore_bins other={0}; }
    immediate_min: coverpoint events[3] { bins hit={1}; ignore_bins other={0}; }
    immediate_max: coverpoint events[4] { bins hit={1}; ignore_bins other={0}; }
    x0_discard: coverpoint events[5] { bins hit={1}; ignore_bins other={0}; }
    rd_rs1_alias: coverpoint events[6] { bins hit={1}; ignore_bins other={0}; }
    rd_rs2_alias: coverpoint events[7] { bins hit={1}; ignore_bins other={0}; }
    load_use: coverpoint events[8] { bins hit={1}; ignore_bins other={0}; }
    negative_memory_offset: coverpoint events[9] { bins hit={1}; ignore_bins other={0}; }
    high_register: coverpoint events[10] { bins hit={1}; ignore_bins other={0}; }
    masked_shift_count: coverpoint events[11] { bins hit={1}; ignore_bins other={0}; }
    alu_kind: coverpoint alu_key iff(is_alu) {
      bins add={10'b0000000_000}; bins sub={10'b0100000_000};
      bins sll={10'b0000000_001}; bins slt={10'b0000000_010}; bins sltu={10'b0000000_011};
      bins xor_op={10'b0000000_100}; bins srl={10'b0000000_101}; bins sra={10'b0100000_101};
      bins or_op={10'b0000000_110}; bins and_op={10'b0000000_111};
    }
  endgroup
`endif
  function new(string name,uvm_component parent);
    super.new(name,parent);
    retire_export=new("retire_export",this);
    data_req_export=new("data_req_export",this);
    data_rsp_export=new("data_rsp_export",this);
    instr_rsp_export=new("instr_rsp_export",this);
    control_export=new("control_export",this);
    foreach(regs[i]) regs[i]=0;
    foreach(branch_hits[i]) branch_hits[i]=0;
    foreach(corner_hits[i]) corner_hits[i]=0;
`ifdef IBEX_UVM_FULL
    retire_cg=new();
    corner_cg=new();
    random_kind_cg=new(); random_alu_cg=new();
    random_memory_cg=new();
`endif
  endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    void'(uvm_config_db#(int)::get(this,"","order_base",order_base));
    if(!uvm_config_db#(ibex_program)::get(this,"","program",image))
      `uvm_fatal("CONFIG","Missing reference program")
  endfunction
  function void write_data_req(ibex_mem_txn t); requests.push_back(t); endfunction
  function void write_control(riscv_control_item t);
    if(t.kind==3) irq_input_active=1;
    else if(t.kind==4) irq_input_active=0;
    else if(t.kind==2) begin
      foreach(regs[i]) regs[i]=0;
      memory.delete(); requests.delete(); responses.delete(); expected_pc='h80;
      retired=0; loads=0; stores=0; branches_taken=0; branches_not_taken=0; jumps=0; signature=0; done=0;
      foreach(branch_hits[i]) branch_hits[i]=0;
      foreach(corner_hits[i]) corner_hits[i]=0;
      last_rd=0; last_load=0; irq_count=0; mret_count=0; parking_seen=0; global_mie=0;
      csr_mie=0; csr_mtvec=0; csr_mcause=0; csr_mepc=0; irq_input_active=0;
    end
  endfunction
  function void write_data_rsp(ibex_mem_txn t); responses.push_back(t); endfunction
  function void write_instr_rsp(ibex_mem_txn t);
    if(t.err!==0 || t.data!==image.instruction(t.address & 32'hffff_fffc))
      `uvm_error("IFETCH_DATA",$sformatf("Bad instruction response at %08x",t.address))
  endfunction
  function void check_bus(bit [31:0] addr,bit write_access,bit [31:0] value);
    ibex_mem_txn req,rsp;
    if(requests.size()==0 || responses.size()==0) begin
      `uvm_error("MEM_MISSING","Retired memory operation lacks observed request/response")
      return;
    end
    req=requests.pop_front(); rsp=responses.pop_front();
    if(req.address!==addr || req.write!==write_access || req.be!==4'hf)
      `uvm_error("MEM_REQUEST",$sformatf("Expected %s address=%08x mask=f, got address=%08x write=%b mask=%x",
        write_access?"store":"load",addr,req.address,req.write,req.be))
    if(write_access && req.data!==value)
      `uvm_error("MEM_STORE_DATA",$sformatf("Expected store data %08x got %08x",value,req.data))
    if(rsp.err!==0 || rsp.address!==addr || rsp.write!==write_access)
      `uvm_error("MEM_RESPONSE","Incorrect memory response identity or error")
    if(!write_access && rsp.data!==value)
      `uvm_error("MEM_LOAD_DATA",$sformatf("Expected load data %08x got %08x",value,rsp.data))
  endfunction
  function void write_retire(ibex_retirement t);
    bit [31:0] insn,next_pc,result,address,imm,value;
    bit [6:0] opcode;
    int rd,rs1,rs2,funct3;
    bit writes,uses_rs1,uses_rs2,taken;
    bit [11:0] events;
    bit interrupt_entry;
    int csr_address;
    if(done) return;
    if($isunknown({t.order,t.pc,t.insn,t.rd,t.rd_data,t.trap,t.halt,t.intr})) begin
      `uvm_error("RVFI_X","Unknown architectural retirement fields")
      return;
    end
    // The CPU adapter configures native order origin; expected state is shared.
    if(t.order!==64'(retired+order_base)) `uvm_error("RVFI_ORDER","Missing, duplicate or reordered retirement")
    interrupt_entry=0;
    if(image.profile_id==3 && expected_pc=='h9c && t.pc=='h22c && t.intr===1'b1) begin
      if(!irq_input_active || !global_mie || !csr_mie[11] || csr_mtvec!='h201 || irq_count!=0)
        `uvm_error("IRQ_ENTRY","Interrupt entry contradicts independent enable/event state")
      csr_mepc='h9c; csr_mcause='h8000000b; global_mie=0; irq_count++;
      expected_pc='h22c; interrupt_entry=1;
    end
    if(t.pc!==expected_pc)
      `uvm_error("RVFI_PC",$sformatf("Expected PC %08x got %08x",expected_pc,t.pc))
    if(!image.valid_instruction(expected_pc)) begin
      `uvm_fatal("MODEL_PC","Reference PC escaped the test image")
    end
    insn=image.instruction(expected_pc);
    if(t.insn!==insn) `uvm_error("RVFI_INSN","Retired instruction differs from loaded image")
    if(t.trap!==0 || t.halt!==0 || t.intr!==(interrupt_entry?1'b1:1'b0))
      `uvm_error("RVFI_TRAP","Unexpected trap, halt or interrupt in smoke")
    opcode=insn[6:0]; rd=int'(insn[11:7]); rs1=int'(insn[19:15]);
    rs2=int'(insn[24:20]); funct3=int'(insn[14:12]);
    next_pc=expected_pc+4; result=0; address=0; value=0;
    writes=0; uses_rs1=0; uses_rs2=0; taken=0;
    case(opcode)
      7'h13: begin
        if(funct3!=0) `uvm_fatal("MODEL_ISA","Only ADDI is implemented in initial OP-IMM model")
        imm={{20{insn[31]}},insn[31:20]};
        result=regs[rs1]+imm; writes=1; uses_rs1=1;
      end
      7'h33: begin
        uses_rs1=1; uses_rs2=1; writes=1;
        case({insn[31:25],insn[14:12]})
          10'b0000000_000: result=regs[rs1]+regs[rs2];
          10'b0100000_000: result=regs[rs1]-regs[rs2];
          10'b0000000_100: result=regs[rs1]^regs[rs2];
          10'b0000000_111: result=regs[rs1]&regs[rs2];
          10'b0000000_110: result=regs[rs1]|regs[rs2];
          10'b0000000_010: result=32'($signed(regs[rs1]) < $signed(regs[rs2]));
          10'b0000000_011: result=32'(regs[rs1] < regs[rs2]);
          10'b0000000_001: result=regs[rs1] << regs[rs2][4:0];
          10'b0000000_101: result=regs[rs1] >> regs[rs2][4:0];
          10'b0100000_101: result=$signed(regs[rs1]) >>> regs[rs2][4:0];
          default: `uvm_fatal("MODEL_ISA","Unsupported register ALU instruction")
        endcase
      end
      7'h37: begin result={insn[31:12],12'b0}; writes=1; end
      7'h03: begin
        if(funct3!=2) `uvm_fatal("MODEL_ISA","Initial load model supports LW only")
        uses_rs1=1; writes=1; imm={{20{insn[31]}},insn[31:20]};
        address=regs[rs1]+imm;
        value=memory.exists(address)?memory[address]:0; result=value; loads++;
        check_bus(address,0,value);
        if(t.mem_addr!==address || t.mem_rmask!==4'hf || t.mem_wmask!==0 || t.mem_rdata!==value)
          `uvm_error("RVFI_LOAD","Load address/mask/value differs from private reference memory")
      end
      7'h23: begin
        if(funct3!=2) `uvm_fatal("MODEL_ISA","Initial store model supports SW only")
        uses_rs1=1; uses_rs2=1;
        imm={{20{insn[31]}},insn[31:25],insn[11:7]};
        address=regs[rs1]+imm; value=regs[rs2]; stores++;
        check_bus(address,1,value);
        if(t.mem_addr!==address || t.mem_wmask!==4'hf || t.mem_wdata!==value)
          `uvm_error("RVFI_STORE","Store address/mask/data differs from expected architectural effect")
        memory[address]=value;
        if(address=='h1004) begin
          signature=value;
          if(value!=1 || expected_pc!=image.terminal_pc) `uvm_error("SIGNATURE","Unexpected terminal signature")
          done=1;
        end
      end
      7'h63: begin
        uses_rs1=1; uses_rs2=1;
        imm={{19{insn[31]}},insn[31],insn[7],insn[30:25],insn[11:8],1'b0};
        if(funct3==0) taken=(regs[rs1]==regs[rs2]);
        else if(funct3==1) taken=(regs[rs1]!=regs[rs2]);
        else `uvm_fatal("MODEL_ISA","Initial branch model supports BEQ/BNE only")
        if(taken) begin next_pc=expected_pc+imm; branches_taken++; end
        else branches_not_taken++;
        branch_hits[(funct3==1?2:0)+(taken?0:1)]++;
      end
      7'h6f: begin
        imm={{11{insn[31]}},insn[31],insn[19:12],insn[20],insn[30:21],1'b0};
        result=expected_pc+4; writes=1; next_pc=expected_pc+imm; jumps++;
      end
      7'h73: begin
        if(image.profile_id!=3) `uvm_fatal("MODEL_ISA","CSR/MRET requires the declared IRQ contract")
        if(insn==32'h30200073) begin
          if(irq_count!=1 || mret_count!=0 || csr_mepc!='h9c) `uvm_error("MRET_STATE","Invalid interrupt return state")
          next_pc=csr_mepc; global_mie=1; mret_count++;
        end else begin
          csr_address=int'(insn[31:20]); uses_rs1=(funct3==1 || funct3==2); writes=1;
          case(csr_address)
            'h300: result=global_mie?8:0;
            'h304: result=csr_mie;
            'h305: result=csr_mtvec;
            'h341: result=csr_mepc;
            'h342: result=csr_mcause;
            default: `uvm_fatal("MODEL_CSR","Unsupported IRQ CSR")
          endcase
          value=funct3==6?32'(rs1):regs[rs1];
          if(funct3!=1 && funct3!=2 && funct3!=6) `uvm_fatal("MODEL_CSR","Unsupported CSR operation")
          if(funct3==1 || value!=0) begin
            if(funct3==2 || funct3==6) value=value|result;
            case(csr_address)
              'h300: global_mie=value[3];
              'h304: csr_mie=value & 'h800;
              'h305: csr_mtvec=(value & 'hffffff00)|1;
              default: `uvm_fatal("MODEL_CSR","CSR write outside IRQ setup contract")
            endcase
          end
        end
      end
      default: `uvm_fatal("MODEL_ISA",$sformatf("Unsupported opcode %02x",opcode))
    endcase
    if(uses_rs1 && (t.rs1!==5'(rs1) || t.rs1_data!==regs[rs1]))
      `uvm_error("RVFI_RS1","Source register 1 differs from independent model")
    if(uses_rs2 && (t.rs2!==5'(rs2) || t.rs2_data!==regs[rs2]))
      `uvm_error("RVFI_RS2","Source register 2 differs from independent model")
    if(t.rd!==5'(writes?rd:0) || (writes && rd!=0 && t.rd_data!==result))
      `uvm_error("RVFI_RD",$sformatf("PC=%08x expected rd=%0d data=%08x got rd=%0d data=%08x",
        expected_pc,writes?rd:0,result,t.rd,t.rd_data))
    events='0;
    if(opcode=='h33 && insn[31:25]==0 && funct3==0) begin
      events[0]=(regs[rs1]=='hffffffff && regs[rs2]==1 && result==0);
      events[1]=(regs[rs1]=='h7fffffff && regs[rs2]==1 && result=='h80000000);
    end
    events[2]=(opcode=='h33 && insn[31:25]=='h20 && funct3==0 && regs[rs1]==0 && regs[rs2]==1 && result=='hffffffff);
    events[3]=(opcode=='h13 && insn[31:20]=='h800 && rs1==0);
    events[4]=(opcode=='h13 && insn[31:20]=='h7ff && rs1==0);
    events[5]=(writes && rd==0 && result!=0);
    events[6]=(writes && rd!=0 && uses_rs1 && rd==rs1);
    events[7]=(writes && rd!=0 && uses_rs2 && rd==rs2);
    events[8]=(last_load && last_rd!=0 && ((uses_rs1 && rs1==last_rd)||(uses_rs2 && rs2==last_rd)));
    events[9]=((opcode==3 || opcode=='h23) && imm[31]);
    events[10]=((writes && rd==31)||(uses_rs1 && rs1==31)||(uses_rs2 && rs2==31));
    events[11]=(opcode=='h33 && (funct3==1 || funct3==5) && regs[rs2]==32);
    foreach(corner_hits[i]) if(events[i]) corner_hits[i]++;
    last_rd=writes?rd:0; last_load=(opcode==3);
    if(writes && rd!=0) regs[rd]=result;
    regs[0]=0; expected_pc=next_pc; retired++;
    if(image.profile_id==3 && t.pc=='h9c && !interrupt_entry) parking_seen=1;
`ifdef IBEX_UVM_FULL
    retire_cg.sample(opcode,taken,3'(funct3));
    corner_cg.sample(events,opcode=='h33,{insn[31:25],insn[14:12]});
    if(image.profile_id==2 && t.pc>='h13c && t.pc<'h23c) begin
      random_kind_cg.sample(opcode);
      if(opcode=='h33) random_alu_cg.sample({insn[31:25],insn[14:12]});
      if(opcode==3 || opcode=='h23) random_memory_cg.sample(address[5:2]);
    end
`endif
  endfunction
  function void check_phase(uvm_phase phase);
    if(image.profile_id==3) begin
      if(!done || retired<15 || retired>1000 || loads!=0 || stores!=1 || branches_taken<1 || branches_not_taken!=1 ||
          jumps!=0 || signature!=1 || irq_count!=1 || mret_count!=1)
        `uvm_error("IRQ_COMPLETION","Interrupt handler/return/mainline contract did not complete")
    end else if(!done || retired!=image.expected_retired || loads!=image.expected_loads || stores!=image.expected_stores ||
       branches_taken!=image.expected_taken || branches_not_taken!=image.expected_not_taken ||
       jumps!=image.expected_jumps || signature!=1)
      `uvm_error("SCENARIOS","Mandatory smoke scenarios did not all complete")
    if(image.profile_id==1 || image.profile_id==2) begin
      foreach(branch_hits[i]) if(branch_hits[i]==0) `uvm_error("BRANCH_HOLE","Missing BEQ/BNE outcome")
      foreach(corner_hits[i]) if(corner_hits[i]==0) `uvm_error("CORNER_HOLE",$sformatf("Missing corner goal %0d",i))
    end
    if(requests.size()!=0 || responses.size()!=0)
      `uvm_error("MEM_EXTRA","Unmatched observed data transactions at completion")
  endfunction
endclass

// Preserve the original public name for existing environment extensions.
typedef riscv_scoreboard ibex_scoreboard;
