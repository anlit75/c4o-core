`timescale 1ns/1ns

module tb_counter;

    reg clk;
    reg rst;
    wire [3:0] count;

    // Instantiate the counter
    counter uut (
        .clk(clk),
        .rst(rst),
        .count(count)
    );

    // Clock generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Test sequence
    initial begin
        // Dump waves
        $dumpfile("build/counter.vcd");
        $dumpvars(0, tb_counter);

        // Reset
        rst = 1;
        #10;
        rst = 0;

        // Wait for first increment
        @(posedge clk);
        #1; // Wait a bit after clock edge for stability
        if (count !== 4'b0001) begin
            $display("Counter mismatch! Expected 1, got %d", count);
            $fatal(1);
        end

        // Wait for second increment
        @(posedge clk);
        #1;
        if (count !== 4'b0010) begin
            $display("Counter mismatch! Expected 2, got %d", count);
            $fatal(1);
        end

        // Wait for third increment
        @(posedge clk);
        #1;
        if (count !== 4'b0011) begin
            $display("Counter mismatch! Expected 3, got %d", count);
            $fatal(1);
        end

        $display("Counter test passed!");
        $finish;
    end

endmodule
