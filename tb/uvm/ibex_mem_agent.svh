// This file is included inside ibex_uvm_pkg after ibex_program is declared.
// Only the passive monitor publishes observations; the responder's private RAM
// is not exposed to the architectural scoreboard.
class ibex_mem_txn extends uvm_sequence_item;
  `uvm_object_utils(ibex_mem_txn)
  logic [31:0] address, data;
  logic [3:0] be;
  logic write, is_response;
  logic err;
  function new(string name="ibex_mem_txn"); super.new(name); endfunction
endclass

class ibex_delay_item extends uvm_sequence_item;
  `uvm_object_utils(ibex_delay_item)
  rand int unsigned grant_delay, response_delay;
  int unsigned max_delay;
`ifdef IBEX_UVM_FULL
  constraint bounded_delays {
    grant_delay inside {[0:max_delay]};
    response_delay inside {[0:max_delay]};
  }
`endif
  function new(string name="ibex_delay_item"); super.new(name); endfunction
endclass

class ibex_delay_sequence extends uvm_sequence #(ibex_delay_item);
  `uvm_object_utils(ibex_delay_sequence)
  int unsigned seed=1;
  int unsigned max_delay=0;
  static int unsigned randomize_calls=0;
  function new(string name="ibex_delay_sequence"); super.new(name); endfunction
  function int unsigned next_random();
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    return seed;
  endfunction
  task body();
    ibex_delay_item item;
    if(seed==0) seed=1;
    forever begin
      item=ibex_delay_item::type_id::create("delay_policy");
      item.max_delay=max_delay;
      start_item(item);
`ifdef IBEX_UVM_FULL
      if(!item.randomize())
        `uvm_fatal("IBEX_RANDOMIZE", "Memory delay constraints have no solution")
      randomize_calls++;
`else
      // Starter mode executes a seeded procedural PRNG, not SV randomization.
      item.grant_delay=next_random()%(max_delay+1);
      item.response_delay=next_random()%(max_delay+1);
