"""ทดสอบโดยใช้ FakeAdb จำลองมือถือ ไม่ต้องต่อเครื่องจริง

รัน: python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cyp  # noqa: E402


class FakeAdb(cyp.Adb):
    def __init__(self, brand="Redmi", installed=(), block_disable=()):
        super().__init__()
        self.props = {"ro.product.brand": brand, "ro.product.manufacturer": brand,
                      "ro.product.model": "Note 13", "ro.build.version.release": "14"}
        self.system = set(installed)        # APK ที่อยู่ในเครื่อง
        self.removed: set[str] = set()      # ถูกถอดสำหรับ user 0
        self.disabled: set[str] = set()
        self.block_disable = set(block_disable)
        self.log: list[str] = []

    def raw(self, *args):
        raise AssertionError("ไม่ควรเรียก adb จริงในเทส")

    def getprop(self, name):
        return self.props.get(name, "")

    def packages(self, flags=""):
        if flags == "-d":
            return set(self.disabled)
        if flags == "-u":
            return set(self.system)
        return self.system - self.removed

    def shell(self, cmd):
        self.log.append(cmd)
        pkg = cmd.split()[-1]
        if cmd.startswith("pm disable-user"):
            if pkg in self.block_disable:
                return "java.lang.SecurityException: Cannot disable system packages"
            self.disabled.add(pkg)
            return f"Package {pkg} new state: disabled-user"
        if cmd.startswith("pm uninstall"):
            self.removed.add(pkg)
            return "Success"
        if cmd.startswith("pm enable"):
            self.disabled.discard(pkg)
            return f"Package {pkg} new state: enabled"
        if cmd.startswith("cmd package install-existing"):
            self.removed.discard(pkg)
            return f"Package {pkg} installed for user: 0"
        return ""


class CypTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cyp.BACKUP_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_brand_family(self):
        self.assertEqual(cyp.brand_family("POCO"), "xiaomi")
        self.assertEqual(cyp.brand_family("realme"), "oplus")
        self.assertIsNone(cyp.brand_family("nokia"))

    def test_tiers_are_cumulative(self):
        safe = {e["id"] for e in cyp.candidates("xiaomi", "safe")}
        rec = {e["id"] for e in cyp.candidates("xiaomi", "recommended")}
        self.assertTrue(safe < rec)
        self.assertIn("com.miui.msa.global", rec)
        self.assertNotIn("com.miui.msa.global", safe)

    def test_denylist_never_returned(self):
        deny = cyp.load_denylist()
        for fam in ["xiaomi", "oplus", "vivo", "samsung", None]:
            ids = {e["id"] for e in cyp.candidates(fam, "advanced")}
            self.assertFalse(ids & deny)

    def test_dry_run_changes_nothing(self):
        adb = FakeAdb(installed={"com.miui.msa.global", "com.miui.home"})
        cyp.main(["apply", "--tier", "recommended", "--dry-run"], adb=adb)
        self.assertEqual(adb.disabled, set())
        self.assertFalse(any(cyp.BACKUP_DIR.iterdir()))

    def test_apply_then_restore_roundtrip(self):
        pkgs = {"com.miui.msa.global", "com.miui.analytics", "com.miui.home"}
        adb = FakeAdb(installed=pkgs, block_disable={"com.miui.analytics"})
        rc = cyp.main(["apply", "--tier", "recommended", "-y", "--allow-uninstall"], adb=adb)
        self.assertEqual(rc, 0)
        self.assertIn("com.miui.msa.global", adb.disabled)
        self.assertIn("com.miui.analytics", adb.removed)
        self.assertNotIn("com.miui.home", adb.disabled)  # อยู่ใน never-touch

        backup = json.loads(next(cyp.BACKUP_DIR.glob("*/backup.json")).read_text())
        self.assertEqual(len(backup["actions"]), 2)

        cyp.main(["restore"], adb=adb)
        self.assertEqual(adb.disabled, set())
        self.assertEqual(adb.removed, set())

    def test_restore_original_undoes_every_run(self):
        adb = FakeAdb(installed={"com.xiaomi.mipicks", "com.miui.msa.global"})
        cyp.main(["apply", "--tier", "safe", "-y"], adb=adb)
        cyp.main(["apply", "--tier", "recommended", "-y"], adb=adb)
        self.assertEqual(len(adb.disabled), 2)
        cyp.main(["restore", "--original"], adb=adb)
        self.assertEqual(adb.disabled, set())

    def test_blocked_disable_without_flag_is_skipped(self):
        adb = FakeAdb(installed={"com.miui.analytics"}, block_disable={"com.miui.analytics"})
        rc = cyp.main(["apply", "--tier", "recommended", "-y"], adb=adb)
        self.assertEqual(rc, 2)
        self.assertEqual(adb.removed, set())


if __name__ == "__main__":
    unittest.main()
