"""オンセット強度包絡の自己相関によるテンポ推定（plan §6 の堅牢化）。

実音源（フルミックス）での検証で、離散オンセットの IBI 方式はオクターブ誤り・
オンセット過多に弱いと判明（territorial pissings 等）。オンセット *包絡* の
自己相関＋テンポ prior（期待 BPM 近傍を優先）の方が頑健で、prior を与えれば
オクターブ誤りが解消することを実測で確認した。

- 包絡: hop ごとのスペクトルフラックス（half-wave rectified）。
- 推定: 窓内の自己相関を BPM レンジで評価し、対数正規 prior で重みづけ → ピーク。
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def spectral_flux(frame: np.ndarray, prev_mag: Optional[np.ndarray], window: np.ndarray):
    """1 フレームのスペクトルフラックスと更新後 mag を返す。"""
    mag = np.abs(np.fft.rfft(frame * window))
    if prev_mag is None:
        return 0.0, mag
    flux = float(np.sum(np.maximum(0.0, mag - prev_mag)))
    return flux, mag


def autocorr_tempo(onset_env: np.ndarray, sr_env: float, min_bpm: float,
                   max_bpm: float, prefer_bpm: float, sigma: float = 0.9) -> Optional[float]:
    """オンセット包絡から BPM を推定（オクターブは prior で曖昧性解消）。

    sr_env: 包絡のサンプルレート（= samplerate / hop_size）。
    prefer_bpm: 期待テンポ（seed/現在テンポ）。対数正規 prior の中心。
    """
    if len(onset_env) < 8:
        return None
    x = onset_env - onset_env.mean()
    if not np.any(x):
        return None
    n = len(x)
    ac = np.correlate(x, x, mode="full")[n - 1:]
    # 不偏正規化（ac[k]/(N-k)）。ラグが長いほど重なり対が減る偏りを除き、
    # 周期的信号のハーモニックピーク高を揃える → オクターブ判断を prior に委ねられる
    ac = ac / np.arange(n, 0, -1)
    ac[:2] = 0.0  # ラグ0付近は除外

    bpms = np.arange(min_bpm, max_bpm + 0.1, 0.5)
    lags = np.clip((sr_env * 60.0 / bpms).astype(int), 0, len(ac) - 1)
    score = np.maximum(0.0, ac[lags].astype(float))
    # 対数正規 prior（オクターブは log2 距離でペナルティ）でオクターブ曖昧性を解消。
    # ※ ハーモニック加算は速いテンポを優遇しオクターブ判断を歪めるため使わない。
    prior = np.exp(-0.5 * (np.log2(bpms / prefer_bpm) / sigma) ** 2)
    score *= prior
    if not np.any(score > 0):
        return None
    return float(bpms[int(np.argmax(score))])
