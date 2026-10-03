import sys
import os
import io
import json
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
            self.assertIn("read_verilog -sv src/sub/sub.v", yosys_cmd)
            self.assertIn("read_verilog -sv src/top.v", yosys_cmd)

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

    def test_schematic_draws_one_module_and_says_which(self):
        # `show` draws everything selected, and for svg yosys refuses more than
        # one module: "For formats different than 'ps' or 'dot' only one module
        # must be selected." Any design with a submodule hits that, which is
        # every real one -- so the selection is not optional, and it is A:top
        # rather than the design's name so that -auto-top is covered too.
        for config in (self.config,
                       {k: v for k, v in self.config.items() if k != "DESIGN_NAME"}):
            script = self._schematic_script(config)
            self.assertRegex(script, r"show\b[^;]*\bA:top\b")

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

    def test_check_says_it_built_no_layout(self):
        # `gds` is an alias of check and exits 0. Without this line a passing
        # run reads as a finished layout when nothing was built.
        self.assertIn("builds no layout", self._check(self._gds_config()))

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

    def test_report_breaks_the_cells_down_by_class_without_fill(self):
        # The real 3.0.14 run: its class counts add up to its 198 cells.
        out = self._report(os.path.join(self.RUN_FIXTURE, "blinky_run", "final", "metrics.json"))

        self.assertIn("57 logic, 46 well taps, 35 timing-repair buffers, 27 inverters, "
                      "26 sequential, 7 clock buffers", out)
        self.assertNotIn("235", out)  # fill

    def test_report_names_an_unmapped_cell_class_by_its_own_name(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with open("classes.json", "w") as f:
                json.dump({"design__instance__count__class:antenna_cell": 3,
                           "design__instance__count__class:clock_inverter": 0}, f)

            out = self._report("classes.json")

            self.assertIn("3 antenna cell", out)
            self.assertNotIn("clock inverter", out)  # none of them
        finally:
            os.chdir(cwd)

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

    def test_sta_step_takes_the_resumed_step_not_the_one_that_sorts_last(self):
        # Directory names from a real LibreLane 3.0.14 run resumed from
        # floorplan: the first pass left 55-, the resume added 119-. As
        # strings "55-" sorts after "119-".
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        old = os.path.join(run, "55-openroad-stapostpnr")
        new = os.path.join(run, "119-openroad-stapostpnr")
        for d in (old, new, os.path.join(run, "final")):
            os.makedirs(d)

        found = entrypoint.sta_step(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, new)

    def test_newest_step_reads_the_ordinal_as_a_number(self):
        # Two-digit against three-digit is where a string sort goes wrong, and
        # the file under the step is what the callers ask for.
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        for step in ("82-yosys-synthesis", "158-yosys-synthesis"):
            os.makedirs(os.path.join(run, step, "reports"))
            open(os.path.join(run, step, "reports", "stat.json"), "w").close()

        found = entrypoint.newest_step(run, "*-yosys-synthesis/reports/stat.json")

        self.assertEqual(
            found, os.path.join(run, "158-yosys-synthesis", "reports", "stat.json"))
        self.assertIsNone(entrypoint.newest_step(run, "*-openroad-cts"))

    def test_find_render_falls_back_to_the_newest_step_directory(self):
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        os.makedirs(os.path.join(run, "final"))
        for step in ("59-klayout-render", "79-klayout-render"):
            os.makedirs(os.path.join(run, step))
            open(os.path.join(run, step, "blinky.png"), "w").close()

        found = entrypoint.find_render(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, os.path.join(run, "79-klayout-render", "blinky.png"))

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

    @patch('entrypoint.log_warn')
    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.load_config')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_warns_when_no_rtl_declares_a_timescale(
        self, mock_ensure, mock_load, mock_run, mock_cfg, mock_check, mock_warn
    ):
        # Icarus then runs at 1 s, and cocotb's Clock in ns fails with an
        # error that names neither the cause nor the file. `make sim` passes.
        os.makedirs(os.path.join(self.test_dir, "pytests"))
        open(os.path.join(self.test_dir, "pytests/test_top.py"), "w").close()
        config = {"VERILOG_FILES": ["src/**/*.v"], "//COCOTB_TESTS": ["dir::pytests/*.py"],
                  "DESIGN_NAME": "top"}
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            args.netlist = None

            entrypoint.cmd_cocotb(args, config)
            self.assertIn("`timescale 1ns/1ps", mock_warn.call_args[0][0])

            mock_warn.reset_mock()
            with open("src/top.v", "w") as f:
                f.write("`timescale 1ns/1ps\nmodule top; endmodule")
            entrypoint.cmd_cocotb(args, config)
            mock_warn.assert_not_called()
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

    @patch('entrypoint.run_command')
    def test_pdk_installs_where_the_readers_look(self, mock_run):
        # The install path used to be a fixed ./pdks while every reader honoured
        # PDK_ROOT, so PDK_ROOT could only ever name a PDK this command had not
        # installed. One shared read-only copy for many checkouts depends on the
        # two agreeing.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shared = os.path.join(self.test_dir, "shared-pdks")
            with patch.dict(os.environ, {"PDK_ROOT": shared}):
                entrypoint.cmd_pdk(MagicMock(), {})
            self.assertTrue(os.path.isdir(shared))
            self.assertIn("--pdk-root", mock_run.call_args[0][0])
            self.assertEqual(
                mock_run.call_args[0][0][mock_run.call_args[0][0].index("--pdk-root") + 1],
                shared,
            )

            # Unset, it still defaults to ./pdks -- every existing checkout.
            mock_run.reset_mock()
            env = {k: v for k, v in os.environ.items() if k != "PDK_ROOT"}
            with patch.dict(os.environ, env, clear=True):
                entrypoint.cmd_pdk(MagicMock(), {})
            self.assertEqual(
                mock_run.call_args[0][0][mock_run.call_args[0][0].index("--pdk-root") + 1],
                os.path.join(self.test_dir, "pdks"),
            )
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    def test_every_command_reads_the_same_language(self, mock_run):
        # One .sv file used to pass two commands and fail two: sim called
        # iverilog with no -g2012 and synth read with no -sv, while cocotb,
        # gatesim and LibreLane all accept SystemVerilog. A student's file
        # is not more or less valid depending on which make target reads it.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            config = {"DESIGN_NAME": "top", "VERILOG_FILES": ["dir::src/top.v"],
                      "//TEST_FILES": ["dir::test/top_tb.v"]}

            entrypoint.cmd_sim(MagicMock(files=None, test_files=None), config)
            argv = mock_run.call_args_list[0][0][0]
            self.assertEqual(argv[0], "iverilog")
            self.assertIn("-g2012", argv)

            for cmd in (entrypoint.cmd_synth, entrypoint.cmd_schematic):
                mock_run.reset_mock()
                cmd(MagicMock(files=None), config)
                script = mock_run.call_args[0][0][-1]
                self.assertIn("read_verilog", script)
                for piece in script.split(";"):
                    if "read_verilog" in piece:
                        self.assertIn("-sv", piece, f"{cmd.__name__}: {piece.strip()}")
        finally:
            os.chdir(cwd)

    # --- site: the page GitHub Pages publishes ---

    # Shaped like a real cocotb 1.9 results file: the seed as a property,
    # wall-clock `time` next to `sim_time_ns`, a failure as a child element.
    COCOTB_XML = """<testsuites name="results"><testsuite name="all" package="all">
<property name="random_seed" value="1790610538" />
<testcase name="counts_up_by_one" classname="t" time="0.0007" sim_time_ns="81.001" />
<testcase name="led_is_the_counter_top_bit" classname="t" time="0.0005" sim_time_ns="41.001">
<failure message="AssertionError" /></testcase>
</testsuite></testsuites>"""

    def _site(self, config=None):
        """Runs cmd_site in test_dir and returns the page it wrote."""
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_site(MagicMock(), config or {"DESIGN_NAME": "blinky"})
        with open(os.path.join("build", "site", "index.html")) as f:
            return f.read()

    def _run_with_render(self):
        final = os.path.join("runs", "blinky_run", "final")
        os.makedirs(os.path.join(final, "render"))
        shutil.copy(self.FIXTURE, final)
        open(os.path.join(final, "render", "blinky.png"), "w").close()

    def test_site_puts_the_report_the_layout_and_the_tests_on_one_page(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._run_with_render()
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            with open("build/schematic.svg", "w") as f:
                f.write("<svg/>")

            page = self._site()

            # The same numbers `report` prints for this fixture.
            self.assertIn("+4.69 ns", page)
            self.assertIn("29.2%", page)
            # The layout is shown, not named: its path means nothing on a website.
            self.assertIn('src="layout.png"', page)
            self.assertNotIn("runs/blinky_run", page)
            self.assertTrue(os.path.exists("build/site/layout.png"))
            self.assertTrue(os.path.exists("build/site/schematic.svg"))
            # A failure is reported as one, with the seed that reruns it.
            self.assertIn("1/2 passed", page)
            self.assertIn('class="FAIL">FAIL', page)
            self.assertIn("1790610538", page)
            self.assertIn("81.001", page)
        finally:
            os.chdir(cwd)

    def test_site_leaves_out_what_was_never_run(self):
        # After `make cocotb` alone there is no layout and no signoff yet, and
        # the page should say what it has rather than refuse.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)

            page = self._site()

            self.assertIn("cocotb, RTL", page)
            self.assertNotIn("Signoff", page)
            self.assertNotIn("layout.png", page)
            self.assertNotIn("gate level", page)
        finally:
            os.chdir(cwd)

    def test_site_errors_when_there_is_nothing_to_show(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with self.assertRaises(SystemExit) as cm:
                self._site()
            self.assertEqual(cm.exception.code, 1)
        finally:
            os.chdir(cwd)

    def test_site_does_not_publish_a_previous_runs_layout(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build/site")
            open("build/site/layout.png", "w").close()
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)

            self._site()

            self.assertFalse(os.path.exists("build/site/layout.png"))
        finally:
            os.chdir(cwd)

    def test_site_escapes_what_it_did_not_write(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML.replace("counts_up_by_one", "a&lt;b&gt;"))

            page = self._site({"DESIGN_NAME": "<script>x</script>"})

            self.assertNotIn("<script>", page)
            self.assertIn("a&lt;b&gt;", page)
        finally:
            os.chdir(cwd)

    @patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://github.com",
                             "GITHUB_REPOSITORY": "o/r", "GITHUB_SHA": "9b2e3e3abcdef",
                             "GITHUB_RUN_ID": "42"})
    def test_site_links_the_commit_it_shows_when_built_on_actions(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)

            page = self._site()

            self.assertIn("https://github.com/o/r/commit/9b2e3e3abcdef", page)
            self.assertIn(">9b2e3e3<", page)
            self.assertIn("https://github.com/o/r/actions/runs/42", page)
        finally:
            os.chdir(cwd)

    # --- site: what the run's own reports say, beyond `report` ---

    # A real ChipForAll blinky run under LibreLane 3.0.14, trimmed: the metrics
    # the page reads, synthesis's stat.json, the STA step's DEFAULT_CORNER, the
    # default corner's power.rpt, and the worst corner's max.rpt cut after its
    # first path.
    RUN_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "run")

    def _run_site(self, edit_metrics=None):
        shutil.copytree(self.RUN_FIXTURE, "runs")
        if edit_metrics:
            path = "runs/blinky_run/final/metrics.json"
            with open(path) as f:
                metrics = json.load(f)
            edit_metrics(metrics)
            with open(path, "w") as f:
                json.dump(metrics, f)
        return self._site()

    def test_site_shows_signoff_timing_area_and_power_from_a_real_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()

            for check in ("Magic DRC", "KLayout DRC", "LVS", "antenna", "XOR"):
                self.assertIn(f"<td>{check}</td>", page)
            self.assertEqual(page.count('class="PASS">PASS'), 5)
            # The worst corner by the metrics, and its path as OpenSTA wrote it.
            self.assertIn("<code>max_ss_100C_1v60</code>", page)
            self.assertIn("Startpoint: _182_", page)
            self.assertIn("4.697966   slack (MET)", page)
            # What the report says, in a sentence: the clock is the edge at
            # 10.0; count[1] is the net _182_ drives; _172_'s D net is
            # auto-named, so the instance stays.
            # Arrival counts from the clock edge, so the clock tree's 0.61 ns
            # to _182_/CLK is not logic; setup 0.148 + uncertainty 0.25 are
            # what the capture side holds back.
            self.assertIn("From <code>count[1]</code> (flip-flop) to <code>_172_</code> (flip-flop). "
                          "Clock 10.0 ns (100 MHz): the clock reaches the start point at 0.61 ns, "
                          "logic and wires take 4.88 ns, and the data arrives 4.70 ns before its "
                          "10.19 ns deadline.", page)
            self.assertIn('<span class="launch" style="width:5.75%"></span>'
                          '<span class="used" style="width:46.11%"></span>'
                          '<span class="spare" style="width:44.37%"></span>'
                          '<span class="reserved" style="width:3.76%"></span>', page)
            self.assertIn("setup time and clock uncertainty 0.40 ns", page)
            self.assertIn("(maximum wire RC, slow transistors, 100 &deg;C, 1.60 V)", page)
            # Utilization is of the core, not the die beside it.
            self.assertIn('<div class="label">core utilization</div><div class="value">57.1%</div>'
                          '<div class="detail">of a 58.4 \u00d7 57.1 \u00b5m core</div>', page)
            self.assertIn("46 of them well taps", page)
            self.assertIn("35 timing-repair buffers, 26 of them for hold", page)
            self.assertIn("timing repair also resizes cells", page)
            self.assertIn("<details><summary>Full OpenSTA report</summary>", page)
            # stat.json: 1366.3104 total, 683.1552 of it sequential -- this
            # design splits exactly in half. Routing's 1906.8 contains both, so
            # the third part is the difference, not a third peer.
            self.assertIn("flip-flops 683.2 &micro;m&sup2;", page)
            self.assertIn("logic 683.2 &micro;m&sup2;", page)
            self.assertIn("added by place and route 540.5 &micro;m&sup2;", page)
            self.assertIn("grew it 40% to 1,906.8 &micro;m&sup2;", page)
            # Cells by origin: 57 logic + 26 sequential + 27 inverters from
            # synthesis; 46 taps + 35 timing-repair + 7 clock buffers added.
            self.assertIn("<h3>Cells: 198</h3>", page)
            self.assertIn("from synthesis 110 ", page)
            self.assertIn("added by the flow 88 ", page)
            self.assertNotIn("cell classes", page)
            # The share bar has a column of its own, never under a number. It
            # is the share of the whole, on a track that is the whole -- scaled
            # to the largest group, 54.4% drew as a full bar. The Total row is
            # the sum, so it gets no bar.
            self.assertIn('<td class="num">54.4%</td><td class="bar"><span class="track">'
                          '<span style="width:54%"></span></span></td>', page)
            self.assertRegex(page, r'<tr class="total"><td>Total</td>.*?<td class="bar"></td></tr>')
            # A bare lint count reads as a flaw; it says what it counts.
            self.assertIn("Verilator on the RTL, inside the flow", page)
            # power.rpt of DEFAULT_CORNER, not the bare power__total metric,
            # which in this run is max_ff's 0.290 mW.
            self.assertIn("<code>nom_tt_025C_1v80</code>", page)
            self.assertIn(">247.9<", page)
            self.assertIn(">54.4%<", page)
            self.assertNotIn("<div class=\"label\">power</div>", page)
            self.assertNotIn("<div class=\"label\">signoff</div>", page)
        finally:
            os.chdir(cwd)

    def _run_with_gds(self):
        os.makedirs("runs/blinky_run/final/gds")
        with open("runs/blinky_run/final/gds/blinky.gds", "wb") as f:
            f.write(b"\x00\x06\x00\x02\x02\x58")  # a GDS HEADER record

    def test_site_publishes_the_gds_with_a_3d_viewer_link(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            self._run_with_gds()

            page = self._site({"DESIGN_NAME": "blinky", "PDK": "sky130A"})

            self.assertTrue(os.path.exists("build/site/blinky.gds"))
            self.assertIn('<a class="btn" href="blinky.gds" download>GDS &middot; 6 B</a>', page)
            # Hidden until the script finds the page has a URL to hand over.
            self.assertIn('data-viewer="sky130A" data-gds="blinky.gds" hidden', page)
            self.assertIn("gds-viewer.tinytapeout.com", page)
            # No note about where the 3D view works: on Pages the button is there.
            self.assertNotIn("opens from the published page", page)
        finally:
            os.chdir(cwd)

    def test_site_offers_the_gds_without_a_viewer_for_a_pdk_it_cannot_draw(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            self._run_with_gds()

            page = self._site({"DESIGN_NAME": "blinky", "PDK": "some130"})

            self.assertIn('<a class="btn" href="blinky.gds" download>GDS &middot; 6 B</a>', page)
            self.assertNotIn("data-viewer", page)
            self.assertNotIn("gds-viewer.tinytapeout.com", page)
        finally:
            os.chdir(cwd)

    def test_site_without_a_gds_has_no_gds_link(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()

            self.assertNotIn(".gds", page)
        finally:
            os.chdir(cwd)

    def test_site_shows_the_worst_corners_path_or_none(self):
        # Make a corner with no max.rpt in the fixture the worst. Showing the
        # max_ss path anyway would present a path that is not the worst one.
        def worsen(metrics):
            metrics["timing__setup__ws__corner:nom_tt_025C_1v80"] = -1.0
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(worsen)
            self.assertNotIn("Worst setup path", page)
        finally:
            os.chdir(cwd)

    def test_site_says_when_it_was_built(self):
        # A published page stays up until the next one replaces it, and a red
        # main does not replace it, so the date is how a reader tells its age.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                page = self._run_site()
            self.assertIn("Built 1970-01-01 00:00 UTC", page)
        finally:
            os.chdir(cwd)

    def test_site_misses_timing_on_a_negative_hold_slack(self):
        # Setup met and hold violated is a chip that fails at any clock: the
        # chip has to read both, not setup alone.
        def hold_violated(metrics):
            metrics["timing__hold__ws"] = -0.05
            metrics["timing__hold_vio__count"] = 2
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(hold_violated)
            self.assertIn('<span class="chip FAIL">Timing missed</span>', page)
        finally:
            os.chdir(cwd)

    def test_site_writes_units_and_cell_classes_as_words(self):
        def clock_inverters(metrics):
            metrics["design__instance__count__class:clock_inverter"] = 5
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(clock_inverters)
            self.assertIn("5 clock inverters", page)
            # report's terminal spelling, um^2, does not reach the page.
            self.assertNotIn("um^2", page)
            self.assertIn("&micro;m&sup2;", page)
            self.assertIn('<th class="num">errors</th>', page)
        finally:
            os.chdir(cwd)

    def test_site_formats_the_summary_for_reading(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            # report's "69.5 x 80.2 um" and "5573.04 um^2", as a reader writes them.
            self.assertIn('<div class="value">69.5 \u00d7 80.2 \u00b5m</div>', page)
            self.assertIn('<div class="detail">5,573.0 \u00b5m\u00b2</div>', page)
            # Positive slack is the good news; it says so in colour.
            self.assertIn('<div class="kpi good"><div class="label">setup slack</div>', page)
            # A tick beside PASS, written so Python's string escapes cannot eat it.
            self.assertIn('td.PASS::before { content: "\u2713"', page)
            # Macro and Pad are zero in a design with neither: rows of 0.0 are noise.
            self.assertNotIn("<td>Macro</td>", page)
            self.assertNotIn("<td>Pad</td>", page)
        finally:
            os.chdir(cwd)

    def test_site_does_not_colour_a_negative_slack_good(self):
        def violated(metrics):
            metrics["timing__setup__ws"] = -0.5
            metrics["design__instance__count__stdcell"] = 12345
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(violated)
            self.assertIn('<div class="kpi"><div class="label">setup slack</div>', page)
            self.assertIn('<div class="value">12,345</div>', page)
        finally:
            os.chdir(cwd)

    def test_site_takes_the_clock_from_the_config(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            page = self._site({"DESIGN_NAME": "blinky", "CLOCK_PERIOD": 10.0})
            self.assertIn('<div class="label">clock</div><div class="value">10.0 ns</div>', page)
        finally:
            os.chdir(cwd)

    def test_site_puts_the_layout_beside_the_title_and_names_the_author(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            self._run_with_gds()
            os.makedirs("runs/blinky_run/final/render")
            open("runs/blinky_run/final/render/blinky.png", "w").close()
            env = {"GITHUB_REPOSITORY": "someone/blinky", "GITHUB_SERVER_URL": "https://github.com"}
            with patch.dict(os.environ, env):
                page = self._site({"DESIGN_NAME": "blinky", "PDK": "sky130A"})

            header = page[page.index("<header"):page.index("</header>")]
            self.assertIn('<header class="has-art">', page)
            self.assertIn('<figure class="hero-art" id="layout">', header)
            self.assertIn("69.5 \u00d7 80.2 \u00b5m &middot; 152 cells + 46 taps &middot; sky130A", header)
            self.assertIn('<p class="byline">by <a href="https://github.com/someone">someone</a></p>', header)
            # The layout is the hero now, not a section of its own further down.
            self.assertNotIn('<section id="layout"', page)
            # Most wanted first: the 3D view, then the source, then the file.
            order = [header.index(s) for s in ("data-viewer=", "View source", "blinky.gds\" download")]
            self.assertEqual(order, sorted(order))
        finally:
            os.chdir(cwd)

    def test_site_says_what_make_gds_adds_until_it_has_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            page = self._site()
            self.assertIn("once <code>make gds</code> has run", page)

            shutil.rmtree("build/site")
            page = self._run_site()
            self.assertNotIn("once <code>make gds</code> has run", page)
        finally:
            os.chdir(cwd)

    def test_site_keeps_the_primary_button_readable_in_both_themes(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            # White on dark mode's #4493f8 is 3.1:1, under AA's 4.5:1.
            self.assertIn("--primary: #1f6feb;", page)
            self.assertIn("color-scheme: light dark;", page)
        finally:
            os.chdir(cwd)

    def test_site_colours_each_runs_chip_by_its_own_verdict(self):
        # Gates failing where the RTL passed is the finding; one shared red
        # chip would hide which side broke.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML.replace(
                    '<failure message="AssertionError" />', ""))
            with open("build/cocotb-gl-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            page = self._site()
            self.assertIn('<span class="chip PASS">2/2 on RTL</span>'
                          '<span class="chip FAIL">1/2 on gates</span>', page)
        finally:
            os.chdir(cwd)

    def test_site_puts_rtl_and_gate_runs_in_one_table(self):
        # The same tests on the RTL and on the gates: side by side that reads
        # as "still passes after synthesis", not as one table printed twice.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            for name in ("build/cocotb-results.xml", "build/cocotb-gl-results.xml"):
                with open(name, "w") as f:
                    f.write(self.COCOTB_XML)
            page = self._site()
            self.assertIn("<h2>Tests: 1/2 on RTL, 1/2 on gates</h2>", page)
            # A chip per run, each with its own verdict.
            self.assertIn('<span class="chip FAIL">1/2 on RTL</span>'
                          '<span class="chip FAIL">1/2 on gates</span>', page)
            self.assertEqual(page.count("<th>test</th>"), 1)
            self.assertIn("<th>RTL</th><th>gates</th></tr>", page)
            # No sim-time column: it could only ever have been one run's.
            self.assertNotIn("sim time", page)
        finally:
            os.chdir(cwd)

    def test_site_reads_as_a_portfolio(self):
        # Layout first, the design described, buttons for what a visitor does
        # with a chip, a link preview, and the schematic folded away.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            self._run_with_gds()
            os.makedirs("runs/blinky_run/final/render")
            open("runs/blinky_run/final/render/blinky.png", "w").close()
            os.makedirs("build")
            with open("build/schematic.svg", "w") as f:
                f.write("<svg/>")
            env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "Some/repo",
                   "GITHUB_SHA": "9b2e3e3abcdef"}
            with patch.dict(os.environ, env):
                page = self._site({"DESIGN_NAME": "blinky", "PDK": "sky130A",
                                   "//DESCRIPTION": "A clock divider that blinks an LED."})
            self.assertLess(page.index('id="layout"'), page.index('id="summary"'))
            self.assertLess(page.index('id="summary"'), page.index('id="signoff"'))
            self.assertIn('<p class="lede">A clock divider that blinks an LED.</p>', page)
            self.assertIn('content="A clock divider that blinks an LED."', page)
            self.assertIn('<meta property="og:image" content="https://some.github.io/repo/layout.png">', page)
            self.assertIn('<a class="btn" href="https://github.com/Some/repo">View source</a>', page)
            # No block diagram here, so the schematic keeps a section, folded.
            self.assertIn("<h2>Schematic</h2>", page)
            self.assertIn("<details><summary>Show the schematic</summary>", page)
        finally:
            os.chdir(cwd)

    def test_site_has_no_link_preview_image_off_actions(self):
        # og:image must be absolute, and the Pages URL is only known on Actions.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._run_with_render()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GITHUB_REPOSITORY", None)
                page = self._site()
            self.assertIn('property="og:title"', page)
            self.assertNotIn("og:image", page)
            self.assertNotIn("View source", page)
        finally:
            os.chdir(cwd)

    def test_site_marks_a_failed_signoff_check(self):
        def dirty(metrics):
            metrics["design__lvs_error__count"] = 3
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(dirty)
            self.assertIn('<td>LVS</td><td class="num">3</td><td class="FAIL">FAIL</td>', page)
        finally:
            os.chdir(cwd)

    def test_site_keeps_the_power_row_when_there_is_no_power_table(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            os.remove("runs/blinky_run/55-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt")
            page = self._site()
            self.assertNotIn("<h2>Power</h2>", page)
            self.assertIn("<div class=\"label\">power</div>", page)
        finally:
            os.chdir(cwd)

    UART_PATH = """Startpoint: _2086_ (rising edge-triggered flip-flop clocked by CLK)
Endpoint: PRDATA[4] (output port clocked by CLK)
                                  0.000000    0.000000   clock CLK (rise edge)
                      0.1   0.2   0.6 ^ _2086_/CLK (sky130_fd_sc_hd__dfrtp_1)
     3    0.01   0.2   0.5   1.1 ^ _2086_/Q (sky130_fd_sc_hd__dfrtp_1)
                                                         uart_rx_fifo_i.pointer_out[0] (net)
                                              9.275290   data arrival time
                                 11.000000   11.000000   clock CLK (rise edge)
                                 -0.250000   10.750000   clock uncertainty
                                 -0.550000   10.200000   output external delay
                                             10.200000   data required time
                                              {slack}   slack ({verdict})
"""

    def test_timing_story_names_the_path_and_the_clock(self):
        s = entrypoint.site_page.timing_story(self.UART_PATH.format(slack="0.924710", verdict="MET"))
        self.assertEqual(s["start"], "uart_rx_fifo_i.pointer_out[0]")
        self.assertEqual((s["end"], s["end_kind"]), ("PRDATA[4]", "output"))
        self.assertEqual(s["period"], 11.0)
        self.assertEqual((s["arrival"], s["required"]), (9.27529, 10.2))

    def test_timing_story_gives_up_rather_than_guess(self):
        # No required time: the page shows the report as printed instead.
        path = self.UART_PATH.replace("data required time", "something else")
        self.assertIsNone(entrypoint.site_page.timing_story(path.format(slack="0.9", verdict="MET")))

    def test_timing_story_leaves_a_half_cycle_path_to_the_report(self):
        # Launched on a falling edge at 5.5: the 5.5 ns to the capture edge is
        # not the clock period, and the page must not call it one.
        path = self.UART_PATH.replace("0.000000    0.000000   clock CLK (rise edge)",
                                      "5.500000    5.500000   clock CLK (fall edge)")
        self.assertIsNone(entrypoint.site_page.timing_story(path.format(slack="0.9", verdict="MET")))

    def test_site_draws_a_violated_path_late_not_spare(self):
        path = self.UART_PATH.replace("9.275290", "10.500000").format(slack="-0.300000",
                                                                      verdict="VIOLATED")
        page = entrypoint.site_page.render("uart", [], None, [], None, {},
                                           timing=("max_ss_100C_1v60", path))
        self.assertIn("0.30 ns after its 10.20 ns deadline", page)
        self.assertIn('<span class="late"', page)
        # The bar has a key: which colour is the overrun.
        self.assertIn("late by 0.30 ns", page)
        self.assertNotIn('<span class="spare"', page)

    UART_PHYSICAL = {"clock": 11.0, "core": (225.4, 223.04), "taps": 714, "hold_buffers": 315,
                     "r2r_setup": 2.109539, "r2r_hold": 0.108761, "skew": 0.2862,
                     "drv": {"slew": 297, "cap": 0, "fanout": 7}, "ir_worst": 0.000524}

    def test_site_reads_the_uart_path_as_a_physical_designer_would(self):
        # The real apb_uart_sv run: the clock reaches _2086_/CLK at 1.30 ns,
        # so of the 9.28 ns arrival only 7.97 is logic; it ends at a port.
        path = self.UART_PATH.replace(
            "0.1   0.2   0.6 ^ _2086_/CLK", "0.1   0.2   1.300449 ^ _2086_/CLK"
        ).format(slack="0.924710", verdict="MET")
        page = entrypoint.site_page.render(
            "uart", [("die", "236.605 x 247.325 um  (58518.3 um^2)"),
                     ("setup slack", "+0.92 ns  (0 violations)")], None, [], None, {},
            timing=("max_ss_100C_1v60", path), physical=self.UART_PHYSICAL)
        self.assertIn("the clock reaches the start point at 1.30 ns, logic and wires take "
                      "7.97 ns, and the data arrives 0.92 ns before its 10.20 ns deadline", page)
        self.assertIn("output delay and clock uncertainty 0.80 ns", page)
        # The worst path is an I/O path; between flops there is more room.
        self.assertIn("This is an I/O path, so the output delay the constraints assume", page)
        self.assertIn("between flip-flops the worst setup slack is +2.11 ns", page)
        self.assertIn("0 violations; reg-to-reg +2.11 ns", page)
        self.assertIn('<div class="label">clock</div><div class="value">11.0 ns</div>'
                      '<div class="detail">91 MHz</div>', page)
        self.assertIn("Worst clock skew on a setup path: 0.29 ns.", page)

    def test_site_names_the_input_delay_on_a_path_from_a_port(self):
        path = self.UART_PATH.replace(
            "Startpoint: _2086_ (rising edge-triggered flip-flop clocked by CLK)",
            "Startpoint: PADDR[2] (input port clocked by CLK)").replace(
            "0.1   0.2   0.6 ^ _2086_/CLK (sky130_fd_sc_hd__dfrtp_1)",
            "0.000000    0.550000 ^ PADDR[2] (in)").format(slack="0.9", verdict="MET")
        s = entrypoint.site_page.timing_story(path)
        self.assertEqual((s["start_kind"], s["leaves"]), ("input", 0.55))
        page = entrypoint.site_page.render("uart", [], None, [], None, {},
                                           timing=("max_ss_100C_1v60", path))
        self.assertIn("the input delay puts the data at the input at 0.55 ns", page)

    def test_site_shows_the_electrical_rules_beside_signoff(self):
        page = entrypoint.site_page.render("uart", [], None, [], None, {},
                                           signoff=[("LVS", 0)], physical=self.UART_PHYSICAL)
        self.assertIn('<tr><td>max transition (slew)</td><td class="num">297</td></tr>', page)
        self.assertIn('<tr><td>max fanout</td><td class="num">7</td></tr>', page)
        self.assertIn("Static IR drop, worst: 0.52 mV.", page)
        self.assertIn("Not analysed by this flow: electromigration", page)
        # The flow does not stop on these, and neither does the chip.
        self.assertIn('<span class="chip PASS">Signoff clean</span>', page)

    def test_site_links_the_schematic_under_the_blocks_instead_of_a_section(self):
        page = entrypoint.site_page.render("uart", [], None, [], "schematic.svg", {},
                                           blocks="blocks/top.svg")
        self.assertIn('<a href="schematic.svg">open the schematic</a>', page)
        self.assertNotIn('<section id="schematic"', page)

    def test_first_path_stops_at_the_first_slack(self):
        text = ("Startpoint: a\nEndpoint: b\n  1.0   slack (VIOLATED)\n"
                "Startpoint: c\n  2.0   slack (MET)\n")
        path = entrypoint.site_page.first_path(text)
        self.assertTrue(path.startswith("Startpoint: a"))
        self.assertTrue(path.endswith("slack (VIOLATED)"))
        self.assertNotIn("Startpoint: c", path)

    # --- report: power names its corner ---

    def test_report_power_is_the_default_corners_and_says_so(self):
        # The bare power__total in this real run is max_ff's 0.290 mW; the
        # default corner, nom_tt, is 0.248.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            out = self._report("runs/blinky_run/final/metrics.json")
            self.assertIn("0.248 mW  (nom_tt_025C_1v80)", out)
            self.assertNotIn("0.290", out)
        finally:
            os.chdir(cwd)

    def test_report_power_without_a_run_directory_says_the_corner_is_unknown(self):
        self.assertIn("0.292 mW  (corner not named)", self._report(self.FIXTURE))

    # --- the block diagram ---

    FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

    def _netlist(self, name):
        with open(os.path.join(self.FIXTURES, name)) as f:
            return json.load(f)

    def test_block_diagram_draws_submodules_by_their_source_names(self):
        # yosys 0.33's JSON of the UART's top, trimmed to that module. Three
        # of its five instances are parameterised and typed $paramod$<hash>\...
        dot = entrypoint.diagrams.block_diagram_dot(self._netlist("apb_uart_top.json"), "apb_uart_sv")
        for name, module in (("uart_rx_i", "uart_rx"), ("uart_tx_i", "uart_tx"),
                             ("uart_rx_fifo_i", "io_generic_fifo"),
                             ("uart_tx_fifo_i", "io_generic_fifo"),
                             ("uart_interrupt_i", "uart_interrupt")):
            self.assertIn(f'"block:{name}" [label="{name}\n{module}"', dot)
        self.assertNotIn("$paramod", dot)
        # A direct block-to-block net, and one through the top's own logic.
        self.assertIn('"block:uart_tx_fifo_i" -> "block:uart_tx_i" [label="tx_data, tx_valid"]', dot)
        self.assertIn('"logic" -> "port:PRDATA"', dot)
        # Clock and reset reach all five: a caption, not ten edges.
        self.assertIn('label="CLK, RSTN reach every block"', dot)
        self.assertNotIn('"port:CLK" ->', dot)
        self.assertIn('"port:rx_i" -> "block:uart_rx_i"', dot)

    def test_block_diagram_is_none_for_a_top_without_submodules(self):
        netlist = self._netlist("counter_wrap.json")
        self.assertIsNone(entrypoint.diagrams.block_diagram_dot(netlist, "counter"))
        self.assertIsNotNone(entrypoint.diagrams.block_diagram_dot(netlist, "counter_wrap"))

    @patch('entrypoint.run_command')
    def test_draw_blocks_does_nothing_for_a_top_without_submodules(self, mock_run):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            netlist = self._netlist("counter_wrap.json")
            netlist["modules"]["counter"]["attributes"]["top"] = "1"
            del netlist["modules"]["counter_wrap"]["attributes"]["top"]
            with open("build/n.json", "w") as f:
                json.dump(netlist, f)
            with contextlib.redirect_stdout(io.StringIO()):
                entrypoint.draw_blocks("build/n.json", ["read_verilog x.v"])
            mock_run.assert_not_called()
            self.assertFalse(os.path.exists("build/blocks"))
        finally:
            os.chdir(cwd)

    # tests/smoke/deep.v, three levels: top_deep -> mid -> two leafs.
    @patch('entrypoint.run_command')
    def test_draw_blocks_draws_every_level_and_links_them(self, mock_run):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            shutil.copy(os.path.join(self.FIXTURES, "deep.json"), "build/n.json")
            with contextlib.redirect_stdout(io.StringIO()):
                entrypoint.draw_blocks("build/n.json", ["read_verilog d.v", "proc", "opt"])

            dots = [c[0][0] for c in mock_run.call_args_list if c[0][0][0] == "dot"]
            self.assertEqual(sorted(c[-1] for c in dots),
                             ["build/blocks/mid.svg", "build/blocks/top.svg"])
            with open("build/blocks/top.dot") as f:
                top = f.read()
            with open("build/blocks/mid.dot") as f:
                mid = f.read()
            self.assertIn('URL="mid.svg"', top)
            self.assertNotIn('"parent"', top)
            # Down to the leaf, and back up to where it was opened from.
            self.assertIn('URL="leaf.svg"', mid)
            self.assertIn('"parent" [label="up to top_deep", shape=note, URL="top.svg"]', mid)
            # The leaf has no submodules: its schematic, in one yosys run that
            # reuses the preparation the caller passed.
            yosys = [c[0][0] for c in mock_run.call_args_list if c[0][0][0] == "yosys"]
            self.assertEqual(len(yosys), 1)
            script = yosys[0][2]
            self.assertTrue(script.startswith("read_verilog d.v; proc; opt; "))
            self.assertIn("show -format svg -viewer none -prefix build/blocks/leaf leaf", script)
        finally:
            os.chdir(cwd)

    def test_diagram_plan_names_files_after_modules_and_keeps_them_apart(self):
        # The UART's two io_generic_fifo instances are two parameterisations,
        # so two modules, so two files.
        plan = entrypoint.diagrams.diagram_plan(self._netlist("apb_uart_top.json"), "apb_uart_sv")
        self.assertEqual(plan["apb_uart_sv"], "top")
        self.assertEqual(sorted(plan.values()), ["io_generic_fifo", "io_generic_fifo_2", "top",
                                                 "uart_interrupt", "uart_rx", "uart_tx"])

    # --- the waveform ---

    BLINKY_VCD = os.path.join(os.path.dirname(__file__), "fixtures", "blinky.vcd")

    def test_read_vcd_names_signals_by_their_scope(self):
        # Icarus's VCD of ChipForAll's tb_blinky, 1ps timescale.
        with open(self.BLINKY_VCD) as f:
            ps, signals = entrypoint.diagrams.read_vcd(f.read())
        self.assertEqual(ps, 1)
        width, changes = signals["tb_blinky.uut.count"]
        self.assertEqual(width, 4)
        self.assertEqual(changes[:3], [(0, "x"), (5000, "0"), (25000, "1")])
        self.assertEqual(signals["tb_blinky.led"][1][1], (5000, "0"))

    def test_read_vcd_returns_to_the_outer_scope_after_upscope(self):
        vcd = ("$scope module t $end $scope module u $end $var wire 1 ! a $end "
               "$upscope $end $var wire 1 \" b $end $upscope $end $enddefinitions $end\n")
        _, signals = entrypoint.diagrams.read_vcd(vcd)
        self.assertEqual(sorted(signals), ["t.b", "t.u.a"])

    def test_waveform_refuses_a_signal_the_vcd_does_not_declare(self):
        with open(self.BLINKY_VCD) as f:
            text = f.read()
        with self.assertRaises(KeyError) as cm:
            entrypoint.diagrams.waveform_svg(text, ["tb_blinky.nope", "tb_blinky.led", "tb_blinky.nah"])
        # Every one of them, so a config with three typos takes one fix, not three.
        self.assertIn("tb_blinky.nope", str(cm.exception))
        self.assertIn("tb_blinky.nah", str(cm.exception))

    def test_waveform_draws_one_segment_per_actual_change(self):
        # Writing the value a signal already holds is still recorded in a
        # VCD; drawn, it would be a boundary where nothing changed.
        vcd = ("$timescale 1ns $end $scope module t $end $var reg 4 ! v $end "
               "$upscope $end $enddefinitions $end\n#0\nb11 !\n#10\nb11 !\n#20\nb101 !\n#30\nb101 !\n")
        svg = entrypoint.diagrams.waveform_svg(vcd, ["t.v"])
        self.assertEqual(svg.count("<rect x="), 2)
        self.assertIn(">3<", svg)
        self.assertIn(">5<", svg)
        self.assertIn(">30 ns<", svg)

    def _wave_site(self, signals, vcd=True):
        os.makedirs("build")
        if vcd:
            shutil.copy(self.BLINKY_VCD, "build/wave.vcd")
        with open("build/cocotb-results.xml", "w") as f:
            f.write(self.COCOTB_XML)
        return self._site({"DESIGN_NAME": "blinky", "//WAVE_SIGNALS": signals})

    def test_site_draws_the_signals_wave_signals_names(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._wave_site(["tb_blinky.clk", "tb_blinky.uut.count"])
            self.assertIn('<img src="wave.svg"', page)
            # The file itself, one click away, for a slide or a report.
            self.assertIn('<a class="zoom-dl" href="wave.svg" download>Download SVG</a>', page)
            self.assertIn("build/wave.vcd", page)
            with open("build/site/wave.svg") as f:
                self.assertIn(">count<", f.read())
        finally:
            os.chdir(cwd)

    def test_site_draws_from_the_vcd_that_has_the_signals_not_just_the_newest(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            shutil.copy(self.BLINKY_VCD, "build/wave.vcd")
            with open("build/other_tb.vcd", "w") as f:
                f.write("$scope module other $end $var wire 1 ! x $end $upscope $end "
                        "$enddefinitions $end\n#0\n1!\n")
            os.utime("build/wave.vcd", (1, 1))  # the other one is newer
            page = self._site({"DESIGN_NAME": "blinky", "//WAVE_SIGNALS": ["tb_blinky.led"]})
            self.assertIn("<code>build/wave.vcd</code>", page)
        finally:
            os.chdir(cwd)

    def test_site_fails_on_a_wave_signal_that_is_not_there(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                self._wave_site(["tb_blinky.cnt"])
            self.assertEqual(cm.exception.code, 1)
            # A typo is the usual cause: the message lists the names there are.
            self.assertIn("It declares: ", error.call_args[0][0])
            self.assertIn("tb_blinky.uut.count", error.call_args[0][0])
        finally:
            os.chdir(cwd)

    def test_site_without_a_vcd_leaves_the_waveform_out(self):
        # After `make cocotb` alone there is no VCD yet; that is not an error.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._wave_site(["tb_blinky.clk"], vcd=False)
            self.assertNotIn("wave.svg", page)
        finally:
            os.chdir(cwd)

    def test_site_shows_the_block_diagram_schematic_drew(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build/blocks")
            for name in ("top.svg", "uart_rx.svg", "top.dot"):
                with open(f"build/blocks/{name}", "w") as f:
                    f.write("<svg/>")
            page = self._site()
            self.assertIn('<img src="blocks/top.svg"', page)
            # Every diagram a block links to, so the links work once published;
            # not the .dot sources.
            self.assertEqual(sorted(os.listdir("build/site/blocks")), ["top.svg", "uart_rx.svg"])
        finally:
            os.chdir(cwd)

    def test_site_diagrams_zoom_and_the_script_comes_only_with_them(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            self.assertNotIn("<script>", self._site())

            with open("build/schematic.svg", "w") as f:
                f.write("<svg/>")
            page = self._site()
            self.assertIn('<div class="zoom-view"><a href="schematic.svg"><img src="schematic.svg"', page)
            self.assertIn('data-zoom="reset"', page)
            self.assertEqual(page.count("<script>"), 1)
        finally:
            os.chdir(cwd)

if __name__ == '__main__':
    unittest.main()
