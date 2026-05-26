from bpm_midi_sync.config import Config
from bpm_midi_sync.controller import Controller, State


def test_seed_locks_immediately():
    ctl = Controller(Config())
    ctl.seed(128.0)
    assert ctl.state == State.LOCKED
    assert ctl.target_bpm == 128.0


def test_acquiring_then_locked():
    cfg = Config(acquire_beats=4)
    ctl = Controller(cfg)
    assert ctl.state == State.IDLE
    t = 0.0
    for i in range(4):
        ctl.on_beat(t, 120.0)
        t += 0.5
    assert ctl.state == State.LOCKED
    assert abs(ctl.target_bpm - 120.0) < 1e-6


def test_silence_goes_to_hold_and_keeps_tempo():
    cfg = Config(acquire_beats=2, silence_timeout_s=1.0)
    ctl = Controller(cfg)
    ctl.on_beat(0.0, 120.0)
    ctl.on_beat(0.5, 120.0)
    assert ctl.state == State.LOCKED
    held = ctl.target_bpm
    # ビートが来ないまま時間だけ進む
    ctl.tick(2.0, 0.01)
    assert ctl.state == State.HOLD
    assert ctl.target_bpm == held  # テンポは維持（Stop は送らない）


def test_low_gain_follow_is_slew_limited():
    # 追従は follow_max_bps[BPM/秒] でしか動かない（plan §0 低ゲイン）
    cfg = Config(acquire_beats=1, follow_max_bps=1.0, lock_tolerance=0.5)
    ctl = Controller(cfg)
    ctl.seed(120.0)
    ctl.on_beat(0.0, 130.0)   # 検出が +10 BPM 跳んでも…
    ctl.tick(0.0, 1.0)        # 1 秒で最大 +1 BPM しか動かない
    assert abs(ctl.target_bpm - 121.0) < 1e-6


def test_octave_detection_ignored_after_lock():
    cfg = Config(acquire_beats=1, lock_tolerance=0.25)
    ctl = Controller(cfg)
    ctl.seed(120.0)
    ctl.on_beat(0.0, 240.0)   # 倍テンポ誤検出は ±25% 外なので無視
    ctl.tick(0.0, 1.0)
    assert abs(ctl.target_bpm - 120.0) < 1e-6
