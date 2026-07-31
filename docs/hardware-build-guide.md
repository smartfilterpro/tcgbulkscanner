# Hardware build guide — bulk-scan rig

This is the brief for building the physical rig that `rig/` (the Python
software in this repo) drives. Hand it to whoever is sourcing parts and
building the feeder — human or AI — alongside
[`bulkscan-contract.md`](bulkscan-contract.md) (the API contract) if they
also need to touch the software.

## What the program does

The software (already built, in `rig/`) runs one **pass** of one **job**
at a time from the command line:

```bash
python -m rig.cli --job <JOB_UUID> --pass 1
```

Its loop, once started, is entirely mechanical:

1. Ask the feeder "any cards left?" (`has_cards()`).
2. If yes, tell the feeder to push one card into camera position
   (`advance_one_card()`) and wait for it to arrive.
3. Pause briefly for the card to stop moving (motion blur kills
   readability).
4. Take one photo.
5. POST that photo to the TrainerDeck server with the job ID, pass
   number, and a sequence number, retrying on transient failures.
6. Repeat until the hopper is empty.

The operator runs this twice per job: once feeding the stack normally
(pass 1), then flips the output pile as a whole and runs it again
(pass 2, so cards arrive in reverse order). The server cross-checks the
two passes to auto-verify each card. None of that pairing/verification
logic is the rig's concern — the rig's only job is to keep cards moving
one at a time, keep photos sharp, and never lose track of which physical
card is which sequence number.

**What still needs to be built is everything physical**: a hopper that
holds a stack of cards, a mechanism that singulates and advances exactly
one card per pulse, two sensors the software reads to know the hopper
state and confirm a card arrived, a fixed camera mount, and consistent
lighting. The software already assumes a specific shape for that
hardware (see below) — treat that as a proposed design, not a
requirement, if a different mechanism makes more sense once you're
sourcing parts.

## Bill of materials

| Part | Role | Notes |
|---|---|---|
| Raspberry Pi 4B or 5 (4GB+) | Runs `rig/`, GPIO control | 5 is faster for capture-to-disk; 4B is fine |
| Raspberry Pi Camera Module 3 (or HQ Camera) | Photographs each card | CSI ribbon, official Pi camera — this is what `picamera2` in `rig/camera.py` talks to |
| MicroSD card (16GB+) + Pi power supply (official 5V/3A) | Boot media, power | Don't run the feed motor off the Pi's 5V rail — see below |
| DC gear motor, low RPM (e.g. 6V or 12V, geared down) | Turns a friction roller/belt to advance cards | Pick by whatever roller/belt mechanism you land on; low RPM + high torque beats a fast motor here |
| Relay module or logic-level MOSFET (e.g. IRLZ44N breakout) | Lets a 3.3V GPIO pin switch motor power on/off | This is `FEEDER_MOTOR_PIN` in the code — an on/off pulse, not variable speed |
| 2× IR break-beam or IR-obstacle sensor module (active-low output) | Card presence detection | One across the hopper, one at the camera lane — see "Sensor placement" |
| Separate motor power supply (e.g. 12V wall adapter, sized to the motor + roller load) | Powers the motor independent of the Pi | Share ground with the Pi, not the 5V rail — a stalled motor can brown out the Pi otherwise |
| 2× diffuse LED strips (~45° mounting angle) | Even lighting, kills holofoil glare | See "Photo requirements" in `bulkscan-contract.md` — this is the single biggest lever on read accuracy |
| Hopper, roller/belt mechanism, camera arm, output tray | The mechanical structure | 3D-printed or laser-cut; this repo has the `cadquery-part` skill available if you want to model these parametrically |
| Jumper wires, perfboard or small breadboard, mounting hardware | Wiring | — |

## How the parts map to the code

`rig/config.py` reads pin numbers and timings from `.env` (see
`.env.example`). Wiring should match these, or you edit `.env` to match
your wiring — either direction works, nothing is hardcoded elsewhere.

