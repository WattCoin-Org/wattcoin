# Raspberry Pi Energy Monitor (Bounty #15 scaffold)

This adds a minimal, mergeable starter implementation for the Pi energy monitor bounty:

- Reads power data from **Kasa smart plug** (`python-kasa`) or a **mock/USB meter JSON feed**
- Stores local history in **SQLite**
- Sends reports to `POST /api/v1/energy/report`
- Signs payloads using an **external signer command** (`WATT_SIGN_CMD`) so keys are not embedded in code
- Includes a `systemd` service example

## Files

- `pi/energy_monitor/monitor.py`
- `pi/energy_monitor/install.sh`
- `pi/energy_monitor/mock_meter.json`
- `pi/energy_monitor/wattcoin-energy-monitor.service`

## Quick start

```bash
cd pi/energy_monitor
bash install.sh
WATT_DEV_SIGNING_SECRET=dev-secret \
  python monitor.py \
    --base-url https://api.wattcoin.org \
    --wallet YOUR_WALLET \
    --source mock \
    --mock-file mock_meter.json \
    --once
```

For production signing, use `WATT_SIGN_CMD` (preferred), e.g. a Solana signer command that accepts payload via stdin and returns a signature via stdout.

## Notes

- `WATT_DEV_SIGNING_SECRET` is **dev-only** fallback for local tests.
- For physical deployment, replace `--source mock` with `--source kasa --kasa-host <ip>`.
- USB meter integration can be added by writing to a JSON file consumed by `--mock-file` (or by extending `monitor.py` with a dedicated reader).
