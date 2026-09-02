#!/usr/bin/env python3
"""Hardware bring-up helper for the feeder.

Run this on the Pi once the motor and sensors are wired up, before
trusting rig.cli to run a real job.

Monitor mode prints each sensor's RAW pin level alongside its
INTERPRETED meaning (per HOPPER_SENSOR_ACTIVE_LOW / FEEDER_EXIT_SENSOR_
ACTIVE_LOW in .env), so a polarity mismatch is obvious at a glance: if
blocking a sensor doesn't change "empty"/"clear" to "CARD", the raw
level is still flipping (check that first) or the wiring/aim is wrong.
If the raw level flips correctly but the interpreted state doesn't
match reality, fix it by flipping the *_ACTIVE_LOW value in .env — not
by editing this script or rig/feeder.py.

Pulse mode fires the motor and reports the exit-sensor edge-pair timing:
how long after the pulse ended the sensor tripped, and how long it
stayed tripped (transit time under the arch). That's what sets
FEED_TIMEOUT_SECONDS (~2x the pulse) and sanity-checks SETTLE_SECONDS.

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
    print(
        f"Configured polarity: hopper_active_low={feeder._hopper_active_low}  "
        f"exit_active_low={feeder._exit_active_low}"
    )
    try:
        while True:
            hopper_raw = "LOW" if feeder._hopper_sensor.is_active else "HIGH"
            exit_raw = "LOW" if feeder._exit_sensor.is_active else "HIGH"
            hopper_present = feeder.has_cards()
            exit_present = feeder._card_present(feeder._exit_sensor, feeder._exit_active_low)
            print(
                f"\rhopper: raw={hopper_raw:<4} -> {'CARD ' if hopper_present else 'empty':<6} | "
                f"exit: raw={exit_raw:<4} -> {'CARD ' if exit_present else 'clear':<6}",
                end="",
                flush=True,
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


def jog(feeder):
    print("Press Enter to fire one feed pulse, Ctrl-C to stop.")
    print(
        "Reports: time from pulse-end to exit-sensor trip, and how long it "
        "stayed tripped (transit time under the arch)."
    )
    try:
        while True:
            input()
            try:
                result = feeder.advance_one_card()
                print(
                    f"  -> ok: tripped {result.time_to_trip * 1000:.0f}ms after "
                    f"pulse end, stayed tripped {result.low_duration * 1000:.0f}ms"
                )
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
        hopper_active_low=cfg.hopper_sensor_active_low,
        exit_active_low=cfg.feeder_exit_sensor_active_low,
    )
    try:
        jog(feeder) if args.pulse else monitor(feeder)
    finally:
        feeder.close()


if __name__ == "__main__":
    main()
