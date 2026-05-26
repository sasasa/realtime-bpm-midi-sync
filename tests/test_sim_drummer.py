from bpm_midi_sync.config import Config
from bpm_midi_sync.eval.sim_drummer import simulate_closed_loop, stability_sweep


def test_closed_loop_stable_for_moderate_gain():
    cfg = Config(acquire_beats=4, follow_max_bps=1.0)
    r = simulate_closed_loop(cfg, intended_bpm=120.0, entrain_gain=0.2,
                             latency_s=0.15, duration_s=30.0, noise_ms=6.0)
    assert not r.diverged
    assert r.final_target() is not None
    # ドラマーの意図テンポ近傍に収束（暴走しない）
    assert abs(r.final_target() - 120.0) < 10.0


def test_stability_sweep_runs():
    cfg = Config(acquire_beats=4)
    rows = stability_sweep(cfg, gains=[0.0, 0.3], latencies=[0.05, 0.2],
                           intended_bpm=120.0, duration_s=15.0)
    assert len(rows) == 4
    for row in rows:
        assert "diverged" in row
