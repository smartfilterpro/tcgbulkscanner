# tcgbulkscanner

Raspberry Pi rig that feeds a stack of cards, photographs each one, and
posts the photos to the TrainerDeck mail-in scanning service. The full
API contract this rig implements lives in
[`docs/bulkscan-contract.md`](docs/bulkscan-contract.md) — read that first
if you're touching `rig/uploader.py`. For the parts list, wiring, and
what still needs to be physically built, see
[`docs/hardware-build-guide.md`](docs/hardware-build-guide.md).

## Status

- `rig/uploader.py` — implements the contract's retry/halt table exactly
  (401/403/409 halt immediately; 400/5xx/network retry the same seq with
  backoff then halt; a mismatched echoed `seq` halts). Unit-tested.
- `rig/camera.py` — thin `picamera2` wrapper (Pi-only import, deferred so
  the rest of the package can be tested off-Pi).
- `rig/feeder.py` — GPIO control for a single-motor, two-sensor feeder.
  **This is a starting point, not a finished design** — the physical
  feeder doesn't exist yet. Expect to adjust pin assumptions, sensor
  polarity, and timing once it's built (see "Building the feeder" below).
- `rig/cli.py` — runs one pass of one job end to end.

## Raspberry Pi setup

1. Flash Raspberry Pi OS (Bookworm or later), enable the camera in
   `raspi-config` if needed, reboot.
2. Install the camera stack and GPIO libs from apt (picamera2 is not
   pip-installable in any reliable way on Pi OS — it depends on
   `libcamera` system bindings):
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-libcamera python3-venv
   ```
3. Clone this repo, then create a venv that can still see the apt-installed
   picamera2/libcamera packages:
   ```bash
   git clone <repo-url> && cd tcgbulkscanner
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Copy the env file and fill in your job's credentials:
   ```bash
   cp .env.example .env
   $EDITOR .env   # set BASE_URL and DEVICE_KEY from the admin page
   ```

## Running a job

Pass 1, feed order:

```bash
python -m rig.cli --job <JOB_UUID> --pass 1
```

Flip the output pile once (see the contract — do not shuffle or
re-square), then pass 2:

```bash
python -m rig.cli --job <JOB_UUID> --pass 2
```

The rig halts (non-zero exit, message on stderr) on anything that means
"stop and fix something": bad key, wrong/closed job, a feeder jam, or an
upload that won't succeed after 5 retries. It logs progress per card but
never logs the device key.

If a pass gets interrupted partway through, you can resume the seq
counter instead of redoing the whole pass:

```bash
python -m rig.cli --job <JOB_UUID> --pass 1 --start-seq 42
```

`--max-cards N` caps how many cards a run will process — useful for a
quick smoke test with a handful of cards before committing to a full box.

## Building the feeder

`rig/feeder.py` assumes:

- A feed motor driven by a relay/MOSFET on `FEEDER_MOTOR_PIN` — pulsed
  high for `FEED_PULSE_SECONDS` per card (open-loop, not closed-loop
  position control).
- Two IR break-beam/obstacle sensors, wired active-low (pin reads LOW
  when a card is present): one across the input hopper
  (`HOPPER_SENSOR_PIN`, used for "are we out of cards"), one at the
  camera lane (`FEEDER_SENSOR_PIN`, used to confirm a card actually
  arrived after a feed pulse).

None of that is load-bearing — it's sized for the simplest mechanism
that could work. Once you've settled on motor/sensor hardware:

```bash
python scripts/feeder_calibrate.py            # live sensor monitor —
                                               # confirm polarity by hand
python scripts/feeder_calibrate.py --pulse    # fire one feed pulse per
                                               # Enter keypress, tune
                                               # FEED_PULSE_SECONDS
```

If the real mechanism ends up materially different (a stepper instead of
a DC motor, a single sensor instead of two, a solenoid pusher), `rig/feeder.py`
is the only file that needs to change — `rig/cli.py` only calls
`has_cards()` and `advance_one_card()`.

## Photo settings

`rig/camera.py` captures at 1600×1200, matching the contract's
recommended 1200–1600px long side. Lighting and camera positioning are a
physical rig concern (see the contract's "Photo requirements") — no
amount of software fixes glare from an overhead point light.

## Running the tests

No Pi or hardware required — `gpiozero`'s mock pin factory stands in for
GPIO, and `responses` mocks the HTTP calls:

```bash
pip install -r requirements-dev.txt
pytest
```
