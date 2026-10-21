"""
Programmatic screenshot generator for Pandora Unified README.
Launches the GUI, fills each view with representative sample data,
captures PNG via PIL ImageGrab, saves to docs/images/.
"""
import os
import sys
import time
import tkinter as tk
from pathlib import Path

# UTF-8 output for Windows console
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab

# Запускаем в английском режиме
settings = ROOT / ".pandora_settings.json"
settings.write_text('{"lang": "en"}', encoding="utf-8")

import pandora_unified as pu
pu.set_lang("en")

OUT_DIR = ROOT / "docs" / "images"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def grab_window(root, out_path):
    """Захватить окно root в PNG. Всегда поверх и в фокусе чтобы не захватить чужие окна."""
    # Форсируем topmost + focus чтобы ничего не могло оказаться поверх
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.update_idletasks()
    root.update()
    time.sleep(0.6)  # дать Windows отрисовать
    # Берём рамку окна (не winfo_rootx — это клиентская область)
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    w = root.winfo_width()
    h = root.winfo_height()
    # Проверка: окно должно быть видимо и иметь положительные координаты
    if root.state() != "normal":
        print(f"  ! Window state is {root.state()!r}, forcing normal")
        root.deiconify()
        root.update()
        time.sleep(0.3)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(out_path)
    print(f"  → {out_path.name} ({w}x{h})")


