module blinky (clk,
    led,
    rst);
 input clk;
 output led;
 input rst;

 wire _000_;
 wire _001_;
 wire _002_;
 wire _003_;
 wire _004_;
 wire _005_;
 wire _006_;
 wire _007_;
 wire _008_;
 wire _009_;
 wire _010_;
 wire _011_;
 wire _012_;
 wire _013_;
 wire _014_;
 wire _015_;
 wire _016_;
 wire _017_;
 wire _018_;
 wire _019_;
 wire _020_;
 wire _021_;
 wire _022_;
 wire _023_;
 wire _024_;
 wire _025_;
 wire _026_;
 wire _027_;
 wire _028_;
 wire _029_;
 wire _030_;
 wire _031_;
 wire _032_;
 wire _033_;
 wire _034_;
 wire _035_;
 wire _036_;
 wire _037_;
 wire _038_;
 wire _039_;
 wire _040_;
 wire _041_;
 wire _042_;
 wire _043_;
 wire _044_;
 wire _045_;
 wire _046_;
 wire _047_;
 wire _048_;
 wire \count[0] ;
 wire \count[10] ;
 wire \count[11] ;
 wire \count[12] ;
 wire \count[13] ;
 wire \count[14] ;
 wire \count[1] ;
 wire \count[2] ;
 wire \count[3] ;
 wire \count[4] ;
 wire \count[5] ;
 wire \count[6] ;
 wire \count[7] ;
 wire \count[8] ;
 wire \count[9] ;
 wire net2;
 wire net1;
 wire net3;
 wire net4;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net9;
 wire net10;
 wire net11;
 wire net12;
 wire net13;
 wire net14;
 wire net15;
 wire net16;
 wire net17;
 wire net18;

 sky130_ef_sc_hd__decap_12 FILLER_0_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_27 ();
 sky130_fd_sc_hd__decap_6 FILLER_0_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_0_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_35 ();
 sky130_ef_sc_hd__decap_12 FILLER_0_39 ();
 sky130_fd_sc_hd__decap_4 FILLER_0_51 ();
 sky130_fd_sc_hd__fill_1 FILLER_0_55 ();
 sky130_fd_sc_hd__decap_3 FILLER_0_57 ();
 sky130_fd_sc_hd__fill_2 FILLER_0_85 ();
 sky130_ef_sc_hd__decap_12 FILLER_10_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_27 ();
 sky130_fd_sc_hd__decap_4 FILLER_10_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_10_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_33 ();
 sky130_ef_sc_hd__decap_12 FILLER_10_41 ();
 sky130_fd_sc_hd__decap_4 FILLER_10_53 ();
 sky130_fd_sc_hd__fill_1 FILLER_10_57 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_79 ();
 sky130_fd_sc_hd__fill_2 FILLER_10_85 ();
 sky130_fd_sc_hd__fill_1 FILLER_11_15 ();
 sky130_fd_sc_hd__fill_2 FILLER_11_19 ();
 sky130_ef_sc_hd__decap_12 FILLER_11_3 ();
 sky130_ef_sc_hd__decap_12 FILLER_11_34 ();
 sky130_fd_sc_hd__decap_8 FILLER_11_46 ();
 sky130_fd_sc_hd__fill_2 FILLER_11_54 ();
 sky130_fd_sc_hd__decap_8 FILLER_11_57 ();
 sky130_fd_sc_hd__decap_3 FILLER_11_72 ();
 sky130_ef_sc_hd__decap_12 FILLER_11_83 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_27 ();
 sky130_fd_sc_hd__decap_3 FILLER_12_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_42 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_46 ();
 sky130_fd_sc_hd__decap_4 FILLER_12_80 ();
 sky130_fd_sc_hd__fill_2 FILLER_12_85 ();
 sky130_fd_sc_hd__decap_4 FILLER_12_90 ();
 sky130_fd_sc_hd__fill_1 FILLER_12_94 ();
 sky130_fd_sc_hd__decap_4 FILLER_13_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_13_19 ();
 sky130_ef_sc_hd__decap_12 FILLER_13_3 ();
 sky130_fd_sc_hd__fill_2 FILLER_13_54 ();
 sky130_fd_sc_hd__fill_1 FILLER_13_57 ();
 sky130_ef_sc_hd__decap_12 FILLER_14_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_14_27 ();
 sky130_fd_sc_hd__decap_4 FILLER_14_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_14_3 ();
 sky130_fd_sc_hd__decap_8 FILLER_14_41 ();
 sky130_fd_sc_hd__decap_3 FILLER_14_49 ();
 sky130_fd_sc_hd__decap_8 FILLER_14_73 ();
 sky130_fd_sc_hd__decap_3 FILLER_14_81 ();
 sky130_fd_sc_hd__decap_8 FILLER_14_85 ();
 sky130_fd_sc_hd__fill_2 FILLER_14_93 ();
 sky130_ef_sc_hd__decap_12 FILLER_15_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_15_27 ();
 sky130_fd_sc_hd__decap_3 FILLER_15_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_15_3 ();
 sky130_ef_sc_hd__decap_12 FILLER_15_40 ();
 sky130_fd_sc_hd__decap_4 FILLER_15_52 ();
 sky130_ef_sc_hd__decap_12 FILLER_15_57 ();
 sky130_ef_sc_hd__decap_12 FILLER_15_69 ();
 sky130_fd_sc_hd__decap_3 FILLER_15_81 ();
 sky130_fd_sc_hd__decap_8 FILLER_15_85 ();
 sky130_fd_sc_hd__fill_2 FILLER_15_93 ();
 sky130_fd_sc_hd__fill_2 FILLER_1_11 ();
 sky130_fd_sc_hd__decap_8 FILLER_1_3 ();
 sky130_fd_sc_hd__decap_6 FILLER_1_47 ();
 sky130_fd_sc_hd__decap_4 FILLER_1_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_61 ();
 sky130_fd_sc_hd__fill_1 FILLER_1_83 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_15 ();
 sky130_fd_sc_hd__decap_8 FILLER_2_20 ();
 sky130_fd_sc_hd__decap_4 FILLER_2_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_2_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_33 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_42 ();
 sky130_fd_sc_hd__decap_6 FILLER_2_77 ();
 sky130_fd_sc_hd__fill_1 FILLER_2_83 ();
 sky130_fd_sc_hd__fill_2 FILLER_2_93 ();
 sky130_fd_sc_hd__decap_4 FILLER_3_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_35 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_44 ();
 sky130_fd_sc_hd__decap_3 FILLER_3_53 ();
 sky130_fd_sc_hd__decap_8 FILLER_3_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_3_73 ();
 sky130_fd_sc_hd__decap_6 FILLER_4_15 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_27 ();
 sky130_fd_sc_hd__decap_6 FILLER_4_29 ();
 sky130_ef_sc_hd__decap_12 FILLER_4_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_35 ();
 sky130_fd_sc_hd__decap_6 FILLER_4_52 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_58 ();
 sky130_fd_sc_hd__decap_8 FILLER_4_65 ();
 sky130_fd_sc_hd__fill_1 FILLER_4_73 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_82 ();
 sky130_fd_sc_hd__fill_2 FILLER_4_85 ();
 sky130_fd_sc_hd__decap_4 FILLER_5_24 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_28 ();
 sky130_fd_sc_hd__decap_4 FILLER_5_3 ();
 sky130_fd_sc_hd__decap_4 FILLER_5_36 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_40 ();
 sky130_fd_sc_hd__decap_8 FILLER_5_47 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_55 ();
 sky130_fd_sc_hd__fill_2 FILLER_5_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_5_7 ();
 sky130_fd_sc_hd__decap_4 FILLER_6_24 ();
 sky130_fd_sc_hd__decap_6 FILLER_6_29 ();
 sky130_fd_sc_hd__decap_8 FILLER_6_41 ();
 sky130_fd_sc_hd__decap_3 FILLER_6_49 ();
 sky130_fd_sc_hd__decap_8 FILLER_6_73 ();
 sky130_fd_sc_hd__fill_2 FILLER_6_93 ();
 sky130_fd_sc_hd__decap_4 FILLER_7_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_36 ();
 sky130_fd_sc_hd__decap_4 FILLER_7_44 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_48 ();
 sky130_fd_sc_hd__decap_4 FILLER_7_52 ();
 sky130_fd_sc_hd__decap_4 FILLER_7_57 ();
 sky130_fd_sc_hd__decap_8 FILLER_7_64 ();
 sky130_fd_sc_hd__fill_1 FILLER_7_7 ();
 sky130_fd_sc_hd__decap_3 FILLER_7_92 ();
 sky130_fd_sc_hd__decap_6 FILLER_8_3 ();
 sky130_fd_sc_hd__decap_6 FILLER_8_37 ();
 sky130_fd_sc_hd__decap_4 FILLER_8_63 ();
 sky130_fd_sc_hd__fill_1 FILLER_8_67 ();
 sky130_fd_sc_hd__decap_3 FILLER_8_85 ();
 sky130_fd_sc_hd__decap_4 FILLER_8_91 ();
 sky130_fd_sc_hd__fill_2 FILLER_9_25 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_3 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_57 ();
 sky130_fd_sc_hd__fill_1 FILLER_9_65 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_0_Left_16 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_0_Right_0 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_10_Left_26 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_10_Right_10 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_11_Left_27 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_11_Right_11 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_12_Left_28 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_12_Right_12 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_13_Left_29 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_13_Right_13 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_14_Left_30 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_14_Right_14 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_15_Left_31 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_15_Right_15 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_1_Left_17 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_1_Right_1 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_2_Left_18 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_2_Right_2 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_3_Left_19 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_3_Right_3 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_4_Left_20 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_4_Right_4 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_5_Left_21 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_5_Right_5 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_6_Left_22 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_6_Right_6 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_7_Left_23 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_7_Right_7 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_8_Left_24 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_8_Right_8 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_9_Left_25 ();
 sky130_fd_sc_hd__decap_3 PHY_EDGE_ROW_9_Right_9 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_32 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_33 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_0_34 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_10_48 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_10_49 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_11_50 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_51 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_12_52 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_13_53 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_14_54 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_14_55 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_15_56 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_15_57 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_15_58 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_1_35 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_2_36 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_2_37 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_3_38 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_4_39 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_4_40 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_5_41 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_6_42 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_6_43 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_7_44 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_8_45 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_8_46 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_TAPCELL_ROW_9_47 ();
 sky130_fd_sc_hd__inv_2 _049_ (.A(net5),
    .Y(_000_));
 sky130_fd_sc_hd__inv_2 _050_ (.A(net3),
    .Y(_016_));
 sky130_fd_sc_hd__nand2_2 _051_ (.A(\count[0] ),
    .B(\count[1] ),
    .Y(_032_));
 sky130_fd_sc_hd__or2_2 _052_ (.A(\count[0] ),
    .B(\count[1] ),
    .X(_033_));
 sky130_fd_sc_hd__and2_2 _053_ (.A(_032_),
    .B(_033_),
    .X(_007_));
 sky130_fd_sc_hd__xnor2_2 _054_ (.A(net8),
    .B(_032_),
    .Y(_008_));
 sky130_fd_sc_hd__and4_2 _055_ (.A(\count[0] ),
    .B(\count[1] ),
    .C(\count[2] ),
    .D(\count[3] ),
    .X(_034_));
 sky130_fd_sc_hd__a31o_2 _056_ (.A1(\count[0] ),
    .A2(\count[1] ),
    .A3(\count[2] ),
    .B1(net17),
    .X(_035_));
 sky130_fd_sc_hd__and2b_2 _057_ (.A_N(_034_),
    .B(_035_),
    .X(_009_));
 sky130_fd_sc_hd__nand2_2 _058_ (.A(net18),
    .B(_034_),
    .Y(_036_));
 sky130_fd_sc_hd__xor2_2 _059_ (.A(net16),
    .B(_034_),
    .X(_010_));
 sky130_fd_sc_hd__xnor2_2 _060_ (.A(net12),
    .B(_036_),
    .Y(_011_));
 sky130_fd_sc_hd__and4_2 _061_ (.A(\count[4] ),
    .B(\count[5] ),
    .C(\count[6] ),
    .D(_034_),
    .X(_037_));
 sky130_fd_sc_hd__a31o_2 _062_ (.A1(\count[4] ),
    .A2(\count[5] ),
    .A3(_034_),
    .B1(\count[6] ),
    .X(_038_));
 sky130_fd_sc_hd__and2b_2 _063_ (.A_N(_037_),
    .B(_038_),
    .X(_012_));
 sky130_fd_sc_hd__and4_2 _064_ (.A(\count[4] ),
    .B(\count[5] ),
    .C(\count[6] ),
    .D(\count[7] ),
    .X(_039_));
 sky130_fd_sc_hd__and2_2 _065_ (.A(_034_),
    .B(_039_),
    .X(_040_));
 sky130_fd_sc_hd__o21ba_2 _066_ (.A1(net13),
    .A2(_037_),
    .B1_N(_040_),
    .X(_013_));
 sky130_fd_sc_hd__xor2_2 _067_ (.A(net14),
    .B(_040_),
    .X(_014_));
 sky130_fd_sc_hd__and3_2 _068_ (.A(\count[8] ),
    .B(\count[9] ),
    .C(_040_),
    .X(_041_));
 sky130_fd_sc_hd__a31o_2 _069_ (.A1(\count[8] ),
    .A2(_034_),
    .A3(_039_),
    .B1(\count[9] ),
    .X(_042_));
 sky130_fd_sc_hd__and2b_2 _070_ (.A_N(_041_),
    .B(_042_),
    .X(_015_));
 sky130_fd_sc_hd__and4_2 _071_ (.A(\count[8] ),
    .B(\count[9] ),
    .C(\count[10] ),
    .D(_040_),
    .X(_043_));
 sky130_fd_sc_hd__xor2_2 _072_ (.A(net10),
    .B(_041_),
    .X(_001_));
 sky130_fd_sc_hd__and4_2 _073_ (.A(\count[8] ),
    .B(\count[9] ),
    .C(\count[10] ),
    .D(\count[11] ),
    .X(_044_));
 sky130_fd_sc_hd__and3_2 _074_ (.A(_034_),
    .B(_039_),
    .C(_044_),
    .X(_045_));
 sky130_fd_sc_hd__o21ba_2 _075_ (.A1(net11),
    .A2(_043_),
    .B1_N(_045_),
    .X(_002_));
 sky130_fd_sc_hd__xor2_2 _076_ (.A(net15),
    .B(_045_),
    .X(_003_));
 sky130_fd_sc_hd__nand3_2 _077_ (.A(\count[12] ),
    .B(\count[13] ),
    .C(_045_),
    .Y(_046_));
 sky130_fd_sc_hd__a21o_2 _078_ (.A1(\count[12] ),
    .A2(_045_),
    .B1(\count[13] ),
    .X(_047_));
 sky130_fd_sc_hd__and2_2 _079_ (.A(_046_),
    .B(_047_),
    .X(_004_));
 sky130_fd_sc_hd__and4_2 _080_ (.A(\count[12] ),
    .B(\count[13] ),
    .C(\count[14] ),
    .D(_045_),
    .X(_048_));
 sky130_fd_sc_hd__xnor2_2 _081_ (.A(net6),
    .B(_046_),
    .Y(_005_));
 sky130_fd_sc_hd__xor2_2 _082_ (.A(net7),
    .B(_048_),
    .X(_006_));
 sky130_fd_sc_hd__inv_2 _083_ (.A(net3),
    .Y(_017_));
 sky130_fd_sc_hd__inv_2 _084_ (.A(net3),
    .Y(_018_));
 sky130_fd_sc_hd__inv_2 _085_ (.A(net4),
    .Y(_019_));
 sky130_fd_sc_hd__inv_2 _086_ (.A(net4),
    .Y(_020_));
 sky130_fd_sc_hd__inv_2 _087_ (.A(net4),
    .Y(_021_));
 sky130_fd_sc_hd__inv_2 _088_ (.A(net4),
    .Y(_022_));
 sky130_fd_sc_hd__inv_2 _089_ (.A(net3),
    .Y(_023_));
 sky130_fd_sc_hd__inv_2 _090_ (.A(net3),
    .Y(_024_));
 sky130_fd_sc_hd__inv_2 _091_ (.A(net3),
    .Y(_025_));
 sky130_fd_sc_hd__inv_2 _092_ (.A(net3),
    .Y(_026_));
 sky130_fd_sc_hd__inv_2 _093_ (.A(net3),
    .Y(_027_));
 sky130_fd_sc_hd__inv_2 _094_ (.A(net3),
    .Y(_028_));
 sky130_fd_sc_hd__inv_2 _095_ (.A(net3),
    .Y(_029_));
 sky130_fd_sc_hd__inv_2 _096_ (.A(net4),
    .Y(_030_));
 sky130_fd_sc_hd__inv_2 _097_ (.A(net4),
    .Y(_031_));
 sky130_fd_sc_hd__dfrtp_2 _098_ (.CLK(clknet_1_0__leaf_clk),
    .D(_004_),
    .RESET_B(_016_),
    .Q(\count[13] ));
 sky130_fd_sc_hd__dfrtp_2 _099_ (.CLK(clknet_1_1__leaf_clk),
    .D(_005_),
    .RESET_B(_017_),
    .Q(\count[14] ));
 sky130_fd_sc_hd__dfrtp_2 _100_ (.CLK(clknet_1_1__leaf_clk),
    .D(_006_),
    .RESET_B(_018_),
    .Q(net2));
 sky130_fd_sc_hd__dfrtp_2 _101_ (.CLK(clknet_1_1__leaf_clk),
    .D(_000_),
    .RESET_B(_019_),
    .Q(\count[0] ));
 sky130_fd_sc_hd__dfrtp_2 _102_ (.CLK(clknet_1_1__leaf_clk),
    .D(_007_),
    .RESET_B(_020_),
    .Q(\count[1] ));
 sky130_fd_sc_hd__dfrtp_2 _103_ (.CLK(clknet_1_0__leaf_clk),
    .D(net9),
    .RESET_B(_021_),
    .Q(\count[2] ));
 sky130_fd_sc_hd__dfrtp_2 _104_ (.CLK(clknet_1_1__leaf_clk),
    .D(_009_),
    .RESET_B(_022_),
    .Q(\count[3] ));
 sky130_fd_sc_hd__dfrtp_2 _105_ (.CLK(clknet_1_1__leaf_clk),
    .D(_010_),
    .RESET_B(_023_),
    .Q(\count[4] ));
 sky130_fd_sc_hd__dfrtp_2 _106_ (.CLK(clknet_1_0__leaf_clk),
    .D(_011_),
    .RESET_B(_024_),
    .Q(\count[5] ));
 sky130_fd_sc_hd__dfrtp_2 _107_ (.CLK(clknet_1_0__leaf_clk),
    .D(_012_),
    .RESET_B(_025_),
    .Q(\count[6] ));
 sky130_fd_sc_hd__dfrtp_2 _108_ (.CLK(clknet_1_0__leaf_clk),
    .D(_013_),
    .RESET_B(_026_),
    .Q(\count[7] ));
 sky130_fd_sc_hd__dfrtp_2 _109_ (.CLK(clknet_1_0__leaf_clk),
    .D(_014_),
    .RESET_B(_027_),
    .Q(\count[8] ));
 sky130_fd_sc_hd__dfrtp_2 _110_ (.CLK(clknet_1_0__leaf_clk),
    .D(_015_),
    .RESET_B(_028_),
    .Q(\count[9] ));
 sky130_fd_sc_hd__dfrtp_2 _111_ (.CLK(clknet_1_0__leaf_clk),
    .D(_001_),
    .RESET_B(_029_),
    .Q(\count[10] ));
 sky130_fd_sc_hd__dfrtp_2 _112_ (.CLK(clknet_1_1__leaf_clk),
    .D(_002_),
    .RESET_B(_030_),
    .Q(\count[11] ));
 sky130_fd_sc_hd__dfrtp_2 _113_ (.CLK(clknet_1_1__leaf_clk),
    .D(_003_),
    .RESET_B(_031_),
    .Q(\count[12] ));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .X(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .X(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s25_1 fanout3 (.A(net1),
    .X(net3));
 sky130_fd_sc_hd__clkdlybuf4s25_1 fanout4 (.A(net1),
    .X(net4));
 sky130_fd_sc_hd__dlygate4sd3_1 hold10 (.A(\count[10] ),
    .X(net10));
 sky130_fd_sc_hd__dlygate4sd3_1 hold11 (.A(\count[11] ),
    .X(net11));
 sky130_fd_sc_hd__dlygate4sd3_1 hold12 (.A(\count[5] ),
    .X(net12));
 sky130_fd_sc_hd__dlygate4sd3_1 hold13 (.A(\count[7] ),
    .X(net13));
 sky130_fd_sc_hd__dlygate4sd3_1 hold14 (.A(\count[8] ),
    .X(net14));
 sky130_fd_sc_hd__dlygate4sd3_1 hold15 (.A(\count[12] ),
    .X(net15));
 sky130_fd_sc_hd__dlygate4sd3_1 hold16 (.A(\count[4] ),
    .X(net16));
 sky130_fd_sc_hd__dlygate4sd3_1 hold17 (.A(\count[3] ),
    .X(net17));
 sky130_fd_sc_hd__dlygate4sd3_1 hold18 (.A(\count[4] ),
    .X(net18));
 sky130_fd_sc_hd__dlygate4sd3_1 hold5 (.A(\count[0] ),
    .X(net5));
 sky130_fd_sc_hd__dlygate4sd3_1 hold6 (.A(\count[14] ),
    .X(net6));
 sky130_fd_sc_hd__dlygate4sd3_1 hold7 (.A(net2),
    .X(net7));
 sky130_fd_sc_hd__dlygate4sd3_1 hold8 (.A(\count[2] ),
    .X(net8));
 sky130_fd_sc_hd__dlygate4sd3_1 hold9 (.A(_008_),
    .X(net9));
 sky130_fd_sc_hd__clkdlybuf4s25_1 input1 (.A(rst),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s25_1 output2 (.A(net2),
    .X(led));
endmodule
