`timescale 1ns/1ps
// Memory-system harness around the unmodified Ibex core + upstream FF RF.
module tb_ibex_uvm;
  import uvm_pkg::*;
  import ibex_pkg::*;
  import ibex_uvm_pkg::*;
  logic clk=0, boot_rst_n=0;
  wire rst_n;
  riscv_control_if control(clk);
  logic data_inflight=0;
  assign rst_n=boot_rst_n && !control.reset_request;
  assign control.effective_rst_n=rst_n;
  assign control.data_request=dmem.req;
  assign control.data_accept=dmem.req && dmem.gnt;
  assign control.data_inflight=data_inflight;
  always @(posedge clk or negedge rst_n)
    if(!rst_n) data_inflight<=0;
    else if(dmem.rvalid) data_inflight<=0;
    else if(dmem.req && dmem.gnt) data_inflight<=1;
  always #5ns clk=~clk;
  initial begin repeat(8) @(negedge clk); boot_rst_n=1; end
  ibex_mem_if imem(clk,rst_n),dmem(clk,rst_n);
  ibex_rvfi_if rvfi(clk,rst_n);
  logic [4:0] rf_ra,rf_rb,rf_wa;
  logic [31:0] rf_da,rf_db,rf_wd;
  logic rf_we,dummy_id,dummy_wb,rf_error;
  logic alert_minor,alert_internal,alert_bus;
  assign imem.we=0;
  assign imem.be=4'hf;
  assign imem.wdata=0;

  ibex_register_file_ff #(.RV32E(0)) u_regfile (
    .clk_i(clk),.rst_ni(rst_n),.test_en_i(1'b0),
    .dummy_instr_id_i(dummy_id),.dummy_instr_wb_i(dummy_wb),
    .raddr_a_i(rf_ra),.rdata_a_o(rf_da),.raddr_b_i(rf_rb),.rdata_b_o(rf_db),
    .waddr_a_i(rf_wa),.wdata_a_i(rf_wd),.we_a_i(rf_we),.err_o(rf_error)
  );
  ibex_core #(
    .RV32E(0),.RV32M(RV32MNone),.RV32B(RV32BNone),
    .ICache(0),.ICacheECC(0),.SecureIbex(0),.WritebackStage(0),
    .BranchPredictor(0),.PMPEnable(0),.ResetAll(1)
  ) u_ibex_core (
    .clk_i(clk),.rst_ni(rst_n),.hart_id_i(32'b0),.boot_addr_i(32'b0),
    .instr_req_o(imem.req),.instr_gnt_i(imem.gnt),.instr_rvalid_i(imem.rvalid),
    .instr_addr_o(imem.addr),.instr_rdata_i(imem.rdata),.instr_err_i(imem.err),
    .data_req_o(dmem.req),.data_gnt_i(dmem.gnt),.data_rvalid_i(dmem.rvalid),
    .data_we_o(dmem.we),.data_be_o(dmem.be),.data_addr_o(dmem.addr),
    .data_wdata_o(dmem.wdata),.data_rdata_i(dmem.rdata),.data_err_i(dmem.err),
    .dummy_instr_id_o(dummy_id),.dummy_instr_wb_o(dummy_wb),
    .rf_raddr_a_o(rf_ra),.rf_raddr_b_o(rf_rb),.rf_waddr_wb_o(rf_wa),
    .rf_we_wb_o(rf_we),.rf_wdata_wb_ecc_o(rf_wd),.rf_rdata_a_ecc_i(rf_da),.rf_rdata_b_ecc_i(rf_db),
    .ic_tag_req_o(),.ic_tag_write_o(),.ic_tag_addr_o(),.ic_tag_wdata_o(),
    .ic_tag_rdata_i('{default:'0}),
    .ic_data_req_o(),.ic_data_write_o(),.ic_data_addr_o(),.ic_data_wdata_o(),
    .ic_data_rdata_i('{default:'0}),.ic_scr_key_valid_i(1'b0),.ic_scr_key_req_o(),
    .irq_software_i(1'b0),.irq_timer_i(1'b0),.irq_external_i(control.irq_external),
    .irq_fast_i(15'b0),.irq_nm_i(1'b0),.irq_pending_o(),
    .debug_req_i(1'b0),.crash_dump_o(),.double_fault_seen_o(),
    .fetch_enable_i(IbexMuBiOn),.core_busy_o(),
    .alert_minor_o(alert_minor),.alert_major_internal_o(alert_internal),.alert_major_bus_o(alert_bus),
    .rvfi_valid(rvfi.valid),.rvfi_order(rvfi.order),.rvfi_insn(rvfi.insn),
    .rvfi_trap(rvfi.trap),.rvfi_halt(rvfi.halt),.rvfi_intr(rvfi.intr),
    .rvfi_mode(),.rvfi_ixl(),.rvfi_rs1_addr(rvfi.rs1),.rvfi_rs2_addr(rvfi.rs2),.rvfi_rs3_addr(),
    .rvfi_rs1_rdata(rvfi.rs1_data),.rvfi_rs2_rdata(rvfi.rs2_data),.rvfi_rs3_rdata(),
    .rvfi_rd_addr(rvfi.rd),.rvfi_rd_wdata(rvfi.rd_data),
    .rvfi_pc_rdata(rvfi.pc),.rvfi_pc_wdata(rvfi.pc_next),
    .rvfi_mem_addr(rvfi.mem_addr),.rvfi_mem_rmask(rvfi.mem_rmask),.rvfi_mem_wmask(rvfi.mem_wmask),
    .rvfi_mem_rdata(rvfi.mem_rdata),.rvfi_mem_wdata(rvfi.mem_wdata),
    .rvfi_ext_pre_mip(),.rvfi_ext_post_mip(),.rvfi_ext_nmi(),.rvfi_ext_nmi_int(),
    .rvfi_ext_debug_req(),.rvfi_ext_debug_mode(),.rvfi_ext_rf_wr_suppress(),.rvfi_ext_mcycle(),
    .rvfi_ext_mhpmcounters(),.rvfi_ext_mhpmcountersh(),.rvfi_ext_ic_scr_key_valid(),.rvfi_ext_irq_valid()
  );
  a_no_alerts: assert property (@(posedge clk) disable iff(!rst_n)
    {alert_minor,alert_internal,alert_bus,rf_error}===4'b0)
    else $error("IBEX_ALERT: unexpected DUT alert or RF error");

  initial begin
    uvm_config_db#(virtual riscv_control_if)::set(null,"uvm_test_top.env.control_agent.*","vif",control);
    uvm_config_db#(virtual riscv_control_if)::set(null,"uvm_test_top.env","control_vif",control);
    uvm_config_db#(virtual ibex_mem_if)::set(null,"uvm_test_top.env.instr_agent.*","vif",imem);
    uvm_config_db#(virtual ibex_mem_if)::set(null,"uvm_test_top.env.data_agent.*","vif",dmem);
    uvm_config_db#(virtual ibex_rvfi_if)::set(null,"uvm_test_top.env.rvfi_monitor","vif",rvfi);
    run_test();
  end
endmodule
