"""Isolate the newly-landed card from a top-down photo of the bucket pile.

The camera sees the whole pile, not one card in a fixed frame: every
shot after the first also contains part of the previous card underneath
the new one, and the pile-to-lens distance shrinks as cards accumulate
(the contract's "one card per frame, filling most of the frame"
requirement doesn't hold for a raw bucket photo).

The newest card is whatever changed between this photo and the one
taken before it landed, so we diff the two frames, find the
largest connected region of change, and treat its rotated bounding
rectangle as the new card. That serves two purposes at once: it is the
crop/deskew region, and its mere existence is a software-only
confirmation that a card actually landed (the exit sensor only proves
one left the deck, not that it landed cleanly in frame).

This is a best-effort image-processing step, not a correctness
guarantee — see cli.py for the fallback when it can't find a clean
region.
"""

import numpy as np
import cv2
from PIL import Image


def to_gray(frame_rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)


def locate_new_card(prev_gray, curr_gray, diff_threshold: int, min_area_fraction: float = 0.03):
    """Returns a cv2.minAreaRect ((cx, cy), (w, h), angle) for the
    newest card, or None if no clean single region of change was found.
    """
    diff = cv2.absdiff(prev_gray, curr_gray)
    _, mask = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area_fraction * mask.size:
        return None

    return cv2.minAreaRect(largest)


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return np.array([tl, tr, br, bl], dtype="float32")


def crop_and_deskew(frame_rgb: np.ndarray, rect, long_side_px: int):
    """Warp the rotated rect out of frame_rgb into an upright image with
    its long side == long_side_px. Returns None if the rect is degenerate.
    """
    (w, h) = rect[1]
    if w <= 1 or h <= 1:
        return None

    src = _order_points(cv2.boxPoints(rect))

    long_edge, short_edge = max(w, h), min(w, h)
    out_long = long_side_px
    out_short = int(round(long_side_px * short_edge / long_edge))
    if h > w:
        out_w, out_h = out_short, out_long
    else:
        out_w, out_h = out_long, out_short

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame_rgb, matrix, (out_w, out_h))


def save_jpeg(frame_rgb: np.ndarray, path: str, quality: int = 85) -> None:
    Image.fromarray(frame_rgb).save(path, format="JPEG", quality=quality)
