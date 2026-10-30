// Shared environment: processor-specific agents publish common observations.
class riscv_env_base extends uvm_env;
  `uvm_component_utils(riscv_env_base)
  ibex_rvfi_monitor rvfi_monitor;
  riscv_scoreboard scoreboard;
  riscv_control_agent control_agent;
  riscv_virtual_sequencer virtual_sequencer;
  virtual riscv_control_if control_vif;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  virtual function void build_memory_agents(); endfunction
  virtual function void connect_memory_agents(); endfunction
  virtual function void connect_virtual_memory(); endfunction
  virtual function int unsigned instr_stalls(); return 0; endfunction
  virtual function int unsigned data_stalls(); return 0; endfunction
  virtual function int unsigned instr_waits(); return 0; endfunction
  virtual function int unsigned data_waits(); return 0; endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    build_memory_agents();
    rvfi_monitor=ibex_rvfi_monitor::type_id::create("rvfi_monitor",this);
    scoreboard=riscv_scoreboard::type_id::create("scoreboard",this);
    control_agent=riscv_control_agent::type_id::create("control_agent",this);
    virtual_sequencer=riscv_virtual_sequencer::type_id::create("virtual_sequencer",this);
    if(!uvm_config_db#(virtual riscv_control_if)::get(this,"","control_vif",control_vif))
      `uvm_fatal("CONTROL_CONFIG","Missing environment control interface")
  endfunction
  function void connect_phase(uvm_phase phase);
    rvfi_monitor.ap.connect(scoreboard.retire_export);
    connect_memory_agents();
    control_agent.monitor.ap.connect(scoreboard.control_export);
    virtual_sequencer.control=control_agent.sequencer;
    virtual_sequencer.scoreboard=scoreboard; virtual_sequencer.vif=control_vif;
    connect_virtual_memory();
  endfunction
endclass

class ibex_env extends riscv_env_base;
  `uvm_component_utils(ibex_env)
  ibex_mem_agent instr_agent,data_agent;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  virtual function void build_memory_agents();
    uvm_config_db#(int)::set(this,"instr_agent","is_instr",1);
    uvm_config_db#(int)::set(this,"data_agent","is_instr",0);
    instr_agent=ibex_mem_agent::type_id::create("instr_agent",this);
    data_agent=ibex_mem_agent::type_id::create("data_agent",this);
  endfunction
  virtual function void connect_memory_agents();
    instr_agent.monitor.response_ap.connect(scoreboard.instr_rsp_export);
    data_agent.monitor.request_ap.connect(scoreboard.data_req_export);
    data_agent.monitor.response_ap.connect(scoreboard.data_rsp_export);
  endfunction
  virtual function void connect_virtual_memory();
    virtual_sequencer.instruction=instr_agent.sequencer; virtual_sequencer.data=data_agent.sequencer;
  endfunction
  virtual function int unsigned instr_stalls(); return instr_agent.monitor.grant_stalls; endfunction
  virtual function int unsigned data_stalls(); return data_agent.monitor.grant_stalls; endfunction
  virtual function int unsigned instr_waits(); return instr_agent.monitor.response_waits; endfunction
  virtual function int unsigned data_waits(); return data_agent.monitor.response_waits; endfunction
endclass

class picorv32_env extends riscv_env_base;
  `uvm_component_utils(picorv32_env)
  picorv32_mem_agent memory_agent;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  virtual function void build_memory_agents();
    memory_agent=picorv32_mem_agent::type_id::create("memory_agent",this);
  endfunction
  virtual function void connect_memory_agents();
    memory_agent.monitor.instr_response_ap.connect(scoreboard.instr_rsp_export);
    memory_agent.monitor.data_request_ap.connect(scoreboard.data_req_export);
    memory_agent.monitor.data_response_ap.connect(scoreboard.data_rsp_export);
  endfunction
  virtual function void connect_virtual_memory(); virtual_sequencer.native_memory=memory_agent.sequencer; endfunction
  virtual function int unsigned instr_stalls(); return memory_agent.monitor.instr_stalls; endfunction
  virtual function int unsigned data_stalls(); return memory_agent.monitor.data_stalls; endfunction
