"""Camera wrapper.

picamera2 only installs/works on a Raspberry Pi with libcamera, so the
import is deferred into __init__ — this lets the rest of the rig (feeder,
uploader, cli argument parsing) be imported and unit-tested on a regular
machine without picamera2 present.
"""

import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_SIZE = (1600, 1200)


class Camera:
    def __init__(self, size=DEFAULT_SIZE, warmup_seconds=1.0):
        from picamera2 import Picamera2

        self._cam = Picamera2()
        still_config = self._cam.create_still_configuration(main={"size": size})
        self._cam.configure(still_config)
        self._cam.start()
        time.sleep(warmup_seconds)  # let auto-exposure/white-balance settle once

    def capture(self, path: str) -> str:
        self._cam.capture_file(path)
        return path

    def close(self):
        self._cam.close()
