create_project -force -part xczu7ev-ffvc1156-2-e tmp_ipq /tmp/claude-1000/tmp_ipq
update_ip_catalog
puts "N=[llength [get_ipdefs -all]]"
puts "A=[get_ipdefs -all *zynq_ultra_ps_e*]"
puts "B=[get_ipdefs -all -filter {VLNV =~ xilinx.com:ip:axi_gpio:*}]"
puts "C=[lindex [lsort [get_ipdefs -all -filter "VLNV =~ xilinx.com:ip:smartconnect:*"]] end]"
puts "D=[get_board_parts -quiet -latest_file_version *zcu104*]"
exit
