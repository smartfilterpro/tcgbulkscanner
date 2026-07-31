"""GPIO control for the card feeder.

This assumes a common, cheap build:

  - FEEDER_MOTOR_PIN drives a relay or MOSFET gate that runs the feed
    motor for as long as the pin is high (a single on/off pulse per
    card, not closed-loop position control).
  - HOPPER_SENSOR_PIN is a break-beam/IR-obstacle sensor sitting across
    the input hopper, wired active-low (most cheap IR obstacle modules
    pull their OUT pin low when they see an object): LOW = a card is
    sitting in the hopper.
  - FEEDER_SENSOR_PIN is a second break-beam sensor at the camera lane,
    same polarity: LOW = a card is in position to be photographed.

None of this is set in stone — it's a starting point sized for a simple
single-motor friction feeder with two IR break-beam sensors. When the
physical rig exists, use scripts/feeder_calibrate.py to check sensor
polarity and tune FEED_PULSE_SECONDS / FEED_TIMEOUT_SECONDS in .env, and
adjust this module if the mechanism (e.g. a stepper, a solenoid pusher,
a single sensor) ends up different.
"""

import logging
import time

from gpiozero import DigitalInputDevice, DigitalOutputDevice

logger = logging.getLogger(__name__)


class FeederJam(RuntimeError):
    """A feed pulse ran but no card arrived at the lane sensor in time."""


class CardFeeder:
    def __init__(
        self,
        motor_pin,
        sensor_pin,
        hopper_sensor_pin,
        pulse_seconds=0.35,
        feed_timeout=2.0,
    ):
        self._motor = DigitalOutputDevice(motor_pin)
        # pull_up=True + active_state=False -> is_active reflects the pin
        # reading LOW, i.e. an active-low sensor.
        self._lane_sensor = DigitalInputDevice(sensor_pin, pull_up=True)
        self._hopper_sensor = DigitalInputDevice(hopper_sensor_pin, pull_up=True)
        self._pulse_seconds = pulse_seconds
        self._feed_timeout = feed_timeout

    def has_cards(self) -> bool:
        """True while the hopper sensor still sees a card."""
        return self._hopper_sensor.is_active

    def advance_one_card(self) -> None:
        """Pulse the feed motor and block until a card reaches the lane
        sensor. Raises FeederJam on timeout — caller should halt the pass,
        not silently skip a seq number."""
        self._motor.on()
        try:
            time.sleep(self._pulse_seconds)
        finally:
            self._motor.off()

        deadline = time.monotonic() + self._feed_timeout
        while time.monotonic() < deadline:
            if self._lane_sensor.is_active:
                return
            time.sleep(0.02)
        raise FeederJam(
            "card did not reach the lane sensor after a feed pulse — check for a jam"
        )

    def close(self):
        self._motor.off()
        self._motor.close()
        self._lane_sensor.close()
        self._hopper_sensor.close()
