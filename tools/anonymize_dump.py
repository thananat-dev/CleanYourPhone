#!/usr/bin/env python3
"""ลบชื่อแอปส่วนตัวออกจากไฟล์ `cyp.py doctor --save-raw` ก่อนแนบใน issue หรือใส่เป็น fixture

แอปจากผู้พัฒนาสาธารณะรายใหญ่ (Google, Samsung, Facebook, LINE ฯลฯ) จะคงชื่อเดิมไว้
แอปอื่นทั้งหมด (แอปงาน แอปที่พัฒนาเอง แอปภายในบริษัท) จะถูกแทนด้วย com.example.appNN
อย่างสม่ำเสมอในทุกส่วนของไฟล์ เพื่อให้ doctor ยังจับคู่ข้อมูลได้เหมือนเดิม

ใช้: python tools/anonymize_dump.py my-phone.json -o my-phone.anon.json
"""
import argparse
import json
import re
import sys

PUBLIC_PREFIXES = (
    "android.", "com.android.", "com.google.", "com.samsung.", "com.sec.", "com.facebook.",
    "com.instagram.", "com.whatsapp", "jp.naver.line.", "com.linecorp.", "com.huawei.",
    "com.xiaomi.", "com.miui.", "com.mi.", "com.oppo.", "com.coloros.", "com.heytap.",
    "com.oplus.", "com.vivo.", "com.bbk.", "com.microsoft.", "com.linkedin.", "us.zoom.",
    "com.grabtaxi.", "com.lineman.", "com.shopee.", "com.lazada.", "com.ss.android.",
    "com.zhiliaoapp.", "com.netflix.", "com.spotify.", "com.twitter.", "org.telegram.",
)


def is_public(pkg: str) -> bool:
    return pkg.startswith(PUBLIC_PREFIXES)


def anonymize(raw: dict) -> tuple[dict, dict]:
    private = sorted({p for p in raw.get("user_apps") or [] if not is_public(p)})
    mapping = {p: f"com.example.app{i:02d}" for i, p in enumerate(private, 1)}
    if not mapping:
        return raw, mapping
    # ชื่อยาวก่อน เพื่อไม่ให้ a.b ไปแทนส่วนหนึ่งของ a.b.test
    pattern = re.compile(r"(?<![\w.])(" + "|".join(
        re.escape(p) for p in sorted(mapping, key=len, reverse=True)) + r")(?![\w])")

    def scrub(value):
        if isinstance(value, str):
            return pattern.sub(lambda m: mapping[m.group(1)], value)
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value

    out = scrub(raw)
    out["user_apps"] = sorted(out["user_apps"])
    return out, mapping


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="ไฟล์ผลลัพธ์ (ค่าเริ่มต้น: แสดงทางหน้าจอ)")
    args = ap.parse_args()
    with open(args.input, encoding="utf-8") as f:
        raw = json.load(f)
    out, mapping = anonymize(raw)
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(f"ซ่อนชื่อแอป {len(mapping)} แอป", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
