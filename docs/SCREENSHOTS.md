# Screenshots to add to the README

The README would benefit from 3-4 screenshots. Take them yourself and drop them in `docs/images/`, then reference from README.

## 1. Main window (hero shot)

Launch:
```bash
python pandora_unified.py
```
Click **1. Полная диагностика** (or whichever language is active). Screenshot the whole window with:
- Header (title + device/language selectors)
- Both button rows
- Status bar
- Log tab filled with diagnostic output

**Save as:** `docs/images/main.png`

## 2. Lock Wizard

Click **🔒 Lock Wizard**. Screenshot:
- Mode: exploit (pandora) — this is the one with the red "НАША ОШИБКА" warning
- Full 3-step text visible

**Save as:** `docs/images/lock-wizard.png`

## 3. UFS Health results

Run **📊 UFS Health** on any phone. Screenshot the log tab with the results.

**Save as:** `docs/images/ufs-health.png`

## 4. Service Report (HTML)

Click **🏥 Отчёт для сервиса**. The HTML opens in your browser. Screenshot the browser view at ~1200px wide — the full-coloured header, the state table, the methods tried table, and at least one service card.

**Save as:** `docs/images/service-report.png`

## Adding to README

Once images are in `docs/images/`, update README.md:

```markdown
## Screenshots

![Main window](docs/images/main.png)
![Lock Wizard](docs/images/lock-wizard.png)
![UFS Health](docs/images/ufs-health.png)
![Service Report](docs/images/service-report.png)
```

## Tips

- Use a 1200x860 window (default), the GUI is designed for this size
- Dark background makes screenshots pop more than light; the tool is already dark-themed
- Screenshot with Windows Snip & Sketch (`Win+Shift+S`) or ShareX
- 1 MB each is a reasonable cap; use PNG for crisp text, not JPEG
- Blur / redact any serial numbers visible in the diagnostic (`serialno`)
