// ==============================================================================
// Divider Bank — Multi-domain clock generation
// Glitch-free ÷1, ÷2, ÷4, ÷8 outputs
// ==============================================================================

module divider_bank (
    input  logic       clk_in,        // VCO clock (10.25 GHz)
    input  logic       rst_n,
    output logic [3:0] clk_divided    // [0]=÷1, [1]=÷2, [2]=÷4, [3]=÷8
);

    // ÷1: passthrough
    assign clk_divided[0] = clk_in;

    // ÷2
    logic div2;
    always_ff @(posedge clk_in or negedge rst_n) begin
        if (!rst_n) div2 <= 0;
        else        div2 <= ~div2;
    end
    assign clk_divided[1] = div2;

    // ÷4
    logic div4;
    always_ff @(posedge div2 or negedge rst_n) begin
        if (!rst_n) div4 <= 0;
        else        div4 <= ~div4;
    end
    assign clk_divided[2] = div4;

    // ÷8
    logic div8;
    always_ff @(posedge div4 or negedge rst_n) begin
        if (!rst_n) div8 <= 0;
        else        div8 <= ~div8;
    end
    assign clk_divided[3] = div8;

endmodule
