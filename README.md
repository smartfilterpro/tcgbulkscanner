# tcgbulkscanner

Raspberry Pi rig that feeds a stack of cards, photographs each one, and
posts the photos to the TrainerDeck mail-in scanning service. The full
API contract this rig implements lives in
[`docs/bulkscan-contract.md`](docs/bulkscan-contract.md) — read that first
if you're touching `rig/uploader.py`. The physical machine — a
bottom-feed magazine that drops cards into a bucket a fixed camera looks
down into — is described in
[`docs/hardware-build-guide.md`](docs/hardware-build-guide.md); read that
first if you're touching `rig/feeder.py` or `rig/vision.py`.

## Status

- `rig/uploader.py` — implements the contract's retry/halt table exactly
  (401/403/409 halt immediately; 400/5xx/network retry the same seq with
  backoff then halt; a mismatched echoed `seq` halts). Unit-tested.
- `rig/feeder.py` — GPIO control for the built machine: one motor pulse
  per card, an edge-pair wait on the exit-arch sensor (transit, not
  arrival), a hopper sensor for magazine-empty. Distinguishes a misfeed
  (nothing reached the arch) from a hard jam (something's stuck under
  it). Unit-tested against a mocked GPIO backend.
- `rig/camera.py` — `picamera2` wrapper with per-shot autofocus, since
  the pile-to-lens distance shrinks as the bucket fills.
- `rig/vision.py` — isolates the newest card from a full-bucket photo by
  diffing against the previous frame, then crops and deskews it to the
  image that actually gets uploaded. Unit-tested with synthetic frames.
- `rig/cli.py` — runs one pass of one job end to end, pausing (not
  ending the pass) when a magazine runs dry, and pausing again when the
  bucket needs emptying.

## Raspberry Pi setup

1. Flash Raspberry Pi OS (Bookworm or later), enable the camera in
   `raspi-config` if needed, reboot.
2. Install the camera stack and GPIO libs from apt (picamera2 is not
   pip-installable in any reliable way on Pi OS — it depends on
   `libcamera` system bindings, including the Python `controls` module
   used for autofocus):
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
4. Copy the env file and fill in your job's credentials **and the
   measured values** — see below:
   ```bash
   cp .env.example .env
   $EDITOR .env
   ```

## Two values you must measure before running a real job

`rig.cli` refuses to start (before touching any GPIO pin) unless both
are set in `.env`:

- **`SETTLE_SECONDS`** — how long a card needs to free-fall off the deck
  and stop tumbling in the bucket before the shutter fires. Not a fixed
  hardware constant; measure it on your build.
- **`BUCKET_CAPACITY_CARDS`** — how many cards can pile up before the
  stack risks the camera's 100mm minimum focus distance.

See [`docs/hardware-build-guide.md`](docs/hardware-build-guide.md) for
how to measure both. `scripts/feeder_calibrate.py` does **not** require
either — it only exercises the feeder, not the camera.

## Running a job

Pass 1, feed order:

```bash
python -m rig.cli --job <JOB_UUID> --pass 1
```

The magazine holds ~150 cards; on a bigger job the rig will pause and
prompt you to load the next magazine rather than ending the pass — keep
answering the prompt (or type `done` when the pass is actually finished)
until the whole stack has gone through. It'll similarly pause and prompt
you to empty the bucket once `BUCKET_CAPACITY_CARDS` is reached.

Flip the **bucket pile** (not a magazine) as one block once the pass is
done — see the contract — then pass 2:

```bash
python -m rig.cli --job <JOB_UUID> --pass 2
```

The rig halts (non-zero exit, message on stderr) on anything that means
"stop and fix something": bad key, wrong/closed job, a misfeed, a hard
jam, an upload that won't succeed after 5 retries, or a SIGTERM/SIGINT —
in every case the motor is left off before the process exits. It logs
progress per card but never logs the device key.

If a pass gets interrupted partway through, you can resume the seq
counter instead of redoing the whole pass:

```bash
python -m rig.cli --job <JOB_UUID> --pass 1 --start-seq 42
```

`--max-cards N` caps how many cards a run will process — useful for a
quick smoke test before committing to a full magazine.

## Photo pipeline

The camera looks straight down into the bucket, not at one card in a
fixed frame — see `docs/hardware-build-guide.md` for why that ruled out
a fixed crop/focus and what `rig/vision.py` does about it (diff against
the previous frame to isolate the newest card, then crop and deskew).
Raw, undeskewed frames are also kept under `CAPTURE_DIR/raw/` for
debugging the crop pipeline. Lighting and camera geometry are a physical
rig concern (see the contract's "Photo requirements") — no amount of
software fixes glare from a mis-mounted LED bar.

## Running the tests

No Pi or hardware required — `gpiozero`'s mock pin factory stands in for
GPIO, `responses` mocks the HTTP calls, and `rig/vision.py` is tested
against synthetic numpy frames instead of real photos:

```bash
pip install -r requirements-dev.txt
pytest
```
