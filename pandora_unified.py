"""
Pandora Unified 1.1 — Единая утилита для Xiaomi 17 Pro China (pandora)

Заменяет pandora_recovery.py и pandora_last_chance.py.
Исправляет баг с shouhoujiance, добавляет анализ bootfail дампа,
проверку UFS, сравнение с OS4 OTA.

v1.1 (2026-10-21, после chip-off ремонта):
  + Lock Wizard — правильная последовательность блокировки
  + Snapshot — бэкап getvar/token перед опасной операцией
  + Service Report — HTML отчёт для сервисного центра
  + Pre-flight confirm — предупреждение перед опасными командами
  + UFS Health — benchmark скорости после chip-off (baseline → compare)
"""
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
import zipfile
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from pathlib import Path

FASTBOOT = r"D:\xiaomi\adb\fastboot.exe"
ADB = r"D:\xiaomi\adb\adb.exe"
REPORTS = Path(__file__).resolve().parent / "unified_reports"
LESSONS = Path(__file__).resolve().parent / "LESSONS_LEARNED.md"
UFS_BASELINE = REPORTS / "ufs_baseline.json"


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


def adb_cmd(*args, timeout=15):
    """Безопасный вызов adb."""
    try:
        r = subprocess.run(
            [ADB] + list(args),
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -1, str(e)


def adb_check():
    """Проверка adb-соединения (телефон загружен в Android)."""
    rc, out = adb_cmd("devices", timeout=3)
    for line in out.splitlines():
        if "\tdevice" in line:
            return True
    return False


# Авторизованные/проверенные сервисы для Xiaomi 17 Pro China (SM8850)
SERVICE_CONTACTS = [
    {
        "name": "Mobil Hafiz telefon servisi",
        "method": "Chip-off NAND/UFS",
        "price_aznish": "300 AZN",
        "warranty": "6 месяцев",
        "proven": True,
        "notes": "Успешно восстановил этот телефон 2026-10-21. Инфракрасная станция.",
    },
    {
        "name": "UMcrew / @three_tools_gsm",
        "method": "Firehose loader (приватный)",
        "price_aznish": "~$80-150",
        "warranty": "Нет",
        "proven": False,
        "notes": "Коммерческий Telegram-сервис, работает удалённо.",
    },
]


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
        root.title("Pandora Unified 1.1 — Xiaomi 17 Pro China")
        root.geometry("1200x860")
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
        ttk.Label(header, text="Xiaomi 17 Pro China (pandora) · SD 8 Elite · Единая утилита 1.1",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # Кнопки — ряд 1 (диагностика)
        btn_frame1 = ttk.Frame(main)
        btn_frame1.pack(fill="x", pady=(0, 6))

        self.buttons = []
        row1_actions = [
            ("1. Полная диагностика", self.action_diagnostic),
            ("2. Проверить UFS", self.action_ufs_check),
            ("3. Анализ bootfail", self.action_bootfail),
            ("4. Сравнить с OS4", self.action_compare_firmware),
            ("5. Отчёты", self.action_open_reports),
        ]
        for text, cmd in row1_actions:
            b = ttk.Button(btn_frame1, text=text, command=cmd, style="Big.TButton")
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)

        # Кнопки — ряд 2 (защита + сервис + здоровье)
        btn_frame2 = ttk.Frame(main)
        btn_frame2.pack(fill="x", pady=(0, 12))

        row2_actions = [
            ("🔒 Lock Wizard", self.action_lock_wizard),
            ("📸 Snapshot (бэкап)", self.action_snapshot),
            ("🏥 Отчёт для сервиса", self.action_service_report),
            ("📊 UFS Health", self.action_ufs_health),
            ("📖 LESSONS_LEARNED", self.action_open_lessons),
        ]
        for text, cmd in row2_actions:
            b = ttk.Button(btn_frame2, text=text, command=cmd, style="Big.TButton")
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

    # === Открыть LESSONS_LEARNED.md ===
    def action_open_lessons(self):
        if LESSONS.exists():
            os.startfile(str(LESSONS))
        else:
            messagebox.showwarning(
                "LESSONS_LEARNED.md не найден",
                f"Файл отсутствует:\n{LESSONS}\n\n"
                "Скачай его из репозитория "
                "https://github.com/alizaderamil/xiaomi-pandora-recovery",
            )

    # === Pre-flight confirm — универсальная защита перед опасной операцией ===
    def _confirm_dangerous(self, title, what, consequences, reference=None):
        """
        Модальное окно подтверждения опасной операции.
        Возвращает True если пользователь согласился продолжить.
        """
        msg = (
            f"⚠️  ОПАСНАЯ ОПЕРАЦИЯ: {title}\n\n"
            f"Что произойдёт:\n{what}\n\n"
            f"Последствия:\n{consequences}\n\n"
        )
        if reference:
            msg += f"Прочитай: {reference}\n\n"
        msg += "Прочитал LESSONS_LEARNED.md и уверен?\n"
        msg += "(Нажми 'Нет' если сомневаешься — ничего не выполнится)"
        return messagebox.askyesno(title, msg, icon="warning", default="no")

    # === 🔒 Lock Wizard — правильная последовательность блокировки ===
    def action_lock_wizard(self):
        self._show_lock_wizard()

    def _show_lock_wizard(self):
        win = tk.Toplevel(self.root)
        win.title("🔒 Lock Wizard — правильная блокировка bootloader")
        win.geometry("820x680")
        win.configure(bg="#0a0f1e")
        win.transient(self.root)

        frame = ttk.Frame(win, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Правильная блокировка bootloader", style="H.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="После НЕОФИЦИАЛЬНОЙ (эксплойт) разблокировки — следуй ТОЧНО этим шагам.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        warning_frame = tk.Frame(frame, bg="#7f1d1d", padx=12, pady=10)
        warning_frame.pack(fill="x", pady=(0, 12))
        tk.Label(
            warning_frame,
            text="❌ НАША ОШИБКА 2026-10-15:",
            bg="#7f1d1d", fg="#fecaca",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            warning_frame,
            text=(
                "Выполнили:  fastboot erase efisp  →  fastboot oem lock\n"
                "Результат:  Device unlocked:false, но Play Protect всё равно отказал,\n"
                "            а потом телефон стуck в Fastboot и пришёл chip-off ремонт."
            ),
            bg="#7f1d1d", fg="#fecaca",
            font=("Consolas", 9), justify="left",
        ).pack(anchor="w", pady=(4, 0))

        steps_text = scrolledtext.ScrolledText(
            frame, bg="#141b2d", fg="#e2e8f0",
            font=("Consolas", 10), wrap="word", height=18, relief="flat", bd=0,
        )
        steps_text.pack(fill="both", expand=True)

        steps = """
✅ ПРАВИЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ (3 шага):

══════════════════════════════════════════════════════════════
ШАГ 1. Прошить СТОКОВУЮ ОФИЦИАЛЬНУЮ прошивку
──────────────────────────────────────────────────────────────
   • Никаких Magisk, TWRP, кастомов, LSPosed.
   • Через MiFlash (БЕЗ флага clean_all_and_lock, обычный flash_all).
   • Убедись что Android грузится и работает нормально.
   • Проверь: Settings → About phone → MIUI version.

══════════════════════════════════════════════════════════════
ШАГ 2. Удалить метку эксплойта из efisp
──────────────────────────────────────────────────────────────
   Перезагрузи в fastboot и выполни ТОЛЬКО это:

       fastboot erase efisp

   ⚠️  НЕ выполняй сейчас  fastboot oem lock !
   ⚠️  НЕ загружай систему между шагами 2 и 3!

══════════════════════════════════════════════════════════════
ШАГ 3. Повторная прошивка с флагом clean_all_and_lock
──────────────────────────────────────────────────────────────
   Из fastboot (система не загружалась) запусти MiFlash снова:

       miflash_pro.exe → выбери ту же прошивку →
       → опция "clean_all_and_lock" (clear_all_lock) → Flash

   После этого телефон:
       • перезагрузится в стоковый Android
       • bootloader будет ЗАЛОЧЕН
       • Verified Boot зелёный, Play Protect пройдёт

══════════════════════════════════════════════════════════════

💡 Почему  fastboot oem lock  сам по себе НЕ работает:

   Эксплойт-разлочка оставляет следы в системных разделах,
   не только в efisp/RPMB. "oem lock" меняет lock state, но
   не чистит эти следы. Verified Boot при загрузке видит
   остатки и отказывает.

   Только  clean_all_and_lock  переписывает все разделы
   заново под Verified Boot атомарно.

══════════════════════════════════════════════════════════════
"""
        steps_text.insert("end", steps)
        steps_text.configure(state="disabled")

        # Кнопки
        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill="x", pady=(12, 0))

        def gen_batch():
            """Сгенерировать .bat файл-напоминалку для шага 2."""
            REPORTS.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            bat = REPORTS / f"{ts}-lock_step2.bat"
            bat.write_text(
                f'@echo off\r\n'
                f'echo === Lock Wizard: Step 2 ===\r\n'
                f'echo.\r\n'
                f'echo Это удалит метку эксплойт-разлочки из efisp.\r\n'
                f'echo ПОСЛЕ этого НЕ грузи систему и запусти MiFlash с clean_all_and_lock.\r\n'
                f'echo.\r\n'
                f'pause\r\n'
                f'"{FASTBOOT}" erase efisp\r\n'
                f'echo.\r\n'
                f'echo Теперь: закрой это окно, открой MiFlash, прошей ту же прошивку\r\n'
                f'echo с опцией clean_all_and_lock. НЕ ПЕРЕЗАГРУЖАЙ В СИСТЕМУ!\r\n'
                f'pause\r\n',
                encoding="cp866",
            )
            messagebox.showinfo(
                "Сгенерирован batch",
                f"Сохранён:\n{bat}\n\n"
                "Запусти его когда будешь ГОТОВ к шагу 2.\n"
                "Он выполнит только  fastboot erase efisp  и напомнит про шаг 3.",
            )

        ttk.Button(btn_bar, text="📝 Создать batch для шага 2", command=gen_batch).pack(side="left")
        ttk.Button(btn_bar, text="📖 Открыть LESSONS_LEARNED.md",
                   command=self.action_open_lessons).pack(side="left", padx=(8, 0))
        ttk.Button(btn_bar, text="Закрыть", command=win.destroy).pack(side="right")

    # === 📸 Snapshot — бэкап getvar + token перед опасной операцией ===
    def action_snapshot(self):
        self.run_async(self._do_snapshot)

    def _do_snapshot(self):
        self.status.set("Делаю snapshot текущего состояния…")
        self.write("", "")
        self.write("═══ SNAPSHOT (бэкап перед операцией) ═══", "hdr")

        if not fb_check_usb():
            self.write("Телефон не найден в Fastboot!", "err")
            self.write("Snapshot делается в режиме Fastboot. Переведи телефон туда.", "warn")
            return

        REPORTS.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        tmp_dir = REPORTS / f"snapshot_{ts}"
        tmp_dir.mkdir(exist_ok=True)

        snapshot = {
            "time": datetime.now().isoformat(),
            "fastboot_version": None,
            "getvar_all": {},
            "oem_commands": {},
            "dynamic_token": None,
        }

        # fastboot version
        rc, out = fb("--version", timeout=3)
        snapshot["fastboot_version"] = out.splitlines()[0] if out else "?"
        self.write(f"Fastboot: {snapshot['fastboot_version']}")

        # getvar all
        self.write("Читаю getvar all…")
        rc, out = fb("getvar", "all", timeout=30)
        (tmp_dir / "getvar_all.txt").write_text(out, encoding="utf-8")
        for line in out.splitlines():
            m = re.match(r"\(bootloader\)\s*(.+?):\s*(.*)", line)
            if m:
                snapshot["getvar_all"][m.group(1).strip()] = m.group(2).strip()
        self.write(f"✓ Сохранено {len(snapshot['getvar_all'])} переменных", "ok")

        # OEM команды (безопасные)
        oem_cmds = [
            ("oem device-info", "device_info"),
            ("oem fbreason", "boot_reason"),
            ("oem get-token", "dynamic_token"),
        ]
        for cmd, label in oem_cmds:
            parts = cmd.split()
            rc, out = fb(*parts, timeout=8)
            snapshot["oem_commands"][cmd] = {"rc": rc, "out": out}
            (tmp_dir / f"{label}.txt").write_text(out, encoding="utf-8")
            if rc == 0:
                self.write(f"✓ {cmd}", "ok")
            else:
                self.write(f"✗ {cmd}: {out[:60]}", "warn")

        # Извлечём dynamic token отдельно
        token_out = snapshot["oem_commands"].get("oem get-token", {}).get("out", "")
        for line in token_out.splitlines():
            m = re.search(r"[A-Za-z0-9+/_-]{32,}=*", line)
            if m and len(m.group(0)) > 30:
                snapshot["dynamic_token"] = m.group(0)
                break
        if snapshot["dynamic_token"]:
            self.write(f"✓ Dynamic token извлечён ({len(snapshot['dynamic_token'])} символов)", "ok")

        # JSON
        (tmp_dir / "snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Упаковываем в zip
        zip_path = REPORTS / f"snapshot_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f_ in tmp_dir.iterdir():
                zf.write(f_, arcname=f_.name)

        # Удаляем временную папку
        for f_ in tmp_dir.iterdir():
            f_.unlink()
        tmp_dir.rmdir()

        self.write("", "")
        self.write(f"✓ Snapshot сохранён: {zip_path.name}", "ok")
        self.write(f"  Размер: {zip_path.stat().st_size / 1024:.1f} КБ")
        self.write("  Храни этот файл перед любой опасной операцией!", "warn")
        self.status.set(f"Snapshot: {zip_path.name}")

    # === 🏥 Service Report — HTML отчёт для сервисного центра ===
    def action_service_report(self):
        self.run_async(self._do_service_report)

    def _do_service_report(self):
        self.status.set("Генерирую отчёт для сервисного центра…")
        self.write("", "")
        self.write("═══ ОТЧЁТ ДЛЯ СЕРВИСА ═══", "hdr")

        # Собираем свежие данные если есть телефон
        variables = self.device_data.get("variables", {})
        if not variables and fb_check_usb():
            self.write("Собираю свежие данные…")
            rc, out = fb("getvar", "all", timeout=30)
            for line in out.splitlines():
                m = re.match(r"\(bootloader\)\s*(.+?):\s*(.*)", line)
                if m:
                    variables[m.group(1).strip()] = m.group(2).strip()
            self.device_data["variables"] = variables

        if not variables:
            self.write("Нет данных диагностики. Запусти Полную диагностику или подключи телефон.", "warn")

        REPORTS.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        html_path = REPORTS / f"service_report_{ts}.html"

        # Собираем все предыдущие отчёты
        prev_reports = sorted(REPORTS.glob("*-diagnostic.json"))[-5:]
        prev_summary = []
        for p in prev_reports:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                prev_summary.append({
                    "file": p.name,
                    "time": d.get("time", "?"),
                    "vars_count": len(d.get("variables", {})),
                })
            except Exception:
                pass

        def row(k, v, tag=""):
            cls = f' class="{tag}"' if tag else ""
            return f"<tr><td class='k'>{html.escape(k)}</td><td{cls}>{html.escape(str(v))}</td></tr>"

        tried_methods = [
            ("fastboot getvar / oem device-info", "OK", "Диагностика работает"),
            ("MiFlash clean_all_and_lock", "FAIL", "Телефон не входит в EDL"),
            ("EDL кабель (COM port)", "FAIL", "Требует подписанный Firehose loader для SM8850"),
            ("TWRP boot (fastboot boot)", "FAIL", "Verified Boot блокирует неподписанные образы"),
            ("GBL exploit (gbl_efi_unlock.efi)", "FAIL", "efisp стёрт + патч закрыл дыру в HyperOS 3.0.304+"),
            ("UnlockerBL_8EG5_v2 повторно", "FAIL", "Требует разблокированный загрузчик"),
            ("Публичные Firehose loaders", "FAIL", "Для SM8850 (Snapdragon 8 Elite) не опубликованы"),
        ]

        services_html = ""
        for s in SERVICE_CONTACTS:
            badge = "✓ ПРОВЕРЕН" if s["proven"] else "не проверен"
            badge_cls = "ok" if s["proven"] else "warn"
            services_html += f"""
            <div class="service">
              <h4>{html.escape(s['name'])} <span class="badge {badge_cls}">{badge}</span></h4>
              <p><b>Метод:</b> {html.escape(s['method'])}</p>
              <p><b>Цена:</b> {html.escape(s['price_aznish'])} · <b>Гарантия:</b> {html.escape(s['warranty'])}</p>
              <p class="notes">{html.escape(s['notes'])}</p>
            </div>"""

        rows_html = ""
        key_fields = [
            "product", "variant", "unlocked", "secure", "current-slot",
            "slot-unbootable:a", "slot-unbootable:b",
            "slot-successful:a", "slot-successful:b",
            "anti", "security-patch-level", "battery-voltage", "cpuid",
        ]
        for k in key_fields:
            v = variables.get(k, "—")
            tag = ""
            if k == "unlocked":
                tag = "err" if v == "no" else "ok"
            if "unbootable" in k and v == "yes":
                tag = "err"
            rows_html += row(k, v, tag)

        tried_html = ""
        for method, result, reason in tried_methods:
            cls = "ok" if result == "OK" else "err"
            tried_html += f"<tr><td>{html.escape(method)}</td><td class='{cls}'>{result}</td><td>{html.escape(reason)}</td></tr>"

        prev_html = ""
        for p in prev_summary:
            prev_html += f"<li><code>{html.escape(p['file'])}</code> — {html.escape(p['time'])} ({p['vars_count']} переменных)</li>"
        if not prev_html:
            prev_html = "<li><i>Нет предыдущих диагностик</i></li>"

        doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Pandora — Отчёт для сервиса ({ts})</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px;
         margin: 20px auto; padding: 20px; background: #f8fafc; color: #0f172a; }}
  h1 {{ color: #0f172a; border-bottom: 3px solid #ea580c; padding-bottom: 8px; }}
  h2 {{ color: #ea580c; margin-top: 32px; }}
  h3 {{ color: #0f172a; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; background: #fff; }}
  th, td {{ padding: 8px 12px; border: 1px solid #e2e8f0; text-align: left; }}
  th {{ background: #f1f5f9; }}
  td.k {{ font-family: Consolas, monospace; font-weight: 600; color: #475569; width: 240px; }}
  td.ok, span.ok {{ color: #16a34a; font-weight: 600; }}
  td.err, span.err {{ color: #dc2626; font-weight: 600; }}
  td.warn, span.warn {{ color: #ca8a04; font-weight: 600; }}
  .meta {{ background: #fff; padding: 16px; border-radius: 8px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  .warning {{ background: #fef2f2; border-left: 4px solid #dc2626; padding: 12px 16px; margin: 16px 0; }}
  .service {{ background: #fff; padding: 12px 16px; margin: 10px 0; border-radius: 8px;
              border-left: 4px solid #0284c7; }}
  .badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge.ok {{ background: #dcfce7; color: #166534; }}
  .badge.warn {{ background: #fef3c7; color: #92400e; }}
  .notes {{ color: #64748b; font-size: 13px; margin: 4px 0 0; }}
  code {{ font-family: Consolas, monospace; background: #f1f5f9; padding: 1px 6px; border-radius: 3px; }}
  footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0;
            color: #64748b; font-size: 12px; }}
</style>
</head>
<body>

<h1>📱 Отчёт для сервисного центра</h1>

<div class="meta">
  <h3>Устройство</h3>
  <table>
    <tr><td class="k">Модель</td><td>Xiaomi 17 Pro China (25098PN5AC)</td></tr>
    <tr><td class="k">Кодовое имя</td><td>pandora</td></tr>
    <tr><td class="k">Процессор</td><td>Snapdragon 8 Elite (SM8850)</td></tr>
    <tr><td class="k">UFS</td><td>{html.escape(variables.get("variant", "?"))}</td></tr>
    <tr><td class="k">Серийный</td><td>d5835558</td></tr>
    <tr><td class="k">Отчёт сгенерирован</td><td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
  </table>
</div>

<h2>⚠️ Текущее состояние</h2>
<table>
{rows_html}
</table>

<h2>❌ Что уже пробовали (программно)</h2>
<table>
  <tr><th>Метод</th><th>Результат</th><th>Причина</th></tr>
  {tried_html}
</table>

<div class="warning">
  <b>Вывод:</b> для CNXM ROM (Китай) + заблокированного SM8850 + стёртого efisp
  публичных программных методов восстановления <b>не существует</b>.
  Нужен либо коммерческий сервис с приватным Firehose loader,
  либо физический chip-off ремонт NAND/UFS.
</div>

<h2>📞 Проверенные/известные сервисы</h2>
{services_html}

<h2>📂 История диагностик</h2>
<ul>
{prev_html}
</ul>

<h2>💡 Что нужно от мастера</h2>
<ol>
  <li>Опыт с <b>Snapdragon 8 Elite / SM8850</b> и UFS 4.0 конкретно.</li>
  <li><b>Инфракрасная паяльная станция</b> (не фен) с трафаретом под UFS этой модели.</li>
  <li><b>Гарантия на пайку</b> минимум 3 месяца.</li>
  <li>Готовность <b>заменить UFS/CPU</b> если chip-off не удастся (цена заранее).</li>
  <li>Если возможно — <b>ISP вместо chip-off</b> (меньше риска, но на новых Xiaomi часто недоступно).</li>
</ol>

<footer>
  Сгенерировано Pandora Unified 1.1 ·
  Полный журнал восстановления:
  <a href="https://github.com/alizaderamil/xiaomi-pandora-recovery">github.com/alizaderamil/xiaomi-pandora-recovery</a>
</footer>

</body>
</html>"""

        html_path.write_text(doc, encoding="utf-8")
        self.write(f"✓ Отчёт сохранён: {html_path.name}", "ok")
        self.write(f"  Путь: {html_path}")
        self.write("  Открываю в браузере…")

        try:
            webbrowser.open(f"file:///{html_path.as_posix()}")
        except Exception as e:
            self.write(f"Не смог открыть в браузере: {e}", "warn")

        self.status.set(f"Отчёт: {html_path.name}")

    # === 📊 UFS Health — benchmark после chip-off ===
    def action_ufs_health(self):
        self.run_async(self._do_ufs_health)

    def _do_ufs_health(self):
        self.status.set("UFS benchmark через ADB…")
        self.write("", "")
        self.write("═══ UFS HEALTH BENCHMARK ═══", "hdr")

        if not adb_check():
            self.write("ADB не видит телефон. Загрузи его в Android и включи USB-отладку.", "err")
            self.write("Если отладка выключена: Settings → About → MIUI 8 раз →", "warn")
            self.write("  Settings → Additional → Developer → USB debugging ON", "warn")
            self.status.set("ADB устройство не найдено")
            return

        # Получаем модель устройства для надёжности
        rc, model_out = adb_cmd("shell", "getprop", "ro.product.model", timeout=5)
        rc, codename_out = adb_cmd("shell", "getprop", "ro.product.name", timeout=5)
        model = model_out.strip()
        codename = codename_out.strip()
        self.write(f"Устройство: {model} ({codename})")

        # Предупреждение если это не pandora
        if codename and "pandora" not in codename.lower():
            self.write(f"⚠️  Внимание: это не pandora (codename={codename})", "warn")
            self.write("   Baseline будет записан в отдельный файл для этого устройства.", "warn")

        # Файл baseline отдельный для каждого устройства
        baseline_file = REPORTS / f"ufs_baseline_{codename or 'unknown'}.json"

        # ЗАПИСЬ (512 МБ, conv=fsync — физический сброс на UFS без кэша)
        # На Android toybox-dd нет iflag=nocache/oflag=sync, используем conv=fsync
        self.write("Тест ЗАПИСИ (512 МБ в /data/local/tmp, conv=fsync)…")
        adb_cmd("shell", "rm -f /data/local/tmp/_ufs_test", timeout=5)
        rc, out = adb_cmd(
            "shell",
            "dd if=/dev/zero of=/data/local/tmp/_ufs_test bs=1M count=512 conv=fsync 2>&1",
            timeout=120,
        )
        write_mbs = self._parse_dd_speed(out)
        if write_mbs:
            self.write(f"✓ Запись: {write_mbs:.1f} МБ/с", "ok")
        else:
            self.write(f"Не смог распарсить скорость записи: {out[:200]}", "warn")

        # Пытаемся «вытолкнуть» файл из page cache: пишем второй большой файл
        # На устройствах с ≤8 ГБ RAM это сбросит часть кэша. Не идеально, но без root
        # лучше нельзя. Если RAM >8 ГБ — чтение всё равно попадёт в кэш.
        self.write("Готовлю чтение (сбрасываю page cache через второй файл)…")
        adb_cmd(
            "shell",
            "dd if=/dev/zero of=/data/local/tmp/_cache_flush bs=1M count=2048 2>&1",
            timeout=120,
        )
        adb_cmd("shell", "rm -f /data/local/tmp/_cache_flush", timeout=10)

        # ЧТЕНИЕ (512 МБ)
        self.write("Тест ЧТЕНИЯ (512 МБ из /data/local/tmp)…")
        rc, out = adb_cmd(
            "shell",
            "dd if=/data/local/tmp/_ufs_test of=/dev/null bs=1M 2>&1",
            timeout=120,
        )
        read_mbs = self._parse_dd_speed(out)
        if read_mbs:
            self.write(f"✓ Чтение: {read_mbs:.1f} МБ/с", "ok")
            if read_mbs > 2500 and write_mbs and read_mbs > write_mbs * 2:
                self.write("   (вероятно частично из RAM-кэша — цифра оптимистичная)", "warn")
        else:
            self.write(f"Не смог распарсить скорость чтения: {out[:200]}", "warn")
        adb_cmd("shell", "rm -f /data/local/tmp/_ufs_test", timeout=5)

        # Сохраняем результат
        REPORTS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().isoformat()
        measurement = {
            "time": now,
            "device": {"model": model, "codename": codename},
            "read_mbs": read_mbs,
            "write_mbs": write_mbs,
        }

        # Baseline (отдельный для каждого устройства)
        if not baseline_file.exists():
            baseline_file.write_text(json.dumps(measurement, indent=2), encoding="utf-8")
            self.write("", "")
            self.write(f"📌 BASELINE сохранён: {baseline_file.name}", "hdr")
            self.write("   Запусти этот тест через месяц, затем через 6/12 месяцев.")
            self.write("   Если скорость упадёт >20% — пайка начинает деградировать.", "warn")
        else:
            baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
            self.write("", "")
            self.write(f"📊 Сравнение с baseline ({baseline['time']}):", "hdr")

            def pct(curr, base):
                if not curr or not base:
                    return None
                return (curr - base) / base * 100

            br = pct(read_mbs, baseline.get("read_mbs"))
            bw = pct(write_mbs, baseline.get("write_mbs"))

            if br is not None:
                tag = "ok" if br > -10 else ("warn" if br > -20 else "err")
                self.write(f"  Чтение: {read_mbs:.1f} vs {baseline['read_mbs']:.1f} МБ/с ({br:+.1f}%)", tag)
            if bw is not None:
                tag = "ok" if bw > -10 else ("warn" if bw > -20 else "err")
                self.write(f"  Запись: {write_mbs:.1f} vs {baseline['write_mbs']:.1f} МБ/с ({bw:+.1f}%)", tag)

            if (br is not None and br < -20) or (bw is not None and bw < -20):
                self.write("", "")
                self.write("⚠️  ВНИМАНИЕ: падение скорости >20%!", "err")
                self.write("   Возможные причины:", "err")
                self.write("     • Пайка после chip-off начинает деградировать", "err")
                self.write("     • Ячейки NAND износились", "err")
                self.write("   Рекомендую: ещё раз замерить через неделю,", "warn")
                self.write("   если тренд подтвердится — обратись в сервис по гарантии.", "warn")

        # История (одна общая, с полем device)
        history_path = REPORTS / "ufs_history.jsonl"
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(measurement, ensure_ascii=False) + "\n")
        self.write("", "")
        self.write(f"✓ История: {history_path.name}", "ok")
        rd = f"{read_mbs:.0f}" if read_mbs else "?"
        wr = f"{write_mbs:.0f}" if write_mbs else "?"
        self.status.set(f"UFS {codename or model}: R={rd} W={wr} МБ/с")

    def _parse_dd_speed(self, output):
        """Парсит скорость из вывода dd (МБ/с)."""
        for line in output.splitlines():
            # dd: "256+0 records in, ..., 268435456 bytes (256 MB) copied, X s, Y MB/s"
            m = re.search(r"([\d.]+)\s*(MB|GB|KB)/s", line)
            if m:
                v = float(m.group(1))
                unit = m.group(2)
                if unit == "GB":
                    return v * 1024
                if unit == "MB":
                    return v
                if unit == "KB":
                    return v / 1024
            # Альтернативный формат: "copied, 2.5 s, 102 MB/s"
            m = re.search(r"copied,.*?([\d.]+)\s*(MB|GB|KB)/s", line)
            if m:
                v = float(m.group(1))
                unit = m.group(2)
                if unit == "GB":
                    return v * 1024
                if unit == "MB":
                    return v
                if unit == "KB":
                    return v / 1024
        return None

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
