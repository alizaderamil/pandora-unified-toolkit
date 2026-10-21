# Promotion templates

Ready-to-paste announcement posts for different communities. Each is pre-filled with the correct repo URL. Just copy, maybe tweak a sentence, and post.

---

## XDA Developers Forums

**Where to post:** [XDA Developers → Xiaomi forums](https://xdaforums.com/f/xiaomi.9680/) · Specifically your device subforum (e.g. "Xiaomi 17 Pro Guides, News, & Discussion")

**Title:**
> [Tool] Pandora Unified — open-source Xiaomi diagnostics + bootloader lock wizard (multi-device, multi-language)

**Body:**
```
Hey folks,

Releasing a GUI tool I built after bricking my Xiaomi 17 Pro China (pandora) by running
`fastboot erase efisp` + `fastboot oem lock` after an exploit unlock. The phone wouldn't
boot, EDL was closed, no public firehose loader exists for SM8850. Ended up at a chip-off
shop — 300 AZN, 6 months warranty, but 2-3 years off the phone's lifespan.

Lesson: `fastboot oem lock` alone does NOT re-lock a phone after an exploit unlock. You
need stock-flash → erase efisp → MiFlash with clean_all_and_lock, in that exact order.
This is documented NOWHERE as a public tool. I made one.

Features:
- Full diagnostic (fastboot getvar + oem dumps)
- UFS vendor detection (critical for auth-free firehose compatibility)
- Bootfail dump analyzer
- 🔒 Lock Wizard — correct lock sequence for your unlock method
- 📸 Snapshot — one-click backup before any risky op
- 🏥 Service report — HTML to hand to a repair shop
- 📊 UFS Health — dd benchmark + baseline tracking (useful post chip-off)

Multi-device, multi-language (en/ru/az). Device profiles are JSON — adding your model
is a 10-min PR, no Python required.

Currently supports:
- pandora (Xiaomi 17 Pro China)
- miel (Redmi Note 11)

MIT licensed, Windows (Tkinter GUI).

GitHub: https://github.com/alizaderamil/pandora-unified-toolkit

Would love profile PRs for Redmi Note 11 Pro (spes), POCO F series, and other flagships.
Any feedback welcome.
```

---

## 4PDA (Russian) — Xiaomi branch

**Where to post:** 4pda.to in a tools/software subforum, or in your device's firmware thread (as "утилита восстановления")

**Title:**
> [Утилита] Pandora Unified — диагностика Xiaomi, правильная блокировка загрузчика, UFS Health. Multi-device + 3 языка

**Тело:**
```
Привет,

Выкладываю GUI утилиту, которую сделал после того как убил свой Xiaomi 17 Pro China
командой fastboot erase efisp + fastboot oem lock после эксплойт-разлочки. Телефон не
грузился, EDL закрыт, публичного firehose loader для SM8850 нет. Пришлось отдавать
в chip-off ремонт — 300 AZN (~$175), 6 месяцев гарантии, но минус 2-3 года жизни телефона.

Урок: fastboot oem lock САМ ПО СЕБЕ не блокирует загрузчик после эксплойт-разлочки.
Правильно: сток-прошивка → erase efisp → MiFlash с clean_all_and_lock, именно в
таком порядке. Этого НИГДЕ нет как публичного инструмента. Сделал.

Что умеет:
- Полная диагностика (fastboot getvar + oem дампы)
- Определение производителя UFS (критично для auth-free firehose)
- Анализ bootfail дампов
- 🔒 Lock Wizard — правильная последовательность блокировки для твоего типа разлочки
- 📸 Snapshot — одна кнопка бэкап перед опасной операцией
- 🏥 Отчёт для сервиса — HTML, который понесёшь мастеру
- 📊 UFS Health — dd benchmark + baseline (полезно после chip-off)

Multi-device, 3 языка (en/ru/az). Профили устройств — обычные JSON, добавить свой
телефон = 10 минут редактирования + PR, Python знать не надо.

Сейчас поддерживаются:
- pandora (Xiaomi 17 Pro China)
- miel (Redmi Note 11)

MIT, Windows (Tkinter).

GitHub: https://github.com/alizaderamil/pandora-unified-toolkit

Жду PR с профилями для Redmi Note 11 Pro (spes), POCO F серии, других флагманов.
Фидбек по багам / предложения — welcome.
```

---

## Reddit — r/Xiaomi, r/AndroidRoot

**Title:**
> [OC] Pandora Unified — open-source toolkit for Xiaomi diagnostics + bootloader lock wizard. Born from a chip-off recovery.

**Body:**
```
TL;DR: I bricked my phone with `fastboot oem lock` after an exploit unlock (lesson:
you also need to re-flash with `clean_all_and_lock`, not just `oem lock`). Phone went
to a chip-off repair shop. I built a GUI tool that packages everything I learned so
nobody else bricks theirs the same way.

**GitHub:** https://github.com/alizaderamil/pandora-unified-toolkit

**Features:**
- GUI diagnostic (no sketchy terminal commands)
- Lock Wizard that shows the CORRECT sequence per unlock method (exploit vs Mi Unlock)
- UFS Health benchmark with baseline tracking (useful if your phone had chip-off work)
- Service report generator for repair shops (HTML, hand it to the technician)
- Multi-device profile system (JSON — add your device without touching Python)
- English/Russian/Azerbaijani UI

**Supported now:** Xiaomi 17 Pro China (pandora), Redmi Note 11 (miel).

Would love PRs for more device profiles. MIT, Python/Tkinter, Windows.
```

---

## Telegram channels (Russian Android/Xiaomi communities)

Short version for channel posts:

```
🔧 Pandora Unified — утилита для Xiaomi

Open-source GUI тулза для диагностики и правильной блокировки загрузчика.
Родилась из опыта чиноффа Xiaomi 17 Pro после моей ошибки с oem lock.

Фишки:
🔒 Lock Wizard — правильная последовательность (которой НЕТ в интернете)
📸 Snapshot — бэкап перед опасными операциями
🏥 Отчёт для сервиса (HTML для мастера)
📊 UFS Health — трекать деградацию UFS после chip-off

🌍 EN / RU / AZ, мультидевайс, JSON профили

https://github.com/alizaderamil/pandora-unified-toolkit
```

---

## Hacker News (if you want wider tech audience)

**Title:**
> Show HN: Pandora Unified – Xiaomi bootloader lock wizard, after I bricked my phone

**Body:**
```
I ran `fastboot erase efisp` + `fastboot oem lock` after unlocking my Xiaomi 17 Pro
with an exploit, following a guide. The phone wouldn't boot. Every public recovery
tool failed — EDL is closed on Snapdragon 8 Elite without a signed firehose loader
(none published for SM8850), and I had already erased the exploit's unlock marker,
so I couldn't re-unlock to flash via fastboot either. The phone went to a chip-off
repair shop — NAND desoldered, programmed externally, soldered back. 300 AZN,
6 months warranty.

The missing step was that after an exploit unlock, you can't just `oem lock` — you
have to flash the stock firmware a second time with MiFlash's `clean_all_and_lock`
option, which atomically rewrites all partitions under Verified Boot. The exploit
leaves traces in system partitions that `oem lock` by itself doesn't clear, so
Verified Boot refuses to boot the "locked" state.

This fact is documented nowhere I could find. I built a GUI tool that packages the
correct sequence as a wizard, plus:
- Diagnostic reports (fastboot getvar + oem dumps)
- Pre-op snapshot (full state backup before anything risky)
- HTML service report generator (so a repair shop gets structured input)
- UFS Health benchmark with baseline tracking
- Multi-device profiles (JSON, no code)
- en/ru/az UI

MIT, Python/Tkinter, Windows.

https://github.com/alizaderamil/pandora-unified-toolkit
```

---

## Where NOT to post

- **Linus Tech Tips forum / general PC forums** — wrong audience, will flop
- **Discord servers without permission** — most mod rules forbid self-promotion
- **Xiaomi official community** — they may ban promotion of unlock tools
- **r/Xiaomi** — moderators sometimes remove unlock-related content; check their rules first

## Order of attack

1. Post on **XDA** first (most likely to get device-profile PRs)
2. Post on **4PDA** for Russian-speaking users
3. Post on **r/Xiaomi** carefully (check rules), then **r/AndroidRoot** (friendlier to unlock tools)
4. Share in **Telegram channels** you're already in (don't spam ones you aren't)
5. Only after that — **Hacker News** Show HN (one-shot opportunity, don't waste it until the repo is polished)
