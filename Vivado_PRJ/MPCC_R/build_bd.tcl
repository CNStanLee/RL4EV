# Vivado 2022.2 block design for ZCU104: PS + the four MPCC_R HLS IPs (plan step 4, F2/F3).
#   vivado -mode batch -source build_bd.tcl -tclargs <ip_repo_dir> [run_impl=1]
# <ip_repo_dir> holds the exported HLS IPs (one sub-directory per component, Vitis HLS 2022.2
# `export_design -format ip_catalog`): mpcc_r_hls, emi_feat_hls, emi_detector_axi, harmonic_estimator_axi.
# Address map (AXI-Lite, 64 KiB each, HPM0 FPD):
#   0xA000_0000 axi_gpio (LEDs)      0xA001_0000 mpcc_r_hls       0xA002_0000 emi_feat_hls
#   0xA003_0000 emi_detector_axi     0xA004_0000 harmonic_estimator_axi   0xA005_0000 axi_timer (PS-side latency)
# Outputs: MPCC_R.xpr, mpcc_r.bit / mpcc_r.hwh (PS_notebook/hardware), system_wrapper.xsa, timing/utilization reports.
set ip_repo [lindex $argv 0]
set run_impl 1
if {[llength $argv] > 1} { set run_impl [lindex $argv 1] }
set here [file dirname [file normalize [info script]]]
set part xczu7ev-ffvc1156-2-e
set board [get_board_parts -quiet -latest_file_version *zcu104*]

create_project -force MPCC_R $here/MPCC_R -part $part
if {$board ne ""} { set_property board_part $board [current_project] }
set_property ip_repo_paths [list $ip_repo] [current_project]
update_ip_catalog

create_bd_design system
proc xip {name} { return [lindex [lsort [get_ipdefs -all -filter "VLNV =~ xilinx.com:ip:${name}:*"]] end] }   ;# version-independent (2022.2 ships zynq_ultra_ps_e 3.4)
# --- PS
set ps [create_bd_cell -type ip -vlnv [xip zynq_ultra_ps_e] zynq_ultra_ps_e_0]
if {$board ne ""} { apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps }
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {1} CONFIG.PSU__USE__M_AXI_GP1 {0} CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] $ps
# --- HLS IPs (100 MHz, AXI-Lite control)
set ips {mpcc_r_hls emi_feat_hls emi_detector_axi harmonic_estimator_axi}
set cells {}
foreach n $ips {
    set vl [get_ipdefs -quiet -filter "NAME == $n"]
    if {$vl eq ""} { puts "ERROR: IP $n not found in $ip_repo"; exit 1 }
    lappend cells [create_bd_cell -type ip -vlnv [lindex $vl 0] ${n}_0]
}
set gpio [create_bd_cell -type ip -vlnv [xip axi_gpio] axi_gpio_0]
set_property -dict [list CONFIG.C_GPIO_WIDTH {4} CONFIG.C_ALL_OUTPUTS {1}] $gpio
set timer [create_bd_cell -type ip -vlnv [xip axi_timer] axi_timer_0]
# --- interconnect: one SmartConnect, HPM0 -> 6 AXI-Lite slaves
set smc [create_bd_cell -type ip -vlnv [xip smartconnect] axi_smc]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {6}] $smc
set rst [create_bd_cell -type ip -vlnv [xip proc_sys_reset] rst_ps8_0_100M]
connect_bd_net [get_bd_pins $ps/pl_clk0] [get_bd_pins $ps/maxihpm0_fpd_aclk] [get_bd_pins $smc/aclk] [get_bd_pins $rst/slowest_sync_clk] \
    [get_bd_pins $gpio/s_axi_aclk] [get_bd_pins $timer/s_axi_aclk]
connect_bd_net [get_bd_pins $ps/pl_resetn0] [get_bd_pins $rst/ext_reset_in]
connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $smc/aresetn] [get_bd_pins $gpio/s_axi_aresetn] [get_bd_pins $timer/s_axi_aresetn]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM0_FPD] [get_bd_intf_pins $smc/S00_AXI]
set mi 0
foreach c $cells {
    connect_bd_net [get_bd_pins $ps/pl_clk0] [get_bd_pins $c/ap_clk]
    connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $c/ap_rst_n]
    connect_bd_intf_net [get_bd_intf_pins $smc/M0${mi}_AXI] [get_bd_intf_pins $c/s_axi_control]
    incr mi
}
connect_bd_intf_net [get_bd_intf_pins $smc/M0${mi}_AXI] [get_bd_intf_pins $gpio/S_AXI]; incr mi
connect_bd_intf_net [get_bd_intf_pins $smc/M0${mi}_AXI] [get_bd_intf_pins $timer/S_AXI]
# --- addresses
assign_bd_address
# two passes: park every segment at a unique temporary offset first, then place the final map (avoids overlaps)
set names [list axi_gpio_0]
foreach n $ips { lappend names ${n}_0 }
lappend names axi_timer_0
set k 0
foreach n $names {
    set seg [get_bd_addr_segs -quiet "zynq_ultra_ps_e_0/Data/SEG_${n}_Reg"]
    if {$seg ne ""} { set_property offset [format 0xA0F%X0000 $k] $seg }
    incr k
}
set k 0
foreach n $names {
    set seg [get_bd_addr_segs -quiet "zynq_ultra_ps_e_0/Data/SEG_${n}_Reg"]
    if {$seg ne ""} { set_property offset [format 0xA00%X0000 $k] $seg }
    incr k
}
# --- LEDs (board interface if the board files are present)
if {$board ne ""} {
    catch { apply_bd_automation -rule xilinx.com:bd_rule:board -config {Board_Interface "led_4bits ( LED ) "} [get_bd_intf_pins $gpio/GPIO] }
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files system.bd] -top
add_files -norecurse [file join $here MPCC_R MPCC_R.gen sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

if {$run_impl} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    open_run impl_1
    report_timing_summary -file $here/timing_impl.rpt
    report_utilization -file $here/util_impl.rpt -hierarchical
    file mkdir $here/out
    file copy -force $here/MPCC_R/MPCC_R.runs/impl_1/system_wrapper.bit $here/out/mpcc_r.bit
    file copy -force $here/MPCC_R/MPCC_R.gen/sources_1/bd/system/hw_handoff/system.hwh $here/out/mpcc_r.hwh
    write_hw_platform -fixed -include_bit -force -file $here/out/system_wrapper.xsa
    puts "BUILD_DONE bit=$here/out/mpcc_r.bit"
}