endclass

class riscv_smoke_test extends uvm_test;
  `uvm_component_utils(riscv_smoke_test)
  riscv_env_base env;
  ibex_program image;
  int unsigned seed=20261029;
  int max_delay=0,cpu_id=0,program_id=0,scenario_id=0;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    int matched;
    super.build_phase(phase);
    matched=$value$plusargs("IBEX_SEED=%d",seed);
    matched=$value$plusargs("IBEX_MAX_DELAY=%d",max_delay);
    matched=$value$plusargs("IBEX_PROGRAM=%d",program_id);
    matched=$value$plusargs("RV_SCENARIO=%d",scenario_id);
    void'(uvm_config_db#(int)::get(this,"","cpu_id",cpu_id));
    if(cpu_id!=0 && cpu_id!=1) `uvm_fatal("CPU_CONFIG","Unknown physical CPU adapter")
    image=ibex_program::type_id::create("program_image");
    image.build_image(seed,program_id); image.write_image();
    uvm_config_db#(ibex_program)::set(this,"env.*","program",image);
    uvm_config_db#(int unsigned)::set(this,"env.*","seed",seed);
    uvm_config_db#(int)::set(this,"env.*","max_delay",max_delay);
    uvm_config_db#(int)::set(this,"env.scoreboard","order_base",cpu_id==0?1:0);
    if(cpu_id==0) env=ibex_env::type_id::create("env",this);
    else env=picorv32_env::type_id::create("env",this);
  endfunction
  task run_phase(uvm_phase phase);
    phase.raise_objection(this);
    fork
      begin wait(env.scoreboard.done); end
      begin #200us; `uvm_fatal("WATCHDOG","CPU failed to complete within 200 us") end
    join_any
    disable fork;
    phase.drop_objection(this);
  endtask
  function void report_phase(uvm_phase phase);
    uvm_report_server server=uvm_report_server::get_server();
`ifdef IBEX_UVM_FULL
    `uvm_info("IBEX_FULL_FEATURES",$sformatf("randomize_calls=%0d coverage_percent=%0.2f",
      ibex_delay_sequence::randomize_calls,env.scoreboard.retire_cg.get_inst_coverage()),UVM_NONE)
    `uvm_info("RV_CORNER_COVERAGE",$sformatf("coverage_percent=%0.2f",env.scoreboard.corner_cg.get_inst_coverage()),UVM_NONE)
    `uvm_info("RV_RANDOM_COVERAGE",$sformatf("kind_percent=%0.2f alu_percent=%0.2f memory_percent=%0.2f",
      env.scoreboard.random_kind_cg.get_inst_coverage(),env.scoreboard.random_alu_cg.get_inst_coverage(),
      env.scoreboard.random_memory_cg.get_inst_coverage()),UVM_NONE)
`endif
    `uvm_info("RV_PROGRAM_RANDOM",$sformatf("instruction_calls=%0d schedule_calls=%0d seed=%0d",
      image.instruction_randomize_calls,image.schedule_randomize_calls,seed),UVM_NONE)
    `uvm_info("RV_BRANCH_HITS",$sformatf("beq_taken=%0d beq_not_taken=%0d bne_taken=%0d bne_not_taken=%0d",
      env.scoreboard.branch_hits[0],env.scoreboard.branch_hits[1],env.scoreboard.branch_hits[2],env.scoreboard.branch_hits[3]),UVM_NONE)
    if(server.get_severity_count(UVM_ERROR)==0 && server.get_severity_count(UVM_FATAL)==0 && env.scoreboard.done)
      `uvm_info("RV_UVM_PASS",$sformatf("retired=%0d loads=%0d stores=%0d branches_taken=%0d branches_not_taken=%0d jumps=%0d signature=%0d instr_stalls=%0d data_stalls=%0d instr_waits=%0d data_waits=%0d seed=%0d max_delay=%0d cpu_id=%0d program_id=%0d",
        env.scoreboard.retired,env.scoreboard.loads,env.scoreboard.stores,env.scoreboard.branches_taken,
        env.scoreboard.branches_not_taken,env.scoreboard.jumps,env.scoreboard.signature,
        env.instr_stalls(),env.data_stalls(),env.instr_waits(),env.data_waits(),seed,max_delay,cpu_id,program_id),UVM_NONE)
  endfunction
