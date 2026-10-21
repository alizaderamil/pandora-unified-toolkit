# Contributing

Thanks for considering a contribution. The two most useful things anyone can add are **a device profile** and **a translation** — both are pure JSON edits, no Python required.

---

## Add a device profile (10 minutes)

1. Boot your phone into fastboot and read its codename:
   ```bash
   fastboot getvar product
   ```
   You'll see something like `(bootloader) product: spes`.

2. Copy `profiles/_template.json` to `profiles/<codename>.json`:
   ```bash
   cp profiles/_template.json profiles/spes.json
   ```

3. Fill in the fields. Required:
   - `codename` — the string from step 1
   - `name` — human-readable name, e.g. "Redmi Note 11 Pro"
   - `models` — list of model numbers, e.g. `["2201116TG"]`
   - `chip` — e.g. "Snapdragon 695 (SM6375)"
   - `storage_type` — one of `UFS 4.0` / `UFS 3.1` / `UFS 2.2` / `eMMC 5.1`
   - `unlock_method` — one of `mi_unlock` (standard) / `exploit` (unofficial)

4. Optional but nice to have:
   - `ufs_speeds_expected: {read, write}` in MB/s — look up the datasheet
   - `ota_paths` — default paths for OTA zips, optional
   - `critical_partitions` — partition name → expected size in bytes. Run the full diagnostic in the tool and read the hex sizes from the State tab. Convert hex to decimal (`0x6000000` → `100663296`).
   - `tried_methods` — table of methods you tested on this device

5. Open a pull request. Include output of `fastboot getvar all` as proof the codename matches.

Example minimal profile:
```json
{
  "codename": "spes",
  "name": "Redmi Note 11 Pro",
  "models": ["2201116TG"],
  "chip": "Mediatek Helio G96",
  "storage_type": "UFS 2.2",
  "unlock_method": "mi_unlock",
  "ota_paths": [],
  "critical_partitions": {},
  "tried_methods": [
    ["fastboot getvar", "OK", "Standard diagnostic"],
    ["Mi Unlock Tool", "OK", "Standard, needs 168+ hour wait"]
  ]
}
```

---

## Add a translation (20 minutes)

1. Copy an existing translation file:
   ```bash
   cp translations/en.json translations/<your_lang>.json
   ```

2. Update `_meta`:
   ```json
   "_meta": {"name": "Deutsch", "code": "de"}
   ```
   `code` should be a 2-letter ISO 639-1 code.

3. Translate each value. **Keep keys unchanged.** **Keep `{placeholders}` intact** — they're filled in at runtime.

4. Open a pull request.

If a key is missing in your translation, the tool falls back to English automatically.

---

## Add a new feature

Features should be:
- **Non-destructive by default** — any button that could brick a phone must show a `_confirm_dangerous(...)` dialog first
- **Localized** — use `tr("some.key")` for all user-visible strings, not hardcoded Russian
- **Device-aware** — if the feature depends on specific firmware/partitions, read from `self.device_profile`, not hardcoded

Open an issue describing the feature first if you're unsure whether it fits the scope.

---

## Submitting changes

- Fork, branch, PR against `main`
- One topic per PR (new device profile = one PR, new language = another)
- Reference any devices you tested on in the PR description
- Include the output of `fastboot getvar all` and `adb shell getprop ro.product.name` for any device profile claim

## Reporting a brick / recovery story

If you brick a phone running something this tool did or should have warned about, please open an issue with:
- Device model + codename
- Firmware version at the time
- Exact command sequence that led to the brick
- How you recovered (or didn't)

Lessons like this are the whole point — they go into `LESSONS_LEARNED.md`.
