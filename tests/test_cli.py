from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from herald.cli import run_init_config


class CliTests(unittest.TestCase):
    def test_run_init_config_writes_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "herald.toml"
            result = run_init_config(output, force=False)

            self.assertEqual(result, 0)
            self.assertTrue(output.exists())
            content = output.read_text(encoding="utf-8")
            self.assertIn("[app]", content)
            self.assertIn('classification_model = "qwen/qwen-2.5-7b-instruct"', content)

    def test_run_init_config_requires_force_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "herald.toml"
            output.write_text("existing\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                run_init_config(output, force=False)