endclass

class riscv_advanced_test extends riscv_smoke_test;
  `uvm_component_utils(riscv_advanced_test)
  riscv_scenario_sequence scenario;
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
  function void build_phase(uvm_phase phase);
    ibex_delay_sequence::type_id::set_type_override(riscv_max_delay_sequence::get_type());
    uvm_config_db#(bit)::set(this,"env.*","auto_policy",0);
    super.build_phase(phase);
  endfunction
  task run_phase(uvm_phase phase);
    phase.raise_objection(this);
    env.virtual_sequencer.seed=seed; env.virtual_sequencer.cpu_id=cpu_id; env.virtual_sequencer.max_delay=max_delay;
    scenario=riscv_scenario_sequence::type_id::create("scenario"); scenario.scenario_id=scenario_id;
    fork
      scenario.start(env.virtual_sequencer);
      begin #200us; `uvm_fatal("WATCHDOG","Advanced scenario did not complete") end
    join_any
    disable fork;
    if(!scenario.completed) `uvm_error("VIRTUAL_SEQUENCE","Virtual sequence did not complete")
    phase.drop_objection(this);
  endtask
  function void check_phase(uvm_phase phase);
    if(riscv_max_delay_sequence::override_calls==0) `uvm_error("FACTORY_UNUSED","Factory-selected policy was not executed")
    if(scenario_id==1 && (env.control_agent.monitor.resets!=1 || env.control_agent.monitor.pending_resets!=1))
      `uvm_error("RESET_SCENARIO","Reset did not interrupt a pending data operation")
    if(scenario_id==1 && env.control_agent.monitor.accepted_resets!=(cpu_id==0?1:0))
      `uvm_error("RESET_ACCEPTANCE","Unexpected reset acceptance boundary")
    if(scenario_id==3 && (env.control_agent.monitor.irq_assertions!=1 || env.control_agent.monitor.irq_deassertions!=1 ||
        env.scoreboard.irq_count!=1 || env.scoreboard.mret_count!=1))
      `uvm_error("IRQ_SCENARIO","Interrupt/return contract was not exercised")
  endfunction
  function void report_phase(uvm_phase phase);
    `uvm_info("RV_ADVANCED",$sformatf("scenario_id=%0d resets=%0d pending_resets=%0d accepted_resets=%0d irq_assertions=%0d irq_deassertions=%0d irq_entries=%0d mret=%0d factory_calls=%0d virtual_completed=%0d",
      scenario_id,env.control_agent.monitor.resets,env.control_agent.monitor.pending_resets,env.control_agent.monitor.accepted_resets,
      env.control_agent.monitor.irq_assertions,env.control_agent.monitor.irq_deassertions,env.scoreboard.irq_count,env.scoreboard.mret_count,
      riscv_max_delay_sequence::override_calls,scenario.completed),UVM_NONE)
    super.report_phase(phase);
  endfunction
endclass

class ibex_smoke_test extends riscv_smoke_test;
  `uvm_component_utils(ibex_smoke_test)
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
endclass
class picorv32_smoke_test extends riscv_smoke_test;
  `uvm_component_utils(picorv32_smoke_test)
  function new(string name,uvm_component parent); super.new(name,parent); endfunction
endclass
