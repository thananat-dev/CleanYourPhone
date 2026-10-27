# CleanYourPhone 📱🧹

**English** · [ภาษาไทย](README.th.md)

**Take your phone back from the ads.** CleanYourPhone switches off system ads, bloatware and
manufacturer telemetry on Android phones over ADB, and tells you why your phone feels slow.
**No root · nothing actually deleted · automatic backup · one-command restore.**

Built first for phones sold in Thailand (Xiaomi, OPPO, realme, vivo, Samsung), but the same
ROMs ship worldwide.

[Usage](#usage) · [Why is my phone slow?](#why-is-my-phone-slow) · [Supported brands](#supported-brands) · [Contributing](CONTRIBUTING.md)

---

## Why

Many Xiaomi, OPPO, realme, vivo and Samsung phones show ads on the lock screen, in the file
manager, when you install an app, and in notifications. They also come with apps you can't
uninstall and background services that send usage data back to the manufacturer. Most people
don't know these can be switched off, and those who do have to type commands one package at a time.

CleanYourPhone keeps **per-brand package lists** that the community checks together, and lets an
**AI agent** walk you through the whole thing step by step.

## Usage

### Easy: let an AI do it (~15 minutes)

1. Install [Claude Code](https://claude.com/claude-code), Codex CLI or Gemini CLI
2. Download this project
   ```bash
   git clone https://github.com/thananat-dev/CleanYourPhone.git
   cd CleanYourPhone
   ```
3. Tell the AI: **`Read PROMPT.md and help me clean up my phone`**

The AI helps you turn on developer mode, connect the phone and scan it. It asks before it
switches anything off.

### Manual

Requires Python 3.9+ and [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`).
No other dependencies.

```bash
python cyp.py info                                  # device and ROM info
python cyp.py doctor                                # why is my phone slow?
python cyp.py scan                                  # what's on this phone
python cyp.py apply --tier safe --dry-run           # preview what will be disabled
python cyp.py apply --tier safe                     # do it (backup is automatic)
python cyp.py apply --tier recommended              # next tier
python cyp.py restore                               # undo the last apply
python cyp.py restore --original                    # return to the state before you first used the tool
```

Over Wi-Fi (Android 11+): turn on *Wireless debugging*, then
```bash
python cyp.py connect 192.168.1.20:37155 --pair-code 123456   # pairing port
python cyp.py connect 192.168.1.20:41427                      # main port
```

## Why is my phone slow?

`python cyp.py doctor` only reads from the phone and never changes anything. It gives a score
from 0 to 100 and lists the causes with the biggest impact first. Each cause says why it slows
the phone down and what to do about it.

```
🩺 สุขภาพเครื่อง Redmi Note 11 · Android 13
   คะแนน 20/100 — ควรแก้ไข

สาเหตุที่ทำให้ช้า (เรียงจากผลกระทบมากไปน้อย)
 1. 🔴 พื้นที่เหลือน้อยมาก (เหลือ 3.1 GB, 3%)          ← storage almost full
 2. 🔴 RAM ไม่พอ ระบบต้องปิดแอปเบื้องหลังบ่อย           ← out of RAM
 3. 🔴 CPU ทำงานหนักตลอดเวลา (58%)                    ← CPU busy: Facebook, TikTok
 4. 🔴 เครื่องร้อนจนถูกลดความเร็ว (44°C)                ← thermal throttling
 ...
```
<sub>Sample from synthetic data. The report is in Thai for now. Use `--json` for machine-readable output, which an AI agent can explain in any language.</sub>

| Checks | Read from |
|---|---|
| Low storage | `df /data` |
| RAM pressure, heavy zram / virtual RAM use | `/proc/meminfo`, `dumpsys meminfo` |
| CPU and RAM hogs, slow storage (iowait) | `dumpsys cpuinfo`, `dumpsys meminfo` |
| Thermal throttling | `dumpsys thermalservice`, `dumpsys battery` |
| Worn battery, battery saver on | `dumpsys battery`, `settings get` |
| Slow animations, long uptime, too many apps | `settings get`, `/proc/uptime`, `pm list` |
| Manufacturer bloat still enabled | package lists in `lists/` |

`--save-raw file.json` saves the raw readings so you can attach them to an issue and help tune the thresholds.

## Risk tiers

| Tier | Meaning | Examples |
|---|---|---|
| `safe` | Preinstalled apps nobody uses. Nothing breaks when they're off | Facebook App Manager, GetApps, Samsung Tips |
| `recommended` | The services behind the ads and data collection | MIUI MSA, OPPO Ads, Samsung Free |
| `advanced` | Can be disabled, but with side effects you should know first | Vendor app stores, system browser, Bixby |

Each tier includes the ones below it. Packages in [`lists/_never_touch.json`](lists/_never_touch.json)
are never touched under any circumstances.

## Supported brands

| Brand | ROM | List |
|---|---|---|
| Xiaomi / Redmi / POCO | MIUI, HyperOS | [`xiaomi.json`](lists/xiaomi.json) |
| OPPO / realme / OnePlus | ColorOS, realme UI, OxygenOS | [`oplus.json`](lists/oplus.json) |
| vivo / iQOO | Funtouch OS, OriginOS | [`vivo.json`](lists/vivo.json) |
| Samsung | One UI | [`samsung.json`](lists/samsung.json) |
| All brands | — | [`common.json`](lists/common.json) |

> ⚠️ **The package lists still need confirming on real devices.** Package names vary by model and ROM version.
> If you've tried it, please [send a device report](../../issues/new?template=device-report.yml) so the next person can be more confident.

## How it works

- Apps are switched off with `pm disable-user --user 0`. The app stays on the phone but doesn't run.
- Some ROMs refuse that (e.g. some MIUI versions). If you pass `--allow-uninstall`, the tool uses
  `pm uninstall -k --user 0` instead. This removes the app for the current user only. The APK stays
  on the phone and comes back with `cmd package install-existing`.
- Before any change, the full package state is saved to `backups/<model>-<time>/backup.json`.
- `restore` compares the current state with the backup and reverts everything that differs.

## FAQ

**Does this void my warranty?** No. There's no root and no bootloader unlocking.
**Will my battery last longer?** Maybe a little, since fewer background services run. That isn't the main goal.
**What happens after an OS update?** Some apps may come back. Run `scan` and `apply` again.
**Can it block ads in YouTube or games?** No, it only handles system ads. Try a Private DNS such as `dns.adguard-dns.com`.

## Disclaimer

Use at your own risk. Every step is designed to be reversible, but ROMs behave differently.
Always back up important data first.

## Credits

Inspired by [CleanYourTV](https://github.com/Gathin23/cleanyourtv), which does the same for Android TVs.

## License

[MIT](LICENSE)
