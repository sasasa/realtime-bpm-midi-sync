"""閉ループ安定性の検証用「反応するドラマー」（plan §12-4）。

録音は固定なので §0 の閉ループ安定性は測れない。ここではドラマーを次のモデルで
シミュレートする:

  next_ibi = (1 - g) * P_intended + g * P_heard + noise

P_heard = ルーパー（= MIDI クロック = controller.target_bpm）を遅延 τ で聴いた周期。
g(entrain_gain) と τ(latency_s)、自前の追従ゲイン follow_max_bps をスイープして
発振せず収束するかを見る。検出器は通さず、ビート時刻を直接 estimator に渡す
（純粋に制御ループの安定性だけを見るため）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from ..config import Config
from ..controller import Controller
from ..tempo_estimator import TempoEstimator


@dataclass
class SimResult:
    times: List[float] = field(default_factory=list)
    target_bpm: List[float] = field(default_factory=list)   # ルーパー側
    drummer_bpm: List[float] = field(default_factory=list)  # ドラマー側
    diverged: bool = False

    def final_target(self) -> Optional[float]:
        return self.target_bpm[-1] if self.target_bpm else None

    def final_drummer(self) -> Optional[float]:
        return self.drummer_bpm[-1] if self.drummer_bpm else None


def simulate_closed_loop(config: Config, intended_bpm: float = 120.0,
                         entrain_gain: float = 0.2, latency_s: float = 0.15,
                         duration_s: float = 30.0, noise_ms: float = 8.0,
                         seed: int = 0, dt: float = 0.01) -> SimResult:
    rng = np.random.default_rng(seed)
    est = TempoEstimator(config)
    ctl = Controller(config)

    p_intended = 60.0 / intended_bpm
    next_beat = p_intended
    res = SimResult()
    # 遅延付きで「聴いたルーパー BPM」を引くための履歴 (t, bpm)
    target_hist: List[tuple] = []

    t = 0.0
    steps = int(duration_s / dt)
    for _ in range(steps):
        t += dt
        target = ctl.tick(t, dt)
        if target is not None:
            target_hist.append((t, target))

        if t >= next_beat:
            bpm = est.on_beat(t)
            ctl.on_beat(t, bpm)

            heard = _heard_bpm(target_hist, t - latency_s)
            if heard is None:
                p_next = p_intended
            else:
                p_heard = 60.0 / heard
                p_next = (1 - entrain_gain) * p_intended + entrain_gain * p_heard
            p_next += rng.uniform(-noise_ms, noise_ms) / 1000.0
            p_next = max(0.1, p_next)
            next_beat += p_next

            res.times.append(t)
            res.target_bpm.append(target if target is not None else float("nan"))
            res.drummer_bpm.append(60.0 / p_next)

            if target is not None and (target < intended_bpm / 2 or target > intended_bpm * 2):
                res.diverged = True

    return res


def _heard_bpm(hist: List[tuple], t: float) -> Optional[float]:
    if not hist or t <= hist[0][0]:
        return None
    # t 以前で最も新しい値
    val = None
    for ts, bpm in hist:
        if ts <= t:
            val = bpm
        else:
            break
    return val


def stability_sweep(config: Config, gains, latencies, **kwargs) -> List[dict]:
    """(entrain_gain, latency) を総当たりし、発散有無と最終誤差を返す。"""
    rows = []
    for g in gains:
        for lat in latencies:
            r = simulate_closed_loop(config, entrain_gain=g, latency_s=lat, **kwargs)
            intended = kwargs.get("intended_bpm", 120.0)
            ft = r.final_target()
            rows.append({
                "entrain_gain": g,
                "latency_s": lat,
                "diverged": r.diverged,
                "final_target": ft,
                "final_error": None if ft is None else abs(ft - intended),
            })
    return rows
