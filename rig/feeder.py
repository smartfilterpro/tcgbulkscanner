"""GPIO control for the card feeder.

The rig as built: cards are singulated from a bottom-feed magazine by
one roller, pass a retard gate, run off the end of the deck, and fall
face-up into a bucket a fixed camera looks straight down into. There is
no belt, no flip drum, and no output tray.

  - FEEDER_MOTOR_PIN drives a low-side MOSFET switching a 12V gearmotor.
    On/off only — no PWM, no speed control, no encoder. One pulse must
    carry a card from the gate, across the deck, and over the edge.
  - HOPPER_SENSOR_PIN is a reflective IR sensor under the deck looking
    up through a sight hole at the underside of the bottom card in the
    magazine. Active-low: reads card-present until the last card is
    pulled.
  - FEEDER_EXIT_SENSOR_PIN is a reflective IR sensor on an arch above
    the deck, upstream of the deck edge. Active-low. It is a TRANSIT
    detector, not an arrival detector: a card trips it on the way past
    and is airborne over the bucket before it clears. It is never LOW
    while the card is in the camera's view, so advance_one_card() must
    wait for the LOW->HIGH edge (card cleared the arch), not for a
    level.

Both sensors are reflective IR, not through-beam, but the polarity
convention (LOW = card present) is the same either way.
"""

import logging
import time

from gpiozero import DigitalInputDevice, DigitalOutputDevice

logger = logging.getLogger(__name__)


class FeederJam(RuntimeError):
    """A card tripped the exit sensor and never cleared it — it is
    stalled under the arch. Hard jam: do not retry the pulse, the card
    is still on the deck."""


class FeederMisfeed(RuntimeError):
    """A feed pulse ran and the exit sensor never went active — no card
    reached the arch. Could be the magazine running dry mid-pulse, a
    slipping roller, or a jammed retard gate; advance_one_card() tells
    the two apart by re-checking the hopper sensor."""


class CardFeeder:
    def __init__(
        self,
        motor_pin,
        exit_sensor_pin,
        hopper_sensor_pin,
        pulse_seconds,
        feed_timeout,
        settle_seconds,
    ):
        self._motor = DigitalOutputDevice(motor_pin)
        # pull_up=True -> is_active reflects the pin reading LOW, i.e.
        # these are active-low sensors.
        self._exit_sensor = DigitalInputDevice(exit_sensor_pin, pull_up=True)
        self._hopper_sensor = DigitalInputDevice(hopper_sensor_pin, pull_up=True)
        self._pulse_seconds = pulse_seconds
        self._feed_timeout = feed_timeout
        self._settle_seconds = settle_seconds

    def has_cards(self) -> bool:
        """True while the hopper sensor still sees a card in the magazine."""
        return self._hopper_sensor.is_active

    def _wait_until(self, sensor, active: bool, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        poll_interval = 0.005
        while time.monotonic() < deadline:
            if sensor.is_active == active:
                return True
            time.sleep(poll_interval)
        return False

    def advance_one_card(self) -> None:
        """Pulse the feed motor, confirm a card actually transited the
        exit arch and cleared it, then wait for it to land and stop
        tumbling in the bucket.

        Raises FeederMisfeed if the exit sensor never trips (nothing
        fed), or FeederJam if it trips and never clears (stalled under
        the arch — a hard jam, don't retry the pulse).
        """
        self._motor.on()
        try:
            time.sleep(self._pulse_seconds)
        finally:
            self._motor.off()

        if not self._wait_until(self._exit_sensor, active=True, timeout=self._feed_timeout):
            if self._hopper_sensor.is_active:
                raise FeederMisfeed(
                    "feed pulse ran but no card reached the exit sensor and the "
                    "magazine still has cards — check the roller and retard gate"
                )
            raise FeederMisfeed(
                "feed pulse ran but no card reached the exit sensor and the "
                "hopper now reads empty — magazine likely ran dry mid-pulse"
            )

        if not self._wait_until(self._exit_sensor, active=False, timeout=self._feed_timeout):
            raise FeederJam(
                "a card tripped the exit sensor and did not clear the arch — "
                "it is stalled on the deck, do not retry, clear it physically"
            )

        time.sleep(self._settle_seconds)

    def close(self):
        self._motor.off()
        self._motor.close()
        self._exit_sensor.close()
        self._hopper_sensor.close()
