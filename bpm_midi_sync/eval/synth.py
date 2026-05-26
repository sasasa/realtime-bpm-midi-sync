"""合成テスト信号（クリック/テンポ変化）。

実機やダウンロードなしで検出〜追従を検証するための既知 BPM 信号を作る。
各ビートに短いノイズバーストを置き、スペクトルフラックスが立つようにする。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np


def _burst(sr: int, ms: float = 8.0, seed: Optional[int] = None) -> np.ndarray:
    n = max(1, int(sr * ms / 1000.0))
    rng = np.random.default_rng(seed)
    env = np.exp(-np.linspace(0, 6, n))           # 速い減衰
    return (rng.standard_normal(n) * env).astype(np.float32)


def click_track(bpm: float, duration_s: float, sr: int = 48000,
                jitter_ms: float = 0.0, seed: int = 0) -> np.ndarray:
    """一定 BPM のクリック列。jitter_ms で各打点に±ゆらぎを与える。"""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(sr * duration_s), dtype=np.float32)
    period = 60.0 / bpm
    burst = _burst(sr, seed=seed)
    t = period  # 1 拍目は少し後ろから（冒頭の無音を作る）
    while t < duration_s:
        jitter = rng.uniform(-jitter_ms, jitter_ms) / 1000.0 if jitter_ms else 0.0
        idx = int((t + jitter) * sr)
        if 0 <= idx < len(out) - len(burst):
            out[idx : idx + len(burst)] += burst
        t += period
    return out


def click_track_bpm_fn(bpm_fn: Callable[[float], float], duration_s: float,
                       sr: int = 48000, seed: int = 0) -> np.ndarray:
    """時刻 → BPM の関数で駆動するクリック列（ステップ/ランプ追従の検証用）。"""
    out = np.zeros(int(sr * duration_s), dtype=np.float32)
    burst = _burst(sr, seed=seed)
    t = 0.5
    while t < duration_s:
        idx = int(t * sr)
        if 0 <= idx < len(out) - len(burst):
            out[idx : idx + len(burst)] += burst
        bpm = max(1.0, bpm_fn(t))
        t += 60.0 / bpm
    return out


def beat_times(bpm: float, duration_s: float) -> List[float]:
    """click_track と同じ拍時刻（参照ビート）。"""
    period = 60.0 / bpm
    out, t = [], period
    while t < duration_s:
        out.append(t)
        t += period
    return out
