class riscv_control_driver extends uvm_driver #(riscv_control_item);
  `uvm_component_utils(riscv_control_driver)
  virtual riscv_control_if vif;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    if(!uvm_config_db#(virtual riscv_control_if)::get(this,"","vif",vif))
      `uvm_fatal("CONTROL_CONFIG","Missing control interface")
  endfunction
  task run_phase(uvm_phase phase);
    vif.reset_request=0; vif.irq_external=0;
    forever begin
      seq_item_port.get_next_item(req);
      @(negedge vif.clk);
      if(req.kind==0) begin
        vif.reset_request<=1;
        repeat(req.cycles) @(negedge vif.clk);
        vif.reset_request<=0;
      end else if(req.kind==1) vif.irq_external<=req.level;
      else `uvm_fatal("CONTROL_COMMAND","Unknown control command")
      seq_item_port.item_done();
    end
  endtask
endclass

class riscv_control_monitor extends uvm_monitor;
  `uvm_component_utils(riscv_control_monitor)
  virtual riscv_control_if vif;
  uvm_analysis_port #(riscv_control_item) ap;
  int resets=0,pending_resets=0,accepted_resets=0,irq_assertions=0,irq_deassertions=0;
  bit released;
  int fd;
  function new(string name,uvm_component parent); super.new(name,parent); ap=new("ap",this); endfunction
  function void build_phase(uvm_phase phase);
    if(!uvm_config_db#(virtual riscv_control_if)::get(this,"","vif",vif))
      `uvm_fatal("CONTROL_CONFIG","Missing passive control interface")
  endfunction
  task run_phase(uvm_phase phase);
    fd=$fopen("control_trace.csv","w");
    if(!fd) `uvm_fatal("CONTROL_FILE","Cannot write control trace")
    $fdisplay(fd,"time,event,pending,accepted");
    fork
      forever begin @(posedge vif.effective_rst_n); released=1; end
      forever begin
        riscv_control_item t;
        @(negedge vif.effective_rst_n);
        if(released) begin
          t=riscv_control_item::type_id::create("observed_reset"); t.kind=2;
          t.pending_data=vif.data_request || vif.data_inflight; t.accepted_data=vif.data_inflight;
          resets++; if(t.pending_data) pending_resets++; if(t.accepted_data) accepted_resets++;
          $fdisplay(fd,"%0t,reset,%0d,%0d",$time,t.pending_data,t.accepted_data); $fflush(fd);
          ap.write(t);
        end
      end
      forever begin
        riscv_control_item t;
        @(vif.irq_external);
        if(vif.effective_rst_n) begin
          t=riscv_control_item::type_id::create("observed_irq"); t.kind=vif.irq_external?3:4;
          if(vif.irq_external) irq_assertions++; else irq_deassertions++;
          $fdisplay(fd,"%0t,irq_%0d,0,0",$time,vif.irq_external); $fflush(fd);
          ap.write(t);
        end
      end
    join
  endtask
  function void final_phase(uvm_phase phase); if(fd) $fclose(fd); endfunction
endclass

class riscv_control_agent extends uvm_agent;
  `uvm_component_utils(riscv_control_agent)
  uvm_sequencer #(riscv_control_item) sequencer;
  riscv_control_driver driver;
  riscv_control_monitor monitor;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    sequencer=uvm_sequencer#(riscv_control_item)::type_id::create("sequencer",this);
    driver=riscv_control_driver::type_id::create("driver",this);
    monitor=riscv_control_monitor::type_id::create("monitor",this);
  endfunction
  function void connect_phase(uvm_phase phase); driver.seq_item_port.connect(sequencer.seq_item_export); endfunction
endclass

class riscv_max_delay_sequence extends ibex_delay_sequence;
  `uvm_object_utils(riscv_max_delay_sequence)
  static int unsigned override_calls=0;
  function new(string name="riscv_max_delay_sequence"); super.new(name); endfunction
  task body();
    ibex_delay_item item;
    forever begin
      item=ibex_delay_item::type_id::create("factory_max_delay"); item.max_delay=max_delay;
      start_item(item);
`ifdef IBEX_UVM_FULL
      if(!item.randomize() with {grant_delay==max_delay; response_delay==max_delay;})
        `uvm_fatal("FACTORY_RANDOMIZE","Cannot produce maximum legal delay")
      randomize_calls++; override_calls++;
`else
      `uvm_fatal("SCENARIO_MODE","Advanced scenarios require full randomization")
`endif
      finish_item(item);
    end
  endtask
endclass

class riscv_virtual_sequencer extends uvm_sequencer;
  `uvm_component_utils(riscv_virtual_sequencer)
  uvm_sequencer #(riscv_control_item) control;
  uvm_sequencer #(ibex_delay_item) instruction,data,native_memory;
  riscv_scoreboard scoreboard;
  virtual riscv_control_if vif;
  int unsigned seed;
  int cpu_id,max_delay;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
endclass

class riscv_control_sequence extends uvm_sequence #(riscv_control_item);
  `uvm_object_utils(riscv_control_sequence)
  int kind;
  bit level;
  function new(string name="riscv_control_sequence"); super.new(name); endfunction
  task body();
    riscv_control_item item=riscv_control_item::type_id::create("command");
    start_item(item); item.kind=kind; item.level=level; item.cycles=8; finish_item(item);
  endtask
endclass

class riscv_scenario_sequence extends uvm_sequence;
  `uvm_object_utils(riscv_scenario_sequence)
  `uvm_declare_p_sequencer(riscv_virtual_sequencer)
  int scenario_id;
  bit completed;
  function new(string name="riscv_scenario_sequence"); super.new(name); endfunction
  task command(int kind,bit level=0);
    riscv_control_sequence s=riscv_control_sequence::type_id::create("control_action");
    s.kind=kind; s.level=level; s.start(p_sequencer.control);
  endtask
  task body();
    ibex_delay_sequence im,dm,nm;
    im=ibex_delay_sequence::type_id::create("virtual_instruction_policy");
    dm=ibex_delay_sequence::type_id::create("virtual_data_policy");
    nm=ibex_delay_sequence::type_id::create("virtual_native_policy");
    im.max_delay=p_sequencer.max_delay; dm.max_delay=p_sequencer.max_delay; nm.max_delay=p_sequencer.max_delay;
    im.seed=p_sequencer.seed^'h13579bdf; dm.seed=p_sequencer.seed^'h2468ace1; nm.seed=p_sequencer.seed^'h31415927;
    if(im.get_type_name()!="riscv_max_delay_sequence" || dm.get_type_name()!="riscv_max_delay_sequence")
      `uvm_fatal("FACTORY_TYPE","Requested factory override was not created")
    fork
      begin if(p_sequencer.cpu_id==0) im.start(p_sequencer.instruction); end
      begin if(p_sequencer.cpu_id==0) dm.start(p_sequencer.data); end
      begin if(p_sequencer.cpu_id==1) nm.start(p_sequencer.native_memory); end
    join_none
    if(scenario_id==1) begin
      if(p_sequencer.cpu_id==0) begin
        do @(posedge p_sequencer.vif.clk); while(!p_sequencer.vif.data_accept);
      end else wait(p_sequencer.vif.data_request && !p_sequencer.vif.data_accept);
      command(0);
    end else if(scenario_id==3) begin
      wait(p_sequencer.scoreboard.parking_seen);
      command(1,1);
      wait(p_sequencer.scoreboard.irq_count==1);
      command(1,0);
    end
    wait(p_sequencer.scoreboard.done);
    completed=1;
  endtask
endclass
