import sys
import os
import re
import io
import json
import contextlib
import unittest
import tempfile
import shutil
import calendar
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
        self.assertRegex(out, r"\n  instances +243 after routing\n")
        self.assertNotIn("standard cells", out)
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

    def test_report_gives_instances_after_synthesis_and_after_routing(self):
        # stat.json says 110 after synthesis; the metrics say 198 after routing.
        # The labels share one column, so the longest, "instance classes",
        # sets where every value starts.
        out = self._report(os.path.join(self.RUN_FIXTURE, "blinky_run", "final", "metrics.json"))

        self.assertIn("\n  instances          110 after synthesis, 198 after routing\n", out)
        self.assertIn("\n  instance classes   57 logic,", out)
        self.assertNotIn("standard cells", out)
        self.assertNotIn("cell classes", out)

    def test_report_breaks_the_instances_down_by_class_without_fill(self):
        # The real 3.0.14 run: its class counts add up to its 198 instances.
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
            # 'clean' is only as strong as the list of what was checked. The
            # two DRC tools are one entry.
            self.assertIn("clean  (DRC, LVS, antenna, XOR)", out)
            self.assertNotIn("Magic", out)
        finally:
            os.chdir(cwd)

    def test_report_names_what_failed_rather_than_listing_zeroes(self):
        out = self._report(self.DIRTY_FIXTURE)

        self.assertIn("signoff", out)
        self.assertIn("2 DRC (Magic), 1 LVS", out)
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

    def _run_with_states(self, final_metrics, steps):
        """A run directory: final/metrics.json, and each step with the metrics its state_out.json holds."""
        run = os.path.join(self.test_dir, "runs", "blinky_run")
        os.makedirs(os.path.join(run, "final"))
        with open(os.path.join(run, "final", "metrics.json"), "w") as f:
            json.dump(final_metrics, f)
        for name, metrics in steps:
            os.makedirs(os.path.join(run, name))
            if metrics is not None:
                with open(os.path.join(run, name, "state_out.json"), "w") as f:
                    json.dump({"metrics": metrics}, f)
        return run

    def test_sta_step_ignores_a_resume_that_never_finished(self):
        # Shape of a real 3.0.14 run: a full flow (76 steps), then a resume
        # from floorplan killed after its post-PnR STA. LibreLane did not
        # rewrite final/, so the summary is the first run's and the timing
        # under it has to be too. 121 was cut off before it wrote its state.
        first, resumed = {"timing__setup__ws": 4.70}, {"timing__setup__ws": 4.63}
        run = self._run_with_states(first, [
            ("55-openroad-stapostpnr", first),
            ("76-misc-reportmanufacturability", first),
            ("119-openroad-stapostpnr", resumed),
            ("121-magic-streamout", None),
        ])

        found = entrypoint.sta_step(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, os.path.join(run, "55-openroad-stapostpnr"))

    def test_sta_step_takes_the_resume_that_did_finish(self):
        first, resumed = {"timing__setup__ws": 4.70}, {"timing__setup__ws": 4.63}
        run = self._run_with_states(resumed, [
            ("55-openroad-stapostpnr", first),
            ("76-misc-reportmanufacturability", first),
            ("119-openroad-stapostpnr", resumed),
            ("140-misc-reportmanufacturability", resumed),
        ])

        found = entrypoint.sta_step(os.path.join(run, "final", "metrics.json"))

        self.assertEqual(found, os.path.join(run, "119-openroad-stapostpnr"))

    def test_last_finished_step_is_the_newest_step_holding_the_final_metrics(self):
        # Every step after the last one that changes a metric holds the same
        # metrics, so the newest of them is the one final/ was written after.
        # A NaN must not make the run unrecognisable: NaN != NaN as a number.
        final = {"timing__setup__ws": 4.70, "design__max_slew": float("nan")}
        run = self._run_with_states(final, [
            ("70-netgen-lvs", final),
            ("76-misc-reportmanufacturability", final),
            ("119-openroad-stapostpnr", {"timing__setup__ws": 4.63}),
        ])

        self.assertEqual(entrypoint.last_finished_step(run), 76)

    def test_last_finished_step_has_no_answer_without_state_files(self):
        run = self._run_with_states({"timing__setup__ws": 4.70}, [
            ("55-openroad-stapostpnr", None),
            ("119-openroad-stapostpnr", None),
        ])

        self.assertIsNone(entrypoint.last_finished_step(run))
        self.assertEqual(
            entrypoint.sta_step(os.path.join(run, "final", "metrics.json")),
            os.path.join(run, "119-openroad-stapostpnr"))

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
            # The schematic is `make schematic`'s file, not part of the page.
            self.assertFalse(os.path.exists("build/site/schematic.svg"))
            self.assertNotIn("schematic", page.lower())

            # The same numbers `report` prints for this fixture.
            self.assertIn("+4.69 ns", page)
            self.assertIn("29.2%", page)
            # The layout is shown, not named: its path means nothing on a website.
            self.assertIn('src="layout.png"', page)
            self.assertNotIn("runs/blinky_run", page)
            self.assertTrue(os.path.exists("build/site/layout.png"))
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
    # the page reads, synthesis's stat.json, the STA step's config.json with
    # the constraints, and the default corner's power.rpt. ir__drop__worst is
    # not from the run: it is a synthetic value, as no real one was at hand.
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

            # One DRC row for both tools, then LVS, antenna and XOR.
            self.assertEqual(page.count('class="PASS">PASS'), 4)
            self.assertRegex(page, r"<td>DRC <span[^>]*>Magic and KLayout</span></td>"
                                   r'<td class="num">0</td><td class="PASS">PASS</td>')
            for check in ("Magic DRC", "KLayout DRC", "<td>Magic</td>", "<td>KLayout</td>"):
                self.assertNotIn(check, page)
            self.assertIn("<td>LVS</td>", page)
            # XOR names the two layouts it compares.
            self.assertIn("<td>XOR <span", page)
            self.assertIn("Magic GDS against KLayout GDS", page)
            # Antenna stays its own row and says why it is not inside DRC.
            self.assertIn("antenna <span", page)
            self.assertIn("checked by OpenROAD, not by DRC", page)
            # Utilization is of the core, not the die beside it.
            self.assertIn('<div class="label">core utilization</div><div class="value">57.1%</div>'
                          '<div class="detail">of a 58.4 \u00d7 57.1 \u00b5m core</div>', page)
            self.assertIn("46 well taps", page)
            self.assertIn("35 timing-repair buffers, 26 of them for hold", page)
            # stat.json: 1366.3104 total, 683.1552 of it sequential -- this
            # design splits exactly in half. Routing's 1906.8 contains both, so
            # the third part is the difference, not a third peer.
            self.assertIn("flip-flops 683.2 &micro;m&sup2;", page)
            self.assertIn("logic 683.2 &micro;m&sup2;", page)
            self.assertIn("added or resized by place and route 540.5 &micro;m&sup2;", page)
            self.assertIn("grew it by 40% to 1,906.8 &micro;m&sup2;", page)
            # Instances: stat.json's 110 after synthesis come first, then the
            # 198 after routing. 57 logic + 26 sequential + 27 inverters from
            # synthesis; 46 taps + 35 timing-repair + 7 clock buffers added.
            self.assertIn("<h3>Instances: 110 after synthesis, 198 after routing</h3>", page)
            self.assertIn('<div class="label">instances</div><div class="value">198</div>'
                          '<div class="detail">after routing, 110 after synthesis</div>', page)
            self.assertIn("from synthesis 110 ", page)
            self.assertIn("added by the flow 88 ", page)
            self.assertNotIn("instance classes", page)
            self.assertNotIn("standard cells</div>", page)
            self.assertNotIn("<h3>Cells", page)
            # The share bar has a column of its own, never under a number. It
            # is the share of the whole, on a track that is the whole -- scaled
            # to the largest group, 54.4% drew as a full bar. The Total row is
            # the sum, so it gets no bar.
            self.assertIn('<td class="num">54.4%</td><td class="bar"><span class="track">'
                          '<span style="width:54%"></span></span></td>', page)
            self.assertRegex(page, r'<tr class="total"><td>Total</td>.*?<td class="bar"></td></tr>')
            # The lint count is not on the page.
            self.assertNotIn("Verilator on the RTL, inside the flow", page)
            # power.rpt of DEFAULT_CORNER, not the bare power__total metric,
            # which in this run is max_ff's 0.290 mW.
            self.assertIn("<code>nom_tt_025C_1v80</code>", page)
            self.assertIn(">247.9<", page)
            self.assertIn(">54.4%<", page)
            self.assertNotIn("<div class=\"label\">power</div>", page)
            # Signoff has its section, and a card in the overview only.
            self.assertEqual(page.count('<div class="label">signoff</div>'), 1)
            self.assertIn('<div class="label">signoff</div>', self._section_text(page, "summary"))
        finally:
            os.chdir(cwd)

    def _sections(self, page):
        return re.findall(r'<section id="([^"]+)"', page)

    def test_site_orders_the_sections_for_a_reviewer(self):
        # The summary first, then the verdicts (tests, timing with its
        # constraints), then area and instances, power, and signoff last.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            page = self._run_site()
            self.assertEqual(self._sections(page),
                             ["summary", "tests-0", "timing", "area", "power", "signoff"])
            self.assertLess(page.index('<section id="summary"'), page.index('<section id="tests-0"'))
        finally:
            os.chdir(cwd)

    def test_site_leaves_out_what_a_reviewer_does_not_read(self):
        # No worst path, no electrical-rule rows, no schematic, block diagram
        # or waveform, even with all of their files and keys present.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build/blocks")
            for name in ("build/schematic.svg", "build/blocks/top.svg", "build/blinky.vcd"):
                with open(name, "w") as f:
                    f.write("<svg/>")
            def with_rules(metrics):
                for rule in ("slew", "cap", "fanout"):
                    metrics[f"design__max_{rule}_violation__count"] = 4
            shutil.copytree(self.RUN_FIXTURE, "runs")
            with open("runs/blinky_run/final/metrics.json") as f:
                metrics = json.load(f)
            with_rules(metrics)
            with open("runs/blinky_run/final/metrics.json", "w") as f:
                json.dump(metrics, f)
            page = self._site({"DESIGN_NAME": "blinky", "//WAVE_SIGNALS": ["blinky.count"]})
            for gone in ("Worst setup path", "Full OpenSTA report", "Electrical rules", "max fanout",
                         "max transition", "max capacitance", "Block diagram", "Waveform",
                         "WAVE_SIGNALS", "Schematic", "schematic.svg", "wave.svg", "blocks/"):
                self.assertNotIn(gone, page)
            self.assertFalse(os.path.exists("build/site/blocks"))
            self.assertFalse(os.path.exists("build/site/schematic.svg"))
            self.assertFalse(os.path.exists("build/site/wave.svg"))
        finally:
            os.chdir(cwd)

    def test_site_says_whether_timing_is_met_and_which_constraints_it_used(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            def r2r(metrics):
                metrics["timing__setup_r2r__ws"] = 5.1
            page = self._run_site(r2r)
            timing = page[page.index('<section id="timing">'):page.index('<section id="area">')]
            self.assertIn("Timing is met", timing)
            self.assertIn('<td>setup</td><td class="num PASS">+4.70 ns</td><td class="num">0</td>'
                          '<td class="num">+5.10 ns</td>', timing)
            self.assertIn('<td>hold</td><td class="num PASS">+0.11 ns</td><td class="num">0</td>'
                          '<td class="num">&mdash;</td>', timing)
            # The run's own values, each with where it came from. CLOCK_PERIOD
            # is in the test's config, the other four are the flow's defaults.
            for row in ("<td>clock period</td><td>10 ns (100 MHz)</td><td>flow default</td>",
                        "<td>clock uncertainty</td><td>0.25 ns</td><td>flow default</td>",
                        "<td>clock transition</td><td>0.15 ns</td><td>flow default</td>",
                        "<td>timing derate</td><td>5%</td><td>flow default</td>",
                        "<td>input and output delay</td><td>20% of the clock period (2 ns)</td>"
                        "<td>flow default</td>"):
                self.assertIn(row, timing)
        finally:
            os.chdir(cwd)

    def test_site_says_when_a_constraint_comes_from_the_config(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            page = self._site({"DESIGN_NAME": "blinky", "CLOCK_PERIOD": 10,
                               "CLOCK_UNCERTAINTY_CONSTRAINT": 0.25})
            self.assertIn("<td>clock period</td><td>10 ns (100 MHz)</td><td>set in config.yaml</td>", page)
            self.assertIn("<td>clock uncertainty</td><td>0.25 ns</td><td>set in config.yaml</td>", page)
            self.assertIn("<td>clock transition</td><td>0.15 ns</td><td>flow default</td>", page)
        finally:
            os.chdir(cwd)

    def test_site_leaves_out_a_constraint_the_run_does_not_state(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            path = "runs/blinky_run/55-openroad-stapostpnr/config.json"
            with open(path) as f:
                run_config = json.load(f)
            for key in ("CLOCK_TRANSITION_CONSTRAINT", "TIME_DERATING_CONSTRAINT"):
                del run_config[key]
            with open(path, "w") as f:
                json.dump(run_config, f)
            page = self._site()
            self.assertIn("<td>clock uncertainty</td>", page)
            self.assertIn("<td>input and output delay</td>", page)
            self.assertNotIn("clock transition", page)
            self.assertNotIn("timing derate", page)
            # No run config at all: no constraints table, and the verdict stays.
            os.remove(path)
            page = self._site()
            self.assertNotIn("Constraints the run used", page)
            self.assertIn("Timing is met", page)
        finally:
            os.chdir(cwd)

    def test_site_shows_ir_drop_in_mv_and_as_a_share_of_the_supply(self):
        # 0.0123 V on the 1.80 V of nom_tt_025C_1v80. The fixture's key is
        # synthetic: no real run's ir__drop__worst was available.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            # An estimate beside the power numbers, not a signoff check.
            power = page[page.index('<section id="power">'):page.index('<section id="signoff">')]
            self.assertIn("<p>Static IR drop, worst: 12 mV, 0.68% of 1.80 V, "
                          "from OpenROAD (<code>ir__drop__worst</code>).</p>", power)
            self.assertNotIn("Static IR drop", page[page.index('<section id="signoff">'):])
            self.assertNotIn("pass or fail", page)
        finally:
            os.chdir(cwd)

    def test_site_gives_a_tiny_ir_drop_two_significant_digits(self):
        def tiny(metrics):
            metrics["ir__drop__worst"] = 0.0000523
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(tiny)
            self.assertIn("Static IR drop, worst: 0.052 mV, 0.0029% of 1.80 V, from OpenROAD", page)
        finally:
            os.chdir(cwd)

    def test_site_says_nothing_about_ir_drop_when_the_run_has_no_key(self):
        def without(metrics):
            del metrics["ir__drop__worst"]
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(without)
            self.assertNotIn("Static IR drop", page)
            self.assertNotIn("ir__drop", page)
            # What the flow does not analyse is said either way.
            self.assertIn("<p>Not analysed: electromigration, crosstalk and dynamic IR drop.</p>", page)
            self.assertIn("<h2>Signoff checks</h2>", page)
        finally:
            os.chdir(cwd)

    def test_site_gives_the_ir_drop_in_mv_when_the_supply_is_unknown(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            path = "runs/blinky_run/55-openroad-stapostpnr/config.json"
            with open(path) as f:
                run_config = json.load(f)
            run_config["DEFAULT_CORNER"] = "typical"
            with open(path, "w") as f:
                json.dump(run_config, f)
            page = self._site()
            self.assertIn("<p>Static IR drop, worst: 12 mV, from OpenROAD", page)
            self.assertNotRegex(page, r"\d% of \d")
        finally:
            os.chdir(cwd)

    def test_site_names_the_tool_that_failed_drc(self):
        def klayout(metrics):
            metrics["klayout__drc_error__count"] = 3
        def both(metrics):
            metrics["magic__drc_error__count"] = 2
            metrics["klayout__drc_error__count"] = 3
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(klayout)
            self.assertRegex(page, r'<td>DRC <span[^>]*>Magic and KLayout</span></td>'
                                   r'<td class="num">3 \(KLayout\)</td><td class="FAIL">FAIL</td>')
            self.assertIn("Signoff: 3 errors", page)
            shutil.rmtree("runs")
            page = self._run_site(both)
            self.assertIn('<td class="num">5 (Magic 2, KLayout 3)</td><td class="FAIL">FAIL</td>', page)
        finally:
            os.chdir(cwd)

    def test_site_names_the_instances_after_synthesis_and_after_routing(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            area = page[page.index('<section id="area">'):page.index('<section id="power">')]
            self.assertIn("<h2>Area and instances</h2>", area)
            self.assertIn("110 after synthesis, 198 after routing", area)
            self.assertNotIn("cell", area)
            # Without synthesis's stat.json the page only has the routed count.
            shutil.rmtree("runs")
            shutil.copytree(self.RUN_FIXTURE, "runs")
            os.remove("runs/blinky_run/06-yosys-synthesis/reports/stat.json")
            page = self._site()
            self.assertIn("<h3>Instances: 198 after routing</h3>", page)
            self.assertNotIn("after synthesis", page)
        finally:
            os.chdir(cwd)

    # --- drive strength: the _N of the cell name, after synthesis and after routing ---

    # A real LibreLane 3.0.14 run of ChipForAll's blinky (WIDTH 16), whole where
    # it is small: final/metrics.json, final/nl/blinky.nl.v, synthesis's
    # stat.json, and the STA step's config.json cut to the keys the page reads.
    # Its 274 instances are 65 from synthesis, 21 the flow added (18 X1 hold and
    # delay cells, 3 X16 clock buffers), 27 taps and 161 decap and fill; its
    # metrics count 113 standard cells, which is the 86 and the taps.
    REAL_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "run-3.0.14-blinky16")
    REAL_METRICS = os.path.join("runs", "blinky_run", "final", "metrics.json")

    def _real_run(self, *remove):
        shutil.copytree(self.REAL_FIXTURE, "runs")
        for path in remove:
            os.remove(os.path.join("runs", "blinky_run", path))

    def test_drive_strength_is_the_number_ending_the_cell_name(self):
        cells = {
            "sky130_fd_sc_hd__dfrtp_2": 16,
            "sky130_fd_sc_hd__clkbuf_16": 3,
            "sky130_fd_sc_hd__dlygate4sd3_1": 14,
            "sky130_fd_sc_hd__clkdlybuf4s25_1": 4,
            "sky130_fd_sc_hd__inv_2": 17,
        }
        self.assertEqual(entrypoint.drive_strengths(cells), {1: 18, 2: 33, 16: 3})

    def test_drive_strength_leaves_out_cells_with_no_logic_function(self):
        cells = {
            "sky130_fd_sc_hd__tapvpwrvgnd_1": 27,
            "sky130_fd_sc_hd__decap_3": 43,
            "sky130_ef_sc_hd__decap_12": 19,
            "sky130_fd_sc_hd__fill_1": 37,
            "sky130_fd_sc_hd__fill_diode_2": 2,
            "sky130_fd_sc_hd__diode_2": 4,
            "sky130_fd_sc_hd__and2_2": 3,
            "my_macro_8": 1,  # a macro is not a standard cell
            "$_AND_": 5,      # nor is a Yosys-internal type
        }
        self.assertEqual(entrypoint.drive_strengths(cells), {2: 3})

    def test_drive_strength_counts_the_routed_netlist_of_a_real_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            cells = entrypoint.routed_cells(self.REAL_METRICS)
            # Every instance, physical ones too: 113 standard cells + 161 fill.
            self.assertEqual(sum(cells.values()), 274)
            self.assertEqual(cells["sky130_fd_sc_hd__tapvpwrvgnd_1"], 27)
            self.assertEqual(entrypoint.drive_table(self.REAL_METRICS),
                             [(1, 0, 18), (2, 65, 65), (16, 0, 3)])
        finally:
            os.chdir(cwd)

    def test_report_gives_the_drive_strength_before_and_after_routing(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            out = self._report(self.REAL_METRICS)
            # One column with the other rows: "instance classes" sets it.
            self.assertIn("\n  drive strength     X1 0->18, X2 65->65, X16 0->3  (synthesis->routing)\n", out)
            self.assertIn("\n  instance classes   32 logic,", out)
        finally:
            os.chdir(cwd)

    def test_report_drive_strength_names_the_stage_it_has_and_never_prints_zeroes_for_the_other(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run("final/nl/blinky.nl.v")
            out = self._report(self.REAL_METRICS)
            self.assertIn("\n  drive strength     X2 65  (after synthesis)\n", out)
            self.assertNotIn("->", out)
            shutil.rmtree("runs")
            self._real_run("06-yosys-synthesis/reports/stat.json")
            out = self._report(self.REAL_METRICS)
            self.assertIn("\n  drive strength     X1 18, X2 65, X16 3  (after routing)\n", out)
            self.assertNotIn("->", out)
            shutil.rmtree("runs")
            self._real_run("final/nl/blinky.nl.v", "06-yosys-synthesis/reports/stat.json")
            self.assertNotIn("drive strength", self._report(self.REAL_METRICS))
        finally:
            os.chdir(cwd)

    def test_site_tabulates_the_drive_strength_of_a_real_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            page = self._site()
            area = page[page.index('<section id="area">'):]
            area = area[:area.index("</section>")]
            self.assertIn("<summary>Drive strength of the instances (3 sizes)</summary>", area)
            self.assertIn('<th>drive strength</th><th class="num">after synthesis</th>'
                          '<th class="num">after routing</th>', area)
            rows = re.findall(r'<tr><td>(X\d+)</td><td class="num">(\d+)</td><td class="num">(\d+)</td></tr>', area)
            self.assertEqual(rows, [("X1", "0", "18"), ("X2", "65", "65"), ("X16", "0", "3")])
            self.assertIn('<tr class="total"><td>Total</td><td class="num">65</td><td class="num">86</td></tr>', area)
            self.assertIn("Place and route added 18 X1 and 3 X16 instances.", area)
            # The 113 routed instances less the 27 well taps are the 86.
            self.assertIn("65 after synthesis, 113 after routing", area)
            self.assertIn("27 well taps", area)
            # A table of its own, not also a card of the summary.
            self.assertNotIn('<div class="label">drive strength</div>', page)
            table = area[area.index('<table class="drive">'):]
            for physical in ("tap", "decap", "fill", "diode"):
                self.assertNotIn(physical, table.split("</table>")[0])
        finally:
            os.chdir(cwd)

    def test_site_drive_strength_has_a_column_only_for_a_stage_it_read(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run("final/nl/blinky.nl.v")
            area = self._site()
            self.assertIn('<th>drive strength</th><th class="num">after synthesis</th></tr>', area)
            self.assertNotIn('<th class="num">after routing</th>', area)
            self.assertNotIn("Place and route added", area)
            shutil.rmtree("runs")
            self._real_run("06-yosys-synthesis/reports/stat.json")
            area = self._site()
            self.assertIn('<th>drive strength</th><th class="num">after routing</th></tr>', area)
            self.assertNotIn('<th class="num">after synthesis</th>', area)
            shutil.rmtree("runs")
            self._real_run("final/nl/blinky.nl.v", "06-yosys-synthesis/reports/stat.json")
            self.assertNotIn("Drive strength", self._site())
        finally:
            os.chdir(cwd)

    def test_site_drive_strength_reading_says_what_routing_added_and_removed(self):
        # Hand-made rows: a real run only ever added.
        text = entrypoint.site_page.drive_table([(1, 0, 2), (2, 3, 1), (4, 5, 5)])
        self.assertIn("Place and route added 2 X1 instances. It removed 2 X2 instances.", text)
        text = entrypoint.site_page.drive_table([(2, 3, 3)])
        self.assertIn("Place and route did not change the mix.", text)

    def test_site_names_the_library_and_says_a_sky130_one_is_single_vt(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            area = self._site()
            self.assertIn("<p>Standard cell library <code>sky130_fd_sc_hd</code>, "
                          "single threshold voltage.</p>", area)
            # No device names: the SkyWater doc and the cell netlists disagree.
            self.assertNotIn("fet_01v8", area)
            # Another PDK's library is named and nothing is claimed about it.
            path = "runs/blinky_run/55-openroad-stapostpnr/config.json"
            with open(path) as f:
                config = json.load(f)
            config["STD_CELL_LIBRARY"] = "gf180mcu_fd_sc_mcu7t5v0"
            with open(path, "w") as f:
                json.dump(config, f)
            area = self._site()
            self.assertIn("<p>Standard cell library <code>gf180mcu_fd_sc_mcu7t5v0</code>.</p>", area)
            self.assertNotIn("threshold", area)
            # A run that states no library gets no line.
            del config["STD_CELL_LIBRARY"]
            with open(path, "w") as f:
                json.dump(config, f)
            self.assertNotIn("Standard cell library", self._site())
        finally:
            os.chdir(cwd)

    def test_site_states_what_the_power_number_assumes(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            power = page[page.index('<section id="power">'):page.index('<section id="signoff">')]
            self.assertIn("<code>nom_tt_025C_1v80</code>", power)
            self.assertIn("1.80 V", power)
            self.assertIn("1.80 V), clock 100 MHz.", power)
            self.assertIn("OpenSTA's default, 0.1 toggles per clock on data nets", power)
            self.assertIn("not taken from simulation", power)
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

    def test_site_says_when_it_was_built(self):
        # A published page stays up until the next one replaces it, and a red
        # main does not replace it, so the date is how a reader tells its age.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                page = self._run_site()
            self.assertIn("Built 1970-01-01 08:00 (UTC+8)", page)
            # 16:30 UTC is already the next day in Taiwan: a page built with
            # the UTC clock, or a wrong offset, shows the wrong date.
            epoch = str(calendar.timegm((2026, 9, 21, 16, 30, 0)))
            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": epoch}):
                page = self._site()
            self.assertIn("Built 2026-09-22 00:30 (UTC+8)", page)
            self.assertNotIn("UTC</", page)
            self.assertNotIn("2026-09-21", page)
            # Off a pinned epoch the clock is read in the same offset.
            site_page = entrypoint.site_page
            fixed = site_page.datetime(2026, 1, 1, 16, 0, tzinfo=site_page.timezone.utc)

            class FakeClock(site_page.datetime):
                @classmethod
                def now(cls, tz=None):
                    return fixed.astimezone(tz)

            env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
            with patch.object(site_page, "datetime", FakeClock), patch.dict(os.environ, env, clear=True):
                page = self._site()
            self.assertIn("Built 2026-01-02 00:00 (UTC+8)", page)
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
            # Positive slack is the good news; it says so in colour, in the
            # timing section, where the slack numbers live now.
            self.assertIn('<td class="num PASS">+4.70 ns</td>', page)
            self.assertNotIn('<div class="label">setup slack</div>', page)
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
            self.assertIn('<td class="num FAIL">-0.50 ns</td>', page)
            self.assertNotIn('<td class="num PASS">-0.50', page)
            self.assertIn("Timing is not met.", page)
            self.assertNotIn("Timing is met", page)
            self.assertIn('<div class="value">12,345</div>', page)
            self.assertIn("after routing, 110 after synthesis", page)
            self.assertIn('<div class="stat bad"><div class="value">-0.50 ns</div>'
                          '<div class="detail">setup &middot; ', page)
        finally:
            os.chdir(cwd)

    def test_site_takes_the_clock_from_the_run_not_the_config(self):
        # The run's own CLOCK_PERIOD is the one the result depends on. A
        # config edited after the run must not change what the page says.
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            shutil.copytree(self.RUN_FIXTURE, "runs")
            page = self._site({"DESIGN_NAME": "blinky", "CLOCK_PERIOD": 4.0})
            self.assertIn("<td>clock period</td><td>10 ns (100 MHz)</td>", page)
            self.assertNotIn("250 MHz", page)
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
            self.assertIn("69.5 \u00d7 80.2 \u00b5m &middot; 198 instances after routing &middot; sky130A", header)
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
        # with a chip, and a link preview.
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
            self.assertLess(page.index('id="layout"'), page.index('id="timing"'))
            self.assertLess(page.index('id="timing"'), page.index('id="signoff"'))
            self.assertIn('<p class="lede">A clock divider that blinks an LED.</p>', page)
            self.assertIn('content="A clock divider that blinks an LED."', page)
            self.assertIn('<meta property="og:image" content="https://some.github.io/repo/layout.png">', page)
            self.assertIn('<a class="btn" href="https://github.com/Some/repo">View source</a>', page)
            # The schematic is a file of `make schematic`, not part of the page.
            self.assertNotIn("Schematic", page)
            # Only the constraints and the drive strength fold away.
            self.assertEqual(page.count("<details"), 2)
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
            # No table; the IR drop line keeps a Power section of its own.
            self.assertNotIn('<table class="power">', page)
            self.assertIn("Static IR drop, worst:", page[page.index('<section id="power">'):])
            self.assertIn('<div class="label">total power</div><div class="value">0.290 mW</div>'
                          '<div class="detail">corner not named</div>', page)
        finally:
            os.chdir(cwd)

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

    def _wave_site(self, signals, vcd=True):
        os.makedirs("build")
        if vcd:
            shutil.copy(self.BLINKY_VCD, "build/wave.vcd")
        with open("build/cocotb-results.xml", "w") as f:
            f.write(self.COCOTB_XML)
        return self._site({"DESIGN_NAME": "blinky", "//WAVE_SIGNALS": signals})

    def _no_testbench_config(self, **keys):
        """RTL and the Python tests, without TEST_FILES unless a key says."""
        os.makedirs(os.path.join(self.test_dir, "pytests"), exist_ok=True)
        open(os.path.join(self.test_dir, "pytests/test_top.py"), "w").close()
        config = {"VERILOG_FILES": ["src/**/*.v"], "DESIGN_NAME": "top"}
        config.update(keys)
        return config

    def _sim_args(self, if_configured):
        args = MagicMock()
        args.files = None
        args.if_configured = if_configured
        return args

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_if_configured_skips_when_only_cocotb_is_configured(self, mock_ensure, mock_run):
        config = self._no_testbench_config(**{"//COCOTB_TESTS": ["dir::pytests/*.py"]})
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch("entrypoint.log_info") as info:
                entrypoint.cmd_sim(self._sim_args(True), config)
            mock_run.assert_not_called()
            self.assertIn("TEST_FILES is not set", info.call_args[0][0])
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_if_configured_fails_when_nothing_is_configured(self, mock_ensure, mock_run):
        config = self._no_testbench_config()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_sim(self._sim_args(True), config)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("TEST_FILES", error.call_args[0][0])
            self.assertIn("COCOTB_TESTS", error.call_args[0][0])
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_if_configured_runs_when_the_testbench_is_configured(self, mock_ensure, mock_run):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            entrypoint.cmd_sim(self._sim_args(True), self.config)
            self.assertEqual(mock_run.call_args_list[0][0][0][0], "iverilog")
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_sim_asked_for_by_name_still_fails_without_a_testbench(self, mock_ensure, mock_run):
        # Even with the Python tests configured: `make sim` named sim.
        config = self._no_testbench_config(**{"//COCOTB_TESTS": ["dir::pytests/*.py"]})
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_sim(self._sim_args(False), config)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("sim has no testbench", error.call_args[0][0])
        finally:
            os.chdir(cwd)

    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_if_configured_skips_when_only_a_testbench_is_configured(
        self, mock_ensure, mock_run, mock_cfg, mock_check
    ):
        config = self._no_testbench_config(**{"TEST_FILES": ["test/*.v"]})
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = self._sim_args(True)
            args.netlist = None
            with patch("entrypoint.log_info") as info:
                entrypoint.cmd_cocotb(args, config)
            mock_run.assert_not_called()
            mock_check.assert_not_called()
            self.assertIn("COCOTB_TESTS is not set", info.call_args[0][0])
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_if_configured_fails_when_nothing_is_configured(self, mock_ensure, mock_run):
        config = self._no_testbench_config()
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = self._sim_args(True)
            args.netlist = None
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_cocotb(args, config)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("TEST_FILES", error.call_args[0][0])
            self.assertIn("COCOTB_TESTS", error.call_args[0][0])
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_cocotb_asked_for_by_name_still_fails_without_tests(self, mock_ensure, mock_run):
        config = self._no_testbench_config(**{"TEST_FILES": ["test/*.v"]})
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = self._sim_args(False)
            args.netlist = None
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_cocotb(args, config)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("No cocotb tests", error.call_args[0][0])
        finally:
            os.chdir(cwd)

    def test_if_configured_is_off_unless_given(self):
        parser = entrypoint.build_parser()
        for command in ("sim", "cocotb"):
            self.assertFalse(parser.parse_args([command]).if_configured)
            self.assertTrue(parser.parse_args([command, "--if-configured"]).if_configured)

    # --- gatesim: the Verilog testbench, else the cocotb tests ---

    @patch('entrypoint.check_cocotb_results')
    @patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__))
    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_runs_the_cocotb_tests_when_there_is_no_gate_testbench(
        self, mock_ensure, mock_run, mock_cfg, mock_check
    ):
        config = self._gl_cocotb_config()
        del config["//GATE_TESTS"]
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.files = None
            args.netlist = None

            entrypoint.cmd_gatesim(args, config)

            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertTrue(any("top.nl.v" in a for a in compile_cmd))
            self.assertFalse(any("src/" in a for a in compile_cmd))
            self.assertIn("build/cocotb-gl.vvp", compile_cmd)
            self.assertEqual(compile_cmd[compile_cmd.index("-s") + 1], "top")
            self.assertEqual(
                mock_check.call_args[0][0], os.path.join("build", "cocotb-gl-results.xml")
            )
        finally:
            os.chdir(cwd)

    @patch('entrypoint.cmd_cocotb')
    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_prefers_the_gate_testbench_to_the_cocotb_tests(
        self, mock_ensure, mock_run, mock_cocotb
    ):
        config = self._gl_cocotb_config()  # holds both keys
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.netlist = None

            entrypoint.cmd_gatesim(args, config)

            mock_cocotb.assert_not_called()
            compile_cmd = mock_run.call_args_list[0][0][0]
            self.assertTrue(any("tb_top_gl.v" in a for a in compile_cmd))
        finally:
            os.chdir(cwd)

    @patch('entrypoint.run_command')
    @patch('entrypoint.ensure_build_dir')
    def test_gatesim_error_names_both_keys(self, mock_ensure, mock_run):
        config = self._gl_workspace()
        del config["//GATE_TESTS"]
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            args = MagicMock()
            args.netlist = None
            with patch("entrypoint.log_error") as error, self.assertRaises(SystemExit) as cm:
                entrypoint.cmd_gatesim(args, config)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("GATE_TESTS", error.call_args[0][0])
            self.assertIn("COCOTB_TESTS", error.call_args[0][0])
            mock_run.assert_not_called()
        finally:
            os.chdir(cwd)

    # --- the waveform of a cocotb run ---

    def _cocotb_compile_cmd(self, config, netlist=None):
        os.makedirs("build", exist_ok=True)
        args = MagicMock()
        args.files = None
        args.netlist = netlist
        with patch('entrypoint.check_cocotb_results'), \
             patch('entrypoint.cocotb_config', return_value=os.path.dirname(__file__)), \
             patch('entrypoint.ensure_build_dir'), \
             patch('entrypoint.run_command') as run:
            entrypoint.cmd_cocotb(args, config)
        return run.call_args_list[0][0][0]

    def _rtl_cocotb_config(self):
        os.makedirs(os.path.join(self.test_dir, "pytests"), exist_ok=True)
        open(os.path.join(self.test_dir, "pytests/test_top.py"), "w").close()
        return {"VERILOG_FILES": ["src/**/*.v"], "//COCOTB_TESTS": ["dir::pytests/*.py"],
                "DESIGN_NAME": "top"}

    def _compile_in(self, config, environ, netlist=None):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            with patch.dict(os.environ, environ):
                return self._cocotb_compile_cmd(config, netlist=netlist)
        finally:
            os.chdir(cwd)

    def test_cocotb_dumps_nothing_unless_asked(self):
        env = {k: v for k, v in os.environ.items() if k != "WAVES"}
        with patch.dict(os.environ, env, clear=True):
            compile_cmd = self._compile_in(self._rtl_cocotb_config(), {})
        self.assertFalse(any("c4o_dump" in a for a in compile_cmd))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "build", "c4o_dump.v")))

    def test_cocotb_dumps_a_vcd_from_the_design_when_waves_is_1(self):
        compile_cmd = self._compile_in(self._rtl_cocotb_config(), {"WAVES": "1"})
        self.assertIn("c4o_dump", compile_cmd)
        dump = os.path.join(self.test_dir, "build", "c4o_dump.v")
        with open(dump) as f:
            text = f.read()
        self.assertIn('$dumpfile("build/top.vcd");', text)
        self.assertIn("$dumpvars(0, top);", text)
        self.assertEqual(compile_cmd[compile_cmd.index("c4o_dump") + 1], dump.replace(self.test_dir + os.sep, ""))

    def test_cocotb_dumps_nothing_for_any_other_waves_value(self):
        for value in ("0", "", "yes", "true"):
            with self.subTest(WAVES=value):
                compile_cmd = self._compile_in(self._rtl_cocotb_config(), {"WAVES": value})
                self.assertFalse(any("c4o_dump" in a for a in compile_cmd))

    def test_cocotb_ignores_the_obsolete_wave_signals_key(self):
        # Copies made before WAVES keep "//WAVE_SIGNALS" in config.yaml. It
        # neither dumps nor breaks the run, and WAVES=1 still dumps.
        config = self._rtl_cocotb_config()
        config["//WAVE_SIGNALS"] = ["top.count"]
        config["WAVE_SIGNALS"] = ["top.count"]
        env = {k: v for k, v in os.environ.items() if k != "WAVES"}
        with patch.dict(os.environ, env, clear=True):
            compile_cmd = self._compile_in(config, {})
        self.assertFalse(any("c4o_dump" in a for a in compile_cmd))
        self.assertIn("c4o_dump", self._compile_in(config, {"WAVES": "1"}))

    def test_cocotb_on_the_netlist_does_not_dump(self):
        config = self._gl_cocotb_config()
        config["//WAVE_SIGNALS"] = ["top.count"]
        compile_cmd = self._compile_in(config, {"WAVES": "1"}, netlist="")
        self.assertFalse(any("c4o_dump" in a for a in compile_cmd))

    def test_site_ignores_the_obsolete_wave_signals_key(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            with open("build/top.vcd", "w") as f:
                f.write("$enddefinitions $end\n")
            page = self._site({"DESIGN_NAME": "top", "//WAVE_SIGNALS": ["top.nothing_like_this"]})
            self.assertIn("1/2 passed", page)
            self.assertNotIn("Waveform", page)
            self.assertFalse(os.path.exists("build/site/wave.svg"))
        finally:
            os.chdir(cwd)

    # --- the Summary section ---

    def _summary(self, page):
        """{label: (value, detail)} of the Summary section's cards."""
        found = re.search(r'<section id="summary">.*?</section>', page, re.S)
        region = found[0] if found else ""
        out = {}
        # The timing card holds two stats; each is read as the card it replaced.
        for m in re.finditer(
                r'<div class="kpi timing"><div class="label">[^<]*</div><div class="stats">(?P<stats>.*?</div></div>)</div></div>'
                r'|<div class="kpi[^"]*"><div class="label">(?P<label>[^<]*)</div><div class="value">(?P<value>[^<]*)</div>'
                r'(?:<div class="detail">(?P<detail>[^<]*)</div>)?', region, re.S):
            if m["stats"]:
                for value, name, vio in re.findall(
                        r'<div class="stat (?:good|bad)"><div class="value">([^<]*)</div>'
                        r'<div class="detail">(setup|hold) &middot; ([^<]*)</div>', m["stats"]):
                    out[f"worst {name} slack"] = (value, vio)
            else:
                out[m["label"]] = (m["value"], m["detail"])
        return out

    SUMMARY_LABELS = ["die", "core utilization", "instances", "clock", "worst setup slack",
                       "worst hold slack", "total power", "signoff"]

    def test_summary_has_every_item_and_is_the_first_section_under_the_nav(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            self.assertEqual(list(self._summary(page)), self.SUMMARY_LABELS)
            self.assertIn("<h2>Summary</h2>", page)
            self.assertEqual(self._sections(page), ["summary", "timing", "area", "power", "signoff"])
            self.assertLess(page.index("<nav"), page.index('<section id="summary">'))
            self.assertLess(page.index('<section id="summary">'), page.index('<section id="timing">'))
            nav = page[page.index("<nav"):page.index("</nav>")]
            self.assertLess(nav.index('href="#summary"'), nav.index('href="#timing"'))
            self.assertIn(">Summary</a>", nav)
            self.assertNotIn('role="region"', page)
        finally:
            os.chdir(cwd)

    def test_summary_values_are_the_values_of_the_sections(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site()
            cards = self._summary(page)
            section = lambda name: self._section_text(page, name)
            timing, area, power = section("timing"), section("area"), section("power")
            # Slack: the timing table's own cells.
            for name in ("setup", "hold"):
                value, detail = cards[f"worst {name} slack"]
                self.assertIn(f'<tr><td>{name}</td><td class="num PASS">{value}</td>'
                              f'<td class="num">{detail.split()[0]}</td>', timing)
            # Clock: the constraint row, as MHz first.
            self.assertEqual(cards["clock"], ("100 MHz", "10 ns period"))
            self.assertIn("<td>clock period</td><td>10 ns (100 MHz)</td>", timing)
            self.assertIn(", clock 100 MHz.", power)
            # Power: the headline of the power section, and the table's Total row.
            mw = cards["total power"][0]
            self.assertEqual(mw, "0.248 mW")
            self.assertIn(f"<strong>{mw} in total</strong>", power)
            self.assertIn(">247.9<", power)
            # The corner in words, as the Power section writes it.
            self.assertEqual(cards["total power"][1],
                             "typical wire RC, typical transistors, 25 \u00b0C, 1.80 V")
            self.assertIn("(typical wire RC, typical transistors, 25 &deg;C, 1.80 V)", power)
            self.assertNotIn("nom_tt_025C_1v80", self._section_text(page, "summary"))
            # Instances: the area section's heading, routed first.
            self.assertEqual(cards["instances"], ("198", "after routing, 110 after synthesis"))
            self.assertIn("<h3>Instances: 110 after synthesis, 198 after routing</h3>", area)
            # Die, utilization and instances live in the Summary only; the
            # area section keeps the detail the Summary has no room for.
            for label in ("die", "core utilization", "instances"):
                self.assertNotIn(f'<div class="label">{label}</div>', area)
            self.assertNotIn('class="kpi', area)
            # The core size is on the utilization card only.
            self.assertNotIn("Core:", area)
            self.assertNotIn("57.1 &micro;m", area)
            self.assertEqual(cards["core utilization"], ("57.1%", "of a 58.4 \u00d7 57.1 \u00b5m core"))
            self.assertEqual(cards["die"][0], "69.5 \u00d7 80.2 \u00b5m")
            self.assertEqual(cards["signoff"][0], "clean")
            self.assertNotIn("FAIL", section("signoff"))
            # The lint count is not on the page.
            self.assertNotIn("lint warnings", cards)
            self.assertNotIn("lint warnings", page)
        finally:
            os.chdir(cwd)

    def test_summary_omits_a_card_whose_data_is_missing(self):
        def without(*keys):
            def edit(metrics):
                for key in keys:
                    metrics.pop(key, None)
            return edit
        cases = [
            ("worst hold slack", without("timing__hold__ws")),
            ("worst setup slack", without("timing__setup__ws")),
            ("die", without("design__die__bbox")),
            ("core utilization", without("design__instance__utilization")),
            ("signoff", without("magic__drc_error__count", "klayout__drc_error__count",
                                "design__lvs_error__count", "route__antenna_violation__count",
                                "design__xor_difference__count")),
        ]
        cwd = os.getcwd()
        for label, edit in cases:
            with self.subTest(label):
                os.chdir(self.test_dir)
                try:
                    cards = self._summary(self._run_site(edit))
                finally:
                    os.chdir(cwd)
                    shutil.rmtree(os.path.join(self.test_dir, "runs"), ignore_errors=True)
                self.assertNotIn(label, cards)
                # The others are still there, and none is a placeholder zero.
                self.assertGreater(len(cards), 3)
                for value, _ in cards.values():
                    self.assertNotIn(value, ("", "0 mW", "0.000 mW", "None", "?"))

    def test_summary_leaves_out_the_clock_and_power_it_has_no_report_for(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._run_site()
            # No STA step and no config.yaml clock: no clock card. No power.rpt
            # and no bare metric: no power card.
            os.remove("runs/blinky_run/55-openroad-stapostpnr/config.json")
            os.remove("runs/blinky_run/55-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt")
            with open("runs/blinky_run/final/metrics.json") as f:
                metrics = json.load(f)
            del metrics["power__total"]
            with open("runs/blinky_run/final/metrics.json", "w") as f:
                json.dump(metrics, f)
            cards = self._summary(self._site({"DESIGN_NAME": "blinky"}))
            self.assertNotIn("clock", cards)
            self.assertNotIn("total power", cards)
            self.assertIn("die", cards)
            # The config's own clock is the fallback the timing section uses too.
            cards = self._summary(self._site({"DESIGN_NAME": "blinky", "CLOCK_PERIOD": 4.0}))
            self.assertEqual(cards["clock"], ("250 MHz", "4 ns period"))
        finally:
            os.chdir(cwd)

    def test_summary_instances_say_which_stage_when_only_one_is_known(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            cards = self._summary(self._run_site(
                lambda m: m.pop("design__instance__count__stdcell")))
            self.assertEqual(cards["instances"], ("110", "after synthesis"))
        finally:
            os.chdir(cwd)

    def test_summary_power_without_a_report_is_the_bare_metric_and_says_so(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._run_site()
            os.remove("runs/blinky_run/55-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt")
            cards = self._summary(self._site({"DESIGN_NAME": "blinky"}))
            self.assertEqual(cards["total power"], ("0.290 mW", "corner not named"))
        finally:
            os.chdir(cwd)

    def test_summary_is_absent_without_a_run(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            page = self._site({"DESIGN_NAME": "top"})
            self.assertNotIn("Summary", page)
            self.assertNotIn('class="kpi', page)
        finally:
            os.chdir(cwd)

    def test_summary_names_what_failed_in_signoff_and_a_negative_slack(self):
        def broken(metrics):
            metrics["klayout__drc_error__count"] = 3
            metrics["design__lvs_error__count"] = 1
            metrics["timing__hold__ws"] = -0.05
            metrics["timing__hold_vio__count"] = 1
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            page = self._run_site(broken)
            cards = self._summary(page)
            self.assertEqual(cards["signoff"][0], "3 DRC (KLayout), 1 LVS")
            self.assertIn('<div class="kpi bad"><div class="label">signoff</div>', page)
            self.assertEqual(cards["worst hold slack"], ("-0.05 ns", "1 violation"))
            self.assertIn('<div class="stat bad"><div class="value">-0.05 ns</div>'
                          '<div class="detail">hold &middot; 1 violation</div>', page)
            # `report` says the same words as the card: one reading of the checks.
            with open("runs/blinky_run/final/metrics.json") as f:
                self.assertEqual(entrypoint.signoff_row(json.load(f)),
                                 ("signoff", "3 DRC (KLayout), 1 LVS"))
        finally:
            os.chdir(cwd)

    def _section_text(self, page, name):
        return page[page.index(f'<section id="{name}">'):].split("</section>")[0]

    def test_the_tests_table_fits_a_phone_without_scrolling_sideways(self):
        # A long test name breaks anywhere, and the result columns are narrow
        # at 600px and below, so RTL and GATES stay in view. Measured in a
        # browser at 390px: the table's scrollWidth equals its clientWidth.
        css = entrypoint.site_page.CSS
        self.assertRegex(css, re.compile(
            r"@media \(max-width: 600px\).*?table\.tests th:not\(:first-child\), "
            r"table\.tests td:not\(:first-child\) \{ width: 56px; \}", re.S))

    def test_hero_caption_gives_the_routed_count_and_says_what_the_picture_is(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            os.makedirs("runs/blinky_run/final/render")
            open("runs/blinky_run/final/render/blinky.png", "w").close()
            page = self._site({"DESIGN_NAME": "blinky", "PDK": "sky130A"})
            caption = page[page.index("<figcaption>"):page.index("</figcaption>")]
            self.assertIn("113 instances after routing", caption)
            self.assertNotIn("65 instances", caption)
            self.assertEqual(caption, "<figcaption>56.4 \u00d7 67.1 \u00b5m &middot; 113 instances "
                                      "after routing")
            self.assertNotIn("LibreLane draws it", page)
            self.assertNotIn("layer colors", page)
        finally:
            os.chdir(cwd)

    def test_hero_caption_labels_the_count_when_only_synthesis_gave_one(self):
        text = entrypoint.site_page.hero_art(
            "layout.png", "d", [("instances", "110 after synthesis")], None)
        self.assertIn("110 instances after synthesis", text)
        text = entrypoint.site_page.hero_art("layout.png", "d", [], None)
        self.assertNotIn("<figcaption>", text)

    def test_corner_words_write_the_temperature_as_a_number(self):
        words = entrypoint.site_page.corner_words
        self.assertIn(", 25 &deg;C, 1.80 V", words("nom_tt_025C_1v80"))
        self.assertIn(", -40 &deg;C, 1.95 V", words("max_ff_n40C_1v95"))
        self.assertIn(", 100 &deg;C, 1.60 V", words("max_ss_100C_1v60"))
        self.assertIn(", 0 &deg;C,", words("nom_tt_000C_1v80"))
        self.assertNotIn("025", words("nom_tt_025C_1v80"))
        self.assertIsNone(words("nonsense"))

    def test_power_headline_is_in_milliwatts_and_the_table_says_it_is_not(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            power = self._section_text(self._run_site(), "power")
            self.assertIn("<strong>0.248 mW in total</strong> at corner <code>nom_tt_025C_1v80</code> "
                          "(typical wire RC, typical transistors, 25 &deg;C, 1.80 V), clock 100 MHz.", power)
            self.assertIn("The table is in &micro;W.", power)
            self.assertNotIn("025 &deg;C", power)
            self.assertNotIn(";", re.sub(r"&[a-z]+;", "", re.sub(r"<[^>]*>", "", power)))
            # The page does not describe its own layout.
            self.assertNotIn("narrow", power)
            self.assertNotIn("Dynamic is", power)
        finally:
            os.chdir(cwd)

    def test_constraints_and_drive_strength_are_collapsed_with_a_label(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            page = self._site()
            timing = self._section_text(page, "timing")
            self.assertRegex(timing, r'<details class="constraints"><summary>Constraints the run used \(5\)</summary>'
                                     r'.*<td>clock period</td>.*</table></div></details>')
            self.assertNotIn("<h3>Constraints", page)
            # The verdict table stays outside the fold.
            self.assertLess(timing.index("<td>setup</td>"), timing.index("<details"))
            area = self._section_text(page, "area")
            self.assertRegex(area, r'<details class="drive-strength"><summary>Drive strength of the '
                                   r'instances \(3 sizes\)</summary>.*<table class="drive">.*Place and route added.*</details>')
            self.assertNotIn("<details open", page)
        finally:
            os.chdir(cwd)

    def test_a_details_label_counts_the_rows_inside(self):
        text = entrypoint.site_page.drive_table([(1, 0, 2), (2, 3, 1), (4, 5, 5)])
        self.assertIn("(3 sizes)</summary>", text)
        self.assertEqual(text.count("<tr><td>X"), 3)
        text = entrypoint.site_page.drive_table([(2, 3, 3)])
        self.assertIn("(1 size)</summary>", text)
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            timing = self._section_text(self._run_site(), "timing")
            details = timing[timing.index("<details"):]
            rows = len(re.findall(r"<tr><td>clock |<tr><td>timing |<tr><td>input ", details))
            self.assertEqual(rows, 5)
            self.assertIn("<summary>Constraints the run used (5)</summary>", details)
            # Fewer constraints in the run, fewer in the label.
            shutil.rmtree("runs")
            path = "runs/blinky_run/55-openroad-stapostpnr/config.json"
            shutil.copytree(self.RUN_FIXTURE, "runs")
            with open(path) as f:
                config = json.load(f)
            for key in [k for k in config if "DERATING" in k]:
                del config[key]
            with open(path, "w") as f:
                json.dump(config, f)
            timing = self._section_text(self._site(), "timing")
            n = timing.count("<tr><td>", timing.index("<details"))
            self.assertIn(f"<summary>Constraints the run used ({n})</summary>", timing)
            self.assertLess(n, 5)
        finally:
            os.chdir(cwd)

    def test_the_header_has_no_about_line_under_the_lede(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            page = self._site({"DESIGN_NAME": "blinky", "//DESCRIPTION": "A blinker."})
            self.assertNotIn("automated report", page)
            self.assertNotIn('class="about"', page)
            self.assertIn('<p class="lede">A blinker.</p><p class="meta">', page)
        finally:
            os.chdir(cwd)

    def test_the_chips_read_tests_then_timing_then_signoff(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            for name in ("cocotb-results.xml", "cocotb-gl-results.xml"):
                with open("build/" + name, "w") as f:
                    f.write(self.COCOTB_XML)
            page = self._run_site()
            chips = re.findall(r'<span class="chip [A-Z]+">([^<]*)</span>', page)
            self.assertEqual(chips, ["1/2 on RTL", "1/2 on gates", "Timing met", "Signoff clean"])
        finally:
            os.chdir(cwd)

    def test_a_test_name_breaks_after_an_underscore_and_copies_whole(self):
        name = entrypoint.site_page.test_name("reset_in_the_middle_restarts")
        self.assertEqual(name, "reset_<wbr>in_<wbr>the_<wbr>middle_<wbr>restarts")
        # <wbr> adds no character: the text a reader copies is the name.
        self.assertEqual(re.sub(r"<[^>]*>", "", name), "reset_in_the_middle_restarts")
        # The name is escaped before the breaks go in.
        self.assertEqual(entrypoint.site_page.test_name("a<b_c"), "a&lt;b_<wbr>c")
        css = entrypoint.site_page.CSS
        self.assertNotIn("overflow-wrap: anywhere", css.split("td code")[1][:40] if "td code" in css else "")
        self.assertNotIn("td code { overflow-wrap: anywhere; }", css)
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            os.makedirs("build")
            with open("build/cocotb-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            single = self._site({"DESIGN_NAME": "top"})
            self.assertRegex(single, r"<code>[a-z]+_<wbr>[a-z_<wbr>]*</code>")
            with open("build/cocotb-gl-results.xml", "w") as f:
                f.write(self.COCOTB_XML)
            merged = self._site({"DESIGN_NAME": "top"})
            self.assertRegex(merged, r"<tr><td><code>[a-z]+_<wbr>")
        finally:
            os.chdir(cwd)

    def test_the_footer_is_written_for_a_reader_and_links_the_generator(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self._real_run()
            env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r",
                   "GITHUB_SHA": "abcdef0"}
            with patch.dict(os.environ, env):
                page = self._site()
            footer = page[page.index("<footer"):page.index("</footer>")]
            # The source is the View source button; the footer does not repeat it.
            self.assertNotIn("Source:", footer)
            self.assertIn('Made with <a href="https://github.com/anlit75/ChipForAll">ChipForAll</a>, '
                          "an open-source chip design flow. "
                          '<a href="https://github.com/anlit75/c4o-core">c4o-core</a> generated this page.', footer)
            self.assertNotIn("<code>site</code>", footer)
            self.assertNotIn("EDA", footer)
        finally:
            os.chdir(cwd)

class TestCoverage(unittest.TestCase):
    """`coverage`: the numbers from coverage.dat, the page they appear on, and the command's exit codes."""
    FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "coverage")
    COCOTB_XML = (
        '<testsuites><testsuite name="all"><properties><property name="random_seed" value="1789965785"/></properties><testcase name="a_passes" sim_time_ns="10"/>'
        '<testcase name="b_fails" sim_time_ns="10"><failure message="x"/></testcase>'
        "</testsuite></testsuites>"
    )

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir)

    def fixture(self, name):
        return os.path.join(self.FIXTURES, name)

    def summary(self, **extra):
        types, modules, files = entrypoint.parse_coverage_dat(self.fixture("run-a.dat"))
        out = {"tests": {"total": 5, "passed": 5}, "files": files, "types": types,
               "modules": [{"name": n, "types": t} for n, t in modules.items()],
               "uncovered": [{"file": "src/top.v", "line": 6, "text": "q <= d;"}]}
        out.update(extra)
        return out

    def page(self, coverage, **kwargs):
        return entrypoint.site_page.render("top", [], None, [], {}, coverage=coverage, **kwargs)

    # --- the numbers ---------------------------------------------------------

    def test_each_kind_is_counted_from_its_own_records(self):
        types, _, _ = entrypoint.parse_coverage_dat(self.fixture("run-a.dat"))
        got = {k: (v["hit"], v["total"], v["percent"]) for k, v in types.items()}
        # Not lcov's: those take the smallest of line, branch and toggle per source line.
        self.assertEqual(got, {"line": (3, 5, 60.0), "branch": (1, 2, 50.0), "toggle": (5, 8, 62.5)})

    def test_user_coverage_is_there_only_when_the_design_has_some(self):
        a, _, _ = entrypoint.parse_coverage_dat(self.fixture("run-a.dat"))
        b, _, _ = entrypoint.parse_coverage_dat(self.fixture("run-b.dat"))
        self.assertNotIn("user", a)
        self.assertEqual((b["user"]["hit"], b["user"]["total"]), (1, 1))

    def test_each_module_is_counted_apart_and_none_of_a_kind_is_not_zero_percent(self):
        _, modules, files = entrypoint.parse_coverage_dat(self.fixture("run-a.dat"))
        self.assertEqual(list(modules), ["sub", "top"])
        self.assertEqual((modules["top"]["line"]["hit"], modules["top"]["line"]["total"]), (2, 4))
        self.assertEqual((modules["sub"]["toggle"]["hit"], modules["sub"]["toggle"]["total"]), (2, 2))
        # sub has no branch: nothing to cover is None, which a page must not show as 0%.
        self.assertEqual(modules["sub"]["branch"], {"hit": 0, "total": 0, "percent": None})
        self.assertEqual(files, ["src/sub.v", "src/top.v"])

    @unittest.skipUnless(shutil.which("verilator_coverage"), "needs verilator_coverage")
    def test_two_runs_are_merged_by_adding_their_counts(self):
        entrypoint.merge_coverage([self.fixture("run-a.dat"), self.fixture("run-b.dat")], "merged.dat")
        types, _, _ = entrypoint.parse_coverage_dat("merged.dat")
        # A point either run hit is hit. Neither alone has 4/5 lines.
        self.assertEqual({k: (v["hit"], v["total"]) for k, v in types.items()},
                         {"line": (4, 5), "branch": (2, 2), "toggle": (6, 8), "user": (1, 1)})

    def test_uncovered_lines_are_blocks_and_branches_no_test_hit_and_never_toggle_holes(self):
        os.makedirs("src")
        with open("src/top.v", "w") as f:
            f.write("".join(f"line {n}\n" for n in range(1, 15)))
        got = entrypoint.uncovered_lines(self.fixture("run-a.dat"))
        # Blocks at lines 6 and 12 and the else branch of line 6 are not hit.
        # Lines 1, 2, 4 and 5 have toggle holes only, and are not listed.
        self.assertEqual(got, [{"file": "src/top.v", "line": 6, "text": "line 6"},
                               {"file": "src/top.v", "line": 12, "text": "line 12"}])

    def test_a_block_that_spans_lines_lists_each_of_them(self):
        os.makedirs("src")
        open("src/top.v", "w").write("a\nb\nc\nd\ne\n")
        with open("blocks.dat", "w") as f:
            f.write("# SystemC::Coverage-3\n")
            f.write("C '\x01f\x02src/top.v\x01l\x021\x01page\x02v_line/top\x01o\x02block\x01S\x021,3-4\x01h\x02.top' 0\n")
            f.write("C '\x01f\x02src/top.v\x01l\x025\x01page\x02v_line/top\x01o\x02block\x01S\x025\x01h\x02.top' 1\n")
        self.assertEqual([m["line"] for m in entrypoint.uncovered_lines("blocks.dat")], [1, 3, 4])

    def test_the_text_of_an_unreadable_source_is_empty_not_an_error(self):
        got = entrypoint.uncovered_lines(self.fixture("run-a.dat"))
        self.assertEqual([m["text"] for m in got], ["", ""])

    # --- the page ------------------------------------------------------------

    def test_the_coverage_section_has_a_row_per_kind_with_hit_and_total(self):
        page = self.page(self.summary())
        section = page[page.index('<section id="coverage">'):]
        section = section[:section.index("</section>")]
        self.assertIn("<h2>Coverage</h2>", section)
        for row in ("<td>Block</td><td class=\"num\">3 / 5</td><td class=\"num\">60.0%</td>",
                    "<td>Branch</td><td class=\"num\">1 / 2</td><td class=\"num\">50.0%</td>",
                    "<td>Toggle</td><td class=\"num\">5 / 8</td><td class=\"num\">62.5%</td>"):
            self.assertIn(row, section)
        self.assertNotIn("User cover", section)
        self.assertIn("Coverage by module (2)", section)
        # The lines stay in summary.json. The page does not list them.
        self.assertNotIn("Lines no test reached", page)
        self.assertNotIn("q &lt;= d;", page)
        self.assertNotIn("coverage-uncovered", page)

    def test_the_section_says_what_it_is_not_and_what_it_leaves_out(self):
        page = self.page(self.summary())
        self.assertIn("Not measured: expression and FSM coverage.", page)
        self.assertNotIn("experimental", page)
        self.assertNotIn("sv2v", page)
        self.assertNotIn("generated <code>.v", page)
        self.assertNotIn("Line/block", page)
        self.assertNotIn("Files measured", page)
        self.assertNotIn("2-state", page)

    def test_the_page_says_which_seed_the_coverage_run_used(self):
        runs = [("cocotb, RTL", "1789965785", [("t", "PASS", 1.0)])]
        same = entrypoint.site_page.render("top", [], None, runs, {}, coverage=self.summary(seed="1789965785"))
        self.assertIn("This run used seed <code>1789965785</code>, the seed of the RTL run in Tests.", same)
        other = entrypoint.site_page.render("top", [], None, runs, {}, coverage=self.summary(seed="7"))
        self.assertIn("This run used seed <code>7</code>. It is not the seed of the RTL run in Tests.", other)
        none = entrypoint.site_page.render("top", [], None, runs, {}, coverage=self.summary())
        self.assertNotIn("This run used seed", none)

    def test_user_coverage_gets_a_row_when_there_is_some(self):
        types, modules, files = entrypoint.parse_coverage_dat(self.fixture("run-b.dat"))
        self.assertIn("<td>User cover</td>", self.page(self.summary(types=types)))

    def test_the_summary_card_has_a_line_for_each_kind_and_no_total(self):
        page = self.page(self.summary())
        summary = page[page.index('<section id="summary">'):]
        summary = summary[:summary.index("</section>")]
        card = re.search(r'<div class="kpi coverage"><div class="label">code coverage</div><div class="stats">(.*?</div></div>)</div></div>', summary, re.S)
        self.assertTrue(card, summary)
        # Three equal stats, in this order, and no number across them.
        self.assertEqual(re.findall(r'<div class="stat"><div class="value">([^<]*)</div><div class="detail">([^<]*)</div></div>',
                                    card[1]),
                         [("60.0%", "Block"), ("50.0%", "Branch"), ("62.5%", "Toggle")])
        self.assertNotIn('class="detail">block.', card[0])
        self.assertNotIn("block.", summary)
        self.assertNotIn("expression", summary)

    def test_the_summary_card_adds_a_user_line_and_a_dash_for_a_kind_with_nothing(self):
        types, _, _ = entrypoint.parse_coverage_dat(self.fixture("run-b.dat"))
        types["branch"] = {"hit": 0, "total": 0, "percent": None}
        card = entrypoint.site_page.coverage_card(self.summary(types=types))
        self.assertEqual(re.findall(r'<div class="value">([^<]*)</div><div class="detail">([^<]*)</div>', card),
                         [("40.0%", "Block"), ("&mdash;", "Branch"), ("12.5%", "Toggle"), ("100.0%", "User cover")])

    def test_a_kind_with_nothing_to_cover_shows_a_dash_and_not_zero(self):
        types = self.summary()["types"]
        types["branch"] = {"hit": 0, "total": 0, "percent": None}
        page = self.page(self.summary(types=types))
        self.assertIn('<td>Branch</td><td class="num">0 / 0</td><td class="num">&mdash;</td>', page)
        self.assertNotIn("Branch 0.0%", page)

    def test_coverage_comes_after_the_tests_and_before_timing(self):
        runs = [("cocotb, RTL", "1", [("t", "PASS", 1.0)])]
        page = entrypoint.site_page.render(
            "top", [], None, runs, {}, coverage=self.summary(),
            physical={"setup": (1.0, 0), "hold": (1.0, 0)})
        ids = re.findall(r'<section id="([a-z0-9-]*)"', page)
        self.assertLess(ids.index("tests-0"), ids.index("coverage"))
        self.assertLess(ids.index("coverage"), ids.index("timing"))

    def test_without_coverage_there_is_no_section_and_no_card(self):
        runs = [("cocotb, RTL", "1", [("t", "PASS", 1.0)])]
        page = entrypoint.site_page.render("top", [], None, runs, {}, physical={"setup": (1.0, 0)})
        self.assertNotIn("Coverage", page)
        self.assertNotIn("code coverage", page)
        self.assertNotIn('id="coverage"', page)

    def test_site_reads_the_summary_json_that_coverage_wrote(self):
        os.makedirs("build/coverage")
        with open("build/cocotb-results.xml", "w") as f:
            f.write(self.COCOTB_XML)
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_site(MagicMock(), {"DESIGN_NAME": "top"})
        self.assertNotIn("Coverage", open("build/site/index.html").read())
        with open("build/coverage/summary.json", "w") as f:
            json.dump(self.summary(), f)
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_site(MagicMock(), {"DESIGN_NAME": "top"})
        page = open("build/site/index.html").read()
        self.assertIn("<h2>Coverage</h2>", page)
        self.assertIn('<div class="stat"><div class="value">60.0%</div><div class="detail">Block</div></div>', page)

    # --- the Summary grid ----------------------------------------------------

    def cards(self, physical, coverage=True, **kwargs):
        numbers = [("die", "50.0 x 60.0 um  (3000.00 um^2)"), ("utilization", "55.0%"),
                   ("instances", "20 after synthesis, 30 after routing")]
        physical = dict(physical, constraints={"clock_period": (10.0, True)}, core=(40.0, 50.0))
        power = ("nom_tt_025C_1v80", [("Total", 0.0, 0.0, 0.0, 0.001)])
        signoff = [("DRC", 0, "Magic", "")]
        return entrypoint.site_page.summary_cards(
            numbers, physical, power, signoff, self.summary() if coverage else None)

    def test_the_cards_come_three_to_a_row_with_coverage_first_in_the_third(self):
        html = self.cards({"setup": (0.9, 0), "hold": (0.1, 0)})
        labels = re.findall(r'<div class="label">([^<]*)</div>', html)
        self.assertEqual(labels, ["die", "core utilization", "instances", "clock", "timing, worst slack",
                                  "code coverage", "total power", "signoff"])

    def test_the_timing_card_has_setup_and_hold_each_coloured_by_its_sign(self):
        html = self.cards({"setup": (0.92, 0), "hold": (-0.05, 1)})
        stats = re.findall(r'<div class="stat (good|bad)"><div class="value">([^<]*)</div>'
                           r'<div class="detail">([^<]*)</div>', html)
        self.assertEqual(stats, [("good", "+0.92 ns", "setup &middot; 0 violations"),
                                 ("bad", "-0.05 ns", "hold &middot; 1 violation")])
        self.assertIn('<div class="kpi timing">', html)

    def test_a_missing_slack_leaves_the_other_and_neither_leaves_no_card(self):
        only_hold = self.cards({"hold": (0.1, 0)})
        self.assertEqual(re.findall(r'<div class="detail">(setup|hold) &middot;', only_hold), ["hold"])
        neither = self.cards({})
        self.assertNotIn("timing, worst slack", neither)
        self.assertNotIn("kpi timing", neither)

    def test_no_coverage_data_leaves_two_cards_in_the_last_row(self):
        html = self.cards({"setup": (0.9, 0), "hold": (0.1, 0)}, coverage=False)
        labels = re.findall(r'<div class="label">([^<]*)</div>', html)
        self.assertEqual(labels[-2:], ["total power", "signoff"])
        self.assertNotIn("code coverage", labels)

    # --- the command ---------------------------------------------------------

    CONFIG = {"DESIGN_NAME": "top", "VERILOG_FILES": ["src/top.v"], "COCOTB_TESTS": ["test/test_top.py"],
              "LINTER_DISABLE_WARNINGS": ["WIDTHEXPAND"]}

    def project(self):
        for path in ("src/top.v", "test/test_top.py"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write("x")

    def fake(self, build_rc=0, writes_dat=True, sim_rc=0, calls=None):
        """subprocess.run as the image would answer it, recording each call."""
        def run(cmd, *args, **kwargs):
            if calls is not None:
                calls.append((cmd, kwargs))
            out = MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0] == "cocotb-config":
                out.stdout = "/x/makefiles" if "--makefiles" in cmd else "/x"
            elif cmd[0] == "make" and cmd[-1].endswith("Vtop"):
                out.returncode, out.stderr = build_rc, "%Error: broken design"
            elif cmd[0] == "make":
                out.returncode = sim_rc
                if writes_dat:
                    shutil.copy(self.fixture("run-a.dat"), os.path.join(kwargs["cwd"], "coverage.dat"))
                    with open(kwargs["env"]["COCOTB_RESULTS_FILE"], "w") as f:
                        f.write(self.COCOTB_XML)
            elif cmd[:2] == ["verilator_coverage", "--write"]:
                shutil.copy(cmd[3], cmd[2])
            return out
        return run

    def coverage(self, config=None, **fake):
        out = io.StringIO()
        with patch("entrypoint.subprocess.run", self.fake(**fake)), contextlib.redirect_stdout(out):
            entrypoint.cmd_coverage(MagicMock(files=None, if_configured=False), config or self.CONFIG)
        return out.getvalue()

    # --- over a test list ----------------------------------------------------

    def listed(self, text="- test: test_top\n  seeds: 3\n- test: test_top.f\n  seeds: 2\n"):
        self.project()
        os.makedirs("tb", exist_ok=True)
        open("tb/regression.yaml", "w").write(text)
        return dict(self.CONFIG, **{"//REGRESSION": "dir::tb/regression.yaml"})

    def test_a_list_is_one_build_and_a_simulation_for_each_entry_and_seed(self):
        config = self.listed()
        os.environ["RANDOM_SEED"] = "31"
        calls = []
        try:
            self.coverage(config, calls=calls)
        finally:
            del os.environ["RANDOM_SEED"]
        builds = [c for c, _ in calls if c[0] == "make" and c[-1].endswith("Vtop")]
        sims = [kw["env"] for c, kw in calls if c[0] == "make" and not c[-1].endswith("Vtop")]
        self.assertEqual(len(builds), 1)
        self.assertEqual(len(sims), 5)
        expect = entrypoint.derive_seeds(31, "test_top", 3) + entrypoint.derive_seeds(31, "test_top.f", 2)
        self.assertEqual([e["RANDOM_SEED"] for e in sims], [str(x) for x in expect])
        self.assertEqual([e.get("TESTCASE") for e in sims], [None] * 3 + ["f"] * 2)
        self.assertTrue(all(e["MODULE"] == "test_top" for e in sims))
        for n in range(1, 6):
            self.assertTrue(os.path.exists(f"build/coverage/run-{n}.dat"))

    def test_the_summary_of_a_list_has_the_base_seed_and_the_number_of_runs(self):
        config = self.listed()
        os.environ["RANDOM_SEED"] = "31"
        try:
            self.coverage(config)
        finally:
            del os.environ["RANDOM_SEED"]
        summary = json.load(open("build/coverage/summary.json"))
        self.assertEqual((summary["seed"], summary["runs"]), (31, 5))
        # Counted over every run, and the command still succeeds with failures in them.
        self.assertEqual(summary["tests"], {"total": 10, "passed": 5})

    def test_without_a_list_the_summary_has_no_runs_key(self):
        self.project()
        self.coverage()
        self.assertNotIn("runs", json.load(open("build/coverage/summary.json")))

    def test_the_merge_takes_every_runs_counts(self):
        config = self.listed()
        merged = []
        real = entrypoint.merge_coverage
        with patch("entrypoint.merge_coverage", side_effect=lambda d, m: (merged.append(list(d)), real(d, m))):
            self.coverage(config)
        self.assertEqual(merged, [[f"build/coverage/run-{n}.dat" for n in range(1, 6)]])

    def test_a_bad_list_stops_before_the_build(self):
        config = self.listed("- test: test_nope\n")
        calls = []
        with patch("entrypoint.log_error"), self.assertRaises(SystemExit) as cm:
            self.coverage(config, calls=calls)
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual([c for c, _ in calls if c[0] == "make"], [])

    def test_a_list_run_that_wrote_no_coverage_fails_the_command(self):
        config = self.listed()
        with self.assertRaises(SystemExit) as cm:
            self.coverage(config, writes_dat=False, sim_rc=1)
        self.assertEqual(cm.exception.code, 1)

    def test_the_page_says_the_coverage_is_merged_and_whether_the_base_seeds_match(self):
        merged = self.summary(seed=31, runs=5)
        same = self.page(merged, regression={"seed": 31, "runs": [{"entry": "t", "seed": 1, "verdict": "pass"}]})
        # The same base seed is named once, in Regression.
        self.assertIn("from the 5 runs of Regression, run again under Verilator and merged.", same)
        self.assertNotIn("second run of the cocotb tests", same)
        self.assertNotIn("<code>31</code>", same[same.index('<section id="coverage">'):])
        other = self.page(merged, regression={"seed": 32, "runs": [{"entry": "t", "seed": 1, "verdict": "pass"}]})
        self.assertIn("It is not the base seed of the Regression section.", other)
        alone = self.page(self.summary(seed="1789965785"))
        self.assertNotIn("Merged over", alone)

    def test_failing_tests_still_give_coverage_and_the_command_succeeds(self):
        self.project()
        os.makedirs("build")
        open("build/cocotb-results.xml", "w").write("the Icarus verdict")
        output = self.coverage()
        summary = json.load(open("build/coverage/summary.json"))
        self.assertEqual(summary["tests"], {"total": 2, "passed": 1})
        self.assertEqual(summary["seed"], "1789965785")
        self.assertEqual(summary["types"]["line"]["hit"], 3)
        self.assertIn("decided by `cocotb` on Icarus", output)
        # The Icarus verdict is another file and stays what it was.
        self.assertEqual(open("build/cocotb-results.xml").read(), "the Icarus verdict")
        self.assertTrue(os.path.exists("build/coverage/results.xml"))
        self.assertTrue(os.path.exists("build/coverage/coverage.dat"))
        self.assertFalse(os.path.exists("build/coverage/work"))

    def test_the_build_runs_the_cocotb_tests_on_verilator_with_the_waivers(self):
        self.project()
        calls = []
        self.coverage(calls=calls)
        env = next(kw["env"] for cmd, kw in calls if cmd[0] == "make")
        self.assertEqual(env["SIM"], "verilator")
        self.assertEqual(env["MODULE"], "test_top")
        self.assertEqual(env["TOPLEVEL"], "top")
        self.assertEqual(env["COMPILE_ARGS"], "--coverage -Wno-WIDTHEXPAND")
        self.assertTrue(env["VERILOG_SOURCES"].endswith("src/top.v") and os.path.isabs(env["VERILOG_SOURCES"]))
        self.assertTrue(env["COCOTB_RESULTS_FILE"].endswith("build/coverage/results.xml"))

    def test_a_design_verilator_cannot_build_fails_the_command(self):
        self.project()
        with self.assertRaises(SystemExit) as cm:
            self.coverage(build_rc=2)
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(os.path.exists("build/coverage/summary.json"))

    def test_a_run_that_wrote_no_coverage_fails_the_command(self):
        self.project()
        with self.assertRaises(SystemExit) as cm:
            self.coverage(writes_dat=False, sim_rc=1)
        self.assertEqual(cm.exception.code, 1)

    def test_no_tests_is_skipped_for_all_and_an_error_by_name(self):
        config = {"DESIGN_NAME": "top", "VERILOG_FILES": ["src/top.v"], "TEST_FILES": ["test/tb.v"]}
        self.project()
        open("test/tb.v", "w").write("x")
        with patch("entrypoint.subprocess.run", side_effect=AssertionError("must not run")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                entrypoint.cmd_coverage(MagicMock(files=None, if_configured=True), config)
            self.assertIn("coverage skipped: COCOTB_TESTS is not set", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                entrypoint.cmd_coverage(MagicMock(files=None, if_configured=False), config)

    def test_each_run_starts_from_an_empty_directory(self):
        self.project()
        os.makedirs("build/coverage")
        open("build/coverage/stale.dat", "w").write("old")
        self.coverage()
        self.assertFalse(os.path.exists("build/coverage/stale.dat"))

class TestRegress(unittest.TestCase):
    """`regress` and `cocotb TEST=`: the list, the seeds, the verdicts, the page."""
    PASS_XML = '<testsuites><testsuite><testcase name="t" sim_time_ns="1"/></testsuite></testsuites>'
    FAIL_XML = '<testsuites><testsuite><testcase name="t" sim_time_ns="1"><failure message="x"/></testcase></testsuite></testsuites>'

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)
        for d in ("rtl", "tb"):
            os.makedirs(d)
        open("rtl/top.v", "w").write("`timescale 1ns/1ps\nmodule top; endmodule")
        for name in ("test_a", "test_b"):
            open(f"tb/{name}.py", "w").write("")
        self.config = {"VERILOG_FILES": ["rtl/*.v"], "DESIGN_NAME": "top",
                       "//COCOTB_TESTS": ["dir::tb/test_*.py"],
                       "//REGRESSION": "dir::tb/regression.yaml"}
        self.env_patch = patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        for name in ("RANDOM_SEED", "TEST", "TESTCASE", "WAVES"):
            os.environ.pop(name, None)
        os.environ["SOURCE_DATE_EPOCH"] = "0"  # the page says when it was built

    def tearDown(self):
        self.env_patch.stop()
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir)

    def listing(self, text):
        with open("tb/regression.yaml", "w") as f:
            f.write(text)

    def args(self, **kw):
        a = MagicMock()
        a.files = None
        a.if_configured = False
        a.netlist = None
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def regress(self, verdicts=None, **kw):
        """
        Runs cmd_regress with the simulator replaced. `verdicts` maps (module,
        seed-index order) -> XML; by default every run passes. Returns (runs,
        run_command mock, exit code or None, printed text).
        """
        runs = []
        verdicts = verdicts or {}

        def fake_vvp(cmd, env=None):
            runs.append(env)
            xml = verdicts.get((env["MODULE"], env.get("TESTCASE")), self.PASS_XML)
            if xml is not None:
                with open(env["COCOTB_RESULTS_FILE"], "w") as f:
                    f.write(xml)
            return MagicMock(returncode=0)

        out, code = io.StringIO(), None
        with patch("entrypoint.run_command") as run_command, \
             patch("entrypoint.cocotb_config", return_value=os.path.dirname(__file__)), \
             patch("entrypoint.subprocess.run", side_effect=fake_vvp), \
             contextlib.redirect_stdout(out):
            try:
                entrypoint.cmd_regress(self.args(**kw), self.config)
            except SystemExit as e:
                code = e.code
        return runs, run_command, code, out.getvalue()

    def summary(self):
        with open("build/regress/summary.json") as f:
            return json.load(f)

    # --- the list ------------------------------------------------------------

    def test_a_module_a_function_and_the_default_of_one_seed(self):
        self.listing("- test: test_a\n  seeds: 20\n- test: test_b.f\n  seeds: 3\n")
        got = entrypoint.load_regression(self.config, ["tb/test_a.py", "tb/test_b.py"])
        self.assertEqual(got, [("test_a", "test_a", None, 20), ("test_b.f", "test_b", "f", 3)])
        self.listing("- test: test_a\n")
        got = entrypoint.load_regression(self.config, ["tb/test_a.py"])
        self.assertEqual(got, [("test_a", "test_a", None, 1)])

    def assertRejected(self, text, message):
        """The list is refused with `message` in the log, before anything is compiled."""
        self.listing(text)
        with patch("entrypoint.log_error") as log:
            runs, run_command, code, _ = self.regress()
        self.assertEqual(code, 1)
        self.assertIn(message, " ".join(str(c[0][0]) for c in log.call_args_list))
        run_command.assert_not_called()
        self.assertEqual(runs, [])

    def test_an_unknown_module_is_refused_and_the_modules_are_named(self):
        self.assertRejected("- test: test_nope\n", "no module test_nope in COCOTB_TESTS. The modules are: test_a, test_b")

    def test_a_function_of_an_unknown_module_is_refused(self):
        self.assertRejected("- test: test_nope.f\n", "no module test_nope")

    def test_an_entry_without_test_is_refused(self):
        self.assertRejected("- seeds: 5\n", "entry 1: needs a `test`")

    def test_a_trailing_dot_is_refused(self):
        self.assertRejected("- test: test_a.\n", "ends in a dot")

    def test_seeds_must_be_a_positive_whole_number(self):
        for bad in ("0", "-3", "2.5", "'4'", "true", "null"):
            with self.subTest(seeds=bad):
                self.assertRejected(f"- test: test_a\n  seeds: {bad}\n", "seeds must be a whole number of 1 or more")

    def test_an_unknown_key_is_refused(self):
        self.assertRejected("- test: test_a\n  seed: 5\n", "unknown key seed")

    def test_a_test_listed_twice_is_refused(self):
        self.assertRejected("- test: test_a\n- test: test_a\n", "listed twice")

    def test_an_empty_list_and_a_non_list_are_refused(self):
        self.assertRejected("", "at least one entry")
        self.assertRejected("test: test_a\n", "must be a list")

    def test_malformed_yaml_is_refused(self):
        self.assertRejected("- test: [unclosed\n", "Failed to parse")

    def test_a_missing_list_file_is_refused(self):
        with patch("entrypoint.log_error") as log:
            runs, run_command, code, _ = self.regress()
        self.assertEqual(code, 1)
        self.assertIn("Could not read the test list tb/regression.yaml", log.call_args[0][0])
        run_command.assert_not_called()

    def test_every_problem_is_reported_not_only_the_first(self):
        self.listing("- test: test_x\n- test: test_a\n  seeds: 0\n")
        with patch("entrypoint.log_error") as log:
            _, _, code, _ = self.regress()
        self.assertEqual(code, 1)
        self.assertEqual(log.call_count, 2)

    # --- the seeds -----------------------------------------------------------

    def test_the_same_base_seed_gives_the_same_seeds(self):
        self.assertEqual(entrypoint.derive_seeds(1234, "test_a", 20),
                         entrypoint.derive_seeds(1234, "test_a", 20))
        self.assertNotEqual(entrypoint.derive_seeds(1234, "test_a", 20),
                            entrypoint.derive_seeds(1235, "test_a", 20))

    def test_the_seeds_of_an_entry_are_distinct_and_positive(self):
        seeds = entrypoint.derive_seeds(7, "test_a", 500)
        self.assertEqual(len(set(seeds)), 500)
        self.assertTrue(all(0 < s < 2**31 for s in seeds))

    def test_an_entry_keeps_its_seeds_when_the_list_changes(self):
        # Another entry, or another order, must not change what this one runs.
        os.environ["RANDOM_SEED"] = "77"
        self.listing("- test: test_a\n  seeds: 3\n- test: test_b\n  seeds: 3\n")
        self.regress()
        both = [r["seed"] for r in self.summary()["runs"] if r["entry"] == "test_b"]
        self.listing("- test: test_b\n  seeds: 3\n")
        self.regress()
        alone = [r["seed"] for r in self.summary()["runs"]]
        self.assertEqual(both, alone)

    def test_random_seed_in_the_environment_is_the_base_seed(self):
        self.listing("- test: test_a\n  seeds: 4\n")
        os.environ["RANDOM_SEED"] = "4242"
        self.regress()
        again = self.summary()
        self.assertEqual(again["seed"], 4242)
        self.regress()
        self.assertEqual(self.summary()["runs"], again["runs"])
        self.assertEqual([r["seed"] for r in again["runs"]], entrypoint.derive_seeds(4242, "test_a", 4))

    def test_without_random_seed_the_base_seed_is_new_each_time(self):
        self.listing("- test: test_a\n")
        self.regress()
        first = self.summary()["seed"]
        self.regress()
        self.assertNotEqual(self.summary()["seed"], first)

    def test_a_base_seed_that_is_not_a_number_is_refused(self):
        self.listing("- test: test_a\n")
        os.environ["RANDOM_SEED"] = "abc"
        with patch("entrypoint.log_error") as log:
            runs, run_command, code, _ = self.regress()
        self.assertEqual(code, 1)
        self.assertIn("RANDOM_SEED must be a whole number", log.call_args[0][0])
        run_command.assert_not_called()

    # --- the runs ------------------------------------------------------------

    def test_the_rtl_is_compiled_once_and_every_seed_is_a_run(self):
        self.listing("- test: test_a\n  seeds: 3\n- test: test_b.f\n  seeds: 2\n")
        os.environ["RANDOM_SEED"] = "11"
        runs, run_command, code, _ = self.regress()
        self.assertIsNone(code)
        self.assertEqual(run_command.call_count, 1)
        self.assertEqual(run_command.call_args[0][0][0], "iverilog")
        self.assertEqual(len(runs), 5)
        a = [r for r in runs if r["MODULE"] == "test_a"]
        b = [r for r in runs if r["MODULE"] == "test_b"]
        self.assertEqual([r["RANDOM_SEED"] for r in a], [str(s) for s in entrypoint.derive_seeds(11, "test_a", 3)])
        # TESTCASE only for the entry that names a function.
        self.assertTrue(all("TESTCASE" not in r for r in a))
        self.assertTrue(all(r["TESTCASE"] == "f" for r in b))
        self.assertEqual(a[0]["COCOTB_RESULTS_FILE"], f"build/regress/test_a-{a[0]['RANDOM_SEED']}.xml")
        self.assertEqual(b[0]["COCOTB_RESULTS_FILE"], f"build/regress/test_b.f-{b[0]['RANDOM_SEED']}.xml")
        self.assertEqual(a[0]["TOPLEVEL"], "top")

    def test_a_testcase_in_the_environment_does_not_leak_into_a_module_run(self):
        self.listing("- test: test_a\n")
        os.environ["TESTCASE"] = "stale"
        runs, *_ = self.regress()
        self.assertNotIn("TESTCASE", runs[0])

    def test_the_summary_has_the_seed_the_runs_and_the_totals(self):
        self.listing("- test: test_a\n  seeds: 2\n- test: test_b\n")
        os.environ["RANDOM_SEED"] = "5"
        self.regress({("test_b", None): self.FAIL_XML})
        got = self.summary()
        self.assertEqual(got["seed"], 5)
        self.assertEqual((got["total"], got["passed"], got["failed"]), (3, 2, 1))
        self.assertEqual([(r["entry"], r["verdict"]) for r in got["runs"]],
                         [("test_a", "pass"), ("test_a", "pass"), ("test_b", "fail")])
        self.assertEqual(sorted(got["runs"][0]), ["entry", "seed", "verdict"])

    def test_a_failure_exits_1_after_the_remaining_runs_and_prints_its_replay(self):
        self.listing("- test: test_a\n  seeds: 2\n- test: test_b\n  seeds: 2\n")
        os.environ["RANDOM_SEED"] = "5"
        runs, _, code, out = self.regress({("test_a", None): self.FAIL_XML})
        self.assertEqual(code, 1)
        self.assertEqual(len(runs), 4)  # the failure stopped nothing
        seed = entrypoint.derive_seeds(5, "test_a", 2)[0]
        self.assertIn(f"make cocotb SEED={seed} TEST=test_a", out)
        self.assertIn("test_b", out)
        self.assertIn("2/4 runs passed", out)

    def test_a_run_that_wrote_no_results_is_a_failure(self):
        self.listing("- test: test_a\n")
        runs, _, code, _ = self.regress({("test_a", None): None})
        self.assertEqual(code, 1)
        self.assertEqual(self.summary()["runs"][0]["verdict"], "fail")

    def test_results_with_no_test_in_them_are_a_failure(self):
        self.listing("- test: test_a.nope\n")
        _, _, code, _ = self.regress({("test_a", "nope"): "<testsuites><testsuite/></testsuites>"})
        self.assertEqual(code, 1)

    def test_unreadable_results_are_a_failure(self):
        self.assertEqual(entrypoint.run_verdict("absent.xml"), "fail")
        open("bad.xml", "w").write("<testsuites><not closed")
        self.assertEqual(entrypoint.run_verdict("bad.xml"), "fail")

    def test_an_error_element_also_fails_a_run(self):
        open("e.xml", "w").write('<testsuites><testsuite><testcase name="x"><error message="b"/></testcase></testsuite></testsuites>')
        self.assertEqual(entrypoint.run_verdict("e.xml"), "fail")

    def test_the_table_has_a_row_per_entry(self):
        self.listing("- test: test_a\n  seeds: 2\n- test: test_b\n")
        _, _, code, out = self.regress()
        self.assertIsNone(code)
        self.assertRegex(out, r"test_a\s+ 2/2")
        self.assertRegex(out, r"test_b\s+ 1/1")

    def test_the_directory_is_cleared_so_no_old_verdict_survives(self):
        os.makedirs("build/regress")
        open("build/regress/summary.json", "w").write('{"stale": true}')
        open("build/regress/old-1.xml", "w").write("x")
        self.listing("- test: test_nope\n")  # stops after clearing
        with patch("entrypoint.log_error"):
            self.regress()
        self.assertFalse(os.path.exists("build/regress/summary.json"))
        self.assertFalse(os.path.exists("build/regress/old-1.xml"))

    # --- without the key -----------------------------------------------------

    def test_without_the_key_if_configured_skips_with_a_message(self):
        del self.config["//REGRESSION"]
        with patch("entrypoint.log_info") as info:
            runs, run_command, code, _ = self.regress(if_configured=True)
        self.assertIsNone(code)
        self.assertIn("regress skipped: REGRESSION is not set", info.call_args[0][0])
        run_command.assert_not_called()
        self.assertEqual(runs, [])

    def test_without_the_key_and_without_the_flag_it_is_an_error(self):
        del self.config["//REGRESSION"]
        with patch("entrypoint.log_error") as log:
            _, run_command, code, _ = self.regress()
        self.assertEqual(code, 1)
        self.assertIn("No test list", log.call_args[0][0])
        run_command.assert_not_called()

    def test_skipping_leaves_no_summary_from_an_earlier_run(self):
        os.makedirs("build/regress")
        open("build/regress/summary.json", "w").write("{}")
        del self.config["//REGRESSION"]
        self.regress(if_configured=True)
        self.assertFalse(os.path.exists("build/regress/summary.json"))

    def test_the_key_is_also_read_without_its_prefix(self):
        self.config["REGRESSION"] = self.config.pop("//REGRESSION")
        self.listing("- test: test_a\n")
        runs, _, code, _ = self.regress()
        self.assertIsNone(code)
        self.assertEqual(len(runs), 1)

    def test_coverage_and_regress_run_the_same_entries_with_the_same_seeds(self):
        self.listing("- test: test_a\n  seeds: 4\n- test: test_b.f\n  seeds: 2\n")
        os.environ["RANDOM_SEED"] = "2024"
        regress_runs, *_ = self.regress()
        sims = []

        def fake(cmd, *a, **kw):
            if cmd[0] == "make" and not cmd[-1].endswith("Vtop"):
                sims.append(kw["env"])
                open(os.path.join(kw["cwd"], "coverage.dat"), "w").write("")
            return MagicMock(returncode=0, stdout="/x", stderr="")

        with patch("entrypoint.subprocess.run", side_effect=fake), \
             patch("entrypoint.merge_coverage"), \
             patch("entrypoint.parse_coverage_dat", return_value=({}, {}, [])), \
             patch("entrypoint.uncovered_lines", return_value=[]), \
             contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_coverage(self.args(), self.config)
        key = lambda e: (e["MODULE"], e.get("TESTCASE"), e["RANDOM_SEED"])
        self.assertEqual([key(e) for e in sims], [key(e) for e in regress_runs])
        self.assertEqual(len(sims), 6)

    # --- cocotb TEST= --------------------------------------------------------

    def cocotb(self, test=None, **kw):
        if test is not None:
            os.environ["TEST"] = test
        with patch("entrypoint.run_command") as run_command, \
             patch("entrypoint.cocotb_config", return_value=os.path.dirname(__file__)), \
             patch("entrypoint.check_cocotb_results"), \
             contextlib.redirect_stdout(io.StringIO()):
            code = None
            try:
                entrypoint.cmd_cocotb(self.args(**kw), self.config)
            except SystemExit as e:
                code = e.code
        return run_command, code

    def test_test_restricts_cocotb_to_one_module(self):
        run_command, code = self.cocotb("test_b")
        env = run_command.call_args_list[1][1]["env"]
        self.assertEqual(env["MODULE"], "test_b")
        self.assertNotIn("TESTCASE", env)

    def test_test_with_a_function_restricts_cocotb_to_that_test(self):
        run_command, code = self.cocotb("test_b.my_test")
        env = run_command.call_args_list[1][1]["env"]
        self.assertEqual((env["MODULE"], env["TESTCASE"]), ("test_b", "my_test"))

    def test_without_test_cocotb_runs_every_module_as_before(self):
        run_command, code = self.cocotb()
        env = run_command.call_args_list[1][1]["env"]
        self.assertEqual(env["MODULE"], "test_a,test_b")
        self.assertNotIn("TESTCASE", env)
        # An empty TEST, as an unset make variable could leave, is no TEST.
        os.environ["TEST"] = ""
        run_command, code = self.cocotb()
        self.assertEqual(run_command.call_args_list[1][1]["env"]["MODULE"], "test_a,test_b")

    def test_an_unknown_test_is_refused_before_anything_is_compiled(self):
        with patch("entrypoint.log_error") as log:
            run_command, code = self.cocotb("test_nope")
        self.assertEqual(code, 1)
        self.assertIn("'test_nope' names no module of COCOTB_TESTS. The modules are: test_a, test_b", log.call_args[0][0])
        run_command.assert_not_called()

    def test_test_is_ignored_by_the_gate_level_run(self):
        os.makedirs("runs/x/final/nl")
        open("runs/x/final/nl/top.nl.v", "w").write("module top; endmodule")
        self.config["PDK"] = "sky130A"
        self.config["STD_CELL_LIBRARY"] = "sky130_fd_sc_hd"
        with patch("entrypoint.find_netlist", return_value="runs/x/final/nl/top.nl.v"), \
             patch("entrypoint.cell_models", return_value=[]):
            run_command, code = self.cocotb("test_b", netlist="")
        self.assertIsNone(code)
        self.assertEqual(run_command.call_args_list[1][1]["env"]["MODULE"], "test_a,test_b")

    # --- the results page ----------------------------------------------------

    SUMMARY = {"seed": 99, "total": 4, "passed": 2, "failed": 2, "runs": [
        {"entry": "test_a", "seed": 1, "verdict": "pass"},
        {"entry": "test_a", "seed": 2, "verdict": "pass"},
        {"entry": "test_b.f", "seed": 3, "verdict": "fail"},
        {"entry": "test_b.f", "seed": 4, "verdict": "fail"}]}

    def site(self):
        os.makedirs("build", exist_ok=True)
        with open("build/cocotb-results.xml", "w") as f:
            f.write(self.PASS_XML)
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_site(MagicMock(), {"DESIGN_NAME": "top"})
        with open("build/site/index.html") as f:
            return f.read()

    def test_the_page_has_a_regression_section_when_a_summary_exists(self):
        os.makedirs("build/regress")
        with open("build/regress/summary.json", "w") as f:
            json.dump(self.SUMMARY, f)
        page = self.site()
        self.assertIn("Regression: 2/4 runs passed", page)
        self.assertIn("2/2", page)  # test_a
        self.assertIn("0/2", page)  # test_b.f
        self.assertIn("make cocotb SEED=3 TEST=test_b.f", page)
        self.assertIn("make cocotb SEED=4 TEST=test_b.f", page)
        self.assertNotIn("make cocotb SEED=1 ", page)
        self.assertIn('href="#regression"', page)
        # After Tests, before anything physical.
        self.assertLess(page.index('id="tests-0"'), page.index('id="regression"'))

    def test_the_page_is_the_same_without_a_summary(self):
        plain = self.site()
        self.assertNotIn("egression", plain)
        os.makedirs("build/regress")
        with open("build/regress/summary.json", "w") as f:
            json.dump(self.SUMMARY, f)
        with_section = self.site()
        self.assertNotEqual(plain, with_section)
        os.remove("build/regress/summary.json")
        self.assertEqual(self.site(), plain)

    def test_the_regression_chip_is_red_when_a_run_failed(self):
        page = entrypoint.site_page.render("top", [], None, [], {"SOURCE_DATE_EPOCH": "0"}, regression=self.SUMMARY)
        self.assertIn('class="chip FAIL">2/4 regression runs', page)

    def test_a_page_with_only_a_regression_is_not_empty(self):
        os.makedirs("build/regress")
        with open("build/regress/summary.json", "w") as f:
            json.dump(self.SUMMARY, f)
        with contextlib.redirect_stdout(io.StringIO()):
            entrypoint.cmd_site(MagicMock(), {"DESIGN_NAME": "top"})
        self.assertTrue(os.path.exists("build/site/index.html"))

    def test_the_page_escapes_what_it_did_not_write(self):
        summary = dict(self.SUMMARY, runs=[{"entry": "<b>x</b>", "seed": 1, "verdict": "fail"}])
        page = entrypoint.site_page.render("top", [], None, [], {}, regression=summary)
        self.assertNotIn("<b>x</b>", page)

if __name__ == '__main__':
    unittest.main()
