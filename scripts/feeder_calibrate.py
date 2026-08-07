#!/usr/bin/env python3
"""Hardware bring-up helper for the feeder.

Run this on the Pi once the motor and sensors are wired up, before
trusting rig.cli to run a real job. It prints live sensor state so you
can confirm polarity (does the reading flip when you block the beam by
hand?) and lets you fire single feed pulses to tune FEED_PULSE_SECONDS
and FEED_TIMEOUT_SECONDS against the exit-arch transit, which is what
advance_one_card() actually waits on now (an edge pair, not a level —
see rig/feeder.py).

This script deliberately does NOT require SETTLE_SECONDS or
BUCKET_CAPACITY_CARDS to be set in .env — it doesn't use either (no
camera involved), and both are still-unmeasured values for this rig.
Settle time is passed as 0 here so a calibration pulse returns as soon
as the exit sensor clears, with no added delay.

Usage:
    python3 scripts/feeder_calibrate.py            # live sensor monitor
    python3 scripts/feeder_calibrate.py --pulse    # jog the motor on Enter
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rig.config import load_config
from rig.feeder import CardFeeder, FeederJam, FeederMisfeed


def monitor(feeder):
    print("Ctrl-C to stop. Block/unblock each sensor by hand and watch it flip.")
    try:
        while True:
            print(
                f"\rhopper={'CARD' if feeder.has_cards() else 'empty':<6} "
                f"exit={'CARD' if feeder._exit_sensor.is_active else 'clear':<6}",
                end="",
                flush=True,
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


def jog(feeder):
    print("Press Enter to fire one feed pulse, Ctrl-C to stop.")
    print("Watch for: sensor never trips (misfeed) vs. trips and clears (ok) "
          "vs. trips and stays tripped (hard jam under the arch).")
    try:
        while True:
            input()
            started = time.monotonic()
            try:
                feeder.advance_one_card()
                print(f"  -> ok, cleared the arch in {time.monotonic() - started:.2f}s")
            except FeederMisfeed as exc:
                print(f"  -> misfeed: {exc}")
            except FeederJam as exc:
                print(f"  -> JAM: {exc}")
    except KeyboardInterrupt:
        print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--pulse", action="store_true", help="jog the motor instead of just monitoring"
    )
    args = p.parse_args()

    cfg = load_config()
    feeder = CardFeeder(
        motor_pin=cfg.feeder_motor_pin,
        exit_sensor_pin=cfg.feeder_exit_sensor_pin,
        hopper_sensor_pin=cfg.hopper_sensor_pin,
        pulse_seconds=cfg.feed_pulse_seconds,
        feed_timeout=cfg.feed_timeout_seconds,
        settle_seconds=0,
    )
    try:
        jog(feeder) if args.pulse else monitor(feeder)
    finally:
        feeder.close()


if __name__ == "__main__":
    main()
