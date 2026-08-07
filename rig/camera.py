"""Camera wrapper.

picamera2/libcamera only install on a Raspberry Pi, so the import is
deferred into __init__ — this lets the rest of the rig (feeder,
uploader, vision, cli argument parsing) be imported and unit-tested on a
regular machine without them present.

The rig looks straight down into a bucket whose pile-to-lens distance
shrinks from ~160mm (empty) to ~113.5mm (full) over a run — both past
the Camera Module 3's 100mm minimum focus, but a fixed focus locked on
an empty bucket will be soft by the time it's full. refocus() runs an
autofocus cycle; cli.py calls it every REFOCUS_EVERY_CARDS cards.
"""

import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_SIZE = (1600, 1200)


class Camera:
    def __init__(self, size=DEFAULT_SIZE, warmup_seconds=1.0):
        from libcamera import controls
        from picamera2 import Picamera2

        self._controls = controls
        self._cam = Picamera2()
        # NOTE: RGB888 request - verify on real hardware that channel
        # order comes back as RGB and not BGR (a known picamera2/libcamera
        # quirk on some versions); swap in vision.save_jpeg if colors
        # look wrong in captured JPEGs.
        still_config = self._cam.create_still_configuration(
            main={"size": size, "format": "RGB888"}
        )
        self._cam.configure(still_config)
        self._cam.set_controls({"AfMode": controls.AfModeEnum.Auto})
        self._cam.start()
        time.sleep(warmup_seconds)  # let AE/AWB settle once at startup

    def capture_array(self):
        return self._cam.capture_array("main")

    def refocus(self) -> bool:
        """Runs a blocking autofocus cycle. Returns whether it actually
        locked — callers should keep going either way (the alternative is
        no photo at all), but should surface a failed lock to the
        operator rather than silently capturing at a stale focus."""
        try:
            locked = self._cam.autofocus_cycle()
        except Exception:
            logger.warning("autofocus cycle raised — keeping current focus")
            return False
        if not locked:
            logger.warning("autofocus cycle did not lock — capturing at current focus anyway")
        return bool(locked)

    def close(self):
        self._cam.close()
