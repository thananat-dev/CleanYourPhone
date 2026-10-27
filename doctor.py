"""ตรวจสุขภาพเครื่อง — สรุปว่าทำไมมือถือช้า (อ่านอย่างเดียว ไม่เปลี่ยนอะไรในเครื่อง)

แยก parser เป็นฟังก์ชันล้วน ๆ เพื่อให้ทดสอบกับ output ตัวอย่างได้โดยไม่ต้องต่อเครื่อง
ทุก probe ทนต่อความล้มเหลว: ถ้า ROM ไม่ให้อ่านค่าไหน จะข้ามไปและบอกว่า "ไม่ทราบ"
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

GB = 1024 * 1024  # kB → GB

LEVEL_WEIGHT = {"high": 25, "medium": 10, "low": 3, "tip": 0}
LEVEL_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡", "tip": "💡"}

THERMAL_STATUS = {0: "ปกติ", 1: "อุ่นเล็กน้อย", 2: "ร้อนปานกลาง", 3: "ร้อนมาก",
                  4: "วิกฤต", 5: "ฉุกเฉิน", 6: "กำลังจะดับ"}
BATTERY_HEALTH = {1: "ไม่ทราบ", 2: "ดี", 3: "ร้อนเกิน", 4: "เสื่อม", 5: "แรงดันเกิน",
                  6: "ผิดปกติ", 7: "เย็นเกิน"}


# ชื่อที่คนทั่วไปรู้จัก สำหรับแอปยอดนิยมในไทย (ที่ไม่อยู่ในนี้จะแสดงชื่อแพ็กเกจ)
APP_NAMES = {
    "com.facebook.katana": "Facebook", "com.facebook.orca": "Messenger",
    "com.facebook.lite": "Facebook Lite", "com.instagram.android": "Instagram",
    "jp.naver.line.android": "LINE", "com.ss.android.ugc.trill": "TikTok",
    "com.zhiliaoapp.musically": "TikTok", "com.shopee.th": "Shopee", "com.lazada.android": "Lazada",
    "com.google.android.youtube": "YouTube", "com.android.chrome": "Chrome",
    "com.google.android.gms": "Google Play services", "com.twitter.android": "X (Twitter)",
    "com.grabtaxi.passenger": "Grab", "com.lineman.android": "LINE MAN",
    "com.kasikorn.retail.mbanking.wap": "K PLUS", "com.scb.phone": "SCB EASY",
    "com.ktb.customer.qr": "Krungthai NEXT", "ktbcs.netbank": "Krungthai NEXT",
    "com.bbl.mobilebanking": "Bualuang mBanking", "com.krungsri.kma": "KMA",
    "com.tencent.ig": "PUBG Mobile", "com.garena.game.kgth": "RoV",
    "com.mobile.legends": "Mobile Legends", "com.netflix.mediaclient": "Netflix",
    "com.spotify.music": "Spotify", "com.whatsapp": "WhatsApp",
    "com.huawei.health": "Huawei Health", "com.sec.android.app.shealth": "Samsung Health",
    "com.linecorp.linemanth": "LINE MAN", "com.linecorp.lineoa": "LINE OA",
    "com.microsoft.office.outlook": "Outlook", "us.zoom.videomeetings": "Zoom",
    "com.linkedin.android": "LinkedIn", "com.mi.health": "Mi Fitness",
    "com.xiaomi.wearable": "Mi Fitness", "com.samsung.android.app.watchmanager": "Galaxy Wearable",
}


def app_name(pkg: str) -> str:
    pkg = pkg.split(":")[0]
    return APP_NAMES.get(pkg, pkg)


@dataclass
class Finding:
    level: str          # high | medium | low | tip
    key: str
    title: str
    detail: str
    fix: str


@dataclass
class Report:
    facts: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    def add(self, *args) -> None:
        self.findings.append(Finding(*args))

    @property
    def score(self) -> int:
        """แต่ละปัญหาหักเป็นสัดส่วนของคะแนนที่เหลือ — ปัญหาเยอะคะแนนต่ำ แต่ไม่ติด 0 ตลอด"""
        s = 100.0
        for f in self.findings:
            s *= 1 - LEVEL_WEIGHT[f.level] / 100
        return round(s)

    def ranked(self) -> list[Finding]:
        order = list(LEVEL_WEIGHT)
        return sorted(self.findings, key=lambda f: order.index(f.level))

    def to_dict(self) -> dict:
        return {"score": self.score, "facts": self.facts, "unknown": self.unknown,
                "findings": [asdict(f) for f in self.ranked()]}


# ------------------------------------------------------------------- parsers

def parse_df(text: str) -> dict | None:
    """`df -k /data` → total/used/avail เป็น kB"""
    for line in reversed(text.strip().splitlines()):
        t = line.split()
        if len(t) >= 6 and (t[-1] == "/data" or t[-1].startswith("/data/")) and t[-2].endswith("%"):
            try:
                return {"total": int(t[-5]), "used": int(t[-4]), "avail": int(t[-3])}
            except ValueError:
                return None
    return None


def parse_proc_meminfo(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)\s*kB", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def parse_dumpsys_meminfo(text: str) -> dict:
    """คืน status ของ RAM (normal/moderate/low/critical) และรายการแอปที่ใช้ RAM มากสุด"""
    status = None
    m = re.search(r"Total RAM:\s*[\d,]+K\s*\(status (\w+)\)", text)
    if m:
        status = m.group(1).lower()
    procs: list[dict] = []
    # PSS นับหน่วยความจำที่ใช้ร่วมกันแบบหารแบ่ง จึงแม่นกว่า RSS — Android 15 มีทั้งสองแบบ โดย RSS มาก่อน
    section = (re.search(r"Total PSS by process:\n(.*?)(?:\n\s*\n|\Z)", text, re.S)
               or re.search(r"Total RSS by process:\n(.*?)(?:\n\s*\n|\Z)", text, re.S))
    if section:
        for line in section.group(1).splitlines():
            pm = re.match(r"\s*([\d,]+)K:\s+(\S+)\s+\(pid", line)
            if pm:
                procs.append({"name": pm.group(2), "kb": int(pm.group(1).replace(",", ""))})
    return {"status": status, "procs": procs}


def parse_cpuinfo(text: str) -> dict:
    """`dumpsys cpuinfo` → total%, iowait% และรายการโปรเซสที่กิน CPU"""
    procs = []
    for m in re.finditer(r"^\s*([\d.]+)% (\d+)/([^:\s]+):", text, re.M):
        procs.append({"name": m.group(3), "pct": float(m.group(1))})
    total = iowait = None
    tm = re.search(r"^\s*([\d.]+)% TOTAL:(.*)$", text, re.M)
    if tm:
        total = float(tm.group(1))
        im = re.search(r"([\d.]+)% iowait", tm.group(2))
        iowait = float(im.group(1)) if im else 0.0
    return {"total": total, "iowait": iowait, "procs": procs}


def parse_thermal(text: str) -> dict:
    status = None
    m = re.search(r"Thermal Status:\s*(\d)", text)
    if m:
        status = int(m.group(1))
    temps: dict[str, float] = {}
    for tm in re.finditer(r"mValue=([\d.]+),\s*mType=(\d+),\s*mName=([^,]+)", text):
        kind = {"0": "cpu", "2": "battery", "3": "skin"}.get(tm.group(2))
        if kind:
            temps[kind] = max(temps.get(kind, 0.0), float(tm.group(1)))
    return {"status": status, "temps": temps}


def parse_battery(text: str) -> dict:
    out = {}
    for key in ("level", "health", "temperature"):
        m = re.search(rf"^\s*{key}:\s*(-?\d+)", text, re.M)
        if m:
            out[key] = int(m.group(1))
    if "temperature" in out:
        out["temperature"] = out["temperature"] / 10
    # Samsung รายงานความจุแบตที่เหลือเทียบกับตอนใหม่ (ASOC) เป็น %
    m = re.search(r"mSavedBatteryAsoc:\s*\[(\d+)\]", text) or re.search(r"AsocData efsValue:(\d+)", text)
    if m and 0 < int(m.group(1)) <= 100:
        out["capacity"] = int(m.group(1))
    return out


def parse_float(text: str) -> float | None:
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def parse_cores(text: str) -> int | None:
    """`/sys/devices/system/cpu/possible` เช่น '0-7' หรือ '0-3,4-7'"""
    n = 0
    try:
        for part in text.strip().split(","):
            a, _, b = part.partition("-")
            n += int(b or a) - int(a) + 1
    except ValueError:
        return None
    return n or None


# -------------------------------------------------------------------- probes

def _try(adb, cmd: str) -> str | None:
    try:
        return adb.shell(cmd)
    except Exception:  # noqa: BLE001 — ROM บางตัวไม่ให้อ่านบางค่า ให้ข้ามไป
        return None


ANIM_KEYS = ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"]


def collect(adb) -> dict:
    """อ่านค่าดิบทั้งหมดจากเครื่อง แยกจากการวิเคราะห์เพื่อให้เก็บเป็น fixture ได้"""
    raw = {
        "df": _try(adb, "df -k /data"),
        "proc_meminfo": _try(adb, "cat /proc/meminfo"),
        "meminfo": _try(adb, "dumpsys meminfo"),
        "cpuinfo": _try(adb, "dumpsys cpuinfo"),
        "thermal": _try(adb, "dumpsys thermalservice"),
        "battery": _try(adb, "dumpsys battery"),
        "low_power": _try(adb, "settings get global low_power"),
        "anim": _try(adb, "; ".join(f"settings get global {k}" for k in ANIM_KEYS)),
        "uptime": _try(adb, "cat /proc/uptime"),
        "cores": _try(adb, "cat /sys/devices/system/cpu/possible"),
    }
    try:
        raw["user_apps"] = sorted(adb.packages("-3"))
    except Exception:  # noqa: BLE001
        raw["user_apps"] = None
    return raw


# ------------------------------------------------------------------ analysis

def _gb(kb: float) -> str:
    return f"{kb / GB:.1f} GB"


def _short(pkg: str) -> str:
    return pkg.split(":")[0]


def by_app(procs: list[dict], key: str, user_apps: set[str]) -> list[dict]:
    """รวมโปรเซสของแอปเดียวกัน (เช่น app กับ app:daemon) เป็นแถวเดียว เฉพาะแอปที่ผู้ใช้ลงเอง"""
    totals: dict[str, float] = {}
    for p in procs:
        pkg = _short(p["name"])
        if pkg in user_apps:
            totals[pkg] = totals.get(pkg, 0) + p[key]
    return [{"name": k, key: v} for k, v in sorted(totals.items(), key=lambda kv: -kv[1])]


def diagnose(raw: dict, bloat_enabled: list[str] | None = None) -> Report:
    r = Report()
    user_apps = set(raw.get("user_apps") or [])

    # --- พื้นที่เก็บข้อมูล ---------------------------------------------------
    df = parse_df(raw["df"]) if raw.get("df") else None
    if df and df["total"]:
        free_pct = df["avail"] / df["total"] * 100
        r.facts["storage"] = f"เหลือ {_gb(df['avail'])} จาก {_gb(df['total'])} ({free_pct:.0f}%)"
        short = f"เหลือ {_gb(df['avail'])}, {free_pct:.0f}%"
        fix = ("ลบวิดีโอ/ไฟล์ที่ไม่ใช้ ล้างแคชของ LINE, TikTok, Facebook ในตั้งค่าแอป "
               "และย้ายรูปไปเก็บบน cloud ควรเหลือว่างอย่างน้อย 15–20%")
        detail = ("หน่วยความจำแฟลชจะเขียนช้าลงมากเมื่อใกล้เต็ม แอปเขียนแคชไม่ได้ "
                  "และระบบไม่มีที่ทำงานเบื้องหลัง")
        if free_pct < 10 or df["avail"] < 3 * GB:
            r.add("high", "storage", f"พื้นที่เหลือน้อยมาก ({short})", detail, fix)
        elif free_pct < 20 or df["avail"] < 6 * GB:
            r.add("medium", "storage", f"พื้นที่เริ่มน้อย ({short})", detail, fix)
    else:
        r.unknown.append("storage")

    # --- RAM -----------------------------------------------------------------
    pm = parse_proc_meminfo(raw.get("proc_meminfo") or "")
    mem = parse_dumpsys_meminfo(raw.get("meminfo") or "")
    total, avail = pm.get("MemTotal"), pm.get("MemAvailable")
    if total:
        r.facts["ram"] = f"{_gb(total)} (ว่าง {_gb(avail or 0)})"
        if mem["status"]:
            r.facts["ram"] += f", สถานะ {mem['status']}"
        ram_fix = ("ปิดแอปที่ไม่ใช้ ถอนแอปที่ใช้ RAM มากแต่ไม่จำเป็น หรือใช้เวอร์ชัน Lite "
                   "(Facebook Lite, Messenger Lite) และรัน `cyp.py apply` เพื่อปิดบริการพื้นหลังที่ไม่จำเป็น")
        if mem["status"] in ("low", "critical"):
            r.add("high", "ram", "RAM ไม่พอ ระบบต้องปิดแอปเบื้องหลังบ่อย",
                  "สลับแอปแล้วแอปโหลดใหม่ทุกครั้ง และเครื่องค้างเป็นช่วง ๆ", ram_fix)
        elif mem["status"] == "moderate" or (avail is not None and avail / total < 0.10):
            r.add("medium", "ram", "RAM เริ่มตึง", "มีแอปเปิดค้างพื้นหลังหลายตัว", ram_fix)
        swap_total, swap_free = pm.get("SwapTotal", 0), pm.get("SwapFree", 0)
        if swap_total and (swap_total - swap_free) / swap_total > 0.6:
            r.facts["swap"] = f"ใช้ {_gb(swap_total - swap_free)} จาก {_gb(swap_total)}"
            r.add("medium", "swap", f"ใช้ RAM เสมือน/zram หนัก ({r.facts['swap']})",
                  "ข้อมูลถูกบีบอัดและย้ายไปมาตลอด กิน CPU และทำให้สลับแอปช้า", ram_fix)
        if total <= 3.2 * GB:
            r.add("low", "ram_hw", f"เครื่องมี RAM แค่ {_gb(total)}",
                  "เป็นข้อจำกัดของฮาร์ดแวร์ แอปสมัยนี้ออกแบบมาสำหรับ RAM 4 GB ขึ้นไป",
                  "ใช้แอปเวอร์ชัน Lite และอย่าเปิดแอปหนักพร้อมกันหลายตัว")
    else:
        r.unknown.append("ram")
    hogs = by_app(mem["procs"], "kb", user_apps)[:5]
    if hogs:
        r.facts["ram_hogs"] = [f"{app_name(p['name'])} {p['kb'] / 1024:.0f} MB" for p in hogs]

    # --- CPU -----------------------------------------------------------------
    cpu = parse_cpuinfo(raw.get("cpuinfo") or "")
    cores = parse_cores(raw.get("cores") or "")
    if cores:
        r.facts["cores"] = cores
    if cpu["total"] is not None:
        r.facts["cpu"] = f"{cpu['total']:.0f}% (iowait {cpu['iowait']:.1f}%)"
        busy = [p for p in by_app(cpu["procs"], "pct", user_apps) if p["pct"] >= 5][:3]
        if busy:
            r.facts["cpu_hogs"] = [f"{app_name(p['name'])} {p['pct']:.0f}%" for p in busy]
        who = ", ".join(app_name(p["name"]) for p in busy)
        why = (f"แอปที่ใช้ CPU มากสุด: {who} — แย่งทรัพยากรจากแอปที่คุณใช้อยู่และทำให้เครื่องร้อน"
               if who else "ส่วนใหญ่เป็นบริการของระบบ — มักลดลงหลังรีสตาร์ตหรือปิดแอปพ่วงด้วย `cyp.py apply`")
        if cpu["total"] >= 50:
            r.add("high", "cpu", f"CPU ทำงานหนักตลอดเวลา ({cpu['total']:.0f}%)",
                  why, "บังคับหยุดหรือถอนแอปที่กิน CPU แล้วปิดการทำงานเบื้องหลังของแอปนั้น")
        elif cpu["total"] >= 25:
            r.add("medium", "cpu", f"CPU ทำงานพื้นหลังค่อนข้างมาก ({cpu['total']:.0f}%)",
                  why, "ปิดการทำงานเบื้องหลัง/ซิงก์อัตโนมัติของแอปเหล่านี้")
        # 3%: Galaxy A14 ที่พื้นที่เต็ม 97% วัดได้ 4.8% และกระตุกชัดเจน หลังเคลียร์เหลือ 0% (issue #1)
        if cpu["iowait"] >= 3:
            r.add("medium", "iowait", f"CPU รอการอ่านเขียนดิสก์ (iowait {cpu['iowait']:.1f}%)",
                  "หน่วยความจำอ่านเขียนช้า มักเกิดจากพื้นที่ใกล้เต็มหรือแฟลชเสื่อมตามอายุ",
                  "เคลียร์พื้นที่ให้เหลืออย่างน้อย 20% แล้วรีสตาร์ตเครื่อง")
    else:
        r.unknown.append("cpu")

    # --- ความร้อน --------------------------------------------------------------
    th = parse_thermal(raw.get("thermal") or "")
    bat = parse_battery(raw.get("battery") or "")
    temps = dict(th["temps"])
    if "temperature" in bat:
        temps["battery"] = max(temps.get("battery", 0.0), bat["temperature"])
    # CPU 60–70°C ตอนทำงานถือว่าปกติ จึงตัดสินจากอุณหภูมิผิวเครื่องและแบตเท่านั้น
    felt = [v for k, v in temps.items() if k in ("skin", "battery")]
    hottest = max(felt) if felt else None
    if th["status"] is not None:
        r.facts["thermal"] = THERMAL_STATUS.get(th["status"], str(th["status"]))
    if temps:
        r.facts["temps"] = {k: round(v, 1) for k, v in temps.items()}
    heat_fix = ("ถอดเคสตอนชาร์จ ไม่เล่นเกม/ดูวิดีโอขณะชาร์จ วางเครื่องในที่โล่ง "
                "และหาแอปที่กิน CPU ในรายการด้านบน")
    heat_detail = "เมื่อเครื่องร้อน ระบบจะลดความเร็ว CPU (thermal throttling) เพื่อป้องกันความเสียหาย"
    if (th["status"] or 0) >= 2 or (hottest or 0) >= 43:
        r.add("high", "thermal", "เครื่องร้อนจนถูกลดความเร็ว" + (f" ({hottest:.0f}°C)" if hottest else ""), heat_detail, heat_fix)
    elif (th["status"] or 0) == 1 or (hottest or 0) >= 38:
        r.add("medium", "thermal", "เครื่องอุ่นกว่าปกติ" + (f" ({hottest:.0f}°C)" if hottest else ""), heat_detail, heat_fix)
    if th["status"] is None and not temps:
        r.unknown.append("thermal")

    # --- แบตเตอรี่และโหมดประหยัด ---------------------------------------------------
    if "level" in bat:
        r.facts["battery"] = f"{bat['level']}%, สภาพ{BATTERY_HEALTH.get(bat.get('health', 1), '?')}"
        if "capacity" in bat:
            r.facts["battery"] += f", ความจุเหลือ {bat['capacity']}%"
    if bat.get("capacity", 100) < 80 and bat.get("health") not in (3, 4, 5, 6):
        r.add("medium", "battery_health", f"แบตเตอรี่เสื่อม ความจุเหลือ {bat['capacity']}%",
              "แบตที่เสื่อมจ่ายไฟได้ไม่พอ บางรุ่นจะลดความเร็ว CPU ลงเพื่อกันเครื่องดับ และหมดเร็วกว่าเดิม",
              "พิจารณาเปลี่ยนแบตเตอรี่ที่ศูนย์บริการ (ปกติแนะนำเมื่อต่ำกว่า 80%)")
    if bat.get("health") in (3, 4, 5, 6):
        r.add("medium", "battery_health", f"แบตเตอรี่{BATTERY_HEALTH[bat['health']]}",
              "แบตที่เสื่อมจ่ายไฟได้ไม่พอ บางรุ่นจะลดความเร็ว CPU ลงเพื่อกันเครื่องดับ",
              "พิจารณาเปลี่ยนแบตเตอรี่ที่ศูนย์บริการ")
    if (raw.get("low_power") or "").strip() == "1":
        r.add("medium", "low_power", "เปิดโหมดประหยัดแบตเตอรี่อยู่",
              "โหมดนี้จำกัดความเร็ว CPU และหยุดการทำงานเบื้องหลัง",
              "ปิดโหมดประหยัดแบตเมื่อไม่จำเป็น (แผงตั้งค่าด่วน)")

    # --- แอนิเมชัน -------------------------------------------------------------
    anim = [parse_float(x) for x in (raw.get("anim") or "").splitlines()][:3]
    anim = [1.0 if a is None else a for a in anim]  # null = ค่าเริ่มต้น 1.0
    if len(anim) == 3:
        r.facts["animation"] = " / ".join(f"{a:g}x" for a in anim)
        fix = ("ตั้งค่า → ตัวเลือกสำหรับนักพัฒนา → ปรับ 'อัตราการเคลื่อนไหวของหน้าต่าง', "
               "'อัตราการเคลื่อนไหวของการเปลี่ยน' และ 'ระยะเวลาของตัวสร้างภาพเคลื่อนไหว' เป็น 0.5x")
        if max(anim) > 1:
            r.add("medium", "animation", "แอนิเมชันถูกตั้งให้ช้ากว่าปกติ",
                  "ทุกการเปิดแอปและสลับหน้าจอจะช้าลงตามตัวคูณนี้", fix)
        elif min(anim) >= 1:
            r.add("tip", "animation", "ลดแอนิเมชันเหลือ 0.5x จะรู้สึกเร็วขึ้นทันที",
                  "ไม่ได้ทำให้เครื่องแรงขึ้น แต่ลดเวลารอทุกครั้งที่เปิดหรือสลับแอป", fix)

    # --- อื่น ๆ ------------------------------------------------------------------
    up = parse_float((raw.get("uptime") or "").split(" ")[0])
    if up is not None:
        days = up / 86400
        r.facts["uptime_days"] = round(days, 1)
        if days >= 7:
            r.add("low", "uptime", f"ไม่ได้รีสตาร์ตมา {days:.0f} วัน",
                  "หน่วยความจำรั่วและโปรเซสค้างสะสม", "รีสตาร์ตเครื่องสัปดาห์ละครั้ง")
    if raw.get("user_apps") is not None:
        n = len(raw["user_apps"])
        r.facts["user_apps"] = n
        if n >= 120:
            r.add("low", "apps", f"ติดตั้งแอปไว้ {n} แอป",
                  "หลายแอปตั้งเวลาทำงานเบื้องหลังเอง ยิ่งมากยิ่งแย่ง RAM และแบต",
                  "ถอนแอปที่ไม่ได้เปิดเกิน 1 เดือน")
    if bloat_enabled:
        r.facts["bloat_enabled"] = len(bloat_enabled)
        r.add("medium", "bloat", f"ยังมีแอปโฆษณา/เก็บข้อมูลของผู้ผลิตทำงานอยู่ {len(bloat_enabled)} ตัว",
              "บริการเหล่านี้ทำงานพื้นหลัง ดึงโฆษณา และส่งข้อมูลกลับผู้ผลิต",
              "รัน `python cyp.py apply --tier recommended`")
    return r


# -------------------------------------------------------------------- render

FACT_LABELS = [("storage", "พื้นที่"), ("ram", "RAM"), ("swap", "RAM เสมือน"), ("cpu", "CPU"),
               ("cores", "จำนวนคอร์"), ("thermal", "ความร้อน"), ("temps", "อุณหภูมิ °C"),
               ("battery", "แบตเตอรี่"), ("animation", "แอนิเมชัน"), ("uptime_days", "เปิดเครื่องมา (วัน)"),
               ("user_apps", "แอปที่ติดตั้ง"), ("ram_hogs", "ใช้ RAM มากสุด"), ("cpu_hogs", "ใช้ CPU มากสุด")]
UNKNOWN_LABELS = {"storage": "พื้นที่", "ram": "RAM", "cpu": "CPU", "thermal": "ความร้อน"}


def render(report: Report, title: str) -> str:
    s = report.score
    grade = "ดี" if s >= 80 else "พอใช้" if s >= 60 else "ควรแก้ไข"
    lines = [f"🩺 สุขภาพเครื่อง {title}", f"   คะแนน {s}/100 — {grade}", ""]
    causes = [f for f in report.ranked() if f.level != "tip"]
    tips = [f for f in report.findings if f.level == "tip"]
    if causes:
        lines.append("สาเหตุที่ทำให้ช้า (เรียงจากผลกระทบมากไปน้อย)")
        for i, f in enumerate(causes, 1):
            lines += [f" {i}. {LEVEL_ICON[f.level]} {f.title}",
                      f"    ทำไม: {f.detail}", f"    แก้: {f.fix}"]
        lines.append("")
    else:
        lines += ["✅ ไม่พบสาเหตุที่ชัดเจน — ถ้ายังรู้สึกช้า อาจเป็นเพราะอายุฮาร์ดแวร์หรือแอปเฉพาะตัว", ""]
    if tips:
        lines.append("เคล็ดลับ")
        for f in tips:
            lines += [f" {LEVEL_ICON['tip']} {f.title}", f"    {f.fix}"]
        lines.append("")
    lines.append("ข้อมูลที่ตรวจ")
    for key, label in FACT_LABELS:
        if key in report.facts:
            v = report.facts[key]
            if isinstance(v, list):
                v = ", ".join(v)
            elif isinstance(v, dict):
                v = ", ".join(f"{k} {x}" for k, x in v.items())
            lines.append(f"  {label:<18} {v}")
    if report.unknown:
        lines.append(f"  อ่านค่าไม่ได้: {', '.join(UNKNOWN_LABELS.get(u, u) for u in report.unknown)}")
    lines += ["", "หมายเหตุ: ค่า CPU วัดย้อนหลังไม่กี่นาที ควรวางเครื่องไว้เฉย ๆ ก่อนตรวจ"]
    return "\n".join(lines)
