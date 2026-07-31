import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from rig.feeder import CardFeeder, FeederJam


@pytest.fixture(autouse=True)
def mock_gpio():
    Device.pin_factory = MockFactory()
    yield
    Device.pin_factory.reset()


def make_feeder(**overrides):
    kwargs = dict(
        motor_pin=17,
        sensor_pin=27,
        hopper_sensor_pin=22,
        pulse_seconds=0,
        feed_timeout=0.2,
    )
    kwargs.update(overrides)
    return CardFeeder(**kwargs)


def test_has_cards_reflects_hopper_sensor():
    feeder = make_feeder()
    hopper_pin = Device.pin_factory.pin(22)

    hopper_pin.drive_high()  # inactive (pulled up, no card)
    assert feeder.has_cards() is False

    hopper_pin.drive_low()  # active-low sensor: card present
    assert feeder.has_cards() is True

    feeder.close()


def test_advance_one_card_succeeds_when_lane_sensor_trips():
    feeder = make_feeder()
    lane_pin = Device.pin_factory.pin(27)
    lane_pin.drive_low()  # card already in place at the lane sensor

    feeder.advance_one_card()  # should not raise

    feeder.close()


def test_advance_one_card_raises_feederjam_on_timeout():
    feeder = make_feeder()
    # lane sensor never trips -> pin stays high (inactive)

    with pytest.raises(FeederJam):
        feeder.advance_one_card()

    feeder.close()
