# Pandora Unified — Xiaomi Diagnostics & Recovery Toolkit

> Open-source GUI tool for diagnosing, backing up, and safely locking/unlocking Xiaomi phones.
> Born from a real chip-off recovery of a Xiaomi 17 Pro — captures the lessons the hard way.

**🌍 Languages:** English · [Русский](README.ru.md)
**🔧 Platform:** Windows (uses Xiaomi's fastboot/adb binaries bundled in `adb/`)
**📝 License:** MIT — see [LICENSE](LICENSE)

---

## Why this exists

In October 2026 a Xiaomi 17 Pro China (codename `pandora`) was bricked by running `fastboot erase efisp` + `fastboot oem lock` after an exploit-based unlock. Every public tool failed. Recovery required chip-off NAND desoldering at a repair shop (300 AZN, 6 months warranty on the solder — but 2-3 years off the phone's lifespan).

**This tool packages everything we learned so it doesn't happen to someone else.**

The underlying mistake — that `fastboot oem lock` alone does NOT re-lock after an exploit unlock — is documented nowhere else as a public tool. See [LESSONS_LEARNED.md](LESSONS_LEARNED.md).

## Features

| Feature | What it does |
|---------|--------------|
| **Full diagnostic** | Reads all `fastboot getvar` + `oem` state, saves JSON report |
| **UFS check** | Detects storage vendor (critical for auth-free firehose compatibility) |
| **Bootfail analysis** | Parses `.bin` bootfail dumps for boot errors, versions, boot reasons |
| **Compare with firmware** | Verifies partition sizes against a known-good OTA zip |
| **🔒 Lock Wizard** | Shows the CORRECT lock sequence for your unlock method (exploit vs Mi Unlock) — the public internet gets this wrong |
| **📸 Snapshot** | One-click backup of `getvar all`, OEM dumps, dynamic token to a zip — run BEFORE any risky op |
| **🏥 Service report** | Self-contained HTML for a repair technician: device state, methods tried, services |
| **📊 UFS Health** | ADB-based `dd` read/write benchmark. First run = baseline. Later runs compare and warn if speed drops >20% (useful after chip-off repair) |

## Supported devices

| Codename | Device | Chip | Storage | Unlock method |
|----------|--------|------|---------|---------------|
| `pandora` | Xiaomi 17 Pro China | Snapdragon 8 Elite | UFS 4.0 | exploit |
| `miel` | Redmi Note 11 | Snapdragon 680 | UFS 2.2 | Mi Unlock |

**Your device not listed?** Adding one is a 10-minute JSON edit — see [profiles/README.md](profiles/README.md).

## Languages

- English (`en`)
- Русский (`ru`)
- Azərbaycanca (`az`)

Switch at runtime from the Language dropdown. Choice is persisted.

## Requirements

- Windows 10/11
- Python 3.8+ (ships with Tkinter)
- No pip dependencies — standard library only
- `adb/fastboot.exe` and `adb/adb.exe` in `adb/` folder (Xiaomi platform-tools)

## Running

```bash
python pandora_unified.py
```

That's it. Everything else is in the GUI.

## Repository layout

```
pandora_unified.py          # The GUI tool
profiles/                   # Device profiles (one JSON per device)
  pandora.json
  miel.json
  _template.json            # Copy this to add your device
  README.md
translations/               # UI translations (one JSON per language)
  en.json
  ru.json
  az.json
LESSONS_LEARNED.md          # What NOT to do when locking bootloader
README.md                   # This file
README.ru.md                # Original Russian narrative (recovery timeline)
LICENSE                     # MIT
CONTRIBUTING.md             # How to add a device / language
adb/                        # fastboot.exe + adb.exe (Windows)
```

## Contributing

**Device profiles and translations are plain JSON — no code required.** See [CONTRIBUTING.md](CONTRIBUTING.md).

Target devices we'd love profiles for:
- Redmi Note 11 Pro (`spes`, `spesn`)
- POCO F series (`munch`, `psyche`)
- Xiaomi flagships with Snapdragon 7/8 series
- Anything with a known-tricky unlock/lock dance

## ⚠️ Disclaimers

This tool CANNOT:
- Perform EDL/firehose flashing (no signed loaders published)
- Unlock a locked bootloader (that's done via Mi Unlock Tool or an exploit)
- Un-brick a phone with corrupted UFS/NAND (that needs chip-off service)

It CAN:
- Diagnose what state your phone is in
- Prevent you from making the mistake that bricked ours
- Give you a professional report to hand to a repair shop
- Track UFS health over time

**Everything is at your own risk.** Backing up before any risky operation is on you — the Snapshot button helps but is not a substitute for a TWRP full backup when possible.

## Credits

- Original device-recovery timeline, lessons, and tool authorship: @alizaderamil
- The Mobil Hafiz telefon servisi (Baku, Azerbaijan) who performed the actual chip-off recovery and shared the correct lock sequence
- Development collaboration with Claude Code

## Links

- Issue / discussion: GitHub issues on this repo
- Repository: https://github.com/alizaderamil/xiaomi-pandora-recovery
