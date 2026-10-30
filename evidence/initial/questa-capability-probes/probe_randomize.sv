module probe_randomize;
  class item;
    rand int unsigned value;
    constraint legal { value inside {[1:7]}; }
  endclass
  initial begin
    item request = new();
    if (!request.randomize()) $fatal(1,"randomize returned false");
    if (!(request.value inside {[1:7]})) $fatal(1,"constraint not honored");
    $display("RANDOMIZE_EXECUTED value=%0d",request.value);
    $finish;
  end
endmodule
