import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recipe as R  # noqa: E402

WF = {"1": {"class_type": "KSampler", "inputs": {"seed": 7, "steps": 20}}}


def make_recipe(wf=None, extra=None):
    return R.build_recipe("levitate", 7, ["input_01.png"], ["ltx-2.3.safetensors"], wf or WF,
                          extra or {"prompt": "a figure rises slowly " * 20})


def ffmpeg(*args):
    r = subprocess.run([R._ffmpeg(), "-y", "-v", "error", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def synth_mp4(path):
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-frames:v", "25",
           "-pix_fmt", "yuv420p", str(path))
    return path


def test_build_and_sidecar_roundtrip(tmp_path):
    rec = make_recipe()
    assert rec["schema"] == "opensauce.recipe/1"
    assert len(rec["id"]) == 10 and rec["api_workflow"] == WF
    p = R.write_sidecar(rec, tmp_path / "recipes")
    assert p.name == f"{rec['id']}.json"
    assert json.loads(p.read_text(encoding="utf-8")) == rec
    assert R.recipe_url(rec).endswith(f"/recipes/{rec['id']}.json")


def test_mp4_metadata_roundtrip(tmp_path):
    rec = make_recipe()
    out = R.embed_mp4_metadata(synth_mp4(tmp_path / "a.mp4"), rec)
    assert R.read_recipe_from_mp4(out, sidecar_dir=None) == rec


def test_mp4_metadata_gzip_large(tmp_path):
    rng = np.random.default_rng(0)
    big = {str(i): {"class_type": "X", "inputs": {"v": rng.random(8).tolist()}} for i in range(2500)}
    rec = make_recipe(wf=big)
    assert len(R._canon(rec)) > R.GZ_LIMIT
    assert R._pack(rec).startswith("gz:")
    out = R.embed_mp4_metadata(synth_mp4(tmp_path / "b.mp4"), rec)
    assert R.read_recipe_from_mp4(out, sidecar_dir=None) == rec


def test_sidecar_fallback_when_tags_stripped(tmp_path):
    rec = make_recipe()
    R.write_sidecar(rec, tmp_path / "recipes")
    out = R.embed_mp4_metadata(synth_mp4(tmp_path / "c.mp4"), rec)
    stripped = tmp_path / "stripped.mp4"
    # keep only the title: drop the recipe payload tags
    ffmpeg("-i", str(out), "-c", "copy", "-map_metadata", "-1", "-metadata",
           f"title=OPEN SAUCE levitate {rec['id']}", str(stripped))
    assert R.read_recipe_from_mp4(stripped, tmp_path / "recipes") == rec


def test_card_non_blank(tmp_path):
    p = R.render_recipe_card(make_recipe(), tmp_path / "card.png")
    img = np.asarray(Image.open(p))
    assert img.shape == (1350, 1080, 3)
    assert img.std() > 10


def _decode_last_frame(frames_u8, crf=32, height=720):
    n, h, w, _ = frames_u8.shape
    raw = subprocess.run(
        [R._ffmpeg(), "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "24",
         "-i", "-", "-vf", f"scale='if(gt(iw,ih),-2,{height})':'if(gt(iw,ih),{height},-2)'", "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
         "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "-"],
        input=frames_u8.tobytes(), capture_output=True)
    assert raw.returncode == 0, raw.stderr
    return raw.stdout


def _roundtrip_last_frame(h, w, tmp_path):
    rng = np.random.default_rng(1)
    base = np.linspace(40, 200, w, dtype=np.float32)[None, :, None] * np.ones((h, 1, 3), np.float32)
    base += rng.normal(0, 6, (h, w, 3))
    frames = np.clip(np.repeat(base[None] / 255.0, 24, axis=0), 0, 1).astype(np.float32)
    url = R.recipe_url(make_recipe())
    burned = R.burn_endframe_qr(frames, url)
    assert burned.dtype == np.float32 and burned.shape == frames.shape
    assert not np.array_equal(burned[-1], frames[-1]) and np.array_equal(burned[0], frames[0])
    assert burned[-1].mean() > 0.1  # LAW-7: never black
    mp4 = tmp_path / "re.mp4"
    mp4.write_bytes(_decode_last_frame((burned * 255).round().astype(np.uint8), height=720))
    cap = cv2.VideoCapture(str(mp4))
    last = None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        last = f
    cap.release()
    assert last is not None
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(last)
    return text, url, last


@pytest.mark.parametrize("h,w", [(1080, 1920), (1280, 704), (704, 1280)])
def test_endframe_qr_survives_recompression(tmp_path, h, w):
    text, url, last = _roundtrip_last_frame(h, w, tmp_path)
    assert min(last.shape[:2]) == 720
    assert text == url


def test_qr_default_size_frac_documented():
    assert R.QR_SIZE_FRAC >= 0.14
