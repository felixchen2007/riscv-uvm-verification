// Encoders build stimulus only. The checker independently decodes the ISA.
`include "riscv_instruction_item.svh"
class ibex_program extends uvm_object;
  `uvm_object_utils(ibex_program)
  bit [31:0] image[bit [31:0]];
  int unsigned operand;
  int profile_id=0;
  int expected_retired=14,expected_loads=1,expected_stores=2;
  int expected_taken=1,expected_not_taken=1,expected_jumps=1;
  bit [31:0] terminal_pc='hbc;
  bit [31:0] cursor;
  int unsigned program_seed,instruction_randomize_calls,schedule_randomize_calls;
  function new(string name="ibex_program"); super.new(name); endfunction
  function bit [31:0] enc_i(int imm, int rs1, int funct3, int rd, int opcode);
    return {12'(imm),5'(rs1),3'(funct3),5'(rd),7'(opcode)};
  endfunction
  function bit [31:0] enc_r(int funct7, int rs2, int rs1, int funct3, int rd);
    return {7'(funct7),5'(rs2),5'(rs1),3'(funct3),5'(rd),7'h33};
  endfunction
  function bit [31:0] enc_s(int imm, int rs2, int rs1);
    bit [11:0] v=12'(imm);
    return {v[11:5],5'(rs2),5'(rs1),3'b010,v[4:0],7'h23};
  endfunction
  function bit [31:0] enc_b(int imm, int rs2, int rs1, int funct3);
    bit [12:0] v=13'(imm);
    return {v[12],v[10:5],5'(rs2),5'(rs1),3'(funct3),v[4:1],v[11],7'h63};
  endfunction
  function bit [31:0] enc_j(int imm, int rd);
    bit [20:0] v=21'(imm);
    return {v[20],v[10:1],v[11],v[19:12],5'(rd),7'h6f};
  endfunction
  function void build_image(int unsigned seed,int program_id=0);
    image.delete();
    operand=(seed % 31)+1;
    program_seed=seed; instruction_randomize_calls=0; schedule_randomize_calls=0;
    profile_id=program_id;
    expected_retired=14; expected_loads=1; expected_stores=2;
    expected_taken=1; expected_not_taken=1; expected_jumps=1; terminal_pc='hbc;
    if(program_id==1) begin build_corners(); return; end
    if(program_id==2) begin build_random(); return; end
    if(program_id==3) begin build_irq(); return; end
    if(program_id!=0) `uvm_fatal("PROGRAM_CONFIG","Unknown program profile")
    image['h80]=enc_i(operand,0,0,1,'h13); // addi x1,x0,seed-derived value
    image['h84]=enc_i(-3,0,0,2,'h13);
    image['h88]=enc_r(0,2,1,0,3);          // add x3,x1,x2
    image['h8c]=enc_r('h20,2,1,0,4);       // sub x4,x1,x2
    image['h90]=enc_r(0,4,3,4,5);          // xor x5,x3,x4
    image['h94]=32'h00001337;             // lui x6,0x1
    image['h98]=enc_s(0,5,6);             // sw x5,0(x6)
    image['h9c]=enc_i(0,6,2,7,'h03);      // lw x7,0(x6)
    image['ha0]=enc_b(8,5,7,0);           // beq taken
    image['ha4]=enc_i(1,0,0,8,'h13);      // poison path, must not retire
    image['ha8]=enc_b(8,5,7,1);           // bne not taken
    image['hac]=enc_i(0,0,0,8,'h13);
    image['hb0]=enc_j(8,9);               // jal with link result
    image['hb4]=enc_i(2,0,0,8,'h13);      // second poison path
    image['hb8]=enc_i(1,0,0,10,'h13);
    image['hbc]=enc_s(4,10,6);            // terminal signature: [0x1004]=1
    image['hc0]=enc_j(0,0);               // safe parking loop
  endfunction
  function void build_random();
`ifdef IBEX_UVM_FULL
    riscv_instruction_item item;
    riscv_instruction_schedule schedule;
    bit [31:0] insn;
    int previous_rd=0,fd,index=0,choice,funct3,funct7;
    build_corners();
    image.delete(terminal_pc); image.delete(terminal_pc+4);
    cursor=terminal_pc; terminal_pc+=64*4;
    expected_retired+=64; expected_loads+=8; expected_stores+=8;
    item=riscv_instruction_item::type_id::create("random_instruction");
    schedule=riscv_instruction_schedule::type_id::create("random_schedule");
    // Local RNG streams must not depend on CPU topology or memory timing RNGs.
    item.srandom(program_seed^32'h739a_4101);
    schedule.srandom(program_seed^32'hbf30_6a27);
    fd=$fopen("program-generation.json","w");
    if(!fd) `uvm_fatal("GENERATION_FILE","Cannot write program-generation.json")
    $fdisplay(fd,"{\"schema_version\":1,\"program_profile\":\"random\",\"seed\":%0d,\"instruction_calls\":64,\"schedule_calls\":8,\"body_start\":316,\"body_end\":572,\"items\":[",program_seed);
    for(int block=0;block<8;block++) begin
      if(!schedule.randomize()) `uvm_fatal("PROGRAM_RANDOMIZE","No legal instruction schedule")
      schedule_randomize_calls++;
      for(int pos=0;pos<8;pos++) begin
        choice=schedule.order[pos];
        item.kind=choice<4?0:choice-3;
        item.previous_rd=previous_rd;
        if(!item.randomize()) `uvm_fatal("PROGRAM_RANDOMIZE","No legal constrained instruction")
        instruction_randomize_calls++;
        funct3=0; funct7=0;
        case(item.kind)
          0: begin
            case(item.alu_kind)
              0: begin funct3=0; funct7=0; end
              1: begin funct3=0; funct7='h20; end
              2: funct3=1;
              3: funct3=2;
              4: funct3=3;
              5: funct3=4;
              6: funct3=5;
              7: begin funct3=5; funct7='h20; end
              8: funct3=6;
              9: funct3=7;
            endcase
            insn=enc_r(funct7,item.rs2,item.rs1,funct3,item.rd);
          end
          1: insn=enc_i(item.immediate,item.rs1,0,item.rd,'h13);
          2: insn={item.upper,5'(item.rd),7'h37};
          3: insn=enc_i(item.slot*4,6,2,item.rd,'h03);
          4: insn=enc_s(item.slot*4,item.rs2,6);
          default: `uvm_fatal("PROGRAM_KIND","Unknown constrained instruction kind")
        endcase
        $fdisplay(fd,"%s{\"pc\":%0d,\"insn\":%0d,\"kind\":%0d,\"rd\":%0d,\"rs1\":%0d,\"rs2\":%0d,\"dependency\":%0d,\"previous_rd\":%0d}",
          index==0?"":",",cursor,insn,item.kind,item.rd,item.rs1,item.rs2,item.dependency,item.previous_rd);
        emit(insn); index++;
        previous_rd=item.kind==4?0:item.rd;
      end
    end
    $fdisplay(fd,"]}"); $fclose(fd);
    if(cursor!=terminal_pc) `uvm_fatal("PROGRAM_LAYOUT","Random body escaped its bound")
    emit(enc_s(4,27,6)); emit(enc_j(0,0));
`else
    `uvm_fatal("PROGRAM_MODE","Random instructions require --full SV constrained randomization")
`endif
  endfunction
  function void emit(bit [31:0] insn);
    image[cursor]=insn; cursor+=4;
  endfunction
  function void build_irq();
    expected_retired=15; expected_loads=0; expected_stores=1;
    expected_taken=1; expected_not_taken=1; expected_jumps=0; terminal_pc='ha4;
    image['h80]=32'h00001337;
    image['h84]=enc_i('h201,0,0,1,'h13);
    image['h88]=enc_i('h305,1,1,0,'h73); // CSRRW mtvec=201, vectored MEI handler=22c.
    image['h8c]=32'h00001137;
    image['h90]=enc_i(-2048,2,0,2,'h13);
    image['h94]=enc_i('h304,2,1,0,'h73); // mie.MEIE=1.
    image['h98]=enc_i('h300,8,6,0,'h73); // CSRRSI mstatus.MIE=1.
    image['h9c]=enc_b(0,0,20,0);        // Remain here until ISR sets x20.
    image['ha0]=enc_i(1,0,0,10,'h13);
    image['ha4]=enc_s(4,10,6);
    image['ha8]=enc_j(0,0);
    image['h22c]=enc_i('h342,0,2,11,'h73); // CSRRS mcause -> 8000000b.
    image['h230]=enc_i('h341,0,2,12,'h73); // CSRRS mepc -> 9c.
    image['h234]=enc_i(1,0,0,20,'h13);
    image['h238]=32'h30200073;             // MRET -> 9c, then mainline completion.
  endfunction
  function void build_corners();
    expected_retired=47; expected_loads=3; expected_stores=4;
    expected_taken=3; expected_not_taken=3; expected_jumps=1;
    terminal_pc='h13c; cursor='h80;
    emit(enc_i(-1,0,0,1,'h13));          // x1=ffffffff
    emit(enc_i(1,0,0,2,'h13));
    emit(enc_r(0,2,1,0,3));             // unsigned addition wraps to zero
    emit(32'h80000237);                 // lui x4,80000
    emit(enc_i(-1,4,0,4,'h13));         // x4=7fffffff; rd aliases rs1
    emit(enc_r(0,2,4,0,5));             // x5=80000000
    emit(enc_r('h20,2,0,0,7));          // 0-1=ffffffff
    emit(enc_i(-2048,0,0,8,'h13));
    emit(enc_i(2047,0,0,9,'h13));
    emit(enc_i(123,0,0,0,'h13));         // x0 write must be discarded
    emit(enc_i(7,0,0,10,'h13));
    emit(enc_r(0,2,10,0,10));
    emit(enc_r(0,10,2,0,10));           // rd aliases rs2
    emit(enc_r(0,5,1,4,11));            // XOR
    emit(enc_r(0,5,1,7,12));            // AND
    emit(enc_r(0,9,5,6,13));            // OR
    emit(enc_r(0,2,5,2,14));            // signed SLT: 80000000 < 1
    emit(enc_r(0,2,5,3,15));            // unsigned SLTU: 80000000 > 1
    emit(enc_i(31,0,0,16,'h13));
    emit(enc_r(0,16,2,1,17));           // SLL by 31
    emit(enc_r(0,16,5,5,18));           // SRL by 31
    emit(enc_r('h20,16,5,5,19));        // SRA by 31
    emit(enc_i(32,0,0,16,'h13));
    emit(enc_r(0,16,2,1,20));           // shift count uses low five bits
    emit(enc_i(operand,0,0,31,'h13));
    emit(enc_r(0,2,31,0,31));           // high-register dependency
    emit(32'h00001337);                 // base x6=1000
    emit(enc_s(0,31,6));
    emit(enc_i(0,6,2,21,'h03));
    emit(enc_r(0,2,21,0,22));           // immediate load-use dependency
    emit(enc_s(8,22,6));
    emit(enc_i(12,6,0,23,'h13));
    emit(enc_i(-4,23,2,24,'h03));       // negative load offset
    emit(enc_s(-12,24,23));             // negative store offset and overwrite
    emit(enc_i(0,6,2,24,'h03));
    emit(enc_b(8,31,21,0));             // BEQ taken at 10c
    emit(enc_i(99,0,0,28,'h13));        // poison path
    emit(enc_b(8,31,21,1));             // BNE not taken at 114
    emit(enc_b(8,0,2,0));               // BEQ not taken at 118
    emit(enc_b(8,0,2,1));               // BNE taken at 11c
    emit(enc_i(98,0,0,28,'h13));        // poison path
    emit(enc_i(2,0,0,25,'h13));
    emit(enc_i(-1,25,0,25,'h13));       // bounded loop body at 128
    emit(enc_b(-4,0,25,1));             // BNE taken then not taken
    emit(enc_j(8,26));
    emit(enc_i(97,0,0,28,'h13));        // poison after JAL
    emit(enc_i(1,0,0,27,'h13));
    if(cursor!=terminal_pc) `uvm_fatal("PROGRAM_LAYOUT","Corner terminal address changed")
    emit(enc_s(4,27,6));
    emit(enc_j(0,0));
  endfunction
  function bit valid_instruction(bit [31:0] address);
    return image.exists(address);
  endfunction
  function bit [31:0] instruction(bit [31:0] address);
    return image.exists(address) ? image[address] : 32'h00000013;
  endfunction
  function void write_image();
    int fd=$fopen("program.hex","w");
    string profile_name;
    if (!fd) `uvm_fatal("IMAGE_FILE","Cannot write program.hex")
    foreach(image[a]) $fdisplay(fd,"@%08x %08x",a>>2,image[a]);
    $fclose(fd);
    if(profile_id!=2) begin
      if(profile_id==0) profile_name="smoke";
      else if(profile_id==1) profile_name="corners";
      else profile_name="irq";
      fd=$fopen("program-generation.json","w");
      if(!fd) `uvm_fatal("GENERATION_FILE","Cannot write directed generation metadata")
      $fdisplay(fd,"{\"schema_version\":1,\"program_profile\":\"%s\",\"seed\":%0d,\"instruction_calls\":0,\"schedule_calls\":0,\"items\":[]}",profile_name,program_seed);
      $fclose(fd);
    end
  endfunction
endclass
