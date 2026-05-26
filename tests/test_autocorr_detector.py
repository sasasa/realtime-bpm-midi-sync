import pytest

from bpm_midi_sync.config import Config
from bpm_midi_sync.engine import Engine
from bpm_midi_sync.eval.synth import click_track
from bpm_midi_sync.sources.array import ArraySource


def _run(cfg, y):
    eng = Engine(cfg)
    eng.run(ArraySource(y, cfg.samplerate, cfg.hop_size))
    return eng


def test_autocorr_recovers_tempo():
    cfg = Config(detector="autocorr", prefer_bpm=120.0)
    y = click_track(120.0, 14.0, cfg.samplerate, seed=1)
    eng = _run(cfg, y)
    assert eng.controller.state.value in ("LOCKED", "HOLD")
    assert abs(eng.controller.target_bpm - 120.0) < 3.0


@pytest.mark.parametrize("prefer,expected", [(90.0, 90.0), (180.0, 180.0)])
def test_autocorr_octave_resolved_by_prior(prefer, expected):
    # 180 BPM のインパルス列（= 90 BPM の 8 分音符）。prior でどちらの拍に乗るか決まる
    cfg = Config(detector="autocorr", prefer_bpm=prefer)
    y = click_track(180.0, 14.0, cfg.samplerate, seed=2)
    eng = _run(cfg, y)
    assert eng.controller.target_bpm is not None
    assert abs(eng.controller.target_bpm - expected) < 4.0


def test_lock_range_excludes_octave():
    # 158 BPM 主体の信号でも、期待 79 ±35%[51-107] に拘束すれば 158 を排除して 79 に乗る
    cfg = Config(detector="autocorr", prefer_bpm=79.0, tempo_lock_range_pct=0.35)
    y = click_track(158.0, 14.0, cfg.samplerate, seed=3)
    eng = _run(cfg, y)
    assert eng.controller.target_bpm is not None
    assert abs(eng.controller.target_bpm - 79.0) < 4.0
