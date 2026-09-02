import pytest

from rig.config import load_config


@pytest.fixture(autouse=True)
def base_env(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://example.test")
    monkeypatch.setenv("DEVICE_KEY", "bk_test")
    monkeypatch.delenv("SETTLE_SECONDS", raising=False)
    monkeypatch.delenv("BUCKET_CAPACITY_CARDS", raising=False)
    monkeypatch.delenv("FEED_PULSE_SECONDS", raising=False)
    monkeypatch.delenv("FEED_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CAMERA_ROTATION_DEGREES", raising=False)
    monkeypatch.delenv("HOPPER_SENSOR_ACTIVE_LOW", raising=False)
    monkeypatch.delenv("FEEDER_EXIT_SENSOR_ACTIVE_LOW", raising=False)
    yield


def test_pulse_must_be_less_than_timeout(monkeypatch):
    monkeypatch.setenv("FEED_PULSE_SECONDS", "2.0")
    monkeypatch.setenv("FEED_TIMEOUT_SECONDS", "2.0")

    with pytest.raises(SystemExit, match="must be less than"):
        load_config()


def test_pulse_less_than_timeout_is_accepted(monkeypatch):
    monkeypatch.setenv("FEED_PULSE_SECONDS", "0.65")
    monkeypatch.setenv("FEED_TIMEOUT_SECONDS", "2.0")

    cfg = load_config()

    assert cfg.feed_pulse_seconds == 0.65


def test_camera_rotation_defaults_to_zero():
    cfg = load_config()
    assert cfg.camera_rotation_degrees == 0


def test_camera_rotation_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("CAMERA_ROTATION_DEGREES", "45")

    with pytest.raises(SystemExit, match="must be one of"):
        load_config()


def test_sensor_polarity_defaults_true():
    cfg = load_config()
    assert cfg.hopper_sensor_active_low is True
    assert cfg.feeder_exit_sensor_active_low is True


def test_sensor_polarity_fixable_via_env(monkeypatch):
    monkeypatch.setenv("HOPPER_SENSOR_ACTIVE_LOW", "false")
    monkeypatch.setenv("FEEDER_EXIT_SENSOR_ACTIVE_LOW", "0")

    cfg = load_config()

    assert cfg.hopper_sensor_active_low is False
    assert cfg.feeder_exit_sensor_active_low is False
