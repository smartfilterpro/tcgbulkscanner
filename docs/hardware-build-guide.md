# Hardware build guide — bulk-scan rig

> **Supersedes the original version of this document.** The first draft
> proposed a lane-and-output-tray design: advance a card into a fixed
> camera framing position, photograph it there, push it to a tray. That
> was never built. What exists is a **bucket rig** — described below —
> and `rig/` has been rewritten to match it. If you're looking at old
> notes, PRs, or a stale checkout that still talks about a "lane sensor"
> or an output tray, they're describing the abandoned design.
>
> **Status: fully wired as of 2026-09-02.** Everything in this document
> is now the electrical state of hardware on the bench, not a plan.

## What the program does

Unchanged at the top level: `python -m rig.cli --job <uuid> --pass 1`
runs one pass of one job — feed a card, photograph it, upload it,
repeat — twice per job (flip the pile as a block between passes; see
`bulkscan-contract.md`). What changed is everything about how "feed"
and "photograph" work mechanically, covered below.

## The machine as built (ground truth)

**Actuation.** One 12V gearmotor, switched by an IRLZ44N low-side MOSFET
on BCM 17 through a 150Ω series gate resistor, with a 10kΩ gate pulldown
to ground — the motor is held off in hardware while GPIO17 floats during
boot, before software ever touches it. A 1N4007 flyback diode is across
the motor. On/off only — no PWM, no speed control, no encoder. **Motor
direction is fixed in copper**: lead polarity and the flyback diode were
set on the bench so a pulse always moves a card toward the bucket.
There is no H-bridge and no reverse capability anywhere in this design
— software must never attempt to drive the motor the other way. If
direction ever looks wrong, that's a hardware fault to fix on the bench,
not something to compensate for in code. A single pulse must carry one
card from the retard gate, across the deck, and over the edge into the
bucket.

The hardware pulldown only covers the boot window. Software is still
responsible for driving the pin low on normal exit and on SIGINT/SIGTERM
— a crashed process that leaves GPIO17 high runs the motor until someone
pulls power. `rig/cli.py` handles this (see "Motor safety" below).

**Hopper sensor — BCM 22.** Reflective IR module under the deck, looking
up through a 3mm sight hole at the underside of the bottom card in the
magazine. Reads card-present until the last card is pulled.

**Exit sensor — BCM 27.** Reflective IR module on an arch above the
deck at lane 36, looking down with 12mm clearance; the deck ends at lane
40. **This is a transit detector, 4mm upstream of the deck edge — not an
arrival detector.** A card trips it on the way past and is already
falling before it clears. It is never active while the card is in the
camera's view. `rig/feeder.py`'s `advance_one_card()` waits for the
trip→clear edge pair, not a level — get this wrong and you photograph an
empty bucket mid-fall.

Both sensors' VCC comes from the Pi's 3V3 rail (physical pin 1), with a
common ground shared with the 12V motor/LED supply. Bench-verified: both
output ≤3.3V in both covered and uncovered states. **Active-low (card =
LOW) is the wiring expectation, but has not yet been confirmed
end-to-end on the Pi** — that confirmation is monitor mode's job, step 1
of the bring-up sequence below. See "Sensor polarity" for how a mismatch
is fixable without touching code.

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

**Power topology — one shared 12V supply.** The motor (through the
MOSFET) and the two cross-polarized 45° LED bars run from the **same**
12V 2A supply, star-wired at its terminals — this changed from an
earlier plan to give the LEDs their own separate supply. Consequences:

- The LEDs are **always on** whenever the supply is powered. There is no
  GPIO for them, no software control, and there must never be one —
  reject any lighting-control code path on sight. **Never PWM-dim
  these** in any case — against a rolling shutter, PWM bands every frame
  differently.
- The rail can sag briefly during a feed pulse. This is fine *because*
  capture never overlaps motor motion: `rig/feeder.py`'s
  pulse→exit-edge→settle ordering already guarantees `advance_one_card()`
  doesn't return (and therefore `rig/cli.py` doesn't call
  `camera.refocus()`/capture) until after `motor.off()` and the settle
  sleep have both completed. No code path fires the shutter while GPIO17
  is high — this is a structural guarantee of the call ordering, not
  something bolted on separately, and it must stay that way.

**Magazine capacity** is roughly 150 cards. A 1000-card job needs
several magazine swaps within a single pass.

## Pin and config mapping

Pin assignments are unchanged from the original wiring and don't need
to move — only the exit sensor's variable name changed, to stop the
software implying it's a fixed-position "lane" sensor.

| `.env` variable | BCM pin | Wired to |
|---|---|---|
| `FEEDER_MOTOR_PIN` | 17 (physical 11) | MOSFET gate driving the feed motor, through a 150Ω resistor |
| `FEEDER_EXIT_SENSOR_PIN` | 27 (physical 13) | Reflective IR sensor on the exit arch |
| `HOPPER_SENSOR_PIN` | 22 (physical 15) | Reflective IR sensor under the magazine |

