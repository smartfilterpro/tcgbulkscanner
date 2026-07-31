import argparse
import logging
import os
import time
from pathlib import Path

from .camera import Camera
from .config import load_config
from .feeder import CardFeeder, FeederJam
from .uploader import PhotoUploader, SequenceMismatch, UploadHalt

logger = logging.getLogger("rig")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Bulk-scan rig: feed cards, photograph, upload one pass of a job."
    )
    p.add_argument("--job", required=True, help="job UUID from the admin page")
    p.add_argument(
        "--pass", dest="pass_num", type=int, required=True, choices=(1, 2)
    )
    p.add_argument(
        "--start-seq",
        type=int,
        default=1,
        help="seq to start counting from, for resuming a partial pass",
    )
    p.add_argument(
        "--max-cards", type=int, default=None, help="stop after this many cards"
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def run(args, cfg):
    Path(cfg.capture_dir).mkdir(parents=True, exist_ok=True)

    uploader = PhotoUploader(cfg.base_url, cfg.device_key)
    feeder = CardFeeder(
        motor_pin=cfg.feeder_motor_pin,
        sensor_pin=cfg.feeder_sensor_pin,
        hopper_sensor_pin=cfg.hopper_sensor_pin,
        pulse_seconds=cfg.feed_pulse_seconds,
        feed_timeout=cfg.feed_timeout_seconds,
    )
    camera = Camera()

    seq = args.start_seq
    try:
        while feeder.has_cards():
            if args.max_cards and seq - args.start_seq >= args.max_cards:
                logger.info("reached --max-cards cap (%s), stopping", args.max_cards)
                break

            try:
                feeder.advance_one_card()
            except FeederJam as exc:
                raise SystemExit(
                    f"HALT: {exc} — fix the jam and re-run this pass from seq={seq}"
                )

            time.sleep(cfg.settle_seconds)
            photo_path = os.path.join(
                cfg.capture_dir, f"pass{args.pass_num}_{seq:05d}.jpg"
            )
            camera.capture(photo_path)

            try:
                result = uploader.upload(args.job, args.pass_num, seq, photo_path)
            except (UploadHalt, SequenceMismatch) as exc:
                raise SystemExit(str(exc))

            logger.info("seq=%s uploaded ok (ordinal=%s)", seq, result.get("ordinal"))
            seq += 1
    finally:
        camera.close()
        feeder.close()

    logger.info("pass %s done: %s cards", args.pass_num, seq - args.start_seq)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config()
    run(args, cfg)


if __name__ == "__main__":
    main()
