module probe_covergroups;
  int value;
  covergroup cg;
    value_cp: coverpoint value { bins observed = {1}; }
  endgroup
  cg coverage;
  initial begin
    coverage = new(); value = 1; coverage.sample();
    if (coverage.get_inst_coverage() < 100.0) $fatal(1,"coverage did not sample");
    $display("COVERGROUP_EXECUTED coverage=%0f",coverage.get_inst_coverage());
    $finish;
  end
endmodule
