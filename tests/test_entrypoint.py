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

if __name__ == '__main__':
    unittest.main()
