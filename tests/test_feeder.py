import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from rig.feeder import CardFeeder, FeederJam, FeederMisfeed


@pytest.fixture(autouse=True)
def mock_gpio():
    Device.pin_factory = MockFactory()
    yield
    Device.pin_factory.reset()


def make_feeder(**overrides):
    kwargs = dict(
        motor_pin=17,
        exit_sensor_pin=27,
        hopper_sensor_pin=22,
        pulse_seconds=0,
        feed_timeout=0.3,
        settle_seconds=0,
    )
    kwargs.update(overrides)
    feeder = CardFeeder(**kwargs)
    # Idle state for both active-low sensors: pin high == no card present.
    Device.pin_factory.pin(kwargs["exit_sensor_pin"]).drive_high()
    Device.pin_factory.pin(kwargs["hopper_sensor_pin"]).drive_high()
    return feeder


def transit(pin, after=0.03, low_for=0.03):
    """Simulate a card transiting the exit arch: pin goes LOW, then HIGH,
    on a background timer, mimicking the real sensor while
    advance_one_card() polls from the main thread."""

    def go_low():
        pin.drive_low()
        threading.Timer(low_for, pin.drive_high).start()

    threading.Timer(after, go_low).start()


def test_has_cards_reflects_hopper_sensor():
    feeder = make_feeder()
    hopper_pin = Device.pin_factory.pin(22)

    assert feeder.has_cards() is False  # idle high = no card

    hopper_pin.drive_low()  # active-low sensor: card present
    assert feeder.has_cards() is True

    feeder.close()


def test_advance_one_card_succeeds_on_clean_transit():
    feeder = make_feeder()
    exit_pin = Device.pin_factory.pin(27)
    transit(exit_pin)

    feeder.advance_one_card()  # should not raise

    feeder.close()


def test_advance_one_card_raises_misfeed_when_hopper_still_has_cards():
    feeder = make_feeder()
    Device.pin_factory.pin(22).drive_low()  # magazine still has cards
    # exit sensor never trips (left idle high by make_feeder)

    with pytest.raises(FeederMisfeed, match="still has cards"):
        feeder.advance_one_card()

    feeder.close()


def test_advance_one_card_raises_misfeed_when_hopper_now_empty():
    feeder = make_feeder()
    # hopper left idle high (empty) by make_feeder; exit sensor never trips

    with pytest.raises(FeederMisfeed, match="hopper now reads empty"):
        feeder.advance_one_card()

    feeder.close()


def test_advance_one_card_raises_jam_when_stalled_under_arch():
    feeder = make_feeder()
    exit_pin = Device.pin_factory.pin(27)
    exit_pin.drive_low()  # trips immediately...
    # ...and never clears (no timer to bring it back high)

    with pytest.raises(FeederJam):
        feeder.advance_one_card()

    feeder.close()


def test_advance_one_card_sleeps_settle_seconds_after_clearing():
    feeder = make_feeder(settle_seconds=0.05)
    exit_pin = Device.pin_factory.pin(27)
    transit(exit_pin)

    started = time.monotonic()
    feeder.advance_one_card()
    elapsed = time.monotonic() - started

    assert elapsed >= 0.05
    feeder.close()
