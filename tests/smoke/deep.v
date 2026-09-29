module leaf(input clk, input d, output reg q); always @(posedge clk) q <= d; endmodule
module mid(input clk, input a, output y); wire t; leaf l0(.clk(clk), .d(a), .q(t)); leaf l1(.clk(clk), .d(t), .q(y)); endmodule
module top_deep(input clk, input a, output y, output z); mid m0(.clk(clk), .a(a), .y(y)); assign z = ~a; endmodule
