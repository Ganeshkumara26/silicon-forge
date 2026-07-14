// ==============================================================================
// Clock Management Top — Adaptive Multi-Domain Clock Management Subsystem
// Integrates AFC, AAC, ADPLL, Divider Bank, Clock Gating, and PMU
// ==============================================================================

module clock_mgmt_top (
    input  logic       clk_ref,          // 50 MHz reference clock
    input  logic       rst_n,
    input  logic       cal_enable,       // Start calibration sequence
    input  logic [7:0] timing_slack,     // From timing analysis
    input  logic       perf_request,     // Performance boost request
    input  logic       test_mode,        // Scan test bypass
    
    // VCO interface (behavioral model in simulation)
    input  logic       clk_vco,          // VCO output clock
    input  logic       amp_high,         // Amplitude comparator outputs
    input  logic       amp_low,
    output logic [4:0] band_select,      // To varactor bank
    output logic [5:0] bias_control,     // To current DAC
    output logic [15:0] freq_control,    // To VCO tuning (ADPLL)
    
    // Output clocks
    output logic [3:0] gated_clocks,     // Per-domain gated clocks
    
    // Status
    output logic       afc_locked,
    output logic       aac_settled,
    output logic       pll_locked,
    output logic [1:0] pmu_state
);

    // -------------------------------------------------------------------------
    // Internal wires
    // -------------------------------------------------------------------------
    logic [3:0] divided_clocks;
    logic [1:0] div_sel;
    logic [3:0] gate_enable;
    logic [1:0] aac_mode;
    
    // VCO divided clock for AFC (divide by ~205 to get ~50 MHz)
    // In a real design this would be a CML divider; here we use the ADPLL's internal divider
    logic clk_vco_div;
    logic [$clog2(205+1)-1:0] vco_div_cnt;
    always_ff @(posedge clk_vco or negedge rst_n) begin
        if (!rst_n) begin
            vco_div_cnt <= '0;
            clk_vco_div <= 0;
        end else begin
            if (vco_div_cnt >= 204) begin
                vco_div_cnt <= '0;
                clk_vco_div <= ~clk_vco_div;
            end else begin
                vco_div_cnt <= vco_div_cnt + 1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // AFC Engine
    // -------------------------------------------------------------------------
    afc_engine #(
        .CAP_BITS     (5),
        .REF_CYCLES   (64),
        .TARGET_RATIO (205)
    ) u_afc (
        .clk_ref      (clk_ref),
        .clk_vco_div  (clk_vco_div),
        .rst_n        (rst_n),
        .enable       (cal_enable),
        .band_select  (band_select),
        .locked       (afc_locked)
    );

    // -------------------------------------------------------------------------
    // AAC Engine
    // -------------------------------------------------------------------------
    aac_engine #(
        .BIAS_BITS    (6),
        .SETTLE_WAIT  (32),
        .DEBOUNCE     (3)
    ) u_aac (
        .clk          (clk_ref),
        .rst_n        (rst_n),
        .enable       (cal_enable & afc_locked),  // AAC starts after AFC locks
        .amp_high     (amp_high),
        .amp_low      (amp_low),
        .bias_control (bias_control),
        .settled      (aac_settled)
    );

    // -------------------------------------------------------------------------
    // ADPLL
    // -------------------------------------------------------------------------
    adpll_core #(
        .DIV_RATIO  (205),
        .CTRL_WIDTH (16),
        .PHASE_WIDTH(24)
    ) u_adpll (
        .clk_ref      (clk_ref),
        .clk_vco      (clk_vco),
        .rst_n        (rst_n),
        .enable       (afc_locked & aac_settled),  // ADPLL starts after cal
        .freq_control (freq_control),
        .pll_locked   (pll_locked)
    );

    // -------------------------------------------------------------------------
    // Divider Bank
    // -------------------------------------------------------------------------
    divider_bank u_dividers (
        .clk_in      (clk_vco),
        .rst_n       (rst_n),
        .clk_divided (divided_clocks)
    );

    // -------------------------------------------------------------------------
    // PMU FSM
    // -------------------------------------------------------------------------
    pmu_fsm u_pmu (
        .clk           (clk_ref),
        .rst_n         (rst_n),
        .timing_slack  (timing_slack),
        .perf_request  (perf_request),
        .pll_locked    (pll_locked),
        .div_sel       (div_sel),
        .gate_enable   (gate_enable),
        .aac_mode      (aac_mode),
        .pmu_state_out (pmu_state)
    );

    // -------------------------------------------------------------------------
    // Clock Gating — one ICG per domain
    // -------------------------------------------------------------------------
    genvar i;
    generate
        for (i = 0; i < 4; i++) begin : gen_clock_gates
            clock_gate u_icg (
                .clk_in    (divided_clocks[i]),
                .enable    (gate_enable[i]),
                .test_mode (test_mode),
                .clk_gated (gated_clocks[i])
            );
        end
    endgenerate

endmodule
