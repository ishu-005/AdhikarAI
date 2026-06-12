import sys
import unittest
import ast
from pathlib import Path
from tempfile import TemporaryDirectory

import run


class RunLauncherTests(unittest.TestCase):
    def test_project_venv_python_is_preferred_when_present(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = "Scripts" if sys.platform.startswith("win") else "bin"
            exe = "python.exe" if sys.platform.startswith("win") else "python"
            expected = root / ".venv" / scripts / exe
            expected.parent.mkdir(parents=True)
            expected.write_text("", encoding="utf-8")

            self.assertEqual(run._project_venv_python(root), expected)

    def test_should_reexec_when_current_python_is_not_project_venv(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = "Scripts" if sys.platform.startswith("win") else "bin"
            exe = "python.exe" if sys.platform.startswith("win") else "python"
            venv_python = root / ".venv" / scripts / exe
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")

            self.assertTrue(run._should_reexec_into_venv(root, Path("C:/Other/python.exe")))
            self.assertFalse(run._should_reexec_into_venv(root, venv_python))

    def test_launcher_has_no_nonstdlib_top_level_imports_before_venv_switch(self):
        tree = ast.parse(Path("run.py").read_text(encoding="utf-8"))
        imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".", 1)[0])

        self.assertNotIn("requests", imports)
        self.assertNotIn("dotenv", imports)

    def test_launcher_source_is_ascii_safe_for_windows_console(self):
        source = Path("run.py").read_text(encoding="utf-8")
        self.assertTrue(source.isascii())


if __name__ == "__main__":
    unittest.main()
