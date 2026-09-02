"""GPIO control for the card feeder.

The rig as built: cards are singulated from a bottom-feed magazine by
one roller, pass a retard gate, run off the end of the deck, and fall
face-up into a bucket a fixed camera looks straight down into. There is
no belt, no flip drum, and no output tray. Motor drive is a single
low-side MOSFET (IRLZ44N) — on/off only, no PWM, no direction/reverse
capability exists in hardware, so none exists here either.

  - FEEDER_MOTOR_PIN drives the MOSFET gate. One pulse must carry a card
    from the gate, across the deck, and over the edge.
  - HOPPER_SENSOR_PIN is a reflective IR sensor under the deck looking
    up through a sight hole at the underside of the bottom card in the
    magazine. Bench-verified to output <=3.3V in both states.
  - FEEDER_EXIT_SENSOR_PIN is a reflective IR sensor on an arch above
    the deck, upstream of the deck edge. It is a TRANSIT detector, not
    an arrival detector: a card trips it on the way past and is airborne
    over the bucket before it clears. It is never active while the card
    is in the camera's view, so advance_one_card() waits for the
    trip->clear edge pair, not a level.

Both sensors are expected to be active-low (card = LOW), but this is a
bench expectation, not yet confirmed end-to-end on the Pi as of the
current bring-up — hence hopper_active_low/exit_active_low are
constructor parameters sourced from .env (see config.py), not hardcoded.
If monitor mode shows a sensor's interpreted state backwards from its
raw level, flip the corresponding *_ACTIVE_LOW value in .env; nothing in
this file should need to change for a polarity mismatch.
"""

import logging
import time
from dataclasses import dataclass

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


@dataclass(frozen=True)
class FeedResult:
    """Timing from one successful advance_one_card() call, in seconds.
    Used by scripts/feeder_calibrate.py to tune FEED_TIMEOUT_SECONDS and
    sanity-check SETTLE_SECONDS, and logged per-card by cli.py so a
    misfeed can be diagnosed from the log alone."""

    time_to_trip: float  # pulse end -> exit sensor went active (entered arch)
    low_duration: float  # exit sensor active -> cleared (transit time under the arch)


class CardFeeder:
    def __init__(
        self,
        motor_pin,
        exit_sensor_pin,
        hopper_sensor_pin,
        pulse_seconds,
        feed_timeout,
        settle_seconds,
        hopper_active_low=True,
        exit_active_low=True,
    ):
        self._motor = DigitalOutputDevice(motor_pin)
        # pull_up=True is a safe default regardless of active_low config:
        # these sensors bench-verify as actively driving both states, so
        # the pull-up only matters if the line is ever floating/disconnected
        # (where it defaults the reading high). Polarity interpretation is
        # handled separately by _card_present(), driven by *_active_low.
        self._exit_sensor = DigitalInputDevice(exit_sensor_pin, pull_up=True)
        self._hopper_sensor = DigitalInputDevice(hopper_sensor_pin, pull_up=True)
        self._hopper_active_low = hopper_active_low
        self._exit_active_low = exit_active_low
        self._pulse_seconds = pulse_seconds
        self._feed_timeout = feed_timeout
        self._settle_seconds = settle_seconds

    def _card_present(self, sensor: DigitalInputDevice, active_low: bool) -> bool:
        """sensor.is_active is True when the pin reads LOW (pull_up=True
        is fixed regardless of active_low — see __init__). This is the
        one place active_low is applied, so a polarity flip in .env
        changes behavior without touching any wait/poll logic."""
        return sensor.is_active if active_low else not sensor.is_active

    def has_cards(self) -> bool:
        """True while the hopper sensor still sees a card in the magazine."""
        return self._card_present(self._hopper_sensor, self._hopper_active_low)

    def _wait_until_present(
        self, sensor: DigitalInputDevice, active_low: bool, present: bool, timeout: float
    ) -> bool:
        deadline = time.monotonic() + timeout
        poll_interval = 0.005
        while time.monotonic() < deadline:
            if self._card_present(sensor, active_low) == present:
                return True
            time.sleep(poll_interval)
        return False

    def advance_one_card(self) -> FeedResult:
        """Pulse the feed motor, confirm a card actually transited the
        exit arch and cleared it, then wait for it to land and stop
        tumbling in the bucket.

        Raises FeederMisfeed if the exit sensor never trips (nothing
        fed), or FeederJam if it trips and never clears (stalled under
        the arch — a hard jam, don't retry the pulse). Returns a
        FeedResult with the edge-pair timing on success.
        """
        self._motor.on()
        try:
            time.sleep(self._pulse_seconds)
        finally:
            self._motor.off()
        pulse_end = time.monotonic()

        tripped = self._wait_until_present(
            self._exit_sensor, self._exit_active_low, present=True, timeout=self._feed_timeout
        )
        trip_time = time.monotonic()

        if not tripped:
            logger.debug(
                "exit sensor never tripped within %.2fs of pulse end", self._feed_timeout
            )
            if self.has_cards():
                raise FeederMisfeed(
                    "feed pulse ran but no card reached the exit sensor and the "
                    "magazine still has cards — check the roller and retard gate"
                )
            raise FeederMisfeed(
                "feed pulse ran but no card reached the exit sensor and the "
                "hopper now reads empty — magazine likely ran dry mid-pulse"
            )

        time_to_trip = trip_time - pulse_end
        logger.debug("exit sensor tripped %.3fs after pulse end", time_to_trip)

        cleared = self._wait_until_present(
            self._exit_sensor, self._exit_active_low, present=False, timeout=self._feed_timeout
        )
        clear_time = time.monotonic()

        if not cleared:
            raise FeederJam(
                "a card tripped the exit sensor and did not clear the arch — "
                "it is stalled on the deck, do not retry, clear it physically"
            )

        low_duration = clear_time - trip_time
        logger.debug("exit sensor cleared %.3fs after tripping (transit time)", low_duration)

        time.sleep(self._settle_seconds)

        return FeedResult(time_to_trip=time_to_trip, low_duration=low_duration)

    def close(self):
        self._motor.off()
        self._motor.close()
        self._exit_sensor.close()
        self._hopper_sensor.close()
