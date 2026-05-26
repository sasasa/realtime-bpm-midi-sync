import pytest

from bpm_midi_sync.config import Config
from bpm_midi_sync.tempo_estimator import TempoEstimator, _fold_bpm


def feed(est, bpm, n=16, t0=0.0):
    period = 60.0 / bpm
    out = None
    t = t0
    for _ in range(n):
        out = est.on_beat(t)
        t += period
    return out


@pytest.mark.parametrize("method", ["median", "pll"])
@pytest.mark.parametrize("bpm", [90.0, 120.0, 150.0])
def test_steady_tempo(method, bpm):
    est = TempoEstimator(Config(estimator=method))
    out = feed(est, bpm)
    assert out is not None
    assert abs(out - bpm) < 1.0


@pytest.mark.parametrize("method", ["median", "pll"])
def test_octave_fold(method):
    # 240 BPM 相当の打点は期待レンジ(60-200)で 120 に畳まれる
    est = TempoEstimator(Config(estimator=method, min_bpm=60, max_bpm=200))
    out = feed(est, 240.0, n=20)
    assert out is not None
    assert abs(out - 120.0) < 2.0


def test_fold_bpm():
    assert abs(_fold_bpm(240.0, 60, 200) - 120.0) < 1e-9
    assert abs(_fold_bpm(40.0, 60, 200) - 80.0) < 1e-9
    assert abs(_fold_bpm(120.0, 60, 200) - 120.0) < 1e-9


def test_outlier_rejected_does_not_jump():
    est = TempoEstimator(Config(estimator="median"))
    feed(est, 120.0, n=10)
    stable = est.bpm_out
    # 1 個だけ極端な IBI（倍以上）を入れても出力は飛ばない
    t = 10 * 0.5
    est.on_beat(t + 0.5)       # 正常
    est.on_beat(t + 0.5 + 1.3) # 外れ値
    assert abs(est.bpm_out - stable) < 1.0


def test_deadband_holds_small_changes():
    cfg = Config(estimator="median", deadband_bpm=0.5)
    est = TempoEstimator(cfg)
    feed(est, 120.0, n=12)
    before = est.bpm_out
    # ごく僅かな変化はデッドバンドで据え置き
    est.on_beat(12 * 0.5)
    est.on_beat(12 * 0.5 + 60.0 / 120.05)
    assert est.bpm_out == before
