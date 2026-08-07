import argparse
import logging
import os
import signal
from pathlib import Path

from . import vision
from .camera import Camera
from .config import load_config, require_measured_values
from .feeder import CardFeeder, FeederJam, FeederMisfeed
from .uploader import PhotoUploader, SequenceMismatch, UploadHalt

logger = logging.getLogger("rig")


class Shutdown(Exception):
    """Raised from a signal handler so SIGTERM/SIGINT go through the same
    try/finally cleanup as everything else — a bare SIGTERM does not run
    Python finally blocks on its own, and a crash that leaves the motor
    pin high runs it until someone pulls power."""


def _install_signal_handlers():
    def _handler(signum, _frame):
        raise Shutdown(f"signal {signal.Signals(signum).name} received")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


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


def _prompt(message: str) -> str:
    return input(message).strip().lower()


def run(args, cfg):
    Path(cfg.capture_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.capture_dir, "raw").mkdir(parents=True, exist_ok=True)

    uploader = PhotoUploader(cfg.base_url, cfg.device_key)
    feeder = None
    camera = None
    seq = args.start_seq
    magazine_num = 1
    cards_since_bucket_empty = 0
    total_captured = 0

    try:
        feeder = CardFeeder(
            motor_pin=cfg.feeder_motor_pin,
            exit_sensor_pin=cfg.feeder_exit_sensor_pin,
            hopper_sensor_pin=cfg.hopper_sensor_pin,
            pulse_seconds=cfg.feed_pulse_seconds,
            feed_timeout=cfg.feed_timeout_seconds,
            settle_seconds=cfg.settle_seconds,
        )
        camera = Camera()

        camera.refocus()
        baseline_gray = vision.to_gray(camera.capture_array())

        while True:
            if not feeder.has_cards():
                logger.info(
                    "magazine empty — %s cards captured so far this pass",
                    seq - args.start_seq,
                )
                answer = _prompt(
                    f"Load magazine #{magazine_num + 1} and press Enter when ready, "
                    "or type 'done' if this pass is finished: "
                )
                if answer == "done":
                    break
                magazine_num += 1
                continue

            if args.max_cards and seq - args.start_seq >= args.max_cards:
                logger.info("reached --max-cards cap (%s), stopping", args.max_cards)
                break

            try:
                feeder.advance_one_card()
            except FeederJam as exc:
                raise SystemExit(
                    f"HALT (hard jam): {exc} — do not retry the pulse; clear the "
                    f"stall physically, then re-run this pass from seq={seq}"
                )
            except FeederMisfeed as exc:
                raise SystemExit(
                    f"HALT (misfeed): {exc} — re-run this pass from seq={seq}"
                )

            if total_captured % cfg.refocus_every_cards == 0:
                camera.refocus()

            frame = camera.capture_array()
            frame_gray = vision.to_gray(frame)

            photo_path = os.path.join(
                cfg.capture_dir, f"pass{args.pass_num}_{seq:05d}.jpg"
            )
            raw_path = os.path.join(
                cfg.capture_dir, "raw", f"pass{args.pass_num}_{seq:05d}.jpg"
            )
            vision.save_jpeg(frame, raw_path)

            rect = vision.locate_new_card(baseline_gray, frame_gray, cfg.card_diff_threshold)
            cropped = (
                vision.crop_and_deskew(frame, rect, cfg.card_output_long_side_px)
                if rect is not None
                else None
            )

            if cropped is not None:
                vision.save_jpeg(cropped, photo_path)
            else:
                logger.warning(
                    "seq=%s: could not isolate the new card from the pile "
                    "(diff-based crop failed) — uploading the full frame, check %s",
                    seq,
                    raw_path,
                )
                vision.save_jpeg(frame, photo_path)

            baseline_gray = frame_gray
            total_captured += 1

            try:
                result = uploader.upload(args.job, args.pass_num, seq, photo_path)
            except (UploadHalt, SequenceMismatch) as exc:
                raise SystemExit(str(exc))

            logger.info("seq=%s uploaded ok (ordinal=%s)", seq, result.get("ordinal"))
            seq += 1
            cards_since_bucket_empty += 1

            if cards_since_bucket_empty >= cfg.bucket_capacity_cards:
                _prompt(
                    f"Bucket at capacity ({cfg.bucket_capacity_cards} cards) — the "
                    "pile may be nearing the camera's minimum focus distance. Empty "
                    "the bucket now, then press Enter to continue: "
                )
                cards_since_bucket_empty = 0
                camera.refocus()
                baseline_gray = vision.to_gray(camera.capture_array())
    except Shutdown as exc:
        raise SystemExit(f"HALT: {exc} — motor stopped, exiting cleanly")
    finally:
        if camera:
            camera.close()
        if feeder:
            feeder.close()

    logger.info("pass %s done: %s cards", args.pass_num, seq - args.start_seq)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    _install_signal_handlers()
    cfg = load_config()
    require_measured_values(cfg)
    run(args, cfg)


if __name__ == "__main__":
    main()
