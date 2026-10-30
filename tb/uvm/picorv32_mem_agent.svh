// Pico-specific physical protocol; shared sequence items, image and TLM records.
class picorv32_mem_driver extends uvm_driver #(ibex_delay_item);
  `uvm_component_utils(picorv32_mem_driver)
  virtual picorv32_mem_if vif;
  ibex_program image;
  protected bit [31:0] memory[bit [31:0]];
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(!uvm_config_db#(virtual picorv32_mem_if)::get(this,"","vif",vif) ||
       !uvm_config_db#(ibex_program)::get(this,"","program",image))
      `uvm_fatal("PICO_CONFIG","Missing physical interface or program")
  endfunction
  task run_phase(uvm_phase phase);
    bit [31:0] address,value,key;
    bit [3:0] mask;
    bit instruction,aborted;
    vif.ready=0; vif.rdata=0;
    forever begin
      @(negedge vif.clk);
      if(!vif.rst_n) begin vif.ready=0; memory.delete(); continue; end
      if(vif.valid!==1) continue;
      seq_item_port.get_next_item(req);
      // Unified Pico completion combines the shared request/response delays.
      aborted=0;
      repeat(req.grant_delay+req.response_delay) begin
        @(negedge vif.clk);
        if(!vif.rst_n) begin aborted=1; break; end
      end
      if(aborted || !vif.rst_n) begin
        vif.ready=0; memory.delete(); seq_item_port.item_done(); continue;
      end
      if(vif.valid!==1 || $isunknown({vif.addr,vif.instr,vif.wstrb}) ||
         ((|vif.wstrb) && $isunknown(vif.wdata)))
        `uvm_fatal("PICO_REQUEST","Invalid memory request before completion")
      address=vif.addr; key=address & 32'hffff_fffc;
      value=vif.wdata; mask=vif.wstrb; instruction=vif.instr;
      if(address>=32'h10000 || address[1:0]!=0)
        `uvm_error("PICO_RANGE","Request outside aligned smoke memory")
      if(instruction) begin
        if(mask!=0) `uvm_error("PICO_INSTR_WRITE","Instruction fetch attempted write")
        vif.rdata=image.instruction(key);
      end else begin
        if(!memory.exists(key)) memory[key]=0;
        vif.rdata=memory[key];
      end
      vif.ready=1;
      @(posedge vif.clk);
      if(vif.rst_n && !instruction && mask!=0)
        for(int lane=0;lane<4;lane++) if(mask[lane]) memory[key][8*lane+:8]=value[8*lane+:8];
      @(negedge vif.clk);
      vif.ready=0;
      seq_item_port.item_done();
    end
  endtask
endclass

class picorv32_mem_monitor extends uvm_monitor;
  `uvm_component_utils(picorv32_mem_monitor)
  virtual picorv32_mem_if vif;
  uvm_analysis_port #(ibex_mem_txn) instr_response_ap,data_request_ap,data_response_ap;
  int unsigned instr_stalls,data_stalls,instr_transfers,data_transfers;
  function new(string name,uvm_component parent);
    super.new(name,parent);
    instr_response_ap=new("instr_response_ap",this);
    data_request_ap=new("data_request_ap",this); data_response_ap=new("data_response_ap",this);
  endfunction
  function void build_phase(uvm_phase phase);
    if(!uvm_config_db#(virtual picorv32_mem_if)::get(this,"","vif",vif))
      `uvm_fatal("PICO_CONFIG","Missing passive monitor interface")
  endfunction
  task run_phase(uvm_phase phase);
    ibex_mem_txn request,response;
    forever begin
      @(vif.mon);
      if(!vif.mon.rst_n) begin instr_stalls=0; data_stalls=0; instr_transfers=0; data_transfers=0; continue; end
      if(vif.mon.valid && !vif.mon.ready) begin
        if(vif.mon.instr) instr_stalls++; else data_stalls++;
      end
      if(vif.mon.valid && vif.mon.ready) begin
        if($isunknown({vif.mon.addr,vif.mon.instr,vif.mon.wstrb}) ||
           ((|vif.mon.wstrb) && $isunknown(vif.mon.wdata)) ||
           (vif.mon.wstrb==0 && $isunknown(vif.mon.rdata)))
          `uvm_error("PICO_TRANSFER_X","Unknown accepted transaction")
        request=ibex_mem_txn::type_id::create("native_request");
        request.address=vif.mon.addr; request.data=vif.mon.wdata;
        request.write=(|vif.mon.wstrb); request.be=request.write?vif.mon.wstrb:4'hf;
        request.is_response=0; request.err=0;
        response=ibex_mem_txn::type_id::create("native_response");
        response.address=request.address; response.data=vif.mon.rdata;
        response.write=request.write; response.be=request.be; response.is_response=1; response.err=0;
        if(vif.mon.instr) begin instr_transfers++; instr_response_ap.write(response); end
        else begin data_transfers++; data_request_ap.write(request); data_response_ap.write(response); end
      end
    end
  endtask
endclass

class picorv32_mem_agent extends uvm_agent;
  `uvm_component_utils(picorv32_mem_agent)
  picorv32_mem_driver driver;
  picorv32_mem_monitor monitor;
  uvm_sequencer #(ibex_delay_item) sequencer;
  int max_delay=0;
  int unsigned seed=1;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    void'(uvm_config_db#(int)::get(this,"","max_delay",max_delay));
    void'(uvm_config_db#(int unsigned)::get(this,"","seed",seed));
    if(max_delay<0 || max_delay>100) `uvm_fatal("PICO_CONFIG","Delay must be 0..100")
    monitor=picorv32_mem_monitor::type_id::create("monitor",this);
    if(get_is_active()==UVM_ACTIVE) begin
      driver=picorv32_mem_driver::type_id::create("driver",this);
      sequencer=uvm_sequencer#(ibex_delay_item)::type_id::create("sequencer",this);
    end
  endfunction
  function void connect_phase(uvm_phase phase);
    if(get_is_active()==UVM_ACTIVE) driver.seq_item_port.connect(sequencer.seq_item_export);
  endfunction
  task run_phase(uvm_phase phase);
    ibex_delay_sequence policy;
    bit auto_policy=1;
    void'(uvm_config_db#(bit)::get(this,"","auto_policy",auto_policy));
    if(get_is_active()==UVM_ACTIVE && auto_policy) begin
      policy=ibex_delay_sequence::type_id::create("unified_delay_policy");
      policy.seed=seed ^ 32'h31415927; policy.max_delay=max_delay;
      policy.start(sequencer);
    end
  endtask
endclass
