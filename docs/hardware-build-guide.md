# Hardware build guide — bulk-scan rig

> **Supersedes the original version of this document.** The first draft
> proposed a lane-and-output-tray design: advance a card into a fixed
> camera framing position, photograph it there, push it to a tray. That
> was never built. What exists is a **bucket rig** — described below —
> and `rig/` has been rewritten to match it. If you're looking at old
> notes, PRs, or a stale checkout that still talks about a "lane sensor"
> or an output tray, they're describing the abandoned design.

## What the program does

Unchanged at the top level: `python -m rig.cli --job <uuid> --pass 1`
runs one pass of one job — feed a card, photograph it, upload it,
repeat — twice per job (flip the pile as a block between passes; see
`bulkscan-contract.md`). What changed is everything about how "feed"
and "photograph" work mechanically, covered below.

## The machine as built (ground truth)

**Actuation.** One 12V gearmotor, switched by an IRLZ44N low-side MOSFET
on BCM 17. On/off only — no PWM, no speed control, no direction control
(set by lead polarity), no encoder. One GPIO write is the entire control
surface. A single pulse must carry one card from the retard gate, across
the deck, and over the edge into the bucket.

**Hopper sensor — BCM 22.** Reflective IR module under the deck, looking
up through a 3mm sight hole at the underside of the bottom card in the
magazine. Reads card-present until the last card is pulled. Active-low.

**Exit sensor — BCM 27.** Reflective IR module on an arch above the
deck at lane 36, looking down with 12mm clearance; the deck ends at lane
40. Active-low. **This is a transit detector, 4mm upstream of the deck
edge — not an arrival detector.** A card trips it on the way past and is
already falling before it clears. It is never LOW while the card is in
the camera's view. `rig/feeder.py`'s `advance_one_card()` waits for the
LOW→HIGH edge (card cleared the arch), not for a level — get this wrong
and you photograph an empty bucket mid-fall.

**Camera.** Raspberry Pi Camera Module 3, standard lens, on CSI, fixed
gantry looking straight down into the bucket, rotated 90° so the card's
long axis lies along the sensor's long axis. Minimum focus 100mm.

| | Empty bucket | Full bucket |
|---|---|---|
| Lens to top card | 160mm | 113.5mm |
| Card width in frame | 1365px | 1924px |

Both distances clear the 100mm minimum, but a fixed focus locked on an
empty bucket will be soft by the time it's full — `rig/camera.py` runs
an autofocus cycle before capture (every `REFOCUS_EVERY_CARDS` cards).

**Lighting.** Two cross-polarized LED bars at 45°, own 12V supply, not
controlled from the Pi. **Never PWM-dim these** — against a rolling
shutter, PWM bands every frame differently.

**Magazine capacity** is roughly 150 cards. A 1000-card job needs
several magazine swaps within a single pass.

## Pin and config mapping

Pin assignments are unchanged from the original wiring and don't need
to move — only the exit sensor's variable name changed, to stop the
software implying it's a fixed-position "lane" sensor.

| `.env` variable | BCM pin | Wired to |
|---|---|---|
| `FEEDER_MOTOR_PIN` | 17 | MOSFET gate driving the feed motor |
| `FEEDER_EXIT_SENSOR_PIN` | 27 | Reflective IR sensor on the exit arch |
| `HOPPER_SENSOR_PIN` | 22 | Reflective IR sensor under the magazine |

Both sensors are active-low: card present = LOW. That part of the
original wiring assumption held and didn't need to change.

Timing variables — see `.env.example` for the full commentary, this is
the summary:

| Variable | Status |
|---|---|
| `FEED_PULSE_SECONDS` | Starting point 0.55–0.75s, given — tune with `scripts/feeder_calibrate.py` |
| `FEED_TIMEOUT_SECONDS` | 2.0s default carries margin at the top of that pulse range |
| `SETTLE_SECONDS` | **Not measured.** No safe default shipped; the rig refuses to start without it set. Free-fall + tumble time, expected to be materially longer than a mechanical-push settle. |
| `BUCKET_CAPACITY_CARDS` | **Not verified.** No safe default shipped; the rig refuses to start without it set. Do not derive this from card thickness — measure it, or get a verified count, and tell the rig what it is. |

## Why the camera pipeline changed

The original photo requirements (one card per frame, fixed distance,
fixed crop) assumed a card presented in a constant position. The bucket
rig can't give the camera that: every frame is a photo of the whole
pile, the newest card is just whatever's on top, and the pile grows
~40% in frame width over a run. `rig/vision.py` compensates in software:

1. Diff the current frame against the photo taken before this card
   landed. The region that changed is the new card — this also proves,
   independent of the exit sensor, that a card actually landed in frame
   (the exit sensor only proves one left the deck).
2. Take that region's rotated bounding rectangle, deskew and crop it to
   an upright image sized to `CARD_OUTPUT_LONG_SIDE_PX` — this is the
   image that actually gets uploaded, not the raw bucket photo.
3. If that fails to find a clean region (first-card lighting mismatch,
   two cards landing on top of each other, etc.), the rig logs a warning
   and uploads the full raw frame rather than halting the pass — a soft
   miss on one card isn't worth stopping a 1000-card job for, but it is
   logged, not silent.

Raw (undeskewed) frames are also kept in `CAPTURE_DIR/raw/` for
debugging — cheap insurance if the crop pipeline needs tuning.

This is a software workaround for a mechanical decision, not a design
you should try to defeat by squaring up the pile — a card landing well
off-register just gives the diff/crop step a worse rectangle to work
with.

## What still needs measuring before a real job

Two numbers are known-unmeasured, not defaulted, and will stop the rig
cold (`SystemExit`, before any GPIO is touched) if you try to run
`rig.cli` without them:

- **`SETTLE_SECONDS`** — watch captured frames (`CAPTURE_DIR/raw/`) for
  motion blur or mid-tumble shots and increase until they stop.
- **`BUCKET_CAPACITY_CARDS`** — how many cards can land before the pile
  risks the camera's 100mm minimum focus. Needs a verified count against
  this specific gantry height, not a thickness-based guess.

## Build / tuning order

1. Wire the Pi and both sensors with the motor *disconnected*; run
   `scripts/feeder_calibrate.py` (monitor mode) and confirm both flip
   correctly when blocked by hand.
2. Wire in the motor; run `scripts/feeder_calibrate.py --pulse` to fire
   single pulses by hand-feeding loose cards, tuning `FEED_PULSE_SECONDS`
   against the exit sensor's clear-edge timing. The script distinguishes
   "never tripped" (misfeed) from "tripped and stuck" (jam) in its
   output.
3. Load the magazine, re-tune pulse timing and `FEED_TIMEOUT_SECONDS`
   against real feeding (magazine feed differs from hand-feeding).
4. Mount the camera and lighting; measure `SETTLE_SECONDS` by capturing
   real drops and checking for blur/tumble in the raw frames.
5. Run a full magazine (~150 cards) with `--max-cards 150` and watch the
   pile grow to determine `BUCKET_CAPACITY_CARDS`.
6. Only then run a real job.
