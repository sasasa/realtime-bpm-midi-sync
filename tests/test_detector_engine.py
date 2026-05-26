import pytest

from bpm_midi_sync.config import Config
from bpm_midi_sync.eval.batch_eval import evaluate_array
from bpm_midi_sync.eval.synth import click_track


@pytest.mark.parametrize("bpm", [100.0, 120.0, 150.0])
def test_numpy_detector_recovers_tempo(bpm):
    cfg = Config(detector="numpy", estimator="pll")
    samples = click_track(bpm, 16.0, cfg.samplerate, jitter_ms=0.0, seed=1)
    res = evaluate_array(cfg, samples, bpm)
    assert res.locked
    assert res.final_bpm is not None
    assert abs(res.final_bpm - bpm) < 3.0


def test_jittered_click_is_smoothed():
    cfg = Config(detector="numpy", estimator="pll")
    bpm = 120.0
    samples = click_track(bpm, 20.0, cfg.samplerate, jitter_ms=6.0, seed=2)
    res = evaluate_array(cfg, samples, bpm)
    assert res.locked
    # 平滑化が効いて出力 BPM のばらつきは小さい
    assert res.jitter is not None
    assert res.jitter < 2.0
