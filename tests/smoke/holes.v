`timescale 1ns/1ps

// A design with a hole the tests below never reach, so the numbers `coverage`
// reports have a known answer: the else branch is never run, and hole_marker
// never leaves 0. The cocotb tests of this file only ever drive sel high.
module holes (
    input clk,
    input rst,
    input sel,
    output reg [1:0] y,
    output reg hole_marker
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            y <= 2'b00;
            hole_marker <= 1'b0;
        end else begin
            if (sel) begin
                y <= y + 1;
            end else begin
                hole_marker <= 1'b1;
            end
        end
    end

endmodule
