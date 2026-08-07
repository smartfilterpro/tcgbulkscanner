import numpy as np
import cv2

from rig import vision


def blank(h=400, w=600, value=40):
    return np.full((h, w, 3), value, dtype=np.uint8)


def test_locate_new_card_finds_axis_aligned_rectangle():
    prev = blank()
    curr = prev.copy()
    cv2.rectangle(curr, (100, 100), (300, 250), (220, 220, 220), thickness=-1)

    rect = vision.locate_new_card(vision.to_gray(prev), vision.to_gray(curr), diff_threshold=30)

    assert rect is not None
    (cx, cy), (w, h), _angle = rect
    assert 190 < cx < 210
    assert 165 < cy < 185
    assert abs(w - 200) < 15 or abs(h - 200) < 15
    assert abs(w - 150) < 15 or abs(h - 150) < 15


def test_locate_new_card_returns_none_when_nothing_changed():
    prev = blank()
    curr = blank()

    rect = vision.locate_new_card(vision.to_gray(prev), vision.to_gray(curr), diff_threshold=30)

    assert rect is None


def test_locate_new_card_finds_rotated_rectangle():
    prev = blank()
    curr = prev.copy()
    center, size, angle = (300, 200), (220, 140), 20
    box = cv2.boxPoints((center, size, angle)).astype(int)
    cv2.fillConvexPoly(curr, box, (220, 220, 220))

    rect = vision.locate_new_card(vision.to_gray(prev), vision.to_gray(curr), diff_threshold=30)

    assert rect is not None
    (cx, cy), _, _ = rect
    assert abs(cx - 300) < 15
    assert abs(cy - 200) < 15


def test_crop_and_deskew_produces_long_side_matching_request():
    prev = blank()
    curr = prev.copy()
    cv2.rectangle(curr, (100, 100), (300, 300 + 140), (220, 220, 220), thickness=-1)
    rect = vision.locate_new_card(vision.to_gray(prev), vision.to_gray(curr), diff_threshold=30)

    warped = vision.crop_and_deskew(curr, rect, long_side_px=500)

    assert warped is not None
    h, w = warped.shape[:2]
    assert max(h, w) == 500


def test_crop_and_deskew_handles_degenerate_rect():
    rect = ((10, 10), (0, 0), 0)

    warped = vision.crop_and_deskew(blank(), rect, long_side_px=500)

    assert warped is None


def test_save_jpeg_round_trip(tmp_path):
    frame = blank(h=50, w=80)
    path = tmp_path / "out.jpg"

    vision.save_jpeg(frame, str(path))

    assert path.exists()
    assert path.stat().st_size > 0
