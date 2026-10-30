"""A deployment export must work without the desktop application's assets."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from server.export import export


class ServerExportTest(unittest.TestCase):
    def test_independent_archive_and_no_accidental_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive_path = export(folder / "server.zip")
            with self.assertRaises(FileExistsError):
                export(archive_path)
            with ZipFile(archive_path) as archive:
                self.assertFalse(any(name.startswith(("Class/", "Resource/", ".venv/")) for name in archive.namelist()))
                self.assertNotIn("networking/client.py", archive.namelist())
                archive.extractall(folder / "standalone")
            result = subprocess.run(
                [sys.executable, "-B", "-c", "import sys; sys.modules['pygame'] = None; import server.__main__, networking.server; print('standalone import OK')"],
                cwd=folder / "standalone", capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("standalone import OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