| `.env` variable | Default (BCM pin) | Wired to |
|---|---|---|
| `FEEDER_MOTOR_PIN` | 17 | Relay/MOSFET gate driving the feed motor |
| `FEEDER_SENSOR_PIN` | 27 | Break-beam sensor at the camera lane |
| `HOPPER_SENSOR_PIN` | 22 | Break-beam sensor across the input hopper |
| `FEED_PULSE_SECONDS` | 0.35 | How long the motor runs per card (tune by hand) |
| `FEED_TIMEOUT_SECONDS` | 2.0 | How long to wait for a card to reach the lane sensor before declaring a jam |
| `SETTLE_SECONDS` | 0.25 | Pause after the card arrives, before the shutter fires |
| — | CSI port | Camera Module, read by `rig/camera.py` via `picamera2` |

`rig/feeder.py` currently assumes both sensors are **active-low**
(reading LOW when a card is blocking the beam) — that's true of most
cheap IR-obstacle modules but not guaranteed for a true through-beam
pair. Verify polarity with `scripts/feeder_calibrate.py` before wiring
assumptions become a debugging session.

## Sensor placement

- **Hopper sensor** (`HOPPER_SENSOR_PIN`): positioned so the beam is
  broken as long as at least one card remains in the input stack, and
  clears the instant the last card is pulled. This is what
  `has_cards()` checks — get this wrong and the rig either stops one
  card early or runs the motor against an empty hopper.
- **Lane sensor** (`FEEDER_SENSOR_PIN`): positioned right at the camera
  framing position, so it trips only once a card is fully in place and
  ready to shoot. `advance_one_card()` blocks until this trips (or times
  out into a jam) — this is the interlock that keeps the photo from
  firing on an empty or half-arrived frame.

## What needs to be designed and built

1. **Hopper** — holds the stack, feeds from the top or bottom (bottom-feed
   with a friction pad is the usual choice for single-card singulation;
   top-feed with a kicker also works). Needs to hold enough cards for a
   sensible batch size without needing a refill mid-pass.
2. **Singulation + advance mechanism** — a motor-driven roller or belt
   that reliably pulls exactly one card per pulse. This is the hardest
   mechanical problem in the whole rig; double-feeds are exactly what
   the two-pass verification is designed to catch, but fewer of them
   means fewer cards falling to manual review.
3. **Camera mount** — fixed distance and angle above the lane, framing
   one card filling most of the shot per `bulkscan-contract.md`'s photo
   requirements. Rigid enough that it doesn't drift between cards or
   between passes.
4. **Lighting rig** — two diffuse LED strips at roughly 45°, no point
   sources, no flash. Glare over a holofoil card's name/number is called
   out in the contract as the top cause of failed reads.
5. **Output tray** — catches the pile as it's fed, in order, so the
   operator can flip it as one block between pass 1 and pass 2 without
   reshuffling.

## Suggested build order

1. Wire the Pi, camera, and both sensors on a breadboard with the motor
   *disconnected*; run `scripts/feeder_calibrate.py` (monitor mode) and
   confirm both sensors flip correctly when you block them by hand.
2. Wire in the motor driver; run `scripts/feeder_calibrate.py --pulse`
   to fire single pulses and tune `FEED_PULSE_SECONDS` against whatever
   roller/belt mechanism you've built, using loose cards by hand before
   the hopper exists.
3. Build the hopper and singulation mechanism, re-tune pulse timing and
   `FEED_TIMEOUT_SECONDS` against real card stock (sleeved and unsleeved
   cards feed differently if that matters for your use case).
4. Mount the camera and lighting, dial in framing and exposure using
   `Picamera2`'s preview tools before wiring it into `rig/camera.py`'s
   fixed still configuration.
5. Run a small real job end to end with `--max-cards 10` before trusting
   it with a full box.