def main():
    root = tk.Tk()
    app = pu.App(root)
    root.geometry("1200x860+40+40")
    root.update()
    # Останавливаем фоновый DeviceMonitor (конфликтует со script-режимом без mainloop)
    # и делаем один прямой опрос в main thread
    if app.device_monitor:
        app.device_monitor.stop()
    print("  Doing a direct device check…")
    state = app.device_monitor._check() if app.device_monitor else {"mode": "none", "info": {}}
    print(f"  Detected: {state['mode']}")
    app._update_device_bar(state)
    root.update()
    time.sleep(0.3)

    # --- 1. MAIN WINDOW with diagnostic output ---
    print("1/4: main.png")

    sample_log = [
        ("═══ FULL DIAGNOSTIC ═══", "hdr"),
        ("", None),
        ("Reading all variables…", None),
        ("✓ Read 142 variables", "ok"),
        ("📱 Device detected: Redmi Note 11 (Global/EU) (miel)", "ok"),
        ("   Chip: Snapdragon 680 (SM6225) · Storage: UFS 2.2", None),
        ("", None),
        ("Trying OEM commands…", None),
        ("✓ device-info", "ok"),
        ("    Device unlocked: true", None),
        ("    Device critical unlocked: true", None),
        ("    Charger screen enabled: true", None),
        ("✓ fbreason", "ok"),
        ("", None),
        ("═══ DIAGNOSIS ═══", "hdr"),
        ("Bootloader: UNLOCKED (unofficial Mi Unlock)", "warn"),
        ("Both slots healthy, slot A active", "ok"),
        ("Anti-rollback counter: 1", None),
        ("Security patch: 2026-09-01", None),
        ("Battery: 3942 mV (healthy)", "ok"),
        ("", None),
        ("Report saved: 20261021-173412-diagnostic.json", None),
    ]

    for text, tag in sample_log:
        app.write(text, tag)

    # Заполняем state tree
    state_data = [
        ("product", "miel_global"),
        ("variant", "SM"),
        ("unlocked", "yes"),
        ("secure", "no"),
        ("current-slot", "a"),
        ("slot-successful:a", "yes"),
        ("slot-unbootable:a", "no"),
        ("slot-retry-count:a", "7"),
        ("slot-successful:b", "yes"),
        ("slot-unbootable:b", "no"),
        ("anti", "1"),
        ("security-patch-level", "2026-09-01"),
        ("variant", "SM"),
        ("cpuid", "SM6225"),
        ("battery-voltage", "3942"),
        ("max-download-size", "536870912"),
        ("kernel", "uefi"),
    ]
    for k, v in state_data:
        app.state_tree.insert("", "end", values=(k, v))

    app.status.set("Diagnostic complete. 142 parameters read, device identified as miel.")
    app.notebook.select(0)  # Log tab
    root.update()
    grab_window(root, OUT_DIR / "main.png")

    # --- 2. UFS HEALTH results ---
    print("2/4: ufs-health.png")

    # Очищаем log и пишем UFS Health результаты
    app.log.configure(state="normal")
    app.log.delete("1.0", "end")
    app.log.configure(state="disabled")

    ufs_log = [
        ("═══ UFS HEALTH BENCHMARK ═══", "hdr"),
        ("", None),
        ("Device: 2201117SG (miel_global)", None),
        ("✓ Profile: Redmi Note 11 (Global/EU) (UFS 2.2)", "ok"),
        ("  Expected speeds: read ~850 MB/s, write ~400 MB/s", None),
        ("", None),
        ("WRITE test (512 MB to /data/local/tmp, conv=fsync)…", None),
        ("✓ Write: 383.4 MB/s", "ok"),
        ("Preparing read (flushing page cache via secondary file)…", None),
        ("READ test (512 MB from /data/local/tmp)…", None),
        ("✓ Read: 1944.2 MB/s", "ok"),
        ("   (likely partially from RAM cache — reading optimistic)", "warn"),
        ("", None),
        ("🎯 Compared with datasheet speeds (UFS 2.2):", "hdr"),
        ("   Write: 96% of expected (383 of ~400)", "ok"),
        ("   Read: optimistic cached result (1944 of ~850)", "ok"),
        ("", None),
        ("📌 BASELINE saved: ufs_baseline_miel_global.json", "hdr"),
        ("   Re-run this test in a month, then at 6/12 months.", None),
        ("   If speed drops >20% — pairing is deteriorating.", "warn"),
        ("", None),
        ("✓ History: ufs_history.jsonl", "ok"),
    ]
    for text, tag in ufs_log:
        app.write(text, tag)

    app.status.set("UFS miel_global: R=1944 W=383 MB/s")
    root.update()
    grab_window(root, OUT_DIR / "ufs-health.png")

    # --- 3. LOCK WIZARD (exploit mode — the key screenshot) ---
    print("3/4: lock-wizard.png")

    # Устанавливаем профиль pandora чтобы Wizard показал exploit mode
    app.device_profile = pu.DEVICE_PROFILES.get("pandora")
    app.manual_device_override = True
    app._show_lock_wizard()
    root.update()
    time.sleep(0.5)

    # Находим Toplevel окно Wizard'а
    wizard = None
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Lock Wizard" in w.title():
            wizard = w
            break

    if wizard:
        wizard.attributes("-topmost", True)
        wizard.lift()
        wizard.focus_force()
        wizard.update()
        time.sleep(0.6)
        wx = wizard.winfo_rootx()
        wy = wizard.winfo_rooty()
        ww = wizard.winfo_width()
        wh = wizard.winfo_height()
        img = ImageGrab.grab(bbox=(wx, wy, wx + ww, wy + wh))
        img.save(OUT_DIR / "lock-wizard.png")
        print(f"  → lock-wizard.png ({ww}x{wh})")
        wizard.destroy()
    else:
        print("  ! Wizard window not found, skipping")

    # Сброс профиля
    app.device_profile = None
    app.manual_device_override = False

    # --- 4. SERVICE REPORT (HTML in default browser is complex to screenshot;
    #    generate it instead and screenshot the HTML directly via Chrome's headless mode)
    print("4/4: service-report.png (HTML → PNG via wkhtmltoimage or Edge headless)")

    # Для screenshot HTML-отчёта используем временный приём: сначала генерим отчёт
    # с pandora профилем и подготовленными данными
    app.device_data["variables"] = {
        "product": "pandora",
        "variant": "SM8",
        "unlocked": "no",
        "secure": "yes",
        "current-slot": "a",
        "slot-unbootable:a": "yes",
        "slot-unbootable:b": "yes",
        "slot-successful:a": "yes",
        "slot-successful:b": "no",
        "anti": "1",
        "security-patch-level": "2026-10-01",
        "battery-voltage": "4384",
        "cpuid": "SM8850",
        "serialno": "d5xxxxxx",
    }
    app.device_profile = pu.DEVICE_PROFILES.get("pandora")

    # Генерим отчёт синхронно (не через run_async)
    try:
        app._do_service_report()
    except Exception as e:
        print(f"  ! Service report generation failed: {e}")

    # Ищем самый свежий HTML
    reports_dir = ROOT / "unified_reports"
    html_files = sorted(reports_dir.glob("service_report_*.html"))
    if html_files:
        latest = html_files[-1]
        print(f"  HTML: {latest.name}")

        # Пробуем Microsoft Edge headless для скриншота
        import subprocess
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge = next((p for p in edge_paths if Path(p).exists()), None)
        out_png = OUT_DIR / "service-report.png"
        if edge:
            try:
                subprocess.run([
                    edge,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--window-size=1200,1800",
                    f"--screenshot={out_png}",
                    f"file:///{latest.as_posix()}",
                ], timeout=30, capture_output=True)
                if out_png.exists():
                    print(f"  → service-report.png (via Edge headless)")
                else:
                    print(f"  ! Edge did not produce screenshot")
            except Exception as e:
                print(f"  ! Edge headless failed: {e}")
        else:
            print("  ! Microsoft Edge not found — service-report.png skipped")

    root.destroy()
    print("\nDone.")


if __name__ == "__main__":
    main()
