# Vitis HLS 2022.2 Tcl flow for the five HLS_PRJ components (the flow used for the ZCU104 builds;
# hls_config.cfg / vitis-comp.json serve the 2023.2+ unified flow instead).
#
#   cd HLS_PRJ
#   HLS_COMPONENT=mpcc_r HLS_STEPS="csim csynth export" vitis_hls -f build_hls.tcl
#
# HLS_COMPONENT : mpcc | mpcc_r | emi_feat | emi_detector | harmonic_estimator
# HLS_STEPS     : any of csim (C simulation against tb_data), csynth (C synthesis),
#                 export (IP catalog); default "csim csynth export"
# The work directory is <component>/<component>/ (ignored by git); the packaged IP is written to
# <component>/<component>/hls/impl/ip, so HLS_PRJ itself can be given to Vivado as the IP repository.
set comp  $::env(HLS_COMPONENT)
set steps [expr {[info exists ::env(HLS_STEPS)] ? $::env(HLS_STEPS) : "csim csynth export"}]
set root  [file dirname [file normalize [info script]]]
set dir   [file join $root $comp]
cd $dir

# hls4ml firmware of the two network components: include paths are absolute so that C simulation,
# which compiles in <work>/hls/csim/build, resolves them. WEIGHTS_DIR keeps its default ("weights");
# firmware/weights is added as a testbench directory so that the default resolves during C simulation.
set nn "-std=c++14 -I$dir/firmware -I$dir/firmware/nnet_utils"
switch $comp {
    mpcc {
        set top mpcc_hls
        set syn [list [list mpcc_hls.cpp ""] [list mpcc_hls.h ""]]
        set tb  [list [list tb_mpcc.cpp ""]]
    }
    mpcc_r {
        set top mpcc_r_hls
        set syn [list [list mpcc_r_hls.cpp ""] [list mpcc_r_hls.h ""]]
        set tb  [list [list tb_mpcc_r.cpp ""] [list ../mpcc/mpcc_hls.cpp ""] [list ../mpcc/mpcc_hls.h ""]]
    }
    emi_feat {
        set top emi_feat_hls
        set syn [list [list emi_feat_hls.cpp ""] [list emi_feat_hls.h ""] [list trig_tables.h ""]]
        set tb  [list [list tb_emi_feat.cpp ""] [list tb_data ""]]
    }
    emi_detector {
        set top emi_detector_axi
        set syn [list [list emi_detector_axi.cpp $nn] [list firmware/emi_detector.cpp $nn]]
        set tb  [list [list tb_emi_detector.cpp $nn] [list tb_data ""] [list firmware/weights ""]]
    }
    harmonic_estimator {
        set top harmonic_estimator_axi
        set syn [list [list harmonic_estimator_axi.cpp $nn] [list firmware/harmonic_estimator.cpp $nn]]
        set tb  [list [list tb_harmonic_estimator.cpp $nn] [list tb_data ""] [list firmware/weights ""]]
    }
    default { puts "ERROR: unknown component '$comp'"; exit 1 }
}

open_project -reset $comp
set_top $top
foreach f $syn {
    if {[lindex $f 1] eq ""} { add_files [lindex $f 0] } else { add_files -cflags [lindex $f 1] [lindex $f 0] }
}
foreach f $tb {
    if {[lindex $f 1] eq ""} { add_files -tb [lindex $f 0] } else { add_files -tb -cflags [lindex $f 1] [lindex $f 0] }
}
open_solution -reset hls -flow_target vivado
set_part xczu7ev-ffvc1156-2-e
create_clock -period 10 -name default
set_clock_uncertainty 27%

if {[lsearch $steps csim]   >= 0} { csim_design }
if {[lsearch $steps csynth] >= 0} { csynth_design }
if {[lsearch $steps export] >= 0} { export_design -format ip_catalog }
exit
