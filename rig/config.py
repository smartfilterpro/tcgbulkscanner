"""Loads rig configuration from environment variables (and a .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    base_url: str
    device_key: str
    feeder_motor_pin: int
    feeder_exit_sensor_pin: int
    hopper_sensor_pin: int
    hopper_sensor_active_low: bool
    feeder_exit_sensor_active_low: bool
    feed_pulse_seconds: float
    feed_timeout_seconds: float
    settle_seconds: float | None
    bucket_capacity_cards: int | None
    refocus_every_cards: int
    camera_rotation_degrees: int
    card_diff_threshold: int
    card_output_long_side_px: int
    capture_dir: str


def _optional_float(name: str):
    raw = os.environ.get(name)
    return float(raw) if raw else None


def _optional_int(name: str):
    raw = os.environ.get(name)
    return int(raw) if raw else None


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def require_measured_values(cfg: "Config") -> None:
    """Not everything that reads config needs these — e.g. the feeder
    calibration script only cares about pulse/timeout. Call this before
    starting a real job (rig.cli does); it's the point where missing
    measured values become fatal instead of silently defaulted."""
    missing = []
    if cfg.settle_seconds is None:
        missing.append("SETTLE_SECONDS")
    if cfg.bucket_capacity_cards is None:
        missing.append("BUCKET_CAPACITY_CARDS")
    if missing:
        raise SystemExit(
            f"{', '.join(missing)} not set. These are measured values from "
            "the physical rig, not something safe to default — see "
            "docs/hardware-build-guide.md."
        )


def load_config() -> Config:
    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    device_key = os.environ.get("DEVICE_KEY", "")
    if not base_url:
        raise SystemExit("BASE_URL is not set (check your .env)")
    if not device_key:
        raise SystemExit("DEVICE_KEY is not set (check your .env)")

    feed_pulse_seconds = float(os.environ.get("FEED_PULSE_SECONDS", 0.65))
    feed_timeout_seconds = float(os.environ.get("FEED_TIMEOUT_SECONDS", 2.0))
    if feed_pulse_seconds >= feed_timeout_seconds:
        raise SystemExit(
            f"FEED_PULSE_SECONDS ({feed_pulse_seconds}) must be less than "
            f"FEED_TIMEOUT_SECONDS ({feed_timeout_seconds}) — otherwise the "
            "motor could still be running past the timeout meant to bound it."
        )

    camera_rotation_degrees = int(os.environ.get("CAMERA_ROTATION_DEGREES", 0))
    if camera_rotation_degrees not in (0, 90, 180, 270):
        raise SystemExit(
            f"CAMERA_ROTATION_DEGREES must be one of 0, 90, 180, 270 "
            f"(got {camera_rotation_degrees})"
        )

    return Config(
        base_url=base_url,
        device_key=device_key,
        feeder_motor_pin=int(os.environ.get("FEEDER_MOTOR_PIN", 17)),
        feeder_exit_sensor_pin=int(os.environ.get("FEEDER_EXIT_SENSOR_PIN", 27)),
        hopper_sensor_pin=int(os.environ.get("HOPPER_SENSOR_PIN", 22)),
        # Bench-verified sensors output <=3.3V in both states; active-low
        # (card=LOW) is expected but not yet confirmed end-to-end on the
        # Pi. If monitor mode shows a sensor's interpreted state backwards
        # from its raw level, flip the corresponding value here — no code
        # change needed for a polarity mismatch.
        hopper_sensor_active_low=_bool("HOPPER_SENSOR_ACTIVE_LOW", True),
        feeder_exit_sensor_active_low=_bool("FEEDER_EXIT_SENSOR_ACTIVE_LOW", True),
        feed_pulse_seconds=feed_pulse_seconds,
        feed_timeout_seconds=feed_timeout_seconds,
        # Left as None rather than defaulted when unset: this is free-fall
        # + tumble settle time for the bucket rig, unmeasured so far. See
        # docs/hardware-build-guide.md. require_measured_values() turns a
        # missing value fatal before a real job starts.
        settle_seconds=_optional_float("SETTLE_SECONDS"),
        # Left as None rather than defaulted when unset: no verified card
        # count for how close the pile can get to the camera's 100mm
        # minimum focus distance.
        bucket_capacity_cards=_optional_int("BUCKET_CAPACITY_CARDS"),
        refocus_every_cards=int(os.environ.get("REFOCUS_EVERY_CARDS", 1)),
        # Default 0 (no-op): the physical 90 degree camera mount may or may
        # not already produce a correctly-oriented raw frame — unverified
        # from here. Check during the camera-check bring-up step and set
        # this only if raw frames actually come out sideways.
        camera_rotation_degrees=camera_rotation_degrees,
        card_diff_threshold=int(os.environ.get("CARD_DIFF_THRESHOLD", 30)),
        card_output_long_side_px=int(os.environ.get("CARD_OUTPUT_LONG_SIDE_PX", 1500)),
        capture_dir=os.environ.get("CAPTURE_DIR", "/tmp/bulkscan"),
    )
