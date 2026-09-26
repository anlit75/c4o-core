`timescale 1ns/1ps

// A second module, which is the whole point of this file.
//
// `schematic` draws one module, and yosys refuses to write svg for more than
// one. counter.v on its own has no submodule, so it never asked the question --
// and the answer was wrong for every design that does. This wrapper is the
// smallest thing that asks it.
module counter_wrap (
    input  wire       clk,
    input  wire       rst,
    output wire [3:0] count
);

    counter inner (
        .clk   (clk),
        .rst   (rst),
        .count (count)
    );

endmodule
