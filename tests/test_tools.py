import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from anonymize_dump import anonymize  # noqa: E402


class AnonymizeTest(unittest.TestCase):
    def test_private_apps_replaced_everywhere_public_kept(self):
        raw = {
            "user_apps": ["com.acme.internal", "com.acme.internal.test", "jp.naver.line.android"],
            "meminfo": "Total PSS by process:\n  9K: com.acme.internal:remote (pid 1)\n"
                       "  8K: com.acme.internal.test (pid 2)\n  7K: jp.naver.line.android (pid 3)\n",
        }
        out, mapping = anonymize(raw)
        self.assertNotIn("acme", str(out))
        self.assertIn("jp.naver.line.android", out["meminfo"])
        a, b = mapping["com.acme.internal"], mapping["com.acme.internal.test"]
        self.assertIn(f"{a}:remote", out["meminfo"])  # suffix ของโปรเซสยังอยู่ doctor จึงรวมได้
        self.assertIn(f"{b} (pid 2)", out["meminfo"])
        self.assertEqual(sorted(out["user_apps"]), sorted([a, b, "jp.naver.line.android"]))


if __name__ == "__main__":
    unittest.main()
