# Vivado block design for the first ZCU104 HIL overlay: PS + mpcc_hls (duty prediction) + LED GPIO.
#   vivado -mode batch -source build_bd.tcl -tclargs <ip_repo_dir> [run_impl=1]
# <ip_repo_dir> holds the exported mpcc_hls IP (HLS_PRJ after `HLS_PRJ/build_all.sh mpcc`).
# This is a version-independent recreation of MPCC.xpr / system.bd, which were saved by Vivado 2025.1
# and cannot be opened by older releases; tested with Vivado 2022.2.
# Address map (AXI-Lite, 64 KiB each): 0xA000_0000 axi_gpio (LEDs), 0xA001_0000 mpcc_hls.
# Outputs: MPCC_tcl/ (project), out/mpcc_hil.bit, out/mpcc_hil.hwh, out/system_wrapper.xsa,
#          timing_impl.rpt, util_impl.rpt. PS driver: PS_notebook/libs/mpcc_overlay.py.
set ip_repo [lindex $argv 0]
set run_impl 1
if {[llength $argv] > 1} { set run_impl [lindex $argv 1] }
set here [file dirname [file normalize [info script]]]
set part xczu7ev-ffvc1156-2-e
set board [get_board_parts -quiet -latest_file_version *zcu104*]

create_project -force MPCC_tcl $here/MPCC_tcl -part $part
if {$board ne ""} { set_property board_part $board [current_project] }
set_property ip_repo_paths [list $ip_repo] [current_project]
update_ip_catalog

create_bd_design system
proc xip {name} { return [lindex [lsort [get_ipdefs -all -filter "VLNV =~ xilinx.com:ip:${name}:*"]] end] }
# --- PS: both FPD master ports feed the SmartConnect, as in system.bd
set ps [create_bd_cell -type ip -vlnv [xip zynq_ultra_ps_e] zynq_ultra_ps_e_0]
if {$board ne ""} { apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps }
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {1} CONFIG.PSU__USE__M_AXI_GP1 {1} CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {128} CONFIG.PSU__MAXIGP1__DATA_WIDTH {128} \
    CONFIG.PSU__USE__IRQ0 {1} CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] $ps
# --- HLS IP
set vl [get_ipdefs -quiet -filter "NAME == mpcc_hls"]
if {$vl eq ""} { puts "ERROR: IP mpcc_hls not found in $ip_repo"; exit 1 }
set mpcc [create_bd_cell -type ip -vlnv [lindex $vl 0] mpcc_hls_0]
set gpio [create_bd_cell -type ip -vlnv [xip axi_gpio] axi_gpio_0]
set_property -dict [list CONFIG.C_GPIO_WIDTH {4} CONFIG.C_ALL_OUTPUTS {1}] $gpio
set smc [create_bd_cell -type ip -vlnv [xip smartconnect] axi_smc]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {2}] $smc
set rst [create_bd_cell -type ip -vlnv [xip proc_sys_reset] rst_ps8_0_100M]
connect_bd_net [get_bd_pins $ps/pl_clk0] [get_bd_pins $ps/maxihpm0_fpd_aclk] [get_bd_pins $ps/maxihpm1_fpd_aclk] \
    [get_bd_pins $smc/aclk] [get_bd_pins $rst/slowest_sync_clk] [get_bd_pins $gpio/s_axi_aclk] [get_bd_pins $mpcc/ap_clk]
connect_bd_net [get_bd_pins $ps/pl_resetn0] [get_bd_pins $rst/ext_reset_in]
connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $smc/aresetn] [get_bd_pins $gpio/s_axi_aresetn] [get_bd_pins $mpcc/ap_rst_n]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM0_FPD] [get_bd_intf_pins $smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM1_FPD] [get_bd_intf_pins $smc/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins $smc/M00_AXI] [get_bd_intf_pins $gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins $smc/M01_AXI] [get_bd_intf_pins $mpcc/s_axi_control]
# --- addresses (same map as system.bd)
assign_bd_address
foreach {n off} {axi_gpio_0 0xA0000000 mpcc_hls_0 0xA0010000} {
    foreach seg [get_bd_addr_segs -quiet "zynq_ultra_ps_e_0/Data/SEG_${n}_Reg"] { set_property offset [format 0xA0F%X0000 [lsearch {axi_gpio_0 mpcc_hls_0} $n]] $seg }
}
foreach {n off} {axi_gpio_0 0xA0000000 mpcc_hls_0 0xA0010000} {
    foreach seg [get_bd_addr_segs -quiet "zynq_ultra_ps_e_0/Data/SEG_${n}_Reg"] { set_property offset $off $seg }
}
# --- LEDs (board interface if the board files are present)
if {$board ne ""} {
    catch { apply_bd_automation -rule xilinx.com:bd_rule:board -config {Board_Interface "led_4bits ( LED ) "} [get_bd_intf_pins $gpio/GPIO] }
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files system.bd] -top
add_files -norecurse [file join $here MPCC_tcl MPCC_tcl.gen sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

if {$run_impl} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    open_run impl_1
    report_timing_summary -file $here/timing_impl.rpt
    report_utilization -file $here/util_impl.rpt -hierarchical
    file mkdir $here/out
    file copy -force $here/MPCC_tcl/MPCC_tcl.runs/impl_1/system_wrapper.bit $here/out/mpcc_hil.bit
    file copy -force $here/MPCC_tcl/MPCC_tcl.gen/sources_1/bd/system/hw_handoff/system.hwh $here/out/mpcc_hil.hwh
    write_hw_platform -fixed -include_bit -force -file $here/out/system_wrapper.xsa
    puts "BUILD_DONE bit=$here/out/mpcc_hil.bit"
}
