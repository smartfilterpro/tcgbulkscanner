import responses

from rig.uploader import PhotoUploader, SequenceMismatch, UploadHalt

URL = "https://example.test/api/bulk/photo"


def make_uploader():
    return PhotoUploader("https://example.test", "bk_test")


@responses.activate
def test_success_returns_body(tmp_path):
    photo = tmp_path / "frame.jpg"
    photo.write_bytes(b"fake-jpeg")
    responses.add(
        responses.POST,
        URL,
        json={"ok": True, "pass": 1, "seq": 17, "ordinal": 17},
        status=200,
    )

    result = make_uploader().upload("job-1", 1, 17, str(photo))

    assert result == {"ok": True, "pass": 1, "seq": 17, "ordinal": 17}


@responses.activate
def test_halts_immediately_on_403(tmp_path):
    photo = tmp_path / "frame.jpg"
    photo.write_bytes(b"fake-jpeg")
    responses.add(responses.POST, URL, body="forbidden", status=403)

    try:
        make_uploader().upload("job-1", 1, 1, str(photo))
        assert False, "expected UploadHalt"
    except UploadHalt:
        pass

    assert len(responses.calls) == 1  # no retries on a halt status


@responses.activate
def test_retries_then_succeeds_on_transient_500(tmp_path, monkeypatch):
    monkeypatch.setattr("rig.uploader.time.sleep", lambda _: None)
    photo = tmp_path / "frame.jpg"
    photo.write_bytes(b"fake-jpeg")
    responses.add(responses.POST, URL, body="server error", status=500)
    responses.add(responses.POST, URL, body="server error", status=500)
    responses.add(
        responses.POST,
        URL,
        json={"ok": True, "pass": 1, "seq": 3, "ordinal": 3},
        status=200,
    )

    result = make_uploader().upload("job-1", 1, 3, str(photo))

    assert result["seq"] == 3
    assert len(responses.calls) == 3


@responses.activate
def test_halts_after_exhausting_retries(tmp_path, monkeypatch):
    monkeypatch.setattr("rig.uploader.time.sleep", lambda _: None)
    photo = tmp_path / "frame.jpg"
    photo.write_bytes(b"fake-jpeg")
    responses.add(responses.POST, URL, body="server error", status=500)

    try:
        make_uploader().upload("job-1", 1, 1, str(photo))
        assert False, "expected UploadHalt"
    except UploadHalt:
        pass

    assert len(responses.calls) == 5


@responses.activate
def test_sequence_mismatch_halts(tmp_path):
    photo = tmp_path / "frame.jpg"
    photo.write_bytes(b"fake-jpeg")
    responses.add(
        responses.POST,
        URL,
        json={"ok": True, "pass": 1, "seq": 99, "ordinal": 99},
        status=200,
    )

    try:
        make_uploader().upload("job-1", 1, 1, str(photo))
        assert False, "expected SequenceMismatch"
    except SequenceMismatch:
        pass
