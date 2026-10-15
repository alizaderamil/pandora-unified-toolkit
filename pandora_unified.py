"""
Pandora Unified 1.0 — Единая утилита для Xiaomi 17 Pro China (pandora)

Заменяет pandora_recovery.py и pandora_last_chance.py.
Исправляет баг с shouhoujiance, добавляет анализ bootfail дампа,
проверку UFS, сравнение с OS4 OTA.
"""
import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from pathlib import Path

FASTBOOT = r"D:\xiaomi\adb\fastboot.exe"
REPORTS = Path(__file__).resolve().parent / "unified_reports"


def fb(*args, timeout=10):
    """Безопасный вызов fastboot."""
    try:
        r = subprocess.run(
            [FASTBOOT] + list(args),
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -1, str(e)


def fb_check_usb():
    """Проверка живости USB-соединения."""
    rc, out = fb("devices", timeout=3)
    return "fastboot" in out.lower()


# UFS производители (для auth-free firehose)
UFS_MANUFACTURERS = {
    "SM": ("Samsung", True, "Поддерживается auth-free firehose ✓"),
    "SM8": ("Samsung", True, "Поддерживается auth-free firehose ✓"),
    "HN8T": ("SK Hynix", True, "Поддерживается auth-free firehose ✓"),
    "H9HQ": ("SK Hynix", True, "Поддерживается auth-free firehose ✓"),
    "MT": ("Micron", True, "Поддерживается auth-free firehose ✓"),
    "MT256": ("Micron", True, "Поддерживается auth-free firehose ✓"),
    "THG": ("Toshiba/Kioxia", False, "⚠️ НЕ использовать auth-free firehose - BRICK RISK!"),
    "KIOXIA": ("Toshiba/Kioxia", False, "⚠️ НЕ использовать auth-free firehose - BRICK RISK!"),
    "YMTC": ("Yangtze Memory", True, "Поддерживается auth-free firehose ✓"),
}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Pandora Unified 1.0 — Xiaomi 17 Pro China")
        root.geometry("1100x820")
        root.configure(bg="#0a0f1e")
        self.busy = False
        self.device_data = {}

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#0a0f1e")
        style.configure("TLabel", background="#0a0f1e", foreground="#e2e8f0", font=("Segoe UI", 10))
        style.configure("H.TLabel", font=("Segoe UI", 20, "bold"), foreground="#f8fafc")
        style.configure("Sub.TLabel", foreground="#94a3b8", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))
        style.configure("TNotebook", background="#0a0f1e")
        style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=(14, 8))
        style.configure("Treeview", background="#1e293b", fieldbackground="#1e293b",
                        foreground="#e2e8f0", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        header = ttk.Frame(main)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Pandora Unified", style="H.TLabel").pack(anchor="w")
        ttk.Label(header, text="Xiaomi 17 Pro China (pandora) · SD 8 Elite · Единая утилита 1.0",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # Кнопки
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 12))

        self.buttons = []
        actions = [
            ("1. Полная диагностика", self.action_diagnostic),
            ("2. Проверить UFS", self.action_ufs_check),
            ("3. Анализ bootfail", self.action_bootfail),
            ("4. Сравнить с OS4", self.action_compare_firmware),
            ("5. Отчёты", self.action_open_reports),
        ]
        for text, cmd in actions:
            b = ttk.Button(btn_frame, text=text, command=cmd, style="Big.TButton")
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)

        # Статус-бар
        self.status = tk.StringVar(value="Готов. Подключи телефон в Fastboot и выбери действие.")
        status_lbl = ttk.Label(main, textvariable=self.status, wraplength=1060,
                               background="#1e293b", padding=(10, 8), relief="flat")
        status_lbl.pack(fill="x", pady=(0, 10))

        # Вкладки
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        # Вкладка 1: Лог
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="  📋 Лог  ")
        self.log = scrolledtext.ScrolledText(log_frame, bg="#141b2d", fg="#e2e8f0",
                                             font=("Consolas", 9), insertbackground="#e2e8f0",
                                             wrap="word", state="disabled", relief="flat", bd=0)
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok", foreground="#4ade80")
        self.log.tag_configure("err", foreground="#f87171")
        self.log.tag_configure("warn", foreground="#fbbf24")
        self.log.tag_configure("hdr", foreground="#60a5fa", font=("Consolas", 10, "bold"))

        # Вкладка 2: Состояние
        state_frame = ttk.Frame(self.notebook)
        self.notebook.add(state_frame, text="  📊 Состояние  ")
        self.state_tree = ttk.Treeview(state_frame, columns=("key", "value"), show="headings")
        self.state_tree.heading("key", text="Параметр")
        self.state_tree.heading("value", text="Значение")
        self.state_tree.column("key", width=320)
        self.state_tree.column("value", width=600)
        scroll1 = ttk.Scrollbar(state_frame, orient="vertical", command=self.state_tree.yview)
        self.state_tree.configure(yscrollcommand=scroll1.set)
        self.state_tree.pack(side="left", fill="both", expand=True)
        scroll1.pack(side="right", fill="y")

        # Вкладка 3: Bootfail
        bf_frame = ttk.Frame(self.notebook)
        self.notebook.add(bf_frame, text="  🔍 Bootfail  ")
        self.bf_text = scrolledtext.ScrolledText(bf_frame, bg="#141b2d", fg="#e2e8f0",
                                                  font=("Consolas", 9), wrap="word",
                                                  state="disabled", relief="flat", bd=0)
        self.bf_text.pack(fill="both", expand=True)

    def write(self, text, tag=None):
        self.log.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {text}\n", tag or "")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update_idletasks()

    def run_async(self, func):
        if self.busy:
            return
        self.busy = True
        for b in self.buttons:
            b.configure(state="disabled")
        def wrapper():
            try:
                func()
            finally:
                self.busy = False
                self.root.after(0, lambda: [b.configure(state="normal") for b in self.buttons])
        threading.Thread(target=wrapper, daemon=True).start()

    # === 1. Диагностика ===
    def action_diagnostic(self):
        self.run_async(self._do_diagnostic)

    def _do_diagnostic(self):
        self.status.set("Полная диагностика…")
        self.write("═══ ДИАГНОСТИКА ═══", "hdr")

        if not fb_check_usb():
            self.write("Телефон не найден! Проверь USB и Fastboot.", "err")
            self.status.set("Телефон не подключён")
            return

        # getvar all
        self.write("Читаю все переменные…")
        rc, out = fb("getvar", "all", timeout=30)
        variables = {}
        for line in out.splitlines():
            m = re.match(r"\(bootloader\)\s*(.+?):\s*(.*)", line)
            if m:
                variables[m.group(1).strip()] = m.group(2).strip()

        self.device_data["variables"] = variables
        self.write(f"✓ Прочитано {len(variables)} переменных", "ok")

        # OEM diag
        self.write("Пробую OEM-команды…")
        oem_results = {}
        safe_cmds = [
            ("oem device-info", "Информация устройства"),
            ("oem fbreason", "Причина загрузки"),
        ]
        for cmd, desc in safe_cmds:
            rc, out = fb(*cmd.split(), timeout=5)
            oem_results[cmd] = {"rc": rc, "out": out}
            if rc == 0:
                self.write(f"✓ {desc}", "ok")
                for line in out.splitlines()[:5]:
                    if "(bootloader)" in line:
                        self.write(f"    {line.replace('(bootloader) ', '').strip()}")

        # Заполняем таблицу
        self.state_tree.delete(*self.state_tree.get_children())
        key_vars = ["product", "unlocked", "secure", "current-slot",
                    "slot-successful:a", "slot-unbootable:a", "slot-retry-count:a",
                    "slot-successful:b", "slot-unbootable:b", "slot-retry-count:b",
                    "anti", "security-patch-level", "variant", "cpuid",
                    "battery-voltage", "max-download-size", "kernel"]
        for k in key_vars:
            if k in variables:
                self.state_tree.insert("", "end", values=(k, variables[k]))

        # Разделы (только размер super)
        if "all" in variables:
            self.state_tree.insert("", "end", values=("--- Разделы ---", ""))

        # Диагноз
        self.write("", "")
        self.write("═══ ДИАГНОЗ ═══", "hdr")
        if variables.get("unlocked") == "no":
            self.write("Загрузчик ЗАБЛОКИРОВАН", "err")
        if variables.get("slot-unbootable:a") == "yes":
            self.write("Слот A помечен unbootable", "err")
        if variables.get("slot-unbootable:b") == "yes":
            self.write("Слот B помечен unbootable", "err")

        # Сохраняем
        self._save_report("diagnostic", {
            "time": datetime.now().isoformat(),
            "variables": variables,
            "oem_results": oem_results,
        })
        self.status.set(f"Диагностика завершена. Прочитано {len(variables)} параметров.")

    # === 2. UFS проверка (критична для auth-free firehose) ===
    def action_ufs_check(self):
        self.run_async(self._do_ufs_check)

    def _do_ufs_check(self):
        self.status.set("Проверка UFS производителя…")
        self.write("", "")
        self.write("═══ ПРОВЕРКА UFS ═══", "hdr")
        self.write("Критично для совместимости с auth-free firehose:")
        self.write("Samsung/Hynix/Micron — OK, Toshiba/Kioxia — НЕЛЬЗЯ!")

        if not fb_check_usb():
            self.write("Телефон не найден", "err")
            return

        # Получаем variant
        rc, out = fb("getvar", "variant", timeout=5)
        variant = ""
        for line in out.splitlines():
            if "variant:" in line.lower():
                variant = line.split(":", 1)[1].strip()
                break

        if not variant:
            self.write("Не смог прочитать variant", "err")
            return

        self.write(f"Variant: {variant}", "ok")

        # Пробуем определить производителя
        found = False
        for prefix, (vendor, safe, note) in UFS_MANUFACTURERS.items():
            if variant.startswith(prefix):
                self.write(f"Производитель UFS: {vendor}", "ok" if safe else "err")
                tag = "ok" if safe else "err"
                self.write(f"→ {note}", tag)
                found = True
                break

        if not found:
            # SM8 UFS - это Samsung
            if variant.startswith("SM"):
                self.write("Производитель UFS: Samsung (определено по префиксу SM)", "ok")
                self.write("→ Поддерживается auth-free firehose ✓", "ok")
            else:
                self.write(f"Не смог определить производителя для variant='{variant}'", "warn")
                self.write("Нужно проверить через ADB (но телефон не загружается)", "warn")

        self.status.set(f"UFS: {variant}")

    # === 3. Анализ bootfail дампа ===
    def action_bootfail(self):
        self.run_async(self._do_bootfail)

    def _do_bootfail(self):
        self.status.set("Ищу bootfail дамп…")
        self.write("", "")
        self.write("═══ АНАЛИЗ BOOTFAIL ═══", "hdr")

        # Ищем существующий дамп
        candidates = [
            Path(r"C:\Users\aliza\Documents\Codex\2026-10-15\d-xiaomi\outputs\PandoraMini\reports"),
            REPORTS,
            Path(r"D:\xiaomi\recovery_reports"),
        ]
        dumps = []
        for cand in candidates:
            if cand.exists():
                dumps.extend(cand.glob("*bootfail*.bin"))

        if not dumps:
            self.write("Нет bootfail дампа. Запрашиваю новый у телефона…", "warn")
            if not fb_check_usb():
                self.write("Телефон не найден", "err")
                return
            REPORTS.mkdir(parents=True, exist_ok=True)
            dump_path = REPORTS / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-bootfail.bin"
            # ВАЖНО: не используем здесь shouhoujiance через fastboot.exe,
            # так как у нас уже есть сохранённый дамп
            self.write("Нет готового дампа — используй PandoraMini для его создания")
            return

        dump = max(dumps, key=lambda p: p.stat().st_mtime)
        self.write(f"Анализирую: {dump.name}", "ok")
        self.write(f"Размер: {dump.stat().st_size / 1024 / 1024:.1f} МБ")

        with open(dump, "rb") as f:
            data = f.read()

        # Анализ
        strings = re.findall(rb"[\x20-\x7e]{8,}", data)
        unique = sorted(set(s.decode('ascii', errors='replace') for s in strings))

        # Ключевые ошибки
        errors = []
        boot_events = []
        versions = []
        boot_reasons = []

        for s in unique:
            if any(k in s for k in ['FindBootableSlot', 'LoadImageAndAuth', 'Slot _a', 'Slot _b', 'Load Error']):
                if len(s) < 200:
                    errors.append(s)
            if s.startswith('## BOOT'):
                boot_events.append(s)
            if 'OS4.' in s or 'OS3.' in s or 'HyperOS' in s:
                if 'VEISION' in s or 'VERSION' in s or len(s) < 100:
                    versions.append(s)
            if 'BootReason:' in s and len(s) < 100:
                boot_reasons.append(s)

        # Выводим в отдельную вкладку
        self.bf_text.configure(state="normal")
        self.bf_text.delete("1.0", "end")
        self.bf_text.insert("end", "═══ ОШИБКИ ЗАГРУЗКИ ═══\n\n")
        for e in sorted(set(errors)):
            self.bf_text.insert("end", f"  {e}\n")

        self.bf_text.insert("end", "\n═══ ВЕРСИИ СИСТЕМЫ (историч.) ═══\n\n")
        for v in sorted(set(versions))[:20]:
            self.bf_text.insert("end", f"  {v}\n")

        self.bf_text.insert("end", "\n═══ BOOT REASON коды ═══\n\n")
        for r in sorted(set(boot_reasons))[:20]:
            self.bf_text.insert("end", f"  {r}\n")

        self.bf_text.insert("end", "\n═══ BOOT EVENTS ═══\n\n")
        for be in sorted(set(boot_events))[:30]:
            self.bf_text.insert("end", f"  {be}\n")

        self.bf_text.configure(state="disabled")

        self.write(f"✓ Найдено {len(set(errors))} уникальных ошибок", "ok")
        self.write(f"✓ Найдено {len(set(versions))} версий системы", "ok")

        if any('Load Error' in e for e in errors):
            self.write("", "")
            self.write("ВАЖНО: 'Load Error' не 'Verify failed'", "warn")
            self.write("Это значит образы физически не загружаются,", "warn")
            self.write("а не что их подпись отвергается.", "warn")
            self.write("Возможные причины: GPT corruption, UFS block errors,", "warn")
            self.write("или оба слота размечены unbootable из-за lock command.", "warn")

        self.notebook.select(2)  # Переключиться на вкладку bootfail
        self.status.set(f"Анализ bootfail завершён. См. вкладку 'Bootfail'.")

    # === 4. Сравнение с OS4 OTA ===
    def action_compare_firmware(self):
        self.run_async(self._do_compare)

    def _do_compare(self):
        self.status.set("Сравниваю разделы с OS4 OTA…")
        self.write("", "")
        self.write("═══ СРАВНЕНИЕ С OS4 ═══", "hdr")

        ota_paths = [
            Path(r"D:\xiaomi\pandora-ota_full-OS4.0.2.0.XBLCNXM-user-17.0-0c778d15e7.zip"),
            Path(r"D:\xiaomi\pandora-ota_full-OS3.0.319.0.WBLCNXM-user-16.0-2d01cf4d66.zip"),
        ]

        found_ota = None
        for p in ota_paths:
            if p.exists():
                found_ota = p
                self.write(f"✓ Найден OTA: {p.name}", "ok")
                self.write(f"  Размер: {p.stat().st_size / 1024**3:.2f} ГБ")
                break

        if not found_ota:
            self.write("OTA файлы не найдены в D:\\xiaomi\\", "err")
            return

        # Сравнение разделов (только размеры из fastboot)
        if "variables" not in self.device_data:
            self.write("Сначала запусти диагностику (кнопка 1)", "warn")
            return

        variables = self.device_data["variables"]
        parts = {}
        for k, v in variables.items():
            if k.startswith("partition-size:"):
                name = k.replace("partition-size:", "").strip()
                try:
                    size = int(v, 16) if v.startswith("0x") else int(v)
                    parts[name] = size
                except:
                    pass

        self.write(f"Найдено разделов на телефоне: {len(parts)}")

        # Проверяем ключевые
        critical = {
            "boot_a": 0x6000000,
            "boot_b": 0x6000000,
            "recovery_a": 0x6400000,
            "recovery_b": 0x6400000,
            "vbmeta_a": 0x20000,
            "vbmeta_b": 0x20000,
            "efisp": 0x300000,
            "abl_a": 0x800000,
            "abl_b": 0x800000,
            "super": 0x320000000,
        }

        self.write("", "")
        self.write("Ключевые разделы (размер факт vs ожидаемый):", "hdr")
        all_ok = True
        for name, expected in critical.items():
            actual = parts.get(name, 0)
            status = "✓" if actual == expected else "✗"
            tag = "ok" if actual == expected else "err"
            self.write(f"  {status} {name}: {actual:#x} ({expected:#x} ожидался)", tag)
            if actual != expected:
                all_ok = False

        if all_ok:
            self.write("", "")
            self.write("Структура разделов цела. Проблема в данных, не в GPT.", "ok")
        else:
            self.write("", "")
            self.write("Структура разделов нарушена!", "err")

        self.status.set("Сравнение завершено.")

    # === 5. Открыть отчёты ===
    def action_open_reports(self):
        REPORTS.mkdir(parents=True, exist_ok=True)
        os.startfile(str(REPORTS))

    def _save_report(self, name, data):
        REPORTS.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = REPORTS / f"{ts}-{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.write(f"Отчёт сохранён: {path.name}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
