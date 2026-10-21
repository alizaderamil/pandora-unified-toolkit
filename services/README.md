# Service contacts

Each `*.json` file in this folder describes a repair service that the tool references in its generated **Service Report** HTML. The tool loads all `*.json` files at startup (except files starting with `_`).

## Adding a service

1. Copy `_template.json` to `<shopname>_<city>.json` (e.g. `tashkent_mobile_moscow.json`).
2. Fill in the fields. **Only mark `proven: true` if you personally used the service** — this becomes a green badge in the report.
3. Keep notes short and factual. No ad language, no superlatives.
4. Open a pull request. Include the device(s) the service recovered for you.

## Verified vs listed

- `proven: true` → service appears with a ✓ VERIFIED badge
- `proven: false` → service appears without a badge (listed but not endorsed)

The tool is intentionally conservative about verification. One personal success story is enough to flip the flag, but hearsay is not.

## Removing a service

If a service is no longer trustworthy — closed, scam, bad warranty, lost staff — open a PR deleting the file with a one-line reason in the commit message.

## Not accepted

- Personal phone numbers in `contact`. Use "WhatsApp" / "Telegram @handle" / "website only" instead.
- Pricing in cryptocurrency as the only option.
- Services that only unlock via social-engineering Xiaomi staff.
