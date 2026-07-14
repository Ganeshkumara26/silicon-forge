// ==============================================================================
// VCO UVM Driver and Monitor
// ==============================================================================

`ifndef VCO_DRIVER_MONITOR_SVH
`define VCO_DRIVER_MONITOR_SVH

import uvm_pkg::*;
`include "uvm_macros.svh"

// ------------------------------------------------------------------------------
// DRIVER
// ------------------------------------------------------------------------------
class vco_driver extends uvm_driver #(vco_transaction);
    `uvm_component_utils(vco_driver)

    // Virtual interface bound to the DUT
    virtual vco_sva_if vif;

    function new(string name="vco_driver", uvm_component parent=null);
        super.new(name, parent);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if(!uvm_config_db#(virtual vco_sva_if)::get(this, "", "vif", vif))
            `uvm_fatal("NO_VIF", "Virtual interface not found in uvm_config_db")
    endfunction

    virtual task run_phase(uvm_phase phase);
        forever begin
            seq_item_port.get_next_item(req);
            
            // Drive the real-number signals on the clock edge
            @(posedge vif.clk);
            vif.v_tune <= req.v_tune;
            // Assuming dt_jitter is injected via a separate port on the DUT in a real implementation.
            // For the MVV, we'll assume the DUT is structurally mapped to receive it.
            
            seq_item_port.item_done();
        end
    endtask
endclass

// ------------------------------------------------------------------------------
// MONITOR
// ------------------------------------------------------------------------------
class vco_monitor extends uvm_monitor;
    `uvm_component_utils(vco_monitor)

    virtual vco_sva_if vif;
    uvm_analysis_port #(real) vout_ap;

    function new(string name="vco_monitor", uvm_component parent=null);
        super.new(name, parent);
        vout_ap = new("vout_ap", this);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if(!uvm_config_db#(virtual vco_sva_if)::get(this, "", "vif", vif))
            `uvm_fatal("NO_VIF", "Virtual interface not found in config_db")
    endfunction

    virtual task run_phase(uvm_phase phase);
        forever begin
            @(posedge vif.clk);
            vout_ap.write(vif.v_out);
        end
    endtask
endclass

// ------------------------------------------------------------------------------
// AGENT
// ------------------------------------------------------------------------------
class vco_agent extends uvm_agent;
    `uvm_component_utils(vco_agent)

    uvm_sequencer #(vco_transaction) sequencer;
    vco_driver driver;
    vco_monitor monitor;

    function new(string name="vco_agent", uvm_component parent=null);
        super.new(name, parent);
    endfunction

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        sequencer = uvm_sequencer#(vco_transaction)::type_id::create("sequencer", this);
        driver = vco_driver::type_id::create("driver", this);
        monitor = vco_monitor::type_id::create("monitor", this);
    endfunction

    virtual function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        driver.seq_item_port.connect(sequencer.seq_item_export);
    endfunction
endclass

`endif // VCO_DRIVER_MONITOR_SVH