### Sensor polarity

Active-low (card present = LOW) is the wiring expectation, bench-verified
at the voltage level (≤3.3V both states) but not yet confirmed as
*active-low specifically* end-to-end on the Pi. If `scripts/feeder_
calibrate.py`'s monitor mode shows a sensor's interpreted state
("CARD"/"empty") backwards from its raw level, **fix it in `.env`, not
code**:

| `.env` variable | Default |
|---|---|
| `HOPPER_SENSOR_ACTIVE_LOW` | `true` |
| `FEEDER_EXIT_SENSOR_ACTIVE_LOW` | `true` |

Flip either to `false` if that sensor's polarity turns out inverted —
`rig/feeder.py` reads both sensors through the same interpretation
helper either way, so nothing else needs to change.

### Motor safety

`FEEDER_MOTOR_PIN` (GPIO17) is guaranteed low: by the hardware pulldown
during boot, by `gpiozero` actively driving it low the moment `rig/`
claims the pin, on every normal exit path, and on SIGINT/SIGTERM (which
`rig/cli.py` routes through the same cleanup as a normal exit — a bare
SIGTERM doesn't run Python `finally` blocks on its own, so this is
handled explicitly, not assumed). A pulse is also hard-capped by
`FEED_PULSE_SECONDS` always being less than `FEED_TIMEOUT_SECONDS` —
`rig/config.py` refuses to start otherwise.

### Camera rotation

| `.env` variable | Default |
|---|---|
| `CAMERA_ROTATION_DEGREES` | `0` |

The physical 90° camera mount may or may not already produce a
correctly-oriented raw frame on its own — unverified without the
hardware in hand. Check this specifically during the camera-check
bring-up step (below); if raw frames come out sideways, set this to
`90`/`180`/`270` rather than adding any rotation logic in code.

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

## Bring-up sequence

The machine is wired; this is the order to bring the software up
against it.

1. **Monitor mode, motor lead disconnected.**
   ```bash
   python scripts/feeder_calibrate.py
   ```
   Cover each sensor's sight hole with a card by hand and confirm
   `hopper=` and `exit=` both flip to `CARD` and back. Output shows raw
   pin level alongside the interpreted state, so a polarity mismatch is
   visible directly — fix it via `HOPPER_SENSOR_ACTIVE_LOW` /
   `FEEDER_EXIT_SENSOR_ACTIVE_LOW` in `.env`, not code, if needed.

2. **Pulse mode.**
   ```bash
   python scripts/feeder_calibrate.py --pulse
   ```
   Load one card at the gate, press Enter. Reports the exit-sensor edge
   pair: how long after the pulse ended it tripped, and how long it
   stayed tripped (transit time). Tune `FEED_PULSE_SECONDS` upward from
   the starting point until transit is clean and repeatable — expect to
   land in **0.55–0.75s**. The reported transit duration is what sets
   `FEED_TIMEOUT_SECONDS` (~2× the pulse) and gives an early read on
   `SETTLE_SECONDS`.

3. **Camera check.**
   ```bash
   rpicam-hello --nopreview -t 2000
   python3 -c "from rig.camera import Camera; c = Camera(); print(c.capture_array().shape); c.close()"
   ```
   Confirm the second command runs clean through the actual `rig/`
   code path, not just the standalone tool. Check a captured raw frame
   for orientation — if it comes out sideways, set
   `CAMERA_ROTATION_DEGREES` (see above) rather than adding rotation
   logic anywhere.

4. **Acceptance run — 50 cards, single-stepped.** `rig.cli` refuses to
   start at all without `SETTLE_SECONDS` and `BUCKET_CAPACITY_CARDS` set
   (`require_measured_values()`), so this run needs *deliberately
   conservative starting guesses* in `.env` first — not invented
   precision, just a safe enough bound to get through the gate:
   `SETTLE_SECONDS` generously longer than the transit time step 2
   measured (free-fall + tumble takes longer than the arch transit), and
   `BUCKET_CAPACITY_CARDS` set low (e.g. 50, matching this run's
   `--max-cards`) so it can't silently run past a real risk. Then:
   ```bash
   python -m rig.cli --job <JOB_UUID> --pass 1 --max-cards 50 -v
   ```
   `-v` turns on per-card `DEBUG` logging of every feed's edge timing
   (`seq=... feed: tripped ...ms after pulse end, transit ...ms`), so a
   misfeed or jam partway through is diagnosable from the log alone
   without having watched it happen live.

Only after a clean 50-card run: tighten `SETTLE_SECONDS` for real from
this run's raw frames (`CAPTURE_DIR/raw/`, check for motion blur/
mid-tumble shots and trim down from the conservative starting guess),
then run a full magazine (~150 cards, `--max-cards 150`) to determine a
real `BUCKET_CAPACITY_CARDS`, then a real job.
