import sys
import os
import io
import contextlib
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add scripts/ to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import entrypoint

class TestEntrypoint(unittest.TestCase):
    def setUp(self):
        # Create a temp dir
        self.test_dir = tempfile.mkdtemp()

        # Create structure: src/sub/sub.v, src/top.v, include/consts.vh, test/top_tb.v
        os.makedirs(os.path.join(self.test_dir, "src/sub"))
        os.makedirs(os.path.join(self.test_dir, "include"))
        os.makedirs(os.path.join(self.test_dir, "test"))

        # Create dummy files
        with open(os.path.join(self.test_dir, "src/top.v"), "w") as f:
            f.write("module top; endmodule")
        with open(os.path.join(self.test_dir, "src/sub/sub.v"), "w") as f:
            f.write("module sub; endmodule")
        with open(os.path.join(self.test_dir, "include/consts.vh"), "w") as f:
            f.write("")
        with open(os.path.join(self.test_dir, "test/top_tb.v"), "w") as f:
            f.write("module top_tb; endmodule")

        self.config = {
            "VERILOG_FILES": ["src/**/*.v"],
            "TEST_FILES": ["test/*.v"],
            "VERILOG_INCLUDE_DIRS": ["include"],
            "DESIGN_NAME": "top"
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_lint(self, mock_ensure, mock_load, mock_run):
        mock_load.return_value = self.config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_lint(args, self.config)

            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], "verilator")

            # Verify RTL files are included
            self.assertTrue(any("src/sub/sub.v" in arg for arg in call_args))
            self.assertTrue(any("src/top.v" in arg for arg in call_args))

            # Verify Test files are NOT included
            self.assertFalse(any("test/top_tb.v" in arg for arg in call_args))

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim(self, mock_ensure, mock_load, mock_run):
        mock_load.return_value = self.config
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_sim(args, self.config)

            calls = mock_run.call_args_list
            compile_cmd = calls[0][0][0]
            self.assertEqual(compile_cmd[0], "iverilog")

            # Verify RTL files are included
            self.assertTrue(any("src/sub/sub.v" in arg for arg in compile_cmd))

            # Verify Test files ARE included for Sim
            self.assertTrue(any("test/top_tb.v" in arg for arg in compile_cmd))

            run_cmd = calls[1][0][0]
            self.assertEqual(run_cmd, ["vvp", "build/sim.vvp"])

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_synth(self, mock_ensure, mock_load, mock_run):
        mock_load.return_value = self.config
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_synth(args, self.config)

            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], "yosys")
            yosys_cmd = call_args[2]

            # Verify RTL files are included
            self.assertIn("read_verilog src/sub/sub.v", yosys_cmd)
            self.assertIn("read_verilog src/top.v", yosys_cmd)

            # Verify Test files are NOT included for Synth
            self.assertNotIn("test/top_tb.v", yosys_cmd)

            self.assertIn("synth -top top", yosys_cmd)

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_librelane_dialect(self, mock_ensure, mock_load, mock_run):
        # A config written the way LibreLane expects: 'dir::' paths, and the
        # key LibreLane does not own hidden behind a '//' prefix so that its
        # strict validation ignores it.
        config = {
            "VERILOG_FILES": ["dir::src/**/*.v"],
            "//TEST_FILES": ["dir::test/*.v"],
            "DESIGN_NAME": "top"
        }
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_sim(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertTrue(any("src/top.v" in arg for arg in compile_cmd))
            self.assertTrue(any("test/top_tb.v" in arg for arg in compile_cmd))
            # The prefix must not survive into the tool invocation
            self.assertFalse(any(arg.startswith("dir::") for arg in compile_cmd))

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_blank_cli_files_does_not_shadow_config(self, mock_ensure, mock_load, mock_run):
        # An empty --files used to win over the config file, leaving the tool
        # with no inputs at all.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = [""]

            entrypoint.cmd_lint(args, self.config)

            call_args = mock_run.call_args[0][0]
            self.assertTrue(any("src/top.v" in arg for arg in call_args))

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_lint_silences_the_warnings_the_config_names(self, mock_ensure, mock_load, mock_run):
        # Generated RTL trips warnings that are about the generator, not the
        # design. Without this the config could say so and lint would refuse
        # the file anyway.
        config = dict(self.config, LINTER_DISABLE_WARNINGS=["WIDTHEXPAND", "MULTIDRIVEN"])
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_lint(args, config)

            call_args = mock_run.call_args[0][0]
            self.assertIn("-Wno-WIDTHEXPAND", call_args)
            self.assertIn("-Wno-MULTIDRIVEN", call_args)

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_lint_waives_nothing_when_the_config_is_silent(self, mock_ensure, mock_load, mock_run):
        # LibreLane defaults this key to DECLFILENAME and EOFNEWLINE. Neither
        # fires in verilator 5.020 unless asked for, so copying that default
        # would add flags that change nothing -- and would quietly widen what
        # `lint` lets through if a later verilator changed its mind.
        mock_load.return_value = self.config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_lint(args, self.config)

            call_args = mock_run.call_args[0][0]
            self.assertFalse([arg for arg in call_args if arg.startswith("-Wno-")])

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_lint_rejects_one_warning_written_without_its_brackets(self, mock_ensure, mock_load, mock_run):
        # A bare string is iterable, so this would otherwise spell out
        # -Wno-W -Wno-I -Wno-D ... and verilator would reject flags nobody
        # typed.
        config = dict(self.config, LINTER_DISABLE_WARNINGS="WIDTHEXPAND")
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            # log_error prints to stdout, so that is where the refusal lands.
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                entrypoint.cmd_lint(args, config)

            self.assertIn("LINTER_DISABLE_WARNINGS", out.getvalue())
            mock_run.assert_not_called()

        finally:
            os.chdir(cwd)

    def test_load_config_prefers_yaml(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with open("config.json", "w") as f:
                f.write('{"DESIGN_NAME": "from_json"}')
            with open("config.yaml", "w") as f:
                f.write("DESIGN_NAME: from_yaml\nVERILOG_FILES:\n  - dir::src/*.v\n")

            config = entrypoint.load_config()
            self.assertEqual(config["DESIGN_NAME"], "from_yaml")
            self.assertEqual(config["VERILOG_FILES"], ["dir::src/*.v"])

            os.remove("config.yaml")
            self.assertEqual(entrypoint.load_config()["DESIGN_NAME"], "from_json")

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_check_missing_rtl(self, mock_ensure, mock_load, mock_run):
        # Config with required GDS keys but missing RTL files
        gds_config = {
            "PDK": "sky130A",
            "STD_CELL_LIBRARY": "sky130_fd_sc_hd",
            "DIE_AREA": "0 0 100 100",
            "FP_CORE_UTIL": 40,
            "FP_SIZING": "absolute",
            "CLOCK_PORT": "clk",
            "CLOCK_PERIOD": 10.0,
            "VERILOG_FILES": ["non_existent.v"]
        }
        mock_load.return_value = gds_config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            # Create a Mock args object that behaves like Namespace but might lack attributes
            # Standard MagicMock allows attribute access, returning new Mocks.
            # We want to ensure access to 'files' returns None if not set, or we want to verify
            # behavior when 'files' is accessed.
            # In Python's argparse, if an argument is not present in the parser, it won't be in the Namespace.
            # So accessing args.files would raise AttributeError.

            # Let's mock a Namespace-like object that raises AttributeError for 'files'
            class MockArgs:
                pass

            args = MockArgs() # No attributes

            # Should exit with code 1 due to no matching files
            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_check(args, gds_config)

            self.assertEqual(cm.exception.code, 1)

        finally:
            os.chdir(cwd)

    # --- sim must never pass without actually simulating something ---

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_errors_when_test_files_match_nothing(self, mock_ensure, mock_load, mock_run):
        # This used to be a warning: sim compiled the RTL alone and exited 0,
        # so a renamed directory or a typo left CI green with nothing verified.
        config = dict(self.config, TEST_FILES=["test/*.sv"])
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_sim(args, config)

            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_errors_without_a_testbench(self, mock_ensure, mock_load, mock_run):
        config = {k: v for k, v in self.config.items() if k != "TEST_FILES"}
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_sim(args, config)

            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_requires_a_top_for_several_testbenches(self, mock_ensure, mock_load, mock_run):
        # Icarus roots every uninstantiated module, and the first $finish ends
        # the run -- so the second testbench was cut off mid-way, silently.
        with open(os.path.join(self.test_dir, "test/other_tb.v"), "w") as f:
            f.write("module other_tb; endmodule")
        mock_load.return_value = self.config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_sim(args, self.config)

            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()

        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_top_selects_the_root(self, mock_ensure, mock_load, mock_run):
        with open(os.path.join(self.test_dir, "test/other_tb.v"), "w") as f:
            f.write("module other_tb; endmodule")
        # Written the way a shared LibreLane config has to spell it.
        config = dict(self.config)
        config["//SIM_TOP"] = "top_tb"
        mock_load.return_value = config

        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None

            entrypoint.cmd_sim(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertIn("-s", compile_cmd)
            self.assertEqual(compile_cmd[compile_cmd.index("-s") + 1], "top_tb")
            # Both testbenches still compile; -s picks which one is the root.
            self.assertTrue(any("test/other_tb.v" in arg for arg in compile_cmd))

        finally:
            os.chdir(cwd)

    # --- schematic: the picture, not the netlist ---

    def _schematic_script(self, config, files=None):
        """Runs cmd_schematic with yosys stubbed and returns the -p script."""
        args = MagicMock()
        args.files = files
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch("entrypoint.run_command") as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    entrypoint.cmd_schematic(args, config)
            cmd = run.call_args[0][0]
        finally:
            os.chdir(cwd)
        self.assertEqual(cmd[0], "yosys")
        self.assertEqual(cmd[1], "-p")
        return cmd[2]

    def test_schematic_stops_before_synthesis(self):
        # The whole point. `synth` would leave a wall of technology cells;
        # proc and opt leave flops, adders and muxes with the source's names.
        script = self._schematic_script(self.config)

        self.assertIn("proc", script)
        self.assertIn("opt", script)
        self.assertNotIn("synth", script)

    def test_schematic_draws_the_top_the_config_names(self):
        self.assertIn("hierarchy -top top", self._schematic_script(self.config))

    def test_schematic_falls_back_to_auto_top(self):
        config = {k: v for k, v in self.config.items() if k != "DESIGN_NAME"}
        self.assertIn("hierarchy -auto-top", self._schematic_script(config))

    def test_schematic_does_not_try_to_open_a_window(self):
        # Without -viewer none, yosys launches a picture viewer for the file
        # it just wrote, which inside a container is an error on the way out.
        script = self._schematic_script(self.config)

        self.assertIn("-viewer none", script)
        self.assertIn(f"-prefix {entrypoint.SCHEMATIC_PREFIX}", script)

    def test_schematic_ignores_testbenches(self):
        # A testbench in the picture is noise, and TEST_FILES is in the config
        # this runs against.
        script = self._schematic_script(self.config)

        self.assertIn("src/top.v", script)
        self.assertNotIn("top_tb.v", script)

    # --- check: values, not just that the keys are there ---

    def _gds_config(self, **overrides):
        config = {
            "PDK": "sky130A",
            "STD_CELL_LIBRARY": "sky130_fd_sc_hd",
            "DIE_AREA": [0, 0, 100, 100],
            "FP_CORE_UTIL": 40,
            "FP_SIZING": "absolute",
            "CLOCK_PORT": "clk",
            "CLOCK_PERIOD": 10.0,
            "DESIGN_NAME": "top",
            "VERILOG_FILES": ["src/*.v"],
        }
        config.update(overrides)
        return config

    def _check(self, config):
        """Runs cmd_check in the temp tree and returns what it printed."""
        args = MagicMock()
        args.files = None
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                entrypoint.cmd_check(args, config)
        finally:
            os.chdir(cwd)
            # Kept on the instance so a test that expects a refusal can still
            # read the message. "A key is missing" that does not say which one
            # is barely better than silence, so the wording is worth asserting.
            self.check_output = out.getvalue()
        return self.check_output

    def test_check_accepts_a_design_that_exists(self):
        # src/top.v declares 'module top', which is what DESIGN_NAME names.
        self.assertIn("verified", self._check(self._gds_config()))

    def test_check_rejects_a_design_name_that_names_no_module(self):
        # The first wall after putting your own design in the template: the
        # config still says 'top' while the module is called something else.
        # Without this it surfaces minutes later as a Yosys error.
        with self.assertRaises(SystemExit) as cm:
            self._check(self._gds_config(DESIGN_NAME="my_cpu"))
        self.assertEqual(cm.exception.code, 1)

    def test_check_rejects_a_die_area_with_no_area(self):
        with self.assertRaises(SystemExit) as cm:
            self._check(self._gds_config(DIE_AREA=[0, 0, 100, 0]))
        self.assertEqual(cm.exception.code, 1)

    def test_check_accepts_relative_sizing_without_a_die_area(self):
        # FP_SIZING: relative computes the die from FP_CORE_UTIL and never
        # reads DIE_AREA. Demanding it anyway refused a config LibreLane would
        # have run -- and relative is the sizing a newcomer wants, since it
        # resizes itself around whatever design they put in.
        config = self._gds_config(FP_SIZING="relative")
        del config["DIE_AREA"]

        self.assertIn("verified", self._check(config))

    def test_check_rejects_relative_sizing_without_a_core_util(self):
        # The other half of the swap: under relative sizing FP_CORE_UTIL is the
        # variable that decides the die, so its absence is the real error.
        config = self._gds_config(FP_SIZING="relative")
        del config["FP_CORE_UTIL"]

        with self.assertRaises(SystemExit) as cm:
            self._check(config)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("FP_CORE_UTIL", self.check_output)

    def test_check_rejects_absolute_sizing_without_a_die_area(self):
        # Unchanged behaviour, and the reason the swap is a swap rather than a
        # removal: absolute sizing has nothing to floorplan without DIE_AREA.
        config = self._gds_config()
        del config["DIE_AREA"]

        with self.assertRaises(SystemExit) as cm:
            self._check(config)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("DIE_AREA", self.check_output)

    def test_check_rejects_a_malformed_die_area_even_under_relative_sizing(self):
        # Optional is not unread: LibreLane validates DIE_AREA's shape whatever
        # the sizing mode, so a malformed one is still an error -- three
        # minutes later, if this does not say it now.
        with self.assertRaises(SystemExit) as cm:
            self._check(self._gds_config(FP_SIZING="relative", DIE_AREA=[0, 0, 100, 0]))

        self.assertEqual(cm.exception.code, 1)

    def test_check_warns_but_passes_on_a_clock_port_absent_from_the_rtl(self):
        # A warning, not an error: proving a name IS a port means parsing a
        # port list. Proving it appears nowhere at all does not, and that is
        # the typo worth catching.
        out = self._check(self._gds_config(CLOCK_PORT="clock"))
        self.assertIn("clock", out)
        self.assertIn("WARN", out)
        self.assertIn("verified", out)

    def test_declared_modules_ignores_commented_out_modules(self):
        path = os.path.join(self.test_dir, "commented.v")
        with open(path, "w") as f:
            f.write("// module ghost;\n/* module phantom; */\nmodule real_one; endmodule\n")

        self.assertEqual(entrypoint.declared_modules([path]), {"real_one"})

    def test_check_is_reachable_under_both_names(self):
        parser_args = entrypoint.build_parser().parse_args(["gds"])
        self.assertIs(parser_args.func, entrypoint.cmd_check)
        parser_args = entrypoint.build_parser().parse_args(["check"])
        self.assertIs(parser_args.func, entrypoint.cmd_check)

    # --- report: the numbers the flow computes and then throws away ---

    FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "metrics.json")

    def _report(self, path):
        """Runs cmd_report and returns what it printed."""
        args = MagicMock()
        args.metrics = path
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            entrypoint.cmd_report(args, {"DESIGN_NAME": "blinky"})
        return out.getvalue()

    def test_report_reads_a_real_metrics_file(self):
        # Values are from an actual blinky run, not invented.
        out = self._report(self.FIXTURE)

        self.assertIn("blinky", out)
        self.assertIn("100 x 100 um", out)
        self.assertIn("10000 um^2", out)
        self.assertIn("29.2%", out)
        self.assertIn("243", out)
        self.assertIn("+4.69 ns", out)
        self.assertIn("+0.11 ns", out)
        self.assertIn("0.292 mW", out)
        self.assertIn("441", out)

    def test_report_ignores_per_corner_and_fill_inflated_metrics(self):
        out = self._report(self.FIXTURE)

        # The bare key is already the worst corner; the nom_tt value is better
        # and must not be the one reported.
        self.assertNotIn("+6.55", out)
        # design__instance__count is 787 because 544 of them are fill cells.
        self.assertNotIn("787", out)

    def test_report_survives_a_file_missing_most_metrics(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with open("partial.json", "w") as f:
                f.write('{"design__die__area": 10000, "design__die__bbox": "0 0 100 100"}')

            out = self._report("partial.json")

            self.assertIn("100 x 100 um", out)
            self.assertNotIn("slack", out)
        finally:
            os.chdir(cwd)

    def test_report_errors_when_no_metric_it_reads_is_present(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with open("other.json", "w") as f:
                f.write('{"route__wirelength": 2276}')

            with self.assertRaises(SystemExit) as cm:
                self._report("other.json")

            self.assertEqual(cm.exception.code, 1)
        finally:
            os.chdir(cwd)

    # --- report: the signoff checks, which say whether it can be made ---

    DIRTY_FIXTURE = os.path.join(
        os.path.dirname(__file__), "fixtures", "metrics-signoff-dirty.json"
    )

    def test_report_names_a_clean_signoff(self):
        # Zeroes rather than a real run's file because a real run cannot carry
        # anything else: LibreLane errors on every one of these checks by
        # default, so a finished run has passed them all by construction.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with open("clean.json", "w") as f:
                f.write('{"design__die__area": 10000,'
                        ' "design__die__bbox": "0 0 100 100",'
                        ' "magic__drc_error__count": 0,'
                        ' "klayout__drc_error__count": 0,'
                        ' "design__lvs_error__count": 0,'
                        ' "route__antenna_violation__count": 0,'
                        ' "design__xor_difference__count": 0}')

            out = self._report("clean.json")

            self.assertIn("signoff", out)
            self.assertIn("clean", out)
            # 'clean' is only as strong as the list of what was checked.
            for label in ("Magic DRC", "KLayout DRC", "LVS", "antenna", "XOR"):
                self.assertIn(label, out)
        finally:
            os.chdir(cwd)

    def test_report_names_what_failed_rather_than_listing_zeroes(self):
        out = self._report(self.DIRTY_FIXTURE)

        self.assertIn("2 Magic DRC", out)
        self.assertIn("1 LVS", out)
        # The whole point: a column of zeroes with one non-zero buried in it is
        # what this replaces.
        self.assertNotIn("clean", out)
        self.assertNotIn("0 antenna", out)

    def test_report_omits_signoff_when_the_run_reported_none(self):
        # The flow's own fixture predates these keys. A missing check is not a
        # passing one, so it must not print a signoff line at all.
        self.assertNotIn("signoff", self._report(self.FIXTURE))

    def test_find_render_prefers_the_copy_under_final(self):
        # Directory and filename both taken from a real LibreLane 3.0.14 run:
        # KLAYOUT_RENDER registers extension "png" and folder "render", so the
        # file is <design>.png, not <design>.klayout.png.
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        step = os.path.join(run, "42-klayout-render")
        final = os.path.join(run, "final", "render")
        os.makedirs(step)
        os.makedirs(final)
        for d in (step, final):
            open(os.path.join(d, "blinky.png"), "w").close()

        found = entrypoint.find_render(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, os.path.join(final, "blinky.png"))

    def test_find_render_falls_back_to_the_step_directory(self):
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        step = os.path.join(run, "42-klayout-render")
        os.makedirs(step)
        os.makedirs(os.path.join(run, "final"))
        open(os.path.join(step, "blinky.png"), "w").close()

        found = entrypoint.find_render(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, os.path.join(step, "blinky.png"))

    def test_find_render_ignores_a_png_some_other_step_wrote(self):
        # Globbing the whole run for *.png would report an IR-drop heatmap, or
        # anything else a step happens to draw, as the layout.
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        other = os.path.join(run, "77-openroad-irdropreport")
        os.makedirs(other)
        os.makedirs(os.path.join(run, "final"))
        open(os.path.join(other, "irdrop.png"), "w").close()

        self.assertIsNone(
            entrypoint.find_render(os.path.join(run, "final", "metrics.json"))
        )

    def test_find_render_returns_none_when_the_flow_rendered_nothing(self):
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        os.makedirs(os.path.join(run, "final"))

        self.assertIsNone(
            entrypoint.find_render(os.path.join(run, "final", "metrics.json"))
        )

    def test_find_render_ignores_a_metrics_file_outside_a_run(self):
        # Two directories up from an arbitrary path is an arbitrary tree. It
        # once reached out of the test's temp directory and found a PNG from a
        # different run entirely.
        stray = os.path.join(self.test_dir, "elsewhere")
        os.makedirs(stray)
        open(os.path.join(stray, "blinky.png"), "w").close()

        self.assertIsNone(
            entrypoint.find_render(os.path.join(stray, "metrics.json"))
        )

    def test_find_metrics_picks_the_newest_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            for tag, mtime in (("old_run", 1_000_000), ("new_run", 2_000_000)):
                path = os.path.join("build", "runs", tag, "final")
                os.makedirs(path)
                metrics = os.path.join(path, "metrics.json")
                with open(metrics, "w") as f:
                    f.write("{}")
                os.utime(metrics, (mtime, mtime))

            self.assertIn("new_run", entrypoint.find_metrics(None))
            # An explicit path always wins.
            self.assertEqual(entrypoint.find_metrics("named.json"), "named.json")
        finally:
            os.chdir(cwd)

    def test_find_metrics_errors_when_no_run_exists(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with self.assertRaises(SystemExit) as cm:
                entrypoint.find_metrics(None)

            self.assertEqual(cm.exception.code, 1)
        finally:
            os.chdir(cwd)

    # --- cocotb: vvp exits 0 even when every test failed ---

    def _results(self, xml):
        path = os.path.join(self.test_dir, "results.xml")
        with open(path, "w") as f:
            f.write(xml)
        return path

    def test_cocotb_results_pass(self):
        path = self._results(
            '<testsuites><testsuite><testcase name="ok"/></testsuite></testsuites>'
        )
        entrypoint.check_cocotb_results(path)  # must not exit

    def test_cocotb_results_failure_exits_nonzero(self):
        # This is the whole reason the function exists: the simulator reports
        # success regardless, so the results file is the only verdict.
        path = self._results(
            '<testsuites><testsuite>'
            '<testcase name="ok"/>'
            '<testcase name="broken"><failure message="nope"/></testcase>'
            '</testsuite></testsuites>'
        )
        with self.assertRaises(SystemExit) as cm:
            entrypoint.check_cocotb_results(path)
        self.assertEqual(cm.exception.code, 1)

    def test_cocotb_results_error_element_also_fails(self):
        path = self._results(
            '<testsuites><testsuite>'
            '<testcase name="blew_up"><error message="boom"/></testcase>'
            '</testsuite></testsuites>'
        )
        with self.assertRaises(SystemExit) as cm:
            entrypoint.check_cocotb_results(path)
        self.assertEqual(cm.exception.code, 1)

    def test_cocotb_missing_results_is_a_failure(self):
        # A run that died before writing results must not read as success.
        with self.assertRaises(SystemExit) as cm:
            entrypoint.check_cocotb_results(os.path.join(self.test_dir, "absent.xml"))
        self.assertEqual(cm.exception.code, 1)

    def test_cocotb_malformed_results_is_a_failure(self):
        path = self._results("<testsuites><not closed")
        with self.assertRaises(SystemExit) as cm:
            entrypoint.check_cocotb_results(path)
        self.assertEqual(cm.exception.code, 1)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_errors_without_tests(self, mock_ensure, mock_load, mock_run):
        config = {"VERILOG_FILES": ["src/**/*.v"], "DESIGN_NAME": "top"}
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_cocotb(args, config)
            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    @patch('entrypoint.cocotb_config', return_value="/no/such/libpython.so")
    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_errors_when_libpython_is_missing(
        self, mock_ensure, mock_load, mock_run, mock_cfg
    ):
        # Without LIBPYTHON_LOC the simulator prints an opaque GPI error and
        # then exits 0 having run nothing. Say what is wrong instead.
        os.makedirs(os.path.join(self.test_dir, "pytests"))
        with open(os.path.join(self.test_dir, "pytests/test_top.py"), "w") as f:
            f.write("")
        config = {
            "VERILOG_FILES": ["src/**/*.v"],
            "//COCOTB_TESTS": ["dir::pytests/*.py"],
            "DESIGN_NAME": "top",
        }
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_cocotb(args, config)
            self.assertEqual(cm.exception.code, 1)
            # It must stop before handing anything to the simulator.
            self.assertEqual(
                [c for c in mock_run.call_args_list if c[0][0][0] == "vvp"], []
            )
        finally:
            os.chdir(cwd)

    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_hands_the_module_and_toplevel_to_the_simulator(
        self, mock_ensure, mock_load, mock_run, mock_cfg, mock_check
    ):
        os.makedirs(os.path.join(self.test_dir, "pytests"))
        with open(os.path.join(self.test_dir, "pytests/test_top.py"), "w") as f:
            f.write("")
        config = {
            "VERILOG_FILES": ["src/**/*.v"],
            "//COCOTB_TESTS": ["dir::pytests/*.py"],
            "DESIGN_NAME": "top",
        }
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            # A MagicMock attribute is truthy, so leaving this out sends the
            # command down the gate-level path argparse would never pick here.
            args.netlist = None

            entrypoint.cmd_cocotb(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertEqual(compile_cmd[0], "iverilog")
            # Without a Verilog testbench the DUT has to be named as the root.
            self.assertEqual(compile_cmd[compile_cmd.index("-s") + 1], "top")
            self.assertTrue(any("src/top.v" in arg for arg in compile_cmd))
            self.assertNotIn("-DFUNCTIONAL", compile_cmd)

            env = mock_run.call_args_list[1][1]["env"]
            self.assertEqual(env["MODULE"], "test_top")
            self.assertIn("LIBPYTHON_LOC", env)
            self.assertEqual(env["TOPLEVEL"], "top")
            self.assertIn("pytests", env["PYTHONPATH"])
            # The verdict is always read back, never assumed.
            mock_check.assert_called_once()
        finally:
            os.chdir(cwd)

    def _gl_cocotb_config(self):
        """_gl_workspace, plus the Python tests cocotb needs."""
        os.makedirs(os.path.join(self.test_dir, "pytests"), exist_ok=True)
        open(os.path.join(self.test_dir, "pytests/test_top.py"), "w").close()
        config = self._gl_workspace()
        config["//COCOTB_TESTS"] = ["dir::pytests/*.py"]
        return config

    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_drives_the_netlist_when_asked(
        self, mock_ensure, mock_load, mock_run, mock_cfg, mock_check
    ):
        # The same Python tests, run against what synthesis produced. This is
        # the claim gatesim cannot make: its testbench is a separate Verilog
        # file written for the netlist, so nothing is shared with the RTL run.
        config = self._gl_cocotb_config()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            args.netlist = ""  # what argparse stores for a bare --netlist

            entrypoint.cmd_cocotb(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertIn("-DFUNCTIONAL", compile_cmd)
            self.assertIn("-DUNIT_DELAY=#1", compile_cmd)
            self.assertTrue(any("primitives.v" in a for a in compile_cmd))
            self.assertTrue(any("sky130_fd_sc_hd.v" in a for a in compile_cmd))
            self.assertTrue(any("top.nl.v" in a for a in compile_cmd))
            # The RTL is deliberately absent: this simulates the gates.
            self.assertFalse(any("src/" in a for a in compile_cmd))
            # Still the DUT as the root -- there is no Verilog testbench here
            # either, which is the whole point.
            self.assertEqual(compile_cmd[compile_cmd.index("-s") + 1], "top")
        finally:
            os.chdir(cwd)

    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_gate_level_does_not_overwrite_the_rtl_verdict(
        self, mock_ensure, mock_load, mock_run, mock_cfg, mock_check
    ):
        # Running both is the normal thing to do, and a shared results file
        # would leave the second run's verdict standing for both.
        config = self._gl_cocotb_config()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            args.netlist = ""

            entrypoint.cmd_cocotb(args, config)

            self.assertEqual(
                mock_check.call_args[0][0], os.path.join("build", "cocotb-gl-results.xml")
            )
            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertIn("build/cocotb-gl.vvp", compile_cmd)
        finally:
            os.chdir(cwd)

    # --- gatesim: the netlist, not the RTL ---

    def _gl_workspace(self):
        """A workspace with a netlist and the two cell-model files."""
        nl = os.path.join(self.test_dir, "build/runs/r/final/nl")
        models = os.path.join(self.test_dir, "pdks/sky130A/libs.ref/sky130_fd_sc_hd/verilog")
        gate = os.path.join(self.test_dir, "gate")
        for d in (nl, models, gate):
            os.makedirs(d, exist_ok=True)
        for f in ("primitives.v", "sky130_fd_sc_hd.v"):
            open(os.path.join(models, f), "w").close()
        open(os.path.join(nl, "top.nl.v"), "w").close()
        open(os.path.join(gate, "tb_top_gl.v"), "w").close()
        return {
            "PDK": "sky130A",
            "STD_CELL_LIBRARY": "sky130_fd_sc_hd",
            "//GATE_TESTS": ["dir::gate/*.v"],
            "VERILOG_FILES": ["src/**/*.v"],
            "DESIGN_NAME": "top",
        }

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_builds_the_netlist_against_the_cell_models(
        self, mock_ensure, mock_load, mock_run
    ):
        config = self._gl_workspace()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.netlist = None

            entrypoint.cmd_gatesim(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertEqual(compile_cmd[0], "iverilog")
            # Both defines are required: verified against sky130_fd_sc_hd, where
            # neither alone compiles without warnings.
            self.assertIn("-DFUNCTIONAL", compile_cmd)
            self.assertIn("-DUNIT_DELAY=#1", compile_cmd)
            self.assertTrue(any("primitives.v" in a for a in compile_cmd))
            self.assertTrue(any("sky130_fd_sc_hd.v" in a for a in compile_cmd))
            self.assertTrue(any("top.nl.v" in a for a in compile_cmd))
            self.assertTrue(any("tb_top_gl.v" in a for a in compile_cmd))
            # The RTL is deliberately absent: this simulates the gates.
            self.assertFalse(any("src/" in a for a in compile_cmd))
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_errors_without_a_gate_testbench(self, mock_ensure, mock_load, mock_run):
        config = self._gl_workspace()
        del config["//GATE_TESTS"]
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.netlist = None
            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_gatesim(args, config)
            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_errors_when_the_cell_models_are_absent(
        self, mock_ensure, mock_load, mock_run
    ):
        config = self._gl_workspace()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.remove("pdks/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v")
            args = MagicMock()
            args.netlist = None
            with self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_gatesim(args, config)
            self.assertEqual(cm.exception.code, 1)
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    def test_cell_models_come_from_pdk_and_library(self):
        # Derived rather than configured, so there is no third key to disagree.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._gl_workspace()
            models = entrypoint.cell_models(
                {"PDK": "sky130A", "STD_CELL_LIBRARY": "sky130_fd_sc_hd"}
            )
            self.assertTrue(models[0].endswith("sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v"))
            self.assertTrue(models[1].endswith("sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v"))
        finally:
            os.chdir(cwd)

    def test_find_netlist_prefers_an_explicit_path_and_errors_when_absent(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self.assertEqual(entrypoint.find_netlist("named.v"), "named.v")
            with self.assertRaises(SystemExit) as cm:
                entrypoint.find_netlist(None)
            self.assertEqual(cm.exception.code, 1)
        finally:
            os.chdir(cwd)

    def test_root_args_is_shared_by_sim_and_gatesim(self):
        # Both commands hit the same silent-truncation trap, so both use the
        # same rule rather than one of them growing its own copy.
        self.assertEqual(entrypoint.root_args({}, ["only.v"], "SIM_TOP"), [])
        self.assertEqual(
            entrypoint.root_args({"//GATE_TOP": "tb"}, ["a.v", "b.v"], "GATE_TOP"),
            ["-s", "tb"],
        )
        with self.assertRaises(SystemExit) as cm:
            entrypoint.root_args({}, ["a.v", "b.v"], "GATE_TOP")
        self.assertEqual(cm.exception.code, 1)

if __name__ == '__main__':
    unittest.main()
