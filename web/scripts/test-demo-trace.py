import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("sanitizer", Path(__file__).with_name("sanitize-demo-trace.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TracePrivacy(unittest.TestCase):
    def test_network_and_action_values_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "raw.zip", Path(tmp) / "safe.zip"
            records = [
                {"type": "context-options", "version": 8, "options": {"httpCredentials": "SECRET_MARKER"}},
                {"type": "before", "callId": "a", "params": {"value": "SECRET_MARKER"}, "stack": ["SECRET_MARKER"]},
                {"type": "after", "callId": "a", "result": "SECRET_MARKER", "error": {"message": "SECRET_MARKER"}},
                {"type": "console", "message": "SECRET_MARKER"},
                {"type": "screencast-frame", "sha1": "frame.jpeg", "timestamp": 1},
            ]
            with zipfile.ZipFile(src, "w") as z:
                z.writestr("trace.trace", "\n".join(json.dumps(r) for r in records))
                z.writestr("trace.network", "Cookie: SECRET_MARKER")
                z.writestr("resources/body", "SECRET_MARKER")
                z.writestr("resources/frame.jpeg", b"synthetic-image")
            module.sanitize(src, dst)
            with zipfile.ZipFile(dst) as z:
                self.assertEqual(z.read("trace.network"), b"")
                self.assertNotIn("resources/body", z.namelist())
                self.assertNotIn(b"SECRET_MARKER", z.read("trace.trace"))
                self.assertIn("resources/frame.jpeg", z.namelist())


if __name__ == "__main__":
    unittest.main()
