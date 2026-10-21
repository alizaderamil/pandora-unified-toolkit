"""
Pandora Unified 1.2 — Утилита для Xiaomi диагностики и прошивки

Поддерживаемые устройства:
  • pandora — Xiaomi 17 Pro China (SM8850, UFS 4.0)
  • miel    — Redmi Note 11 (SD680, UFS 2.2)

Заменяет pandora_recovery.py и pandora_last_chance.py.
Исправляет баг с shouhoujiance, добавляет анализ bootfail дампа,
проверку UFS, сравнение с прошивкой.

v1.1 (2026-10-21, после chip-off ремонта):
  + Lock Wizard — правильная последовательность блокировки
  + Snapshot — бэкап getvar/token перед опасной операцией
  + Service Report — HTML отчёт для сервисного центра
  + Pre-flight confirm — предупреждение перед опасными командами
  + UFS Health — benchmark скорости после chip-off (baseline → compare)

v1.2 (2026-10-21):
  + Профиль устройств (DEVICE_PROFILES) — pandora и miel
  + Автоопределение по product из fastboot
  + Lock Wizard: два сценария — эксплойт (pandora) и Mi Unlock (miel)
  + Compare использует OTA и размеры разделов из профиля
  + Service Report — методы и выводы под детектированное устройство
  + UFS Health — сравнение с паспортными скоростями профиля
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
import urllib.request
import webbrowser
import zipfile
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from pathlib import Path

TOOL_VERSION = "1.3"
GITHUB_REPO = "alizaderamil/pandora-unified-toolkit"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

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


SERVICES_DIR = Path(__file__).resolve().parent / "services"


def _load_services():
    """Загружает все записи сервисов из services/*.json."""
    services = []
    if not SERVICES_DIR.exists():
        return services
    for p in sorted(SERVICES_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # Normalise: поля price_<lang> / price_aznish_<lang> совместимость
            services.append(data)
        except Exception as e:
            print(f"[WARN] Failed to load service {p.name}: {e}", file=sys.stderr)
    # Verified сначала
    services.sort(key=lambda s: (not s.get("proven", False), s.get("name", "")))
    return services


SERVICE_CONTACTS = _load_services()


def service_i18n(service, field):
    """Pick language-aware service field with fallback across naming schemes."""
    for key in (f"{field}_{_CURRENT_LANG}", f"{field}_en", f"{field}_aznish_{_CURRENT_LANG}", f"{field}_aznish_en"):
        if service.get(key):
            return service[key]
    return service.get(field, "")


class Tooltip:
    """Minimal tooltip: shows a popup after hover_delay ms, hides on leave."""

    def __init__(self, widget, text_fn, delay=600):
        self.widget = widget
        self.text_fn = text_fn  # callable returning current text (для i18n)
        self.delay = delay
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._cancel)
        widget.bind("<ButtonPress>", self._cancel)

    def _schedule(self, _event=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay, self._show)

    def _cancel(self, _event=None):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None

    def _show(self):
        try:
            text = self.text_fn() if callable(self.text_fn) else self.text_fn
        except Exception:
            return
        if not text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        self.tip.configure(bg="#1e293b")
        label = tk.Label(
            self.tip, text=text, bg="#1e293b", fg="#e2e8f0",
            font=("Segoe UI", 9), padx=10, pady=6,
            wraplength=380, justify="left",
        )
        label.pack()


class DeviceMonitor:
    """
    Фоновый поллинг fastboot + adb. Вызывает callback(state) когда состояние
    меняется. state = {"mode": "fastboot"|"adb"|"none", "info": {...}}
    """

    def __init__(self, callback, interval=2.5):
        self.callback = callback
        self.interval = interval
        self.running = False
        self.thread = None
        self.last_state = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                state = self._check()
                # Сообщаем только при изменении, чтобы не долбить callback
                if state != self.last_state:
                    self.last_state = state
                    try:
                        self.callback(state)
                    except Exception as e:
                        print(f"[DeviceMonitor] callback error: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[DeviceMonitor] poll error: {e}", file=sys.stderr)
            time.sleep(self.interval)

    def _check(self):
        # Fastboot первым — он быстрее отвечает когда телефон там
        rc, out = fb("devices", timeout=2)
        if "fastboot" in out.lower():
            info = {}
            for var in ("product", "unlocked", "current-slot", "secure"):
                rc, o = fb("getvar", var, timeout=2)
                m = re.search(r"\(bootloader\)\s*" + re.escape(var) + r":\s*(.*)", o)
                if m:
                    info[var] = m.group(1).strip()
            return {"mode": "fastboot", "info": info}

        rc, out = adb_cmd("devices", timeout=2)
        for line in out.splitlines():
            if "\tdevice" in line:
                info = {}
                for prop, key in (
                    ("ro.product.name", "product"),
                    ("ro.product.model", "model"),
                    ("ro.boot.flash.locked", "locked"),
                    ("ro.boot.verifiedbootstate", "verified"),
                ):
                    rc, o = adb_cmd("shell", "getprop", prop, timeout=2)
                    info[key] = o.strip()
                return {"mode": "adb", "info": info}
        return {"mode": "none", "info": {}}


PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
SETTINGS_FILE = Path(__file__).resolve().parent / ".pandora_settings.json"
DEVICE_HISTORY_FILE = Path(__file__).resolve().parent / "unified_reports" / "device_history.jsonl"


def _log_device_seen(state):
    """Append one line to device_history.jsonl when a new device is seen."""
    if state.get("mode") == "none":
        return
    info = state.get("info", {})
    key = (info.get("product") or info.get("model") or "").strip()
    if not key:
        return
    try:
        DEVICE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "mode": state["mode"],
            "product": info.get("product", ""),
            "model": info.get("model", ""),
            "locked": info.get("locked") or info.get("unlocked") or "",
        }
        # Dedup: не писать ту же запись подряд
        if DEVICE_HISTORY_FILE.exists():
            try:
                last_line = DEVICE_HISTORY_FILE.read_text(encoding="utf-8").splitlines()[-1]
                last = json.loads(last_line)
                if (last.get("product") == entry["product"]
                        and last.get("mode") == entry["mode"]
                        and last.get("model") == entry["model"]):
                    return  # дубликат — не пишем
            except Exception:
                pass
        with open(DEVICE_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[device_history] write failed: {e}", file=sys.stderr)


def _recent_devices(limit=5):
    """Last N unique devices seen (dedup by product)."""
    if not DEVICE_HISTORY_FILE.exists():
        return []
    try:
        lines = DEVICE_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    seen = []
    seen_keys = set()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        key = entry.get("product") or entry.get("model")
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        seen.append(entry)
        if len(seen) >= limit:
            break
    return seen


def _load_translations():
    """Загружает все переводы из translations/*.json."""
    trans = {}
    if not TRANSLATIONS_DIR.exists():
        return trans
    for p in sorted(TRANSLATIONS_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            code = data.get("_meta", {}).get("code", p.stem)
            trans[code] = data
        except Exception as e:
            print(f"[WARN] Failed to load translation {p.name}: {e}", file=sys.stderr)
    return trans


TRANSLATIONS = _load_translations()
_CURRENT_LANG = "ru"  # default


def set_lang(code):
    global _CURRENT_LANG
    if code in TRANSLATIONS:
        _CURRENT_LANG = code


def tr(key, **kwargs):
    """Translate a key. Falls back to English, then to the key itself."""
    for lang in (_CURRENT_LANG, "en"):
        trans = TRANSLATIONS.get(lang, {})
        if key in trans:
            try:
                return trans[key].format(**kwargs)
            except Exception:
                return trans[key]
    return key


def _load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_settings(settings):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


# Загружаем язык из настроек
_settings = _load_settings()
if "lang" in _settings and _settings["lang"] in TRANSLATIONS:
    _CURRENT_LANG = _settings["lang"]


def _load_device_profiles():
    """Загружает все профили устройств из profiles/*.json (кроме начинающихся с _)."""
    profiles = {}
    if not PROFILES_DIR.exists():
        return profiles
    for p in sorted(PROFILES_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            codename = data.get("codename", p.stem)
            profiles[codename] = data
        except Exception as e:
            print(f"[WARN] Failed to load profile {p.name}: {e}", file=sys.stderr)
    return profiles


DEVICE_PROFILES = _load_device_profiles()


def detect_device(variables):
    """Определить профиль устройства по getvar переменным."""
    product = variables.get("product", "").lower()
    for key, profile in DEVICE_PROFILES.items():
        if key in product:
            return profile
    model = variables.get("variant", "")
    for key, profile in DEVICE_PROFILES.items():
        if any(m.lower() in model.lower() for m in profile.get("models", [])):
            return profile
    return None


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
        devices_str = " + ".join(sorted(DEVICE_PROFILES.keys()))
        root.title(f"Pandora Unified {TOOL_VERSION} — Xiaomi diagnostics ({devices_str})")
        root.geometry("1200x860")
        root.configure(bg="#0a0f1e")
        self.busy = False
        self.device_data = {}
        self.device_profile = None  # DEVICE_PROFILES[...] либо None
        self.manual_device_override = False  # True если пользователь выбрал вручную
        self.current_device_state = {"mode": "none", "info": {}}
        self.device_monitor = None  # запустим после _build_ui

        self._setup_styles()
        self._build_ui()

        # Запускаем мониторинг устройства после построения UI
        self.device_monitor = DeviceMonitor(self._on_device_state_change)
        self.device_monitor.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Проверка обновлений в фоне (не блокирует запуск)
        threading.Thread(target=self._check_updates, daemon=True).start()

        # First-launch wizard (если ещё не показан)
        settings = _load_settings()
        if not settings.get("wizard_shown"):
            root.after(400, self._show_first_launch_wizard)

    def _show_first_launch_wizard(self):
        """Welcome wizard — показывается один раз на первом запуске."""
        win = tk.Toplevel(self.root)
        win.title(tr("wizard.title"))
        win.geometry("720x540")
        win.configure(bg="#0a0f1e")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=tr("wizard.title"), style="H.TLabel").pack(anchor="w")
        ttk.Label(frame, text=tr("wizard.subtitle"), style="Sub.TLabel").pack(
            anchor="w", pady=(2, 16)
        )

        choices = [
            ("wizard.diagnose", self.action_diagnostic),
            ("wizard.lock", self.action_lock_wizard),
            ("wizard.health", self.action_ufs_health),
            ("wizard.backup", self.action_snapshot),
            ("wizard.explore", None),
        ]

        for key_prefix, action in choices:
            card = tk.Frame(frame, bg="#1e293b", padx=14, pady=10)
            card.pack(fill="x", pady=4)

            title_lbl = tk.Label(
                card, text=tr(f"{key_prefix}.title"),
                bg="#1e293b", fg="#60a5fa",
                font=("Segoe UI", 11, "bold"), anchor="w", justify="left",
            )
            title_lbl.pack(anchor="w")
            body_lbl = tk.Label(
                card, text=tr(f"{key_prefix}.body"),
                bg="#1e293b", fg="#cbd5e1",
                font=("Segoe UI", 9), anchor="w", justify="left", wraplength=640,
            )
            body_lbl.pack(anchor="w")

            def make_click(a=action):
                def on_click(_event=None):
                    win.destroy()
                    if a:
                        self.root.after(100, a)
                return on_click

            handler = make_click()
            for widget in (card, title_lbl, body_lbl):
                widget.bind("<Button-1>", handler)
                widget.configure(cursor="hand2")

        # Checkbox «не показывать больше» + close
        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(14, 0))
        dontshow_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bottom, text=tr("wizard.dontshow"), variable=dontshow_var,
        ).pack(side="left")

        def close():
            if dontshow_var.get():
                settings = _load_settings()
                settings["wizard_shown"] = True
                _save_settings(settings)
            win.destroy()

        ttk.Button(bottom, text="Close", command=close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)

    def _check_updates(self):
        """Проверить GitHub Releases на новую версию."""
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_API,
                headers={"User-Agent": f"pandora-unified-toolkit/{TOOL_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            if not latest:
                return
            if self._version_newer(latest, TOOL_VERSION):
                url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
                # Показать неблокирующее уведомление через after
                self.root.after(0, lambda: self._announce_update(latest, url))
        except Exception:
            # Нет интернета / API rate limited — просто молча
            pass

    @staticmethod
    def _version_newer(a, b):
        """True если версия a новее b (semver-ish)."""
        try:
            pa = tuple(int(x) for x in a.split("."))
            pb = tuple(int(x) for x in b.split("."))
            return pa > pb
        except Exception:
            return False

    def _announce_update(self, latest, url):
        """Показать уведомление о новой версии в лог + в status."""
        self.write("", "")
        self.write(f"🎉 New version available: {latest} (you have {TOOL_VERSION})", "hdr")
        self.write(f"   {url}", "ok")
        self.status.set(f"Update available: v{latest}. See log tab.")

    def _on_close(self):
        if self.device_monitor:
            self.device_monitor.stop()
        self.root.destroy()

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

    def _build_device_bar(self, parent):
        """Live device status bar — mode, device info, reboot buttons, progress bar."""
        bar = tk.Frame(parent, bg="#1a2235", padx=14, pady=10)
        bar.pack(fill="x", pady=(0, 10))

        # Левая часть — иконка состояния + текст
        left = tk.Frame(bar, bg="#1a2235")
        left.pack(side="left", fill="x", expand=True)

        self.devbar_icon = tk.Label(
            left, text="⚫", font=("Segoe UI", 16),
            bg="#1a2235", fg="#64748b",
        )
        self.devbar_icon.pack(side="left", padx=(0, 10))

        self.devbar_text = tk.StringVar(value="Checking for devices…")
        tk.Label(
            left, textvariable=self.devbar_text,
            font=("Segoe UI", 10), bg="#1a2235", fg="#e2e8f0",
            anchor="w", justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Правая часть — reboot кнопки + progress
        right = tk.Frame(bar, bg="#1a2235")
        right.pack(side="right")

        self.progress_bar = ttk.Progressbar(
            right, mode="indeterminate", length=120,
        )
        # Пока скрыта — покажем во время async операций

        self.reboot_btn = ttk.Button(
            right, text="— ", command=self._on_reboot_click, state="disabled",
        )
        self.reboot_btn.pack(side="right")
        Tooltip(
            self.reboot_btn,
            lambda: {
                "to_fastboot": "Reboot phone from Android to Fastboot (bootloader mode)",
                "to_android": "Reboot phone from Fastboot to Android",
            }.get(self.reboot_mode, "No device connected"),
        )

        # Текущая роль кнопки: None | "to_fastboot" | "to_android"
        self.reboot_mode = None
        # Последнее известное состояние (для действий)
        self.current_device_state = {"mode": "none", "info": {}}

    def _update_device_bar(self, state):
        """Обновить status bar по новому состоянию (главный поток)."""
        self.current_device_state = state
        mode = state["mode"]
        info = state["info"]

        # Логируем в device_history (внутри сам дедуплицирует)
        _log_device_seen(state)
        # Обновляем Recent devices dropdown
        self._refresh_recent_devices_menu()

        if mode == "fastboot":
            product = info.get("product", "?")
            unlocked = info.get("unlocked", "?")
            slot = info.get("current-slot", "?")
            lock_badge = "🔓 unlocked" if unlocked == "yes" else "🔒 locked"
            self.devbar_icon.configure(text="🔌", fg="#60a5fa")
            self.devbar_text.set(
                f"Fastboot · {product} · {lock_badge} · slot {slot}"
            )
            self.reboot_btn.configure(
                text="↻ Reboot to Android",
                state="normal",
            )
            self.reboot_mode = "to_android"
        elif mode == "adb":
            product = info.get("product", "?")
            model = info.get("model", "")
            locked = info.get("locked", "")
            lock_badge = "🔒 locked" if locked == "1" else "🔓 unlocked"
            label = f"{product}" + (f" ({model})" if model and model != product else "")
            self.devbar_icon.configure(text="📱", fg="#4ade80")
            self.devbar_text.set(
                f"Android (ADB) · {label} · {lock_badge}"
            )
            self.reboot_btn.configure(
                text="↻ Reboot to Fastboot",
                state="normal",
            )
            self.reboot_mode = "to_fastboot"
        else:
            self.devbar_icon.configure(text="⚫", fg="#64748b")
            self.devbar_text.set(
                "No device detected · Connect phone via USB (Fastboot or Android with USB debugging)"
            )
            self.reboot_btn.configure(text="— ", state="disabled")
            self.reboot_mode = None

    def _on_reboot_click(self):
        """One-click reboot между fastboot и android."""
        if self.reboot_mode == "to_android":
            self.write("↻ Rebooting to Android…")
            threading.Thread(
                target=lambda: fb("reboot", timeout=5),
                daemon=True,
            ).start()
        elif self.reboot_mode == "to_fastboot":
            self.write("↻ Rebooting to Fastboot (bootloader)…")
            threading.Thread(
                target=lambda: adb_cmd("reboot", "bootloader", timeout=5),
                daemon=True,
            ).start()

    def _on_device_state_change(self, state):
        """Thread-safe callback from DeviceMonitor."""
        self.root.after(0, lambda: self._update_device_bar(state))

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        # Заголовок
        header = ttk.Frame(main)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Pandora Unified", style="H.TLabel").pack(side="left")
        devices_list = ", ".join(f"{p['codename']}" for p in DEVICE_PROFILES.values())
        self.subtitle_var = tk.StringVar(
            value=tr("app.subtitle", devices=devices_list) + "  ·  v1.3"
        )
        ttk.Label(header, textvariable=self.subtitle_var,
                  style="Sub.TLabel").pack(side="left", padx=(14, 0), pady=(10, 0))

        # Live device status bar — всегда показывает текущее состояние телефона
        self._build_device_bar(main)

        # Селекторы — язык + устройство
        selector_frame = ttk.Frame(main)
        selector_frame.pack(fill="x", pady=(0, 10))

        # Язык
        ttk.Label(selector_frame, text=tr("label.language")).pack(side="left")
        self.lang_var = tk.StringVar(value=_CURRENT_LANG)
        lang_options = [(code, data["_meta"]["name"]) for code, data in TRANSLATIONS.items()]
        self.lang_combo = ttk.Combobox(
            selector_frame, textvariable=self.lang_var, width=14,
            values=[f"{name} ({code})" for code, name in lang_options],
            state="readonly",
        )
        # Устанавливаем текущее значение
        for code, name in lang_options:
            if code == _CURRENT_LANG:
                self.lang_combo.set(f"{name} ({code})")
                break
        self.lang_combo.pack(side="left", padx=(6, 20))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        # Устройство
        ttk.Label(selector_frame, text=tr("label.device")).pack(side="left")
        self.device_var = tk.StringVar(value=tr("label.auto_detect"))
        device_values = [tr("label.auto_detect")] + [
            f"{p['codename']} — {p['name']}" for p in DEVICE_PROFILES.values()
        ]
        self.device_combo = ttk.Combobox(
            selector_frame, textvariable=self.device_var, width=42,
            values=device_values, state="readonly",
        )
        self.device_combo.pack(side="left", padx=(6, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_change)

        # Recent devices — кнопка-меню
        self.recent_btn = ttk.Menubutton(selector_frame, text="📜 Recent")
        self.recent_menu = tk.Menu(self.recent_btn, tearoff=False)
        self.recent_btn["menu"] = self.recent_menu
        self.recent_btn.pack(side="left", padx=(10, 0))
        Tooltip(self.recent_btn, lambda: "Devices seen in previous sessions. Click to filter / select.")
        self._refresh_recent_devices_menu()

        # Кнопки — ряд 1 (диагностика)
        btn_frame1 = ttk.Frame(main)
        btn_frame1.pack(fill="x", pady=(0, 6))

        # Mode requirements: "fastboot", "adb", or None (works anywhere)
        self.buttons = []
        self.button_keys = []  # (button, translation_key, mode) для обновления при смене языка
        row1_actions = [
            ("btn.diagnostic", self.action_diagnostic, "fastboot"),
            ("btn.ufs_check", self.action_ufs_check, "fastboot"),
            ("btn.bootfail", self.action_bootfail, None),
            ("btn.compare", self.action_compare_firmware, "fastboot"),
            ("btn.reports", self.action_open_reports, None),
        ]
        for key, cmd, mode in row1_actions:
            b = ttk.Button(btn_frame1, text=self._btn_text(key, mode),
                           command=cmd, style="Big.TButton")
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)
            self.button_keys.append((b, key, mode))
            tip_key = key.replace("btn.", "tip.")
            Tooltip(b, lambda k=tip_key: tr(k))

        # Кнопки — ряд 2 (защита + сервис + здоровье)
        btn_frame2 = ttk.Frame(main)
        btn_frame2.pack(fill="x", pady=(0, 12))

        row2_actions = [
            ("btn.lock_wizard", self.action_lock_wizard, None),
            ("btn.snapshot", self.action_snapshot, "fastboot"),
            ("btn.service_report", self.action_service_report, None),
            ("btn.ufs_health", self.action_ufs_health, "adb"),
            ("btn.lessons", self.action_open_lessons, None),
        ]
        for key, cmd, mode in row2_actions:
            b = ttk.Button(btn_frame2, text=self._btn_text(key, mode),
                           command=cmd, style="Big.TButton")
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)
            self.button_keys.append((b, key, mode))
            tip_key = key.replace("btn.", "tip.")
            Tooltip(b, lambda k=tip_key: tr(k))

        # Статус-бар
        self.status = tk.StringVar(value=tr("status.ready"))
        status_lbl = ttk.Label(main, textvariable=self.status, wraplength=1140,
                               background="#1e293b", padding=(10, 8), relief="flat")
        status_lbl.pack(fill="x", pady=(0, 10))

        # Вкладки
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        # Вкладка 1: Лог
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text=tr("tab.log"))
        self.log_tab_idx = 0

        # Mini-тулбар для лога: Copy / Save / Clear / Support bundle
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill="x", pady=(4, 2), padx=4)

        self.log_action_btns = []
        for key, cmd, tip_key in [
            ("btn.log.copy", self._copy_log, "tip.log.copy"),
            ("btn.log.save", self._save_log, "tip.log.save"),
            ("btn.log.clear", self._clear_log, "tip.log.clear"),
            ("btn.log.support", self.action_support_bundle, "tip.log.support"),
        ]:
            b = ttk.Button(log_toolbar, text=tr(key), command=cmd)
            b.pack(side="left", padx=(0, 4))
            Tooltip(b, lambda k=tip_key: tr(k))
            self.log_action_btns.append((b, key))

        # Contribute partition sizes — скрыта, появляется после диагностики на незнакомом профиле
        self.contribute_btn = ttk.Button(
            log_toolbar, text="🎁 Contribute partition sizes",
            command=self.action_contribute_partitions,
        )
        Tooltip(
            self.contribute_btn,
            lambda: "Open a pre-filled GitHub issue with partition sizes from this device. "
                    "Helps other users of the same model.",
        )
        # Не pack — покажем только когда есть что контрибьютить

        # Firmware links — всегда доступна, открывает ссылки из профиля
        self.firmware_btn = ttk.Button(
            log_toolbar, text="📥 Firmware", command=self.action_firmware_links,
        )
        self.firmware_btn.pack(side="right", padx=(4, 0))
        Tooltip(
            self.firmware_btn,
            lambda: "Open official firmware download pages for the active device profile.",
        )

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
        self.notebook.add(state_frame, text=tr("tab.state"))
        self.state_tab_idx = 1
        self.state_tree = ttk.Treeview(state_frame, columns=("key", "value"), show="headings")
        self.state_tree.heading("key", text=tr("col.key"))
        self.state_tree.heading("value", text=tr("col.value"))
        self.state_tree.column("key", width=320)
        self.state_tree.column("value", width=600)
        scroll1 = ttk.Scrollbar(state_frame, orient="vertical", command=self.state_tree.yview)
        self.state_tree.configure(yscrollcommand=scroll1.set)
        self.state_tree.pack(side="left", fill="both", expand=True)
        scroll1.pack(side="right", fill="y")

        # Вкладка 3: Bootfail
        bf_frame = ttk.Frame(self.notebook)
        self.notebook.add(bf_frame, text=tr("tab.bootfail"))
        self.bootfail_tab_idx = 2
        self.bf_text = scrolledtext.ScrolledText(bf_frame, bg="#141b2d", fg="#e2e8f0",
                                                  font=("Consolas", 9), wrap="word",
                                                  state="disabled", relief="flat", bd=0)
        self.bf_text.pack(fill="both", expand=True)

        # Keyboard shortcuts: F1-F10 для 10 кнопок, Ctrl+L/C/S для лога
        self._bind_keyboard_shortcuts()

    def _bind_keyboard_shortcuts(self):
        """Привязка клавиатурных сочетаний."""
        # F1-F10 → 10 кнопок по порядку
        for i, btn in enumerate(self.buttons[:10]):
            key = f"<F{i+1}>"
            self.root.bind(key, lambda e, b=btn: b.invoke())

        self.root.bind("<Control-l>", lambda e: self._clear_log())
        self.root.bind("<Control-L>", lambda e: self._clear_log())
        self.root.bind("<Control-c>", lambda e: self._copy_log())
        self.root.bind("<Control-C>", lambda e: self._copy_log())
        self.root.bind("<Control-s>", lambda e: self._save_log())
        self.root.bind("<Control-S>", lambda e: self._save_log())

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status.set("Log cleared.")

    def _copy_log(self):
        text = self.log.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.status.set(f"Log copied to clipboard ({len(text)} chars).")

    def _save_log(self):
        text = self.log.get("1.0", "end-1c")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = filedialog.asksaveasfilename(
            title="Save log",
            defaultextension=".txt",
            initialfile=f"pandora_log_{ts}.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.status.set(f"Log saved: {Path(path).name}")

    def _on_lang_change(self, event=None):
        """Переключение языка."""
        selection = self.lang_combo.get()
        # Извлекаем код из "Name (code)"
        m = re.search(r"\(([a-z]{2})\)$", selection)
        if m:
            new_code = m.group(1)
            if new_code != _CURRENT_LANG:
                set_lang(new_code)
                settings = _load_settings()
                settings["lang"] = new_code
                _save_settings(settings)
                self._refresh_ui_language()

    def _refresh_recent_devices_menu(self):
        """Rebuild the Recent devices menu based on device_history.jsonl."""
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.delete(0, "end")
        recent = _recent_devices(limit=8)
        if not recent:
            self.recent_menu.add_command(label="(no history yet)", state="disabled")
            return
        for entry in recent:
            product = entry.get("product", "?")
            mode = entry.get("mode", "?")
            when = entry.get("time", "")[:16].replace("T", " ")
            label = f"{product}  ({mode}, {when})"

            def set_profile(prod=product):
                # Если профиль есть — выставить его в селектор
                for key, prof in DEVICE_PROFILES.items():
                    if key in prod.lower():
                        self.device_combo.set(f"{prof['codename']} — {prof['name']}")
                        self._on_device_change()
                        return
                self.write(f"ℹ️  No profile for {prod} yet. Connect it to collect data.", "warn")

            self.recent_menu.add_command(label=label, command=set_profile)
        self.recent_menu.add_separator()
        self.recent_menu.add_command(
            label="Open device_history.jsonl",
            command=lambda: os.startfile(str(DEVICE_HISTORY_FILE))
            if DEVICE_HISTORY_FILE.exists() else None,
        )

    def _btn_text(self, key, mode):
        """Button text with mode suffix (FB / ADB)."""
        base = tr(key)
        if mode == "fastboot":
            return f"{base}  · FB"
        elif mode == "adb":
            return f"{base}  · ADB"
        return base

    def _check_mode_or_prompt(self, needed_mode):
        """
        Проверка что телефон в нужном режиме. Если нет — предлагаем ребутнуть.
        Returns True если можно продолжать, False если юзер отменил или
        операция ребута запущена (должна быть повторена пользователем).
        """
        if needed_mode is None:
            return True
        current = self.current_device_state.get("mode", "none")
        if current == needed_mode:
            return True

        # Нужен другой режим
        if needed_mode == "fastboot":
            if current == "adb":
                ok = messagebox.askyesno(
                    "Reboot required",
                    "This action requires Fastboot mode, but the phone is in Android (ADB).\n\n"
                    "Reboot to Fastboot now? (Click the action button again after reboot completes.)",
                )
                if ok:
                    threading.Thread(
                        target=lambda: adb_cmd("reboot", "bootloader", timeout=5),
                        daemon=True,
                    ).start()
                    self.write("↻ Rebooting to Fastboot… wait ~10 sec, then click again.", "warn")
                return False
            else:
                messagebox.showwarning(
                    "No device",
                    "No phone detected. Connect via USB in Fastboot mode and try again.",
                )
                return False
        elif needed_mode == "adb":
            if current == "fastboot":
                ok = messagebox.askyesno(
                    "Reboot required",
                    "This action requires Android mode (ADB), but the phone is in Fastboot.\n\n"
                    "Reboot to Android now? (Click the action button again after reboot + USB debugging prompt.)",
                )
                if ok:
                    threading.Thread(
                        target=lambda: fb("reboot", timeout=5),
                        daemon=True,
                    ).start()
                    self.write("↻ Rebooting to Android… wait ~20 sec + accept USB debug prompt.", "warn")
                return False
            else:
                messagebox.showwarning(
                    "No device",
                    "No phone detected. Connect via USB (Android with USB debugging enabled) and try again.",
                )
                return False
        return True

    def _refresh_ui_language(self):
        """Обновить тексты кнопок, статуса, вкладок после смены языка."""
        for btn, key, mode in self.button_keys:
            btn.configure(text=self._btn_text(key, mode))
        for btn, key in getattr(self, "log_action_btns", []):
            btn.configure(text=tr(key))
        self.status.set(tr("status.ready"))
        devices_list = ", ".join(f"{p['codename']}" for p in DEVICE_PROFILES.values())
        self.subtitle_var.set(tr("app.subtitle", devices=devices_list) + "  ·  v1.3")
        try:
            self.notebook.tab(self.log_tab_idx, text=tr("tab.log"))
            self.notebook.tab(self.state_tab_idx, text=tr("tab.state"))
            self.notebook.tab(self.bootfail_tab_idx, text=tr("tab.bootfail"))
        except Exception:
            pass
        try:
            self.state_tree.heading("key", text=tr("col.key"))
            self.state_tree.heading("value", text=tr("col.value"))
        except Exception:
            pass

    def _on_device_change(self, event=None):
        """Ручной выбор устройства (overrides auto-detect)."""
        selection = self.device_combo.get()
        if selection == tr("label.auto_detect"):
            # Сброс — следующий _ensure_profile переопределит
            self.device_profile = None
            self.manual_device_override = False
            self.write(f"ℹ️  {tr('label.device')} {tr('label.auto_detect')}")
            return
        # "codename — name" → извлекаем codename
        codename = selection.split(" — ")[0].strip()
        profile = DEVICE_PROFILES.get(codename)
        if profile:
            self.device_profile = profile
            self.manual_device_override = True
            self.write(tr("msg.detected", name=profile["name"], codename=profile["codename"]), "ok")
            self.write(tr("msg.chip_storage", chip=profile["chip"], storage=profile["storage_type"]))

    def write(self, text, tag=None):
        self.log.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {text}\n", tag or "")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update_idletasks()

    def _detect_and_announce_device(self, variables):
        """Определить профиль устройства и записать в лог. Уважает ручной override."""
        if self.manual_device_override and self.device_profile:
            # Пользователь выбрал вручную — не переопределяем
            self.write(
                f"📌 {tr('label.device')} {self.device_profile['name']} "
                f"(вручную, автоопределение пропущено)",
                "ok",
            )
            return
        profile = detect_device(variables)
        self.device_profile = profile
        if profile:
            self.write(
                tr("msg.detected", name=profile["name"], codename=profile["codename"]), "ok"
            )
            self.write(
                tr("msg.chip_storage", chip=profile["chip"], storage=profile["storage_type"])
            )
        else:
            product = variables.get("product", "?")
            self.write(tr("msg.unknown_device", product=product), "warn")
            self.write(tr("msg.limited_features"), "warn")

    def _ensure_profile(self):
        """
        Для функций, которые могут быть вызваны без диагностики: собрать базовые
        getvar и определить профиль. Возвращает True если профиль найден или
        собраны хотя бы базовые переменные.
        """
        if self.device_profile:
            return True
        if "variables" in self.device_data and self.device_data["variables"]:
            self._detect_and_announce_device(self.device_data["variables"])
            return self.device_profile is not None

        # Собираем через fastboot (быстро — только product, variant)
        if not fb_check_usb():
            return False
        variables = {}
        for var in ("product", "variant", "unlocked", "secure", "current-slot"):
            rc, out = fb("getvar", var, timeout=3)
            for line in out.splitlines():
                m = re.match(r"\(bootloader\)\s*(.+?):\s*(.*)", line)
                if m:
                    variables[m.group(1).strip()] = m.group(2).strip()
        self.device_data["variables"] = variables
        self._detect_and_announce_device(variables)
        return self.device_profile is not None

    def run_async(self, func):
        if self.busy:
            return
        self.busy = True
        for b in self.buttons:
            b.configure(state="disabled")
        # Показываем progress bar
        try:
            self.progress_bar.pack(side="right", padx=(0, 10))
            self.progress_bar.start(interval=50)
        except Exception:
            pass

        def wrapper():
            try:
                func()
            finally:
                self.busy = False

                def finish():
                    for b in self.buttons:
                        b.configure(state="normal")
                    try:
                        self.progress_bar.stop()
                        self.progress_bar.pack_forget()
                    except Exception:
                        pass

                self.root.after(0, finish)

        threading.Thread(target=wrapper, daemon=True).start()

    # === 1. Диагностика ===
    def action_diagnostic(self):
        if not self._check_mode_or_prompt("fastboot"):
            return
        self.run_async(self._do_diagnostic)

    def _do_diagnostic(self):
        self.status.set(tr("btn.diagnostic") + "…")
        self.write("═══ " + tr("btn.diagnostic") + " ═══", "hdr")

        if not fb_check_usb():
            self.write(tr("msg.no_phone"), "err")
            self.status.set(tr("status.not_connected"))
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

        # Определяем профиль устройства
        self._detect_and_announce_device(variables)

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

        # Partition crowdsource prompt — если профиль есть, но partition sizes пусты
        self._maybe_offer_partition_pr(variables)

        self.status.set(f"Диагностика завершена. Прочитано {len(variables)} параметров.")

    def _maybe_offer_partition_pr(self, variables):
        """Если профиль устройства существует, но critical_partitions пустой —
        предложить юзеру отправить размеры в репо через GitHub issue."""
        profile = self.device_profile
        if not profile:
            return
        critical = profile.get("critical_partitions") or {}
        if critical:  # уже заполнены — ничего не делаем
            return

        # Собираем размеры разделов
        parts = {}
        for k, v in variables.items():
            if k.startswith("partition-size:"):
                name = k.replace("partition-size:", "").strip()
                try:
                    size = int(v, 16) if v.startswith("0x") else int(v)
                    parts[name] = size
                except Exception:
                    pass
        if not parts:
            return

        codename = profile.get("codename", "unknown")
        self.write("", "")
        self.write(f"🎁 Этот профиль ({codename}) не содержит partition sizes.", "hdr")
        self.write(f"   Собрано {len(parts)} разделов — помоги другим юзерам, отправь данные в репо.", "ok")
        self.write("   Нажми '🎁 Contribute partition sizes' в логе чтобы открыть GitHub issue.", None)

        # Храним собранные данные для последующего использования кнопкой
        self._pending_partition_data = {
            "codename": codename,
            "partitions": parts,
            "variables_sample": {
                k: v for k, v in variables.items()
                if k in ("product", "variant", "cpuid", "security-patch-level")
            },
        }
        # Обновляем лог toolbar — показываем кнопку contribute
        try:
            self.contribute_btn.pack(side="left", padx=(10, 0))
        except Exception:
            pass

    def action_contribute_partitions(self):
        """Открыть GitHub issue с собранными partition sizes."""
        data = getattr(self, "_pending_partition_data", None)
        if not data:
            messagebox.showinfo(
                "Nothing to contribute",
                "Run Full diagnostic first on a device whose profile has no partition sizes.",
            )
            return

        codename = data["codename"]
        parts_json = json.dumps(
            {k: hex(v) for k, v in data["partitions"].items()},
            indent=2,
        )
        vars_sample = json.dumps(data["variables_sample"], indent=2)

        issue_body = (
            f"**Device profile:** `{codename}`\n\n"
            f"**Variables sample:**\n```json\n{vars_sample}\n```\n\n"
            f"**Partition sizes:**\n```json\n{parts_json}\n```\n\n"
            f"This data was captured automatically by Pandora Unified "
            f"{TOOL_VERSION} on {datetime.now().strftime('%Y-%m-%d')}. "
            f"Please merge into `profiles/{codename}.json` → `critical_partitions`.\n\n"
            f"Reviewer: convert hex to int before merging. The tool stores "
            f"sizes as integers in JSON."
        )
        issue_title = f"[profile] Partition sizes for {codename}"

        import urllib.parse
        url = (
            f"https://github.com/{GITHUB_REPO}/issues/new?"
            f"title={urllib.parse.quote(issue_title)}&"
            f"body={urllib.parse.quote(issue_body)}&"
            f"labels=profile-contribution"
        )
        self.write(f"🌐 Opening GitHub issue draft for {codename}…", "ok")
        try:
            webbrowser.open(url)
        except Exception as e:
            self.write(f"Could not open browser: {e}", "err")
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.write("URL copied to clipboard instead.", "warn")

    # === 2. UFS проверка (критична для auth-free firehose) ===
    def action_ufs_check(self):
        if not self._check_mode_or_prompt("fastboot"):
            return
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
        if not self._check_mode_or_prompt("fastboot"):
            return
        self.run_async(self._do_compare)

    def _do_compare(self):
        self.status.set("Сравниваю разделы с OTA прошивкой…")
        self.write("", "")
        self.write("═══ СРАВНЕНИЕ С ПРОШИВКОЙ ═══", "hdr")

        if not self._ensure_profile():
            self.write("Устройство не распознано. Подключи телефон в fastboot.", "err")
            return

        profile = self.device_profile
        self.write(f"Профиль: {profile['name']} ({profile['codename']})")

        # Ищем OTA — сначала из профиля, потом даём выбрать вручную
        found_ota = None
        for p_str in profile.get("ota_paths", []):
            p = Path(p_str)
            if p.exists():
                found_ota = p
                self.write(f"✓ Найден OTA: {p.name}", "ok")
                self.write(f"  Размер: {p.stat().st_size / 1024**3:.2f} ГБ")
                break

        if not found_ota:
            self.write("OTA по стандартным путям не найден.", "warn")
            self.write("Открываю диалог выбора файла…")
            self.root.after(0, self._pick_ota_file)
            # Диалог откроется асинхронно; продолжим только сравнение разделов

        # Сравнение разделов
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
                except Exception:
                    pass

        self.write(f"Найдено разделов на телефоне: {len(parts)}")

        critical = profile.get("critical_partitions", {})
        if not critical:
            # Для профилей без хардкода размеров — проверяем только наличие ключевых
            self.write("", "")
            self.write("Для этого устройства точные размеры разделов не захардкожены.", "warn")
            self.write("Проверяю только НАЛИЧИЕ ключевых разделов:", "hdr")
            expected_names = ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "super",
                              "recovery_a", "recovery_b", "abl_a", "abl_b"]
            for name in expected_names:
                size = parts.get(name)
                if size:
                    self.write(f"  ✓ {name}: {size:#x} ({size / 1024**2:.1f} МБ)", "ok")
                else:
                    self.write(f"  ✗ {name}: отсутствует", "err")
        else:
            self.write("", "")
            self.write("Ключевые разделы (факт vs ожидаемый):", "hdr")
            all_ok = True
            for name, expected in critical.items():
                actual = parts.get(name, 0)
                status = "✓" if actual == expected else "✗"
                tag = "ok" if actual == expected else "err"
                self.write(f"  {status} {name}: {actual:#x} ({expected:#x} ожидался)", tag)
                if actual != expected:
                    all_ok = False
            self.write("", "")
            if all_ok:
                self.write("Структура разделов цела. Проблема в данных, не в GPT.", "ok")
            else:
                self.write("Структура разделов нарушена!", "err")

        self.status.set("Сравнение завершено.")

    def _pick_ota_file(self):
        """Открывает диалог выбора OTA zip."""
        path = filedialog.askopenfilename(
            title="Выбери OTA прошивку (.zip)",
            filetypes=[("OTA/Firmware zip", "*.zip *.tgz"), ("Все файлы", "*.*")],
            initialdir=r"D:\xiaomi",
        )
        if path:
            p = Path(path)
            self.write(f"✓ Выбран файл: {p.name}", "ok")
            self.write(f"  Размер: {p.stat().st_size / 1024**3:.2f} ГБ")

    # === 5. Открыть отчёты ===
    def action_open_reports(self):
        REPORTS.mkdir(parents=True, exist_ok=True)
        os.startfile(str(REPORTS))

    # === 📦 Support bundle — всё для Issues/мастеров в один zip ===
    def action_support_bundle(self):
        self.run_async(self._do_support_bundle)

    def _do_support_bundle(self):
        self.status.set("Building support bundle…")
        self.write("", "")
        self.write("═══ SUPPORT BUNDLE ═══", "hdr")

        REPORTS.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bundle_path = REPORTS / f"support_bundle_{ts}.zip"

        included = []
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Лог целиком
            log_text = self.log.get("1.0", "end-1c")
            zf.writestr("current_log.txt", log_text.encode("utf-8"))
            included.append("current_log.txt")

            # Device state
            state_summary = {
                "time": datetime.now().isoformat(),
                "monitor_state": self.current_device_state,
                "profile": self.device_profile,
                "manual_override": self.manual_device_override,
                "lang": _CURRENT_LANG,
                "profiles_loaded": sorted(DEVICE_PROFILES.keys()),
            }
            zf.writestr(
                "device_state.json",
                json.dumps(state_summary, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            included.append("device_state.json")

            # Все files из unified_reports (кроме других bundles — не вкладываем zip в zip)
            for p in REPORTS.rglob("*"):
                if p.is_file() and p.name != bundle_path.name:
                    if p.suffix == ".zip" and "support_bundle" in p.name:
                        continue
                    try:
                        rel = p.relative_to(REPORTS)
                        zf.write(p, arcname=f"reports/{rel.as_posix()}")
                        included.append(f"reports/{rel.as_posix()}")
                    except Exception as e:
                        self.write(f"  Skip {p.name}: {e}", "warn")

            # Version info
            version_info = {
                "tool_version": "1.3",
                "python": sys.version,
                "platform": sys.platform,
            }
            zf.writestr(
                "version.json",
                json.dumps(version_info, indent=2).encode("utf-8"),
            )
            included.append("version.json")

        self.write(f"✓ Bundle created: {bundle_path.name}", "ok")
        self.write(f"  Size: {bundle_path.stat().st_size / 1024:.1f} KB")
        self.write(f"  Files included: {len(included)}")
        self.write("  Attach this zip to a GitHub issue or send to a technician.", "ok")
        self.status.set(f"Bundle: {bundle_path.name} ({bundle_path.stat().st_size / 1024:.0f} KB)")

    # === 📥 Firmware links — открыть страницу загрузки прошивки для профиля ===
    def action_firmware_links(self):
        self._ensure_profile()
        profile = self.device_profile
        if not profile:
            messagebox.showinfo(
                "No profile",
                "Connect a device in fastboot or pick one from the Device dropdown first.",
            )
            return
        links = profile.get("firmware_links", [])
        if not links:
            messagebox.showinfo(
                "No firmware links",
                f"Profile {profile.get('codename', '?')} has no firmware_links. "
                f"Add some via a PR to profiles/{profile.get('codename', 'x')}.json",
            )
            return

        # Popup меню с ссылками
        menu = tk.Menu(self.root, tearoff=False)
        for link in links:
            label = link.get("label", link.get("url", "?"))
            url = link.get("url", "")
            if not url:
                continue
            menu.add_command(
                label=f"🌐 {label}",
                command=lambda u=url: webbrowser.open(u),
            )
        menu.add_separator()
        menu.add_command(
            label=f"📝 Suggest a firmware link for {profile.get('codename')}…",
            command=self._suggest_firmware_link,
        )
        # Показать под кнопкой
        try:
            x = self.firmware_btn.winfo_rootx()
            y = self.firmware_btn.winfo_rooty() + self.firmware_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _suggest_firmware_link(self):
        """Открыть pre-filled GitHub issue для добавления firmware link."""
        profile = self.device_profile
        codename = profile.get("codename", "unknown") if profile else "unknown"
        issue_body = (
            f"**Device profile:** `{codename}`\n\n"
            f"**Proposed firmware link:**\n\n"
            f"- Label: _(e.g. XiaomiFirmwareUpdater · dada)_\n"
            f"- URL: _(paste the full URL here)_\n\n"
            f"**Why it's useful:** _(what's on that page — stable releases, "
            f"community mirror, specific build…)_"
        )
        import urllib.parse
        url = (
            f"https://github.com/{GITHUB_REPO}/issues/new?"
            f"title={urllib.parse.quote(f'[profile] Add firmware link for {codename}')}&"
            f"body={urllib.parse.quote(issue_body)}&"
            f"labels=profile-contribution"
        )
        webbrowser.open(url)

    # === Открыть LESSONS_LEARNED.md ===
    def action_open_lessons(self):
        if LESSONS.exists():
            os.startfile(str(LESSONS))
        else:
            messagebox.showwarning(
                "LESSONS_LEARNED.md не найден",
                f"Файл отсутствует:\n{LESSONS}\n\n"
                "Скачай его из репозитория "
                "https://github.com/alizaderamil/pandora-unified-toolkit",
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

    # Relock reference only: profiles and bootable Android cannot certify relock safety.
    def action_lock_wizard(self):
        self._show_lock_wizard()

    def _show_lock_wizard(self):
        win = tk.Toplevel(self.root)
        win.title(tr("lock.review.title"))
        win.geometry("860x620")
        win.configure(bg="#0a0f1e")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=tr("lock.review.title"), style="H.TLabel").pack(anchor="w")
        body = scrolledtext.ScrolledText(
            frame, bg="#141b2d", fg="#e2e8f0", font=("Segoe UI", 11),
            wrap="word", height=20, relief="flat", bd=0,
        )
        body.pack(fill="both", expand=True, pady=(12, 12))
        body.insert("end", tr("lock.review.body"))
        body.configure(state="disabled")
        ttk.Button(frame, text=tr("lock.review.close"), command=win.destroy).pack(side="right")

    # === 📸 Snapshot — бэкап getvar + token перед опасной операцией ===
    def action_snapshot(self):
        if not self._check_mode_or_prompt("fastboot"):
            return
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

    def _conclusion_block(self, profile, tried_methods):
        """HTML-блок с выводом в отчёте для сервиса."""
        fails = [m for m in tried_methods if m[1] == "FAIL"]
        is_en = _CURRENT_LANG == "en"
        if not fails:
            msg = (
                "<b>Status:</b> standard programmatic methods are available. "
                "A service shop is usually not needed unless there is physical damage."
                if is_en else
                "<b>Статус:</b> стандартные программные методы доступны. "
                "Обращение в сервис обычно не требуется, если нет физических повреждений."
            )
            return f'<div class="warning" style="background:#eff6ff;border-left-color:#0284c7">{msg}</div>'
        codename = (profile or {}).get("codename", "")
        if codename == "pandora":
            msg = (
                "<b>Conclusion:</b> for CNXM ROM (China) + locked SM8850 + erased efisp, "
                "<b>no public programmatic recovery exists</b>. "
                "You need either a commercial service with a private Firehose loader, "
                "or physical chip-off NAND/UFS repair."
                if is_en else
                "<b>Вывод:</b> для CNXM ROM (Китай) + заблокированного SM8850 + стёртого efisp "
                "публичных программных методов восстановления <b>не существует</b>. "
                "Нужен либо коммерческий сервис с приватным Firehose loader, "
                "либо физический chip-off ремонт NAND/UFS."
            )
            return f'<div class="warning">{msg}</div>'
        msg = (
            f"<b>Conclusion:</b> some programmatic methods did not work ({len(fails)}). "
            "Recommend a service shop experienced with this specific model."
            if is_en else
            f"<b>Вывод:</b> часть программных методов не сработала ({len(fails)}). "
            "Рекомендую обратиться в сервис с опытом по этой конкретной модели."
        )
        return f'<div class="warning">{msg}</div>'

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
            self._detect_and_announce_device(variables)

        if not variables:
            self.write("Нет данных диагностики. Запусти Полную диагностику или подключи телефон.", "warn")

        # Профиль устройства
        profile = self.device_profile
        if not profile and variables:
            profile = detect_device(variables)
            self.device_profile = profile

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

        # Методы — из профиля (с языковым fallback), иначе generic
        if profile:
            lang_key = f"tried_methods_{_CURRENT_LANG}"
            tried_methods = profile.get(lang_key) or profile.get("tried_methods") or []
        else:
            tried_methods = []
        if not tried_methods:
            if _CURRENT_LANG == "en":
                tried_methods = [
                    ("fastboot getvar", "OK", "Standard diagnostic"),
                    ("MiFlash", "?", "Standard flash path"),
                    ("EDL cable", "?", "Depends on Firehose loader availability"),
                ]
            else:
                tried_methods = [
                    ("fastboot getvar", "OK", "Стандартная диагностика"),
                    ("MiFlash", "?", "Стандартный путь прошивки"),
                    ("EDL кабель", "?", "Зависит от доступности Firehose loader"),
                ]

        is_en = _CURRENT_LANG == "en"
        lbl_method = "Method" if is_en else "Метод"
        lbl_price = "Price" if is_en else "Цена"
        lbl_warranty = "Warranty" if is_en else "Гарантия"
        lbl_verified = "✓ VERIFIED" if is_en else "✓ ПРОВЕРЕН"
        lbl_unverified = "not verified" if is_en else "не проверен"
        services_html = ""
        for s in SERVICE_CONTACTS:
            badge = lbl_verified if s["proven"] else lbl_unverified
            badge_cls = "ok" if s["proven"] else "warn"
            services_html += f"""
            <div class="service">
              <h4>{html.escape(s['name'])} <span class="badge {badge_cls}">{badge}</span></h4>
              <p><b>{lbl_method}:</b> {html.escape(s['method'])}</p>
              <p><b>{lbl_price}:</b> {html.escape(service_i18n(s, 'price'))} · <b>{lbl_warranty}:</b> {html.escape(service_i18n(s, 'warranty'))}</p>
              {('<p><small>📍 ' + html.escape(s.get('city', '')) + ', ' + html.escape(s.get('country', '')) + ' · ' + html.escape(s.get('contact', '')) + '</small></p>') if s.get('city') else ''}
              <p class="notes">{html.escape(service_i18n(s, 'notes'))}</p>
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
            prev_html = f"<li><i>{tr('report.no_history')}</i></li>"

        # Данные устройства — из профиля либо из переменных
        if profile:
            dev_name = profile["name"]
            dev_models = ", ".join(profile.get("models", []))
            dev_chip = profile["chip"]
            dev_storage = profile["storage_type"]
            dev_codename = profile["codename"]
        else:
            dev_name = variables.get("product", "неизвестное устройство")
            dev_models = variables.get("product", "?")
            dev_chip = variables.get("cpuid", "?")
            dev_storage = variables.get("variant", "?")
            dev_codename = variables.get("product", "?")

        serial = variables.get("serialno") or variables.get("device-serial") or "?"

        doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{html.escape(dev_name)} — {html.escape(tr("report.title"))} ({ts})</title>
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

<h1>{tr("report.h1")}</h1>

<div class="meta">
  <h3>{tr("report.device")}</h3>
  <table>
    <tr><td class="k">{tr("report.model")}</td><td>{html.escape(dev_name)} ({html.escape(dev_models)})</td></tr>
    <tr><td class="k">{tr("report.codename")}</td><td>{html.escape(dev_codename)}</td></tr>
    <tr><td class="k">{tr("report.processor")}</td><td>{html.escape(dev_chip)}</td></tr>
    <tr><td class="k">{tr("report.storage")}</td><td>{html.escape(dev_storage)} ({html.escape(variables.get("variant", "?"))})</td></tr>
    <tr><td class="k">{tr("report.serial")}</td><td>{html.escape(serial)}</td></tr>
    <tr><td class="k">{tr("report.generated")}</td><td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
  </table>
</div>

<h2>{tr("report.state")}</h2>
<table>
{rows_html}
</table>

<h2>{tr("report.tried")}</h2>
<table>
  <tr><th>{tr("report.col.method")}</th><th>{tr("report.col.result")}</th><th>{tr("report.col.reason")}</th></tr>
  {tried_html}
</table>

{self._conclusion_block(profile, tried_methods)}

<h2>{tr("report.services")}</h2>
{services_html}

<h2>{tr("report.history")}</h2>
<ul>
{prev_html}
</ul>

<h2>{tr("report.ask_master")}</h2>
<ol>
  <li>{tr("report.ask.1")}</li>
  <li>{tr("report.ask.2")}</li>
  <li>{tr("report.ask.3")}</li>
  <li>{tr("report.ask.4")}</li>
  <li>{tr("report.ask.5")}</li>
</ol>

<footer>
  {tr("report.footer")}
  <a href="https://github.com/alizaderamil/pandora-unified-toolkit">github.com/alizaderamil/pandora-unified-toolkit</a>
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
        if not self._check_mode_or_prompt("adb"):
            return
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

        # Определяем профиль устройства (для ожидаемых скоростей)
        profile = None
        for key, p in DEVICE_PROFILES.items():
            if key in codename.lower() or key in model.lower():
                profile = p
                break
        if profile:
            self.write(f"✓ Профиль: {profile['name']} ({profile['storage_type']})", "ok")
            exp = profile.get("ufs_speeds_expected", {})
            if exp:
                self.write(f"  Ожидаемые скорости: чтение ~{exp['read']} МБ/с, запись ~{exp['write']} МБ/с")
        else:
            self.write(f"⚠️  Устройство ({codename}) не в списке профилей — ожидаемые скорости неизвестны", "warn")

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

        # Сравнение с ожидаемыми скоростями из профиля (сразу, при первом замере)
        if profile and profile.get("ufs_speeds_expected"):
            exp = profile["ufs_speeds_expected"]
            self.write("", "")
            self.write(f"🎯 Сравнение с паспортными скоростями ({profile['storage_type']}):", "hdr")
            if write_mbs and exp.get("write"):
                ratio = write_mbs / exp["write"] * 100
                tag = "ok" if ratio > 70 else ("warn" if ratio > 50 else "err")
                self.write(f"   Запись: {ratio:.0f}% от ожидаемого ({write_mbs:.0f} из ~{exp['write']})", tag)
            if read_mbs and exp.get("read"):
                ratio = read_mbs / exp["read"] * 100
                tag = "ok" if ratio > 70 else ("warn" if ratio > 50 else "err")
                self.write(f"   Чтение: {ratio:.0f}% от ожидаемого ({read_mbs:.0f} из ~{exp['read']})", tag)

        # Baseline (отдельный для каждого устройства)
        if not baseline_file.exists():
            if profile:
                measurement["expected_speeds"] = profile.get("ufs_speeds_expected", {})
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
