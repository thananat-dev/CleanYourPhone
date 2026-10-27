"""ทดสอบ doctor ด้วยค่าดิบตัวอย่างใน tests/fixtures/ (รูปแบบเดียวกับ `cyp.py doctor --save-raw`)

อยากช่วยปรับเกณฑ์? รัน `python cyp.py doctor --save-raw my-phone.json` บนเครื่องจริง
แล้วเพิ่มไฟล์นั้นใน fixtures พร้อมเทสที่บอกว่าควรได้ผลอะไร
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cyp  # noqa: E402
import doctor  # noqa: E402
from test_cyp import FakeAdb  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


class ParserTest(unittest.TestCase):
    def test_df(self):
        d = doctor.parse_df(load("slow_redmi")["df"])
        self.assertEqual(d["avail"], 3219456)
        self.assertIsNone(doctor.parse_df("df: /data: Permission denied"))
        # รองรับ Samsung / modern Android mount point เช่น /data/user/0
        d_samsung = doctor.parse_df("Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-57 112781312 24433896 88216344 22% /data/user/0")
        self.assertIsNotNone(d_samsung)
        self.assertEqual(d_samsung["avail"], 88216344)

    def test_meminfo_status_and_procs(self):
        m = doctor.parse_dumpsys_meminfo(load("slow_redmi")["meminfo"])
        self.assertEqual(m["status"], "low")
        self.assertEqual(m["procs"][0], {"name": "com.facebook.katana", "kb": 512340})
        self.assertEqual(len(m["procs"]), 5)  # หยุดที่ section แรก

    def test_cpuinfo(self):
        c = doctor.parse_cpuinfo(load("slow_redmi")["cpuinfo"])
        self.assertEqual(c["total"], 58.0)
        self.assertEqual(c["iowait"], 6.2)
        self.assertEqual(c["procs"][0]["name"], "com.facebook.katana")

    def test_thermal(self):
        t = doctor.parse_thermal(load("slow_redmi")["thermal"])
        self.assertEqual(t["status"], 2)
        self.assertEqual(t["temps"]["skin"], 44.1)

    def test_battery_temperature_is_celsius(self):
        self.assertEqual(doctor.parse_battery(load("slow_redmi")["battery"])["temperature"], 41.2)

    def test_cores(self):
        self.assertEqual(doctor.parse_cores("0-7"), 8)
        self.assertEqual(doctor.parse_cores("0-3,4-7"), 8)
        self.assertEqual(doctor.parse_cores("0"), 1)
        self.assertIsNone(doctor.parse_cores("garbage"))


class DiagnoseTest(unittest.TestCase):
    def test_slow_phone_finds_main_causes(self):
        r = doctor.diagnose(load("slow_redmi"), bloat_enabled=["com.miui.msa.global"])
        keys = {f.key: f.level for f in r.findings}
        for key in ["storage", "ram", "cpu", "thermal"]:
            self.assertEqual(keys.get(key), "high", key)
        for key in ["swap", "iowait", "animation", "bloat"]:
            self.assertEqual(keys.get(key), "medium", key)
        self.assertEqual(keys.get("uptime"), "low")
        self.assertLess(r.score, 40)
        self.assertEqual(r.ranked()[0].level, "high")
        # ระบบ (system_server, com.miui.home) ไม่ถูกนับเป็นแอปที่ผู้ใช้ลง
        self.assertTrue(r.facts["ram_hogs"][0].startswith("Facebook"))
        self.assertNotIn("system", " ".join(r.facts["ram_hogs"]))

    def test_healthy_phone(self):
        r = doctor.diagnose(load("healthy"))
        causes = [f for f in r.findings if f.level != "tip"]
        self.assertEqual(causes, [])
        self.assertEqual(r.score, 100)
        self.assertEqual([f.key for f in r.findings], ["animation"])  # เหลือแค่เคล็ดลับ

    def test_everything_unreadable_does_not_crash(self):
        raw = {k: None for k in load("healthy")}
        r = doctor.diagnose(raw)
        self.assertEqual(set(r.unknown), {"storage", "ram", "cpu", "thermal"})
        self.assertIn("อ่านค่าไม่ได้", doctor.render(r, "test"))

    def test_hot_cpu_alone_is_not_overheating(self):
        raw = load("healthy") | {"thermal": "Thermal Status: 0\n\tTemperature{mValue=68.0, mType=0, mName=cpu0, mStatus=0}\n"}
        self.assertNotIn("thermal", {f.key for f in doctor.diagnose(raw).findings})

    def test_slow_phone_score_is_low_but_not_zero(self):
        s = doctor.diagnose(load("slow_redmi"), bloat_enabled=["x.y"]).score
        self.assertTrue(5 <= s < 40, s)

    def test_battery_saver_flagged(self):
        raw = load("healthy") | {"low_power": "1"}
        self.assertIn("low_power", {f.key for f in doctor.diagnose(raw).findings})


class DoctorCommandTest(unittest.TestCase):
    """ทดสอบทั้งเส้นทาง: FakeAdb → collect → diagnose → render"""

    def make_adb(self, fixture):
        raw = load(fixture)
        adb = FakeAdb(installed=set(raw["user_apps"]) | {"com.miui.msa.global", "com.miui.home"})
        canned = {
            "df -k /data": raw["df"], "cat /proc/meminfo": raw["proc_meminfo"],
            "dumpsys meminfo": raw["meminfo"], "dumpsys cpuinfo": raw["cpuinfo"],
            "dumpsys thermalservice": raw["thermal"], "dumpsys battery": raw["battery"],
            "settings get global low_power": raw["low_power"], "cat /proc/uptime": raw["uptime"],
            "cat /sys/devices/system/cpu/possible": raw["cores"],
        }
        third_party = set(raw["user_apps"])
        orig_shell, orig_packages = adb.shell, adb.packages

        def shell(cmd):
            if cmd in canned:
                return canned[cmd]
            if cmd.startswith("settings get global window_animation_scale"):
                return raw["anim"]
            if cmd.startswith(("pm ", "cmd ")):
                return orig_shell(cmd)
            raise cyp.AdbError("unsupported")

        adb.shell = shell
        adb.packages = lambda flags="": third_party if flags == "-3" else orig_packages(flags)
        return adb

    def test_text_output_is_read_only(self):
        adb = self.make_adb("slow_redmi")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cyp.main(["doctor"], adb=adb)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("คะแนน", out)
        self.assertIn("พื้นที่เหลือน้อยมาก", out)
        self.assertIn("แอปโฆษณา", out)  # com.miui.msa.global ยังเปิดอยู่
        self.assertEqual(adb.disabled, set())
        self.assertEqual(adb.log, [])  # ไม่มีคำสั่ง pm ที่เปลี่ยนสถานะเลย

    def test_json_output(self):
        adb = self.make_adb("healthy")
        buf = io.StringIO()
        with redirect_stdout(buf):
            cyp.main(["doctor", "--json"], adb=adb)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["device"]["family"], "xiaomi")
        self.assertIn("score", data)
        self.assertEqual(data["facts"]["cores"], 8)


if __name__ == "__main__":
    unittest.main()
