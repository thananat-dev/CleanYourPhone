#!/usr/bin/env python3
"""ตรวจรูปแบบไฟล์ใน lists/ — รันใน CI ทุก pull request"""
import json
import re
import sys
from pathlib import Path

LISTS = Path(__file__).resolve().parent.parent / "lists"
TIERS = {"safe", "recommended", "advanced"}
PKG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$")
REQUIRED = {"id", "name", "tier", "note"}


def main() -> int:
    errors: list[str] = []
    deny = set(json.loads((LISTS / "_never_touch.json").read_text(encoding="utf-8"))["packages"])
    seen: dict[str, str] = {}

    for path in sorted(LISTS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: JSON ไม่ถูกต้อง ({e})")
            continue
        if path.name == "_never_touch.json":
            continue
        for i, e in enumerate(data.get("packages", [])):
            where = f"{path.name}[{i}]"
            missing = REQUIRED - e.keys()
            if missing:
                errors.append(f"{where}: ขาดฟิลด์ {sorted(missing)}")
                continue
            if not PKG_RE.match(e["id"]):
                errors.append(f"{where}: ชื่อแพ็กเกจไม่ถูกต้อง '{e['id']}'")
            if e["tier"] not in TIERS:
                errors.append(f"{where}: tier '{e['tier']}' ต้องเป็นหนึ่งใน {sorted(TIERS)}")
            if e["id"] in deny:
                errors.append(f"{where}: '{e['id']}' อยู่ใน _never_touch.json")
            if e["id"] in seen:
                errors.append(f"{where}: '{e['id']}' ซ้ำกับ {seen[e['id']]}")
            seen[e["id"]] = path.name
            if not e["note"].strip():
                errors.append(f"{where}: note ว่าง — อธิบายว่าปิดแล้วเกิดอะไรขึ้น")

    for err in errors:
        print("✗", err)
    if not errors:
        print(f"✓ ผ่าน — {len(seen)} แพ็กเกจ")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