`endif
      finish_item(item);
    end
  endtask
endclass

class ibex_mem_driver extends uvm_driver #(ibex_delay_item);
  `uvm_component_utils(ibex_mem_driver)
  virtual ibex_mem_if vif;
  ibex_program image;
  int is_instr=0;
  protected bit [31:0] mem[bit [31:0]];
  function new(string name, uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(!uvm_config_db#(virtual ibex_mem_if)::get(this,"","vif",vif))
      `uvm_fatal("IBEX_CONFIG", "Memory driver virtual interface is missing")
    if(!uvm_config_db#(ibex_program)::get(this,"","program",image))
      `uvm_fatal("IBEX_CONFIG", "Memory driver program image is missing")
    void'(uvm_config_db#(int)::get(this,"","is_instr",is_instr));
  endfunction
  function void clear_outputs();
    vif.gnt=0; vif.rvalid=0; vif.rdata=0; vif.err=0;
  endfunction
  task respond(ibex_delay_item policy);
    bit [31:0] address, write_data, reply, key;
    bit [3:0] byte_enable;
    bit write_request;
    repeat(policy.grant_delay) begin
      @(negedge vif.clk);
      if(!vif.rst_n) begin clear_outputs(); mem.delete(); return; end
    end
    if(vif.req!==1'b1)
      `uvm_fatal("IBEX_MEM_WITHDRAWN", "Request disappeared before its grant")
    if($isunknown({vif.addr,vif.we,vif.be}) ||
        (vif.we && $isunknown(vif.wdata)))
      `uvm_fatal("IBEX_MEM_REQUEST_X", "Accepted memory request has unknown payload")
    address=vif.addr; write_data=vif.wdata;
    byte_enable=vif.be; write_request=vif.we;
    key=address & 32'hffff_fffc;
    if(address>=32'h0001_0000)
      `uvm_error("IBEX_MEM_RANGE", $sformatf("Unexpected address %08x",address))
    vif.gnt=1;
    @(posedge vif.clk);
    // Acceptance is sampled on this edge. Payload was set on the falling edge.
    if(!vif.rst_n) begin clear_outputs(); mem.delete(); return; end
    if(is_instr) begin
      if(write_request) `uvm_error("IBEX_INSTR_WRITE", "Instruction port issued a write")
      reply=image.instruction(key);
    end else begin
      if(!mem.exists(key)) mem[key]=0;
      if(write_request) begin
        for(int lane=0;lane<4;lane++)
          if(byte_enable[lane]) mem[key][lane*8+:8]=write_data[lane*8+:8];
      end
      reply=mem[key];
    end
    @(negedge vif.clk);
    vif.gnt=0;
    if(!vif.rst_n) begin clear_outputs(); mem.delete(); return; end
    repeat(policy.response_delay) begin
      @(negedge vif.clk);
      if(!vif.rst_n) begin clear_outputs(); mem.delete(); return; end
    end
    vif.rdata=reply; vif.err=0; vif.rvalid=1;
    @(negedge vif.clk);
    vif.rvalid=0;
  endtask
  task run_phase(uvm_phase phase);
    clear_outputs();
    forever begin
      @(negedge vif.clk);
      if(!vif.rst_n) begin clear_outputs(); mem.delete(); continue; end
      if(vif.req!==1'b1) continue;
      seq_item_port.get_next_item(req);
      respond(req);
      seq_item_port.item_done();
    end
  endtask
endclass

class ibex_mem_monitor extends uvm_monitor;
  `uvm_component_utils(ibex_mem_monitor)
  virtual ibex_mem_if vif;
  uvm_analysis_port #(ibex_mem_txn) request_ap, response_ap;
  ibex_mem_txn pending[$];
  int unsigned requests, responses, grant_stalls, response_waits;
  function new(string name, uvm_component parent);
    super.new(name,parent);
    request_ap=new("request_ap",this); response_ap=new("response_ap",this);
  endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(!uvm_config_db#(virtual ibex_mem_if)::get(this,"","vif",vif))
      `uvm_fatal("IBEX_CONFIG", "Memory monitor virtual interface is missing")
  endfunction
  task run_phase(uvm_phase phase);
    ibex_mem_txn item, accepted;
    forever begin
      @(vif.mon);
      if(!vif.mon.rst_n) begin
        pending.delete(); requests=0; responses=0;
        grant_stalls=0; response_waits=0;
        continue;
      end
      if(vif.mon.gnt && !vif.mon.req)
        `uvm_error("IBEX_MEM_GRANT", "Grant without an asserted request")
      // Responses are at least one cycle after acceptance in this responder.
      if(vif.mon.rvalid) begin
        if(pending.size()==0)
          `uvm_error("IBEX_MEM_UNSOLICITED", "Response has no outstanding request")
        else begin
          accepted=pending.pop_front();
          item=ibex_mem_txn::type_id::create("memory_response");
          item.address=accepted.address; item.write=accepted.write;
          item.be=accepted.be; item.data=vif.mon.rdata;
          item.err=vif.mon.err; item.is_response=1;
          responses++; response_ap.write(item);
        end
      end else if(pending.size()!=0) response_waits++;
      if(vif.mon.req && !vif.mon.gnt) grant_stalls++;
      if(vif.mon.req && vif.mon.gnt) begin
        if($isunknown({vif.mon.addr,vif.mon.we,vif.mon.be}) ||
            (vif.mon.we && $isunknown(vif.mon.wdata)))
          `uvm_error("IBEX_MEM_REQUEST_X", "Accepted memory request has unknown payload")
        item=ibex_mem_txn::type_id::create("memory_request");
        item.address=vif.mon.addr; item.data=vif.mon.wdata;
        item.write=vif.mon.we; item.be=vif.mon.be;
        item.err=0; item.is_response=0;
        pending.push_back(item); requests++; request_ap.write(item);
      end
    end
  endtask
endclass

class ibex_mem_agent extends uvm_agent;
  `uvm_component_utils(ibex_mem_agent)
  uvm_sequencer #(ibex_delay_item) sequencer;
  ibex_mem_driver driver;
  ibex_mem_monitor monitor;
  int is_instr=0;
  int max_delay=0;
  int unsigned seed=1;
  function new(string name, uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    void'(uvm_config_db#(int)::get(this,"","is_instr",is_instr));
    void'(uvm_config_db#(int)::get(this,"","max_delay",max_delay));
    void'(uvm_config_db#(int unsigned)::get(this,"","seed",seed));
    if(max_delay<0 || max_delay>100)
      `uvm_fatal("IBEX_CONFIG", "max_delay must be in 0..100")
    monitor=ibex_mem_monitor::type_id::create("monitor",this);
    if(get_is_active()==UVM_ACTIVE) begin
      sequencer=uvm_sequencer#(ibex_delay_item)::type_id::create("sequencer",this);
      driver=ibex_mem_driver::type_id::create("driver",this);
      uvm_config_db#(int)::set(this,"driver","is_instr",is_instr);
    end
  endfunction
  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    if(get_is_active()==UVM_ACTIVE)
      driver.seq_item_port.connect(sequencer.seq_item_export);
  endfunction
  task run_phase(uvm_phase phase);
    ibex_delay_sequence sequence_policy;
    bit auto_policy=1;
    void'(uvm_config_db#(bit)::get(this,"","auto_policy",auto_policy));
    if(get_is_active()==UVM_ACTIVE && auto_policy) begin
      sequence_policy=ibex_delay_sequence::type_id::create("memory_delay_sequence");
      sequence_policy.max_delay=max_delay;
      sequence_policy.seed=seed ^ (is_instr ? 32'h1357_9bdf : 32'h2468_ace1);
      sequence_policy.start(sequencer);
    end
  endtask
endclass
