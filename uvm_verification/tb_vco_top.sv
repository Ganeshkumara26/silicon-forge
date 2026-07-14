// ==============================================================================
// VCO Top-Level Verification Environment
// Binds generated SVA packages and initiates UVM test phasing
// ==============================================================================

`timescale 1ns/1ps

import uvm_pkg::*;
`include "uvm_macros.svh"

// Include UVM Components and Generated Assets
`include "vco_sva_pkg.sv"
`include "vco_transaction.svh"
`include "vco_jitter_sequence.svh"
`include "vco_agent.svh"

// ------------------------------------------------------------------------------
// UVM Environment and Test
// ------------------------------------------------------------------------------
class vco_env extends uvm_env;
    `uvm_component_utils(vco_env)
    vco_agent agent;

    function new(string name="vco_env", uvm_component parent=null);
        super.new(name, parent);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        agent = vco_agent::type_id::create("agent", this);
    endfunction
endclass

class vco_test extends uvm_test;
    `uvm_component_utils(vco_test)
    vco_env env;
    vco_jitter_sequence seq;

    function new(string name="vco_test", uvm_component parent=null);
        super.new(name, parent);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        env = vco_env::type_id::create("env", this);
    endfunction

    virtual task run_phase(uvm_phase phase);
        phase.raise_objection(this);
        seq = vco_jitter_sequence::type_id::create("seq");
        seq.start(env.agent.sequencer);
        #100ns; // Let settling occur
        phase.drop_objection(this);
    endtask
endclass

// ------------------------------------------------------------------------------
// Top-Level Module
// ------------------------------------------------------------------------------
module tb_vco_top;

    logic clk;
    logic rst_n;
    real  v_tune;
    real  dt_jitter;
    real  v_out;

    // Clock Generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Reset Generation
    initial begin
        rst_n = 0;
        #20 rst_n = 1;
    end

    // Instantiate the Discrete RNM DUT
    vco_rnm_dut dut (
        .clk(clk),
        .rst_n(rst_n),
        .v_tune(v_tune),
        .dt_jitter(dt_jitter),
        .v_out(v_out)
    );

    // Bind the generated SystemVerilog Assertions to the DUT
    // This allows concurrent property checking without modifying structural RTL
    bind vco_rnm_dut vco_sva_if bind_sva_if (
        .clk(clk),
        .rst_n(rst_n),
        .v_out(v_out),
        .v_tune(v_tune)
    );

    initial begin
        // Pass the bound interface down to the UVM database
        uvm_config_db#(virtual vco_sva_if)::set(null, "uvm_test_top.env.agent.*", "vif", dut.bind_sva_if);
        
        // Start the UVM test
        run_test("vco_test");
    end

endmodule
