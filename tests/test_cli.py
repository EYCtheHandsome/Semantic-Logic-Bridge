"""Unit tests for the folnlp command line interface."""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from folnlp import cli  # noqa: E402


class WebCommandTests(unittest.TestCase):
    def test_missing_flask_reports_clear_message(self) -> None:
        error = ModuleNotFoundError("No module named 'flask'", name="flask")
        with mock.patch("folnlp.cli._import_web_run", side_effect=error):
            buffer = io.StringIO()
            with redirect_stderr(buffer):
                exit_code = cli.main(["web"])
        self.assertEqual(exit_code, 1)
        self.assertIn("Flask is required for the web interface", buffer.getvalue())

    def test_web_command_invokes_runner(self) -> None:
        fake_run = mock.Mock()
        with mock.patch("folnlp.cli._import_web_run", return_value=fake_run):
            exit_code = cli.main(["web", "--host", "0.0.0.0", "--port", "9999"])
        self.assertEqual(exit_code, 0)
        fake_run.assert_called_once_with(host="0.0.0.0", port=9999)


if __name__ == "__main__":
    unittest.main()
