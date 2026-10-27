#!/usr/bin/env python3
"""CleanYourPhone — ปิดโฆษณา แอปพ่วง และการส่งข้อมูลบนมือถือ Android ผ่าน ADB

ไม่ต้อง root ไม่ลบแอปจริง สำรองสถานะก่อนทุกครั้ง และกู้คืนได้ในคำสั่งเดียว
Debloat Android phones over ADB. No root, reversible, backup first.

ต้องการแค่ Python 3.9+ (stdlib) และ adb (Android platform-tools)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import doctor

__version__ = "0.2.0"

ROOT = Path(__file__).resolve().parent
LISTS_DIR = ROOT / "lists"
BACKUP_DIR = ROOT / "backups"

TIERS = ["safe", "recommended", "advanced"]

# ยี่ห้อที่ใช้ ROM ร่วมกันจะใช้รายการเดียวกัน
BRAND_FAMILY = {
    "xiaomi": "xiaomi", "redmi": "xiaomi", "poco": "xiaomi",
    "oppo": "oplus", "realme": "oplus", "oneplus": "oplus",
    "vivo": "vivo", "iqoo": "vivo",
    "samsung": "samsung",
}

ROM_PROPS = {
    "MIUI": "ro.miui.ui.version.name",
    "HyperOS": "ro.mi.os.version.name",
    "ColorOS": "ro.build.version.oplusrom",
    "FuntouchOS/OriginOS": "ro.vivo.os.version",
    "One UI": "ro.build.version.oneui",
}


class AdbError(RuntimeError):
    pass


# --------------------------------------------------------------------------- adb

class Adb:
    """ตัวห่อคำสั่ง adb แยกออกมาเพื่อให้ทดสอบด้วย fake ได้"""

    def __init__(self, serial: str | None = None, exe: str = "adb"):
        self.serial = serial
        self.exe = exe

    def _base(self) -> list[str]:
        cmd = [self.exe]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def raw(self, *args: str) -> str:
        try:
            out = subprocess.run(self._base() + list(args), capture_output=True,
                                 text=True, timeout=60)
        except FileNotFoundError:
            raise AdbError("ไม่พบ adb — ติดตั้ง Android platform-tools แล้วเพิ่มใน PATH ก่อน")
        except subprocess.TimeoutExpired:
            raise AdbError("adb ไม่ตอบสนองภายใน 60 วินาที")
        text = (out.stdout or "") + (out.stderr or "")
        if out.returncode != 0:
            raise AdbError(text.strip() or f"adb exited {out.returncode}")
        return text

    def shell(self, cmd: str) -> str:
        return self.raw("shell", cmd)

    def getprop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    def packages(self, flags: str = "") -> set[str]:
        out = self.shell(f"pm list packages {flags}".strip())
        return {line.split(":", 1)[1].strip() for line in out.splitlines()
                if line.startswith("package:")}


# ------------------------------------------------------------------------- lists

def load_list(name: str) -> dict:
    path = LISTS_DIR / f"{name}.json"
    if not path.exists():
        return {"packages": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_denylist() -> set[str]:
    return set(load_list("_never_touch").get("packages", []))


def brand_family(brand: str) -> str | None:
    return BRAND_FAMILY.get(brand.strip().lower())


def tier_rank(tier: str) -> int:
    return TIERS.index(tier)


def candidates(family: str | None, max_tier: str) -> list[dict]:
    """รวมรายการ common + ยี่ห้อ กรองตาม tier (สะสม: recommended รวม safe ด้วย)"""
    entries: list[dict] = []
    seen: set[str] = set()
    for name in ["common"] + ([family] if family else []):
        for e in load_list(name).get("packages", []):
            if e["id"] in seen:
                continue
            if tier_rank(e["tier"]) <= tier_rank(max_tier):
                entries.append({**e, "list": name})
                seen.add(e["id"])
    deny = load_denylist()
    return [e for e in entries if e["id"] not in deny]


# ---------------------------------------------------------------------- commands

def format_rom_version(rom: str, val: str) -> str:
    """One UI เก็บเวอร์ชันเป็นตัวเลขแบบ MMmmpp เช่น 70000 → 7.0, 60100 → 6.1"""
    if rom == "One UI" and val.isdigit() and len(val) >= 5:
        n = int(val)
        return f"{n // 10000}.{(n // 100) % 100}"
    return val


def device_info(adb: Adb) -> dict:
    info = {
        "brand": adb.getprop("ro.product.brand"),
        "manufacturer": adb.getprop("ro.product.manufacturer"),
        "model": adb.getprop("ro.product.model"),
        "device": adb.getprop("ro.product.device"),
        "android": adb.getprop("ro.build.version.release"),
        "sdk": adb.getprop("ro.build.version.sdk"),
        "build": adb.getprop("ro.build.display.id"),
    }
    for rom, prop in ROM_PROPS.items():
        val = adb.getprop(prop)
        if val:
            info["rom"] = f"{rom} {format_rom_version(rom, val)}"
            break
    info["family"] = brand_family(info["brand"]) or brand_family(info["manufacturer"])
    return info


def snapshot(adb: Adb) -> dict:
    installed = adb.packages()
    return {
        "installed": sorted(installed),
        "disabled": sorted(adb.packages("-d")),
        # -u รวมแพ็กเกจที่ถูก uninstall สำหรับ user 0 แต่ยังอยู่ในระบบ
        "removed_for_user": sorted(adb.packages("-u") - installed),
    }


def cmd_info(adb: Adb, args) -> int:
    info = device_info(adb)
    for k, v in info.items():
        print(f"{k:>13}: {v}")
    if not info["family"]:
        print("\n⚠ ยังไม่มีรายการเฉพาะยี่ห้อนี้ จะใช้เฉพาะ lists/common.json "
              "— ช่วยส่งรายการผ่าน issue ได้นะครับ")
    return 0


def cmd_backup(adb: Adb, args) -> Path:
    info = device_info(adb)
    now = _dt.datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    safe_model = "".join(c if c.isalnum() else "-" for c in info["model"]) or "device"
    out = BACKUP_DIR / f"{safe_model}-{stamp}"
    n = 1
    while out.exists():
        n += 1
        out = BACKUP_DIR / f"{safe_model}-{stamp}-{n}"
    out.mkdir(parents=True)
    data = {"tool_version": __version__, "created": now.isoformat(timespec="microseconds"), "device": info,
            "state": snapshot(adb), "actions": []}
    (out / "backup.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    print(f"✓ สำรองสถานะไว้ที่ {out}")
    return out


def cmd_scan(adb: Adb, args) -> int:
    info = device_info(adb)
    family = args.brand or info["family"]
    state = snapshot(adb)
    installed, disabled = set(state["installed"]), set(state["disabled"])
    rows = [e for e in candidates(family, "advanced") if e["id"] in installed]
    print(f"{info['brand']} {info['model']} · Android {info['android']} · "
          f"{info.get('rom', '?')} · รายการ: common{', ' + family if family else ''}\n")
    if not rows:
        print("ไม่พบแพ็กเกจในรายการบนเครื่องนี้")
        return 0
    for tier in TIERS:
        group = [e for e in rows if e["tier"] == tier]
        if not group:
            continue
        print(f"[{tier}]")
        for e in group:
            mark = "ปิดแล้ว" if e["id"] in disabled else "เปิดอยู่"
            print(f"  {mark:<8} {e['id']:<48} {e['name']} — {e['note']}")
        print()
    return 0


def find_backup(original: bool = False) -> Path | None:
    """ล่าสุด หรือเก่าสุด (= สภาพโรงงานก่อนใช้เครื่องมือครั้งแรก)"""
    if not BACKUP_DIR.exists():
        return None
    dirs = sorted((p for p in BACKUP_DIR.iterdir() if (p / "backup.json").exists()),
                  key=lambda p: json.loads((p / "backup.json").read_text(encoding="utf-8"))["created"])
    if not dirs:
        return None
    return dirs[0] if original else dirs[-1]


def _disable(adb: Adb, pkg: str, allow_uninstall: bool) -> str:
    """คืนค่าวิธีที่ใช้: 'disabled' | 'removed' ; โยน AdbError ถ้าทำไม่ได้"""
    out = adb.shell(f"pm disable-user --user 0 {pkg}")
    if "disabled-user" in out or "new state: disabled" in out:
        return "disabled"
    if not allow_uninstall:
        raise AdbError(out.strip() or "disable-user failed")
    # บาง ROM (เช่น MIUI) ไม่ยอมให้ disable แอประบบ — ถอดเฉพาะ user 0 แทน
    # ไฟล์ APK ยังอยู่ในเครื่อง กู้คืนได้ด้วย install-existing
    out = adb.shell(f"pm uninstall -k --user 0 {pkg}")
    if "Success" in out:
        return "removed"
    raise AdbError(out.strip())


def cmd_apply(adb: Adb, args) -> int:
    info = device_info(adb)
    family = args.brand or info["family"]
    state = snapshot(adb)
    installed, disabled = set(state["installed"]), set(state["disabled"])
    todo = [e for e in candidates(family, args.tier)
            if e["id"] in installed and e["id"] not in disabled]
    if args.only:
        wanted = set(args.only.split(","))
        todo = [e for e in todo if e["id"] in wanted]
    if not todo:
        print("ไม่มีอะไรต้องทำ — แพ็กเกจในระดับนี้ถูกปิดไปหมดแล้วหรือไม่มีในเครื่อง")
        return 0

    print(f"จะปิด {len(todo)} แพ็กเกจ (tier ≤ {args.tier}):")
    for e in todo:
        print(f"  [{e['tier']}] {e['id']} — {e['name']}")
    if args.dry_run:
        print("\n(dry-run: ยังไม่ได้เปลี่ยนอะไร)")
        return 0
    if not args.yes:
        if input("\nยืนยัน? พิมพ์ y เพื่อดำเนินการ: ").strip().lower() != "y":
            print("ยกเลิก")
            return 1

    bdir = cmd_backup(adb, args)
    bfile = bdir / "backup.json"
    data = json.loads(bfile.read_text(encoding="utf-8"))
    failed = 0
    for e in todo:
        try:
            how = _disable(adb, e["id"], args.allow_uninstall)
            data["actions"].append({"id": e["id"], "action": how})
            print(f"  ✓ {how:<8} {e['id']}")
        except AdbError as err:
            failed += 1
            print(f"  ✗ ข้าม     {e['id']} ({err})")
        bfile.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nเสร็จ: สำเร็จ {len(todo) - failed} / ไม่สำเร็จ {failed}")
    print(f"ถ้ามีอะไรผิดปกติ: python cyp.py restore {bdir}")
    return 0 if failed == 0 else 2


def cmd_restore(adb: Adb, args) -> int:
    bdir = Path(args.backup) if args.backup else find_backup(args.original)
    if not bdir or not (bdir / "backup.json").exists():
        print("ไม่พบไฟล์สำรอง — ระบุโฟลเดอร์ใน backups/ ")
        return 1
    data = json.loads((bdir / "backup.json").read_text(encoding="utf-8"))
    orig = data["state"]
    now = snapshot(adb)

    # คืนสภาพทุกอย่างให้ตรงกับตอนสำรอง ไม่ใช่แค่สิ่งที่เครื่องมือนี้ทำ
    to_enable = set(now["disabled"]) - set(orig["disabled"])
    to_reinstall = set(orig["installed"]) - set(now["installed"])
    print(f"กู้คืนจาก {bdir}: เปิด {len(to_enable)} · ติดตั้งกลับ {len(to_reinstall)}")
    for pkg in sorted(to_enable):
        try:
            adb.shell(f"pm enable --user 0 {pkg}")
            print(f"  ✓ enable   {pkg}")
        except AdbError as err:
            print(f"  ✗ {pkg} ({err})")
    for pkg in sorted(to_reinstall):
        try:
            adb.shell(f"cmd package install-existing --user 0 {pkg}")
            print(f"  ✓ reinstall {pkg}")
        except AdbError as err:
            print(f"  ✗ {pkg} ({err})")
    print("\nรีสตาร์ตเครื่องหนึ่งครั้งเพื่อให้ทุกอย่างกลับมาครบ")
    return 0


def cmd_doctor(adb: Adb, args) -> int:
    """ตรวจว่าเครื่องช้าเพราะอะไร — อ่านอย่างเดียว ไม่เปลี่ยนอะไร"""
    info = device_info(adb)
    print("กำลังตรวจเครื่อง (ใช้เวลาประมาณ 10–20 วินาที)...", file=sys.stderr)
    raw = doctor.collect(adb)
    state = snapshot(adb)
    installed, disabled = set(state["installed"]), set(state["disabled"])
    bloat = [e["id"] for e in candidates(info["family"], "recommended")
             if e["id"] in installed and e["id"] not in disabled]
    report = doctor.diagnose(raw, bloat_enabled=bloat)
    if args.json:
        print(json.dumps({"device": info, **report.to_dict()}, indent=2, ensure_ascii=False))
    else:
        title = f"{info['brand']} {info['model']} · Android {info['android']}"
        print(doctor.render(report, title))
    if args.save_raw:
        Path(args.save_raw).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_raw).write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nบันทึกค่าดิบไว้ที่ {args.save_raw}", file=sys.stderr)
    return 0


def cmd_connect(adb: Adb, args) -> int:
    if args.pair_code:
        print(adb.raw("pair", args.address, args.pair_code).strip())
        return 0
    print(adb.raw("connect", args.address).strip())
    return 0


# -------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cyp", description="CleanYourPhone — Android debloat via ADB")
    p.add_argument("-s", "--serial", help="serial ของเครื่อง (เมื่อต่อหลายเครื่อง)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("connect", help="เชื่อมผ่าน Wi-Fi (Wireless debugging)")
    c.add_argument("address", help="IP:PORT ที่เห็นในหน้า Wireless debugging")
    c.add_argument("--pair-code", help="รหัสจับคู่ 6 หลัก (ใช้กับพอร์ตสำหรับ pair)")

    sub.add_parser("info", help="ดูข้อมูลเครื่องและ ROM")

    d = sub.add_parser("doctor", help="ตรวจว่าเครื่องช้าเพราะอะไร (อ่านอย่างเดียว)")
    d.add_argument("--json", action="store_true", help="แสดงผลเป็น JSON สำหรับ AI agent")
    d.add_argument("--save-raw", metavar="FILE",
                   help="บันทึกค่าดิบจากเครื่อง (ใช้แนบใน issue เพื่อช่วยปรับเกณฑ์)")
    sub.add_parser("backup", help="สำรองสถานะแพ็กเกจ")

    s = sub.add_parser("scan", help="ดูว่าแพ็กเกจไหนในรายการอยู่ในเครื่อง")
    s.add_argument("--brand", choices=sorted(set(BRAND_FAMILY.values())))

    a = sub.add_parser("apply", help="ปิดแพ็กเกจตามระดับความเสี่ยง")
    a.add_argument("--tier", choices=TIERS, default="safe")
    a.add_argument("--brand", choices=sorted(set(BRAND_FAMILY.values())))
    a.add_argument("--only", help="จำกัดเฉพาะแพ็กเกจที่ระบุ คั่นด้วยจุลภาค")
    a.add_argument("--dry-run", action="store_true", help="แสดงรายการเฉย ๆ ไม่เปลี่ยนอะไร")
    a.add_argument("--yes", "-y", action="store_true", help="ไม่ต้องถามยืนยัน")
    a.add_argument("--allow-uninstall", action="store_true",
                   help="ถ้า disable ไม่ได้ ให้ถอดเฉพาะ user 0 (กู้คืนได้)")

    r = sub.add_parser("restore", help="คืนสถานะจากไฟล์สำรอง (ค่าเริ่มต้น: ล่าสุด)")
    r.add_argument("backup", nargs="?")
    r.add_argument("--original", action="store_true",
                   help="ใช้ไฟล์สำรองแรกสุด เพื่อคืนเครื่องเป็นสภาพก่อนใช้เครื่องมือ")
    return p


def main(argv: list[str] | None = None, adb: Adb | None = None) -> int:
    args = build_parser().parse_args(argv)
    adb = adb or Adb(args.serial)
    handlers = {"connect": cmd_connect, "info": cmd_info, "backup": cmd_backup,
                "scan": cmd_scan, "apply": cmd_apply, "restore": cmd_restore,
                "doctor": cmd_doctor}
    try:
        result = handlers[args.cmd](adb, args)
        return result if isinstance(result, int) else 0
    except AdbError as err:
        print(f"ผิดพลาด: {err}", file=sys.stderr)
        if "no devices" in str(err) or "unauthorized" in str(err):
            print("ตรวจว่าเปิด USB/Wireless debugging และกดอนุญาตบนมือถือแล้ว",
                  file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
