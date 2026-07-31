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
    feeder_sensor_pin: int
    hopper_sensor_pin: int
    feed_pulse_seconds: float
    feed_timeout_seconds: float
    settle_seconds: float
    capture_dir: str


def load_config() -> Config:
    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    device_key = os.environ.get("DEVICE_KEY", "")
    if not base_url:
        raise SystemExit("BASE_URL is not set (check your .env)")
    if not device_key:
        raise SystemExit("DEVICE_KEY is not set (check your .env)")

    return Config(
        base_url=base_url,
        device_key=device_key,
        feeder_motor_pin=int(os.environ.get("FEEDER_MOTOR_PIN", 17)),
        feeder_sensor_pin=int(os.environ.get("FEEDER_SENSOR_PIN", 27)),
        hopper_sensor_pin=int(os.environ.get("HOPPER_SENSOR_PIN", 22)),
        feed_pulse_seconds=float(os.environ.get("FEED_PULSE_SECONDS", 0.35)),
        feed_timeout_seconds=float(os.environ.get("FEED_TIMEOUT_SECONDS", 2.0)),
        settle_seconds=float(os.environ.get("SETTLE_SECONDS", 0.25)),
        capture_dir=os.environ.get("CAPTURE_DIR", "/tmp/bulkscan"),
    )
