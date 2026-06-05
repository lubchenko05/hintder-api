"""Tests for the Gemini service's pure helpers (no network calls)."""

import base64

from dating.services.ai import (
    _decode_image,
    _GeminiMessage,
    _GeminiPhoto,
    _msg,
    _photos,
    DEFAULT_TONE,
    normalise_tone,
    SUPPORTED_TONES,
)


def test_normalise_tone_passes_supported() -> None:
    for tone in SUPPORTED_TONES:
        assert normalise_tone(tone) == tone


def test_normalise_tone_falls_back() -> None:
    assert normalise_tone(None) == DEFAULT_TONE
    assert normalise_tone("nonsense") == DEFAULT_TONE


def test_decode_image_data_url() -> None:
    raw = b"\x89PNG fake bytes"
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode()
    decoded, mime = _decode_image(data_url)
    assert decoded == raw
    assert mime == "image/png"


def test_decode_image_raw_base64_defaults_jpeg() -> None:
    raw = b"hello"
    decoded, mime = _decode_image(base64.b64encode(raw).decode())
    assert decoded == raw
    assert mime == "image/jpeg"


def test_msg_generates_id_and_clamps_cringe() -> None:
    m = _GeminiMessage(text="hi", category="best", label="opener", cringeRisk=150)
    out = _msg(m, "funny")
    assert out.tone == "funny"
    assert len(out.id) == 10
    assert out.cringeRisk == 100


def test_photos_rotate_palette() -> None:
    photos = [
        _GeminiPhoto(caption="a", vibe="v", tags=["t"], unlocks="u"),
        _GeminiPhoto(caption="b", vibe="v", tags=["t"], unlocks="u"),
    ]
    out = _photos(photos)
    assert out[0].art == 0 and out[1].art == 1
    assert out[0].g1 and out[0].g2
    assert out[0].g1 != out[1].g1
