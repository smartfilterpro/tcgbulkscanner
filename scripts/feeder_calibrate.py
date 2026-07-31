#!/usr/bin/env python3
"""Hardware bring-up helper for the feeder.

Run this on the Pi once the motor and sensors are wired up, before
trusting rig.cli to run a real job. It prints live sensor state so you
can confirm polarity (does the reading flip when you block the beam by
hand?) and lets you fire single feed pulses to tune FEED_PULSE_SECONDS.

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
from rig.feeder import CardFeeder, FeederJam


def monitor(feeder):
    print("Ctrl-C to stop. Block/unblock each sensor by hand and watch it flip.")
    try:
        while True:
            print(
                f"\rhopper={'CARD' if feeder.has_cards() else 'empty':<6} "
                f"lane={'CARD' if feeder._lane_sensor.is_active else 'clear':<6}",
                end="",
                flush=True,
            )
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()


def jog(feeder):
    print("Press Enter to fire one feed pulse, Ctrl-C to stop.")
    try:
        while True:
            input()
            try:
                feeder.advance_one_card()
                print("  -> card reached the lane sensor")
            except FeederJam as exc:
                print(f"  -> {exc}")
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
        sensor_pin=cfg.feeder_sensor_pin,
        hopper_sensor_pin=cfg.hopper_sensor_pin,
        pulse_seconds=cfg.feed_pulse_seconds,
        feed_timeout=cfg.feed_timeout_seconds,
    )
    try:
        jog(feeder) if args.pulse else monitor(feeder)
    finally:
        feeder.close()


if __name__ == "__main__":
    main()
