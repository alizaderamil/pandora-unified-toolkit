# Device profiles

Each `*.json` file in this folder describes a supported device. The tool loads all `*.json` files at startup (except files starting with `_`).

## Adding a new device

1. Copy `_template.json` to `<codename>.json` (e.g. `spes.json` for Redmi Note 11 Pro).
2. Fill in the fields:
   - `codename` — short name used in `fastboot getvar product` (e.g. `spes`).
   - `name` — full human-readable name.
   - `models` — list of model numbers (e.g. `["2201116TG"]`).
   - `chip` — processor name.
   - `storage_type` — `UFS 4.0` / `UFS 3.1` / `UFS 2.2` / `eMMC 5.1`.
   - `ufs_speeds_expected` — datasheet sequential speeds in MB/s. Omit if unknown.
   - `unlock_method` — `mi_unlock` (standard) or `exploit` (unofficial).
   - `ota_paths` — optional default firmware paths on disk.
   - `critical_partitions` — expected partition sizes in BYTES (convert from hex if needed). Leave `{}` to skip size checks.
   - `tried_methods` — table of methods tested on this device.

3. Submit a pull request to the main repository.

## Finding partition sizes

Run the diagnostic in the tool and look at the **Состояние/State** tab. Fastboot reports sizes in hex (e.g. `0x6000000`). Convert to bytes for the JSON:

- Python: `int("0x6000000", 16)` → `100663296`
- Online: `0x6000000` in dec = `100663296`

## Finding your codename

```bash
fastboot getvar product
```

Returns something like `(bootloader) product: pandora`.
