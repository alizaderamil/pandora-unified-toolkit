"""
Pandora Recovery 0.2 — Диагностика и попытка восстановления Xiaomi 17 Pro China (pandora)

Использует fastboot.exe для связи с телефоном.
Все операции логируются в папку reports.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime
from pathlib import Path

# Путь к fastboot
FASTBOOT_PATHS = [
    Path(r"D:\xiaomi\adb\fastboot.exe"),
    Path(r"D:\xiaomi\tools_r25.0.4\fastboot.exe"),
]

REPORTS_DIR = Path(__file__).resolve().parent / "recovery_reports"


def find_fastboot():
    for p in FASTBOOT_PATHS:
        if p.exists():
            return str(p)
    # Попробовать в PATH
    try:
        subprocess.run(["fastboot", "--version"], capture_output=True, timeout=5)
        return "fastboot"
    except Exception:
        return None


def run_fastboot(*args, timeout=15):
    """Запустить fastboot команду, вернуть (returncode, stdout, stderr)."""
    fb = find_fastboot()
    if not fb:
        return -1, "", "fastboot.exe не найден"
    try:
        result = subprocess.run(
            [fb] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Таймаут команды"
    except Exception as e:
        return -1, "", str(e)


def parse_getvar_all(stdout, stderr):
    """Разобрать вывод fastboot getvar all."""
    variables = {}
    for line in (stdout + "\n" + stderr).splitlines():
        # Формат: "(bootloader) key:value" или "key: value"
        m = re.match(r"\(bootloader\)\s*(.+?):\s*(.*)", line)
        if m:
            variables[m.group(1).strip()] = m.group(2).strip()
            continue
        m = re.match(r"([a-z][a-z0-9_\-:.]+):\s*(.*)", line, re.IGNORECASE)
        if m and m.group(1).lower() not in ("finished", "error"):
            variables[m.group(1).strip()] = m.group(2).strip()
    return variables


class PandoraRecovery:
    def __init__(self, root):
        self.root = root
        self.root.title("Pandora Recovery — Xiaomi 17 Pro")
        self.root.geometry("960x750")
        self.root.minsize(860, 700)
        self.root.configure(bg="#0f172a")
        self.busy = False
        self.log_lines = []

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        bg = "#0f172a"
        fg = "#e2e8f0"
        accent = "#3b82f6"
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#f8fafc")
        style.configure("Sub.TLabel", foreground="#94a3b8", font=("Segoe UI", 9))
        style.configure("Status.TLabel", foreground="#fbbf24", font=("Segoe UI", 10, "bold"))
        style.configure("Ok.TLabel", foreground="#4ade80", font=("Segoe UI", 10, "bold"))
        style.configure("Err.TLabel", foreground="#f87171", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 8))
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10))
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=(12, 6))

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        # Заголовок
        ttk.Label(main, text="Pandora Recovery", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="Xiaomi 17 Pro China (pandora)  ·  Версия 0.2", style="Sub.TLabel").pack(anchor="w", pady=(2, 8))

        # Статус
        self.status_var = tk.StringVar(value="Подключи телефон в режиме Fastboot и нажми кнопку.")
        self.status_label = ttk.Label(main, textvariable=self.status_var, wraplength=900)
        self.status_label.pack(anchor="w", pady=(0, 10))

        # Кнопки
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 10))

        self.buttons = []
        actions = [
            ("1. Полная диагностика", self.do_full_diagnostic),
            ("2. Попробовать EDL", self.do_try_edl),
            ("3. Список разделов", self.do_list_partitions),
            ("4. Открыть отчёты", self.open_reports),
        ]
        for text, cmd in actions:
            b = ttk.Button(btn_frame, text=text, command=cmd, style="Action.TButton")
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)

        # Вкладки
        notebook = ttk.Notebook(main)
        notebook.pack(fill="both", expand=True, pady=(5, 0))

        # Вкладка лог
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="  Лог  ")
        self.log_text = scrolledtext.ScrolledText(
            log_frame, bg="#1e293b", fg="#e2e8f0", font=("Consolas", 10),
            insertbackground="#e2e8f0", selectbackground="#3b82f6",
            wrap="word", state="disabled", relief="flat", bd=0
        )
        self.log_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Вкладка переменные
        var_frame = ttk.Frame(notebook)
        notebook.add(var_frame, text="  Переменные  ")
        self.var_tree = ttk.Treeview(var_frame, columns=("key", "value"), show="headings", height=20)
        self.var_tree.heading("key", text="Параметр")
        self.var_tree.heading("value", text="Значение")
        self.var_tree.column("key", width=350)
        self.var_tree.column("value", width=500)
        scrollbar = ttk.Scrollbar(var_frame, orient="vertical", command=self.var_tree.yview)
        self.var_tree.configure(yscrollcommand=scrollbar.set)
        self.var_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Нижняя строка
        ttk.Label(main, text="Утилита не отправляет данные в интернет. Все отчёты остаются на ПК.",
                  style="Sub.TLabel").pack(anchor="w", pady=(8, 0))

    def log(self, text, tag=None):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self.log_lines.append(line)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def set_status(self, text, style="TLabel"):
        self.status_var.set(text)
        self.status_label.configure(style=style)

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in self.buttons[:3]:  # Не блокируем кнопку отчётов
            b.configure(state=state)

    def run_in_thread(self, func):
        if self.busy:
            return
        self.set_busy(True)
        threading.Thread(target=func, daemon=True).start()

    def save_report(self, name, data):
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = REPORTS_DIR / f"{ts}-{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(f"Отчёт сохранён: {path.name}")
        return path

    def open_reports(self):
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(REPORTS_DIR))

    # === Полная диагностика ===
    def do_full_diagnostic(self):
        self.run_in_thread(self._full_diagnostic)

    def _full_diagnostic(self):
        self.set_status("Проверяю связь с телефоном…", "Status.TLabel")
        self.log("═══ Полная диагностика ═══")

        # 1. Проверка fastboot
        fb = find_fastboot()
        if not fb:
            self.log("ОШИБКА: fastboot.exe не найден в D:\\xiaomi\\adb или D:\\xiaomi\\tools_r25.0.4")
            self.set_status("fastboot.exe не найден!", "Err.TLabel")
            self.set_busy(False)
            return
        self.log(f"fastboot: {fb}")

        # 2. Проверка устройства
        self.log("Ищу подключённые устройства…")
        rc, out, err = run_fastboot("devices")
        devices = [l for l in (out + err).splitlines() if "fastboot" in l.lower()]
        if not devices:
            self.log("Устройство не найдено. Проверь USB-кабель и режим Fastboot.")
            self.set_status("Телефон не найден! Проверь подключение.", "Err.TLabel")
            self.set_busy(False)
            return
        self.log(f"Найдено: {devices[0].strip()}")

        # 3. getvar all
        self.log("Читаю все переменные (getvar all)…")
        rc, out, err = run_fastboot("getvar", "all", timeout=30)
        variables = parse_getvar_all(out, err)
        self.log(f"Прочитано переменных: {len(variables)}")

        # Заполнение таблицы
        self.var_tree.delete(*self.var_tree.get_children())
        for k, v in sorted(variables.items()):
            self.var_tree.insert("", "end", values=(k, v))

        # 4. Ключевые параметры
        product = variables.get("product", "?")
        unlocked = variables.get("unlocked", "?")
        slot = variables.get("current-slot", "?")
        secure = variables.get("secure", "?")
        anti = variables.get("anti", "?")

        self.log(f"Модель: {product}")
        self.log(f"Загрузчик: {'ЗАБЛОКИРОВАН' if unlocked == 'no' else unlocked}")
        self.log(f"Secure: {secure}")
        self.log(f"Активный слот: {slot}")
        self.log(f"Anti-rollback: {anti}")

        # Слоты
        for s in ("a", "b"):
            unb = variables.get(f"slot-unbootable:{s}", "?")
            suc = variables.get(f"slot-successful:{s}", "?")
            retry = variables.get(f"slot-retry-count:{s}", "?")
            self.log(f"Слот {s}: unbootable={unb}, successful={suc}, retry={retry}")

        # 5. Дополнительные OEM-команды (только чтение)
        self.log("Пробую информационные OEM-команды…")
        oem_cmds = [
            ("oem device-info", "Информация об устройстве"),
            ("oem fbreason", "Причина загрузки в Fastboot"),
            ("oem battery", "Батарея"),
        ]
        oem_results = {}
        for cmd, desc in oem_cmds:
            args = cmd.split()
            rc, out, err = run_fastboot(*args, timeout=10)
            result_text = (out + err).strip()
            oem_results[cmd] = {"rc": rc, "output": result_text}
            status = "OK" if rc == 0 else "отказ"
            self.log(f"  {desc} ({cmd}): {status}")
            for line in result_text.splitlines()[:5]:
                if line.strip():
                    self.log(f"    {line.strip()}")

        # 6. Итог
        report = {
            "time": datetime.now().isoformat(),
            "action": "full_diagnostic",
            "fastboot": fb,
            "devices": devices,
            "variables": variables,
            "oem_commands": oem_results,
        }
        self.save_report("diagnostic", report)

        if unlocked == "no":
            self.log("")
            self.log("═══ ИТОГ ═══")
            self.log("Загрузчик ЗАБЛОКИРОВАН.")
            self.log("Прошивка через fastboot flash невозможна в этом состоянии.")
            self.log("Варианты: EDL (кнопка 2), сервис, тестпоинты на плате.")
            self.set_status("Диагностика завершена. Загрузчик заблокирован, оба слота unbootable.", "Err.TLabel")
        else:
            self.set_status("Диагностика завершена.", "Ok.TLabel")

        self.set_busy(False)

    # === Попытка EDL ===
    def do_try_edl(self):
        self.run_in_thread(self._try_edl)

    def _try_edl(self):
        self.set_status("Пытаюсь перевести в EDL (9008)…", "Status.TLabel")
        self.log("")
        self.log("═══ Попытка перехода в EDL ═══")
        self.log("EDL (Emergency Download Mode / Qualcomm 9008) — режим")
        self.log("аварийного восстановления, работает ниже загрузчика.")
        self.log("")

        results = {}

        # Метод 1: oem edl
        self.log("Метод 1: fastboot oem edl")
        rc, out, err = run_fastboot("oem", "edl", timeout=10)
        result = (out + err).strip()
        results["oem_edl"] = {"rc": rc, "output": result}
        if rc == 0:
            self.log("  УСПЕХ! Телефон должен перейти в EDL.")
            self.log("  Проверь диспетчер устройств — ищи Qualcomm HS-USB QDLoader 9008.")
        else:
            self.log(f"  Отказ: {result}")

        # Метод 2: reboot edl
        self.log("Метод 2: fastboot reboot edl")
        rc, out, err = run_fastboot("reboot", "edl", timeout=10)
        result = (out + err).strip()
        results["reboot_edl"] = {"rc": rc, "output": result}
        if rc == 0:
            self.log("  Команда принята. Проверь диспетчер устройств.")
            self.log("  Если телефон вернулся в Fastboot — EDL не поддерживается командой.")
        else:
            self.log(f"  Отказ: {result}")

        # Метод 3: reboot emergency
        self.log("Метод 3: fastboot reboot emergency")
        rc, out, err = run_fastboot("reboot", "emergency", timeout=10)
        result = (out + err).strip()
        results["reboot_emergency"] = {"rc": rc, "output": result}
        if rc == 0:
            self.log("  Команда принята. Проверь диспетчер устройств.")
        else:
            self.log(f"  Отказ: {result}")

        # Метод 4: oem reboot-edl
        self.log("Метод 4: fastboot oem reboot-edl")
        rc, out, err = run_fastboot("oem", "reboot-edl", timeout=10)
        result = (out + err).strip()
        results["oem_reboot_edl"] = {"rc": rc, "output": result}
        if rc == 0:
            self.log("  Команда принята!")
        else:
            self.log(f"  Отказ: {result}")

        # Итог
        report = {
            "time": datetime.now().isoformat(),
            "action": "try_edl",
            "results": results,
        }
        self.save_report("edl-attempt", report)

        any_ok = any(r["rc"] == 0 for r in results.values())
        self.log("")
        if any_ok:
            self.log("═══ ОДНА ИЗ КОМАНД ПРИНЯТА ═══")
            self.log("Открой Диспетчер устройств Windows (devmgmt.msc).")
            self.log("Ищи: Порты (COM) → Qualcomm HS-USB QDLoader 9008")
            self.log("Если видишь 9008 — телефон в EDL, можно прошивать через MiFlash.")
            self.log("Если снова Fastboot — команда не сработала.")
            self.set_status("Команда EDL принята — проверь диспетчер устройств!", "Ok.TLabel")
        else:
            self.log("═══ ВСЕ МЕТОДЫ ОТКЛОНЕНЫ ═══")
            self.log("Программный переход в EDL не поддерживается.")
            self.log("")
            self.log("Оставшийся вариант — аппаратный (тестпоинты):")
            self.log("  1. Разобрать телефон")
            self.log("  2. Найти test point на плате (ищи схему для pandora)")
            self.log("  3. Замкнуть тестпоинт → телефон перейдёт в 9008")
            self.log("  4. Прошить через MiFlash или QFIL")
            self.log("")
            self.log("Это требует навыка и аккуратности. Лучше — в сервисе.")
            self.set_status("EDL через команды не поддерживается. Нужен аппаратный метод.", "Err.TLabel")

        self.set_busy(False)

    # === Список разделов ===
    def do_list_partitions(self):
        self.run_in_thread(self._list_partitions)

    def _list_partitions(self):
        self.set_status("Читаю список разделов…", "Status.TLabel")
        self.log("")
        self.log("═══ Список разделов ═══")

        # getvar all содержит partition-size:xxx
        rc, out, err = run_fastboot("getvar", "all", timeout=30)
        all_output = out + "\n" + err
        partitions = {}
        for line in all_output.splitlines():
            m = re.search(r"partition-size[:\s]+(\S+)[:\s]+0x([0-9a-fA-F]+)", line)
            if m:
                name = m.group(1)
                size_hex = m.group(2)
                size_bytes = int(size_hex, 16)
                partitions[name] = size_bytes

        if not partitions:
            # Попробуем другой формат
            for line in all_output.splitlines():
                m = re.search(r"\(bootloader\)\s*partition-size:(\S+):\s*0x([0-9a-fA-F]+)", line)
                if m:
                    partitions[m.group(1)] = int(m.group(2), 16)

        if partitions:
            self.log(f"Найдено разделов: {len(partitions)}")
            self.log("")
            self.log(f"{'Раздел':<30} {'Размер':>15}")
            self.log("─" * 50)
            for name, size in sorted(partitions.items()):
                if size > 1024 * 1024 * 1024:
                    size_str = f"{size / (1024**3):.1f} GB"
                elif size > 1024 * 1024:
                    size_str = f"{size / (1024**2):.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                self.log(f"  {name:<28} {size_str:>15}")

            # Ключевые разделы
            self.log("")
            key_parts = ["boot_a", "boot_b", "recovery_a", "recovery_b",
                         "system_a", "system_b", "vbmeta_a", "vbmeta_b",
                         "efisp", "modem_a", "modem_b", "abl_a", "abl_b"]
            self.log("Ключевые разделы:")
            for p in key_parts:
                if p in partitions:
                    self.log(f"  ✓ {p}")
                else:
                    self.log(f"  ✗ {p} — не найден")
        else:
            self.log("Не удалось прочитать список разделов.")
            self.log("Телефон может не поддерживать эту команду в заблокированном состоянии.")

        report = {
            "time": datetime.now().isoformat(),
            "action": "list_partitions",
            "partitions": {k: v for k, v in sorted(partitions.items())},
            "count": len(partitions),
        }
        self.save_report("partitions", report)

        self.set_status(f"Найдено {len(partitions)} разделов.", "Ok.TLabel" if partitions else "Err.TLabel")
        self.set_busy(False)


def main():
    root = tk.Tk()
    app = PandoraRecovery(root)
    root.mainloop()


if __name__ == "__main__":
    main()
