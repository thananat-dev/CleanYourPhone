# CleanYourPhone 📱🧹

**เอามือถือของคุณคืนมาจากโฆษณา** — ปิดโฆษณาในระบบ แอปพ่วง และการส่งข้อมูลกลับผู้ผลิต
บนมือถือ Android ที่ขายในไทย ผ่าน ADB **ไม่ต้อง root · ไม่ลบแอปจริง · สำรองก่อนทุกครั้ง · กู้คืนได้ในคำสั่งเดียว**

[English](#english) · [วิธีใช้](#วิธีใช้) · [ยี่ห้อที่รองรับ](#ยี่ห้อที่รองรับ) · [ช่วยพัฒนา](CONTRIBUTING.md)

---

## ทำไมต้องมี

มือถือ Xiaomi, OPPO, realme, vivo และ Samsung หลายรุ่นมีโฆษณาโผล่ในล็อกสกรีน ในตัวจัดการไฟล์
ตอนติดตั้งแอป และในแจ้งเตือน พร้อมแอปพ่วงที่ลบไม่ได้และบริการพื้นหลังที่ส่งข้อมูลการใช้งานกลับผู้ผลิต
คนส่วนใหญ่ไม่รู้ว่าปิดได้ และคนที่รู้ก็ต้องนั่งพิมพ์คำสั่งทีละบรรทัด

CleanYourPhone รวม **รายการแพ็กเกจแยกตามยี่ห้อ** ที่ชุมชนช่วยกันตรวจ และให้ **AI agent** พาคุณทำทีละขั้น

## วิธีใช้

### แบบง่าย: ให้ AI ทำให้ (~15 นาที)

1. ติดตั้ง [Claude Code](https://claude.com/claude-code), Codex CLI หรือ Gemini CLI
2. ดาวน์โหลดโปรเจกต์นี้
   ```bash
   git clone https://github.com/thananat-dev/CleanYourPhone.git
   cd CleanYourPhone
   ```
3. พิมพ์กับ AI: **`อ่าน PROMPT.md แล้วช่วยทำความสะอาดมือถือของฉัน`**

AI จะพาเปิดโหมดนักพัฒนา เชื่อมต่อมือถือ สแกน แล้วถามคุณก่อนปิดทุกครั้ง

### แบบทำเอง

ต้องมี Python 3.9+ และ [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`)

```bash
python cyp.py info                                  # ดูข้อมูลเครื่อง
python cyp.py scan                                  # ดูว่าเจออะไรในเครื่อง
python cyp.py apply --tier safe --dry-run           # ดูก่อนว่าจะปิดอะไร
python cyp.py apply --tier safe                     # ปิดจริง (สำรองให้อัตโนมัติ)
python cyp.py apply --tier recommended              # ระดับถัดไป
python cyp.py restore                               # ย้อนการ apply ครั้งล่าสุด
python cyp.py restore --original                    # คืนเครื่องเป็นสภาพก่อนใช้เครื่องมือ
```

เชื่อมผ่าน Wi-Fi (Android 11+): เปิด *Wireless debugging* แล้ว
```bash
python cyp.py connect 192.168.1.20:37155 --pair-code 123456   # พอร์ตจับคู่
python cyp.py connect 192.168.1.20:41427                      # พอร์ตหลัก
```

## ระดับความเสี่ยง

| ระดับ | ความหมาย | ตัวอย่าง |
|---|---|---|
| `safe` | แอปพ่วงที่ไม่มีใครใช้ ปิดแล้วไม่กระทบอะไร | Facebook App Manager, GetApps, Samsung Tips |
| `recommended` | ตัวต้นเหตุโฆษณาและการเก็บข้อมูล | MIUI MSA, OPPO Ads, Samsung Free |
| `advanced` | ปิดได้ แต่มีผลข้างเคียงที่ต้องรู้ก่อน | ร้านแอปของผู้ผลิต, เบราว์เซอร์ระบบ, Bixby |

ระดับสูงรวมระดับต่ำกว่าเสมอ และแพ็กเกจใน [`lists/_never_touch.json`](lists/_never_touch.json)
จะไม่ถูกแตะไม่ว่ากรณีใด

## ยี่ห้อที่รองรับ

| ยี่ห้อ | ROM | ไฟล์ |
|---|---|---|
| Xiaomi / Redmi / POCO | MIUI, HyperOS | [`xiaomi.json`](lists/xiaomi.json) |
| OPPO / realme / OnePlus | ColorOS, realme UI, OxygenOS | [`oplus.json`](lists/oplus.json) |
| vivo / iQOO | Funtouch OS, OriginOS | [`vivo.json`](lists/vivo.json) |
| Samsung | One UI | [`samsung.json`](lists/samsung.json) |
| ทุกยี่ห้อ | — | [`common.json`](lists/common.json) |

> ⚠️ **รายการเริ่มต้น (v0.1) ยังต้องการการยืนยันบนเครื่องจริง** ชื่อแพ็กเกจต่างกันได้ตามรุ่นและเวอร์ชัน ROM
> ถ้าคุณลองแล้ว ช่วย [ส่งรายงานเครื่อง](../../issues/new?template=device-report.yml) เพื่อให้คนต่อไปมั่นใจขึ้น

## ทำงานอย่างไร

- ปิดด้วย `pm disable-user --user 0` — แอปยังอยู่ในเครื่อง แค่ไม่ทำงาน
- ถ้า ROM ไม่ยอม (เช่น MIUI บางเวอร์ชัน) และคุณใส่ `--allow-uninstall` จะใช้ `pm uninstall -k --user 0`
  ซึ่งถอดเฉพาะผู้ใช้ปัจจุบัน ไฟล์ APK ยังอยู่ กู้คืนด้วย `cmd package install-existing`
- ก่อนเปลี่ยนอะไร จะบันทึกรายการแพ็กเกจทั้งหมดไว้ใน `backups/<รุ่น>-<เวลา>/backup.json`
- `restore` เทียบสถานะปัจจุบันกับไฟล์สำรอง แล้วคืนทุกอย่างที่ต่างไป

## คำถามที่พบบ่อย

**ประกันหายไหม?** ไม่ ไม่ได้ root หรือปลดล็อก bootloader
**แบตจะอึดขึ้นไหม?** อาจดีขึ้นเล็กน้อยเพราะบริการพื้นหลังลดลง แต่ไม่ใช่เป้าหมายหลัก
**อัปเดต OS แล้วเป็นอย่างไร?** บางแอปอาจถูกเปิดกลับมา ให้รัน `scan` แล้ว `apply` อีกรอบ
**ปิดโฆษณาใน YouTube/เกมได้ไหม?** ไม่ได้ เครื่องมือนี้จัดการเฉพาะโฆษณาของระบบ ลองใช้ Private DNS อย่าง `dns.adguard-dns.com`

## ข้อจำกัดความรับผิดชอบ

ใช้งานด้วยความเสี่ยงของคุณเอง เครื่องมือนี้ออกแบบให้ย้อนกลับได้ทุกขั้น แต่ ROM แต่ละรุ่นทำงานต่างกัน
สำรองข้อมูลสำคัญไว้ก่อนเสมอ

---

## English

**CleanYourPhone** disables system ads, bloatware and telemetry on Android phones sold in Thailand
(Xiaomi, OPPO, realme, vivo, Samsung) over ADB — no root, nothing actually deleted, automatic backup,
one-command restore. Inspired by [CleanYourTV](https://github.com/Gathin23/cleanyourtv).

Point an AI coding agent at [`PROMPT.md`](PROMPT.md), or run `cyp.py` yourself (Python 3.9+, stdlib only).
Package lists live in [`lists/`](lists/) as JSON with three risk tiers; contributions for new models
are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
