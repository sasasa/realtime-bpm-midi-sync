"""テンポ推定 + 平滑化（plan §7）。

ビート時刻（秒, サンプル基準）を逐次受け取り、滑らかな BPM を返す。
2 つの前段（period 測定）を切替できる:

- ``median``: 直近 N 個の IBI（octave 補正済み）の中央値。シンプルで着手向き。
- ``pll``   : 位相同期ループ。周期を誤差で少しずつ更新。揺らぎに強く滑らか。

どちらも octave 補正（半分/倍テンポを期待レンジへ畳む）と外れ値除去を行い、
共通の後段（スルーレート制限 → IIR → デッドバンド）で出力を平滑化する。
"""

from __future__ import annotations

import collections
import statistics
from typing import Optional

from .config import Config


def _fold_bpm(bpm: float, min_bpm: float, max_bpm: float) -> float:
    """半分/倍テンポを期待レンジ [min, max] に畳み込む。"""
    if bpm <= 0:
        return bpm
    while bpm < min_bpm:
        bpm *= 2.0
    while bpm > max_bpm:
        bpm /= 2.0
    return bpm


class TempoEstimator:
    def __init__(self, config: Config):
        self.cfg = config
        self.bpm_out: Optional[float] = None      # 平滑後の出力 BPM
        self.bpm_target: Optional[float] = None    # 内部目標（デッドバンドでも更新）
        self._last_beat_t: Optional[float] = None
        # median 用
        self._ibis: collections.deque[float] = collections.deque(maxlen=config.median_n)
        # pll 用
        self._period: Optional[float] = None        # 拍周期 [秒]
        self._seed_ibis: collections.deque[float] = collections.deque(maxlen=4)
        self._reject_run = 0                        # 連続外れ値カウント（再シード判定用）

    # ------------------------------------------------------------------ #
    def on_beat(self, t: float) -> Optional[float]:
        """ビート時刻 t [秒] を受け取り、平滑後 BPM（または None）を返す。"""
        if self._last_beat_t is None:
            self._last_beat_t = t
            return self.bpm_out

        dt = t - self._last_beat_t
        if dt <= 0:
            return self.bpm_out

        if self.cfg.estimator == "median":
            target = self._measure_median(dt, t)
        else:
            target = self._measure_pll(dt, t)

        if target is None:
            return self.bpm_out

        self.bpm_target = target
        self._smooth(target)
        return self.bpm_out

    # ------------------------------------------------------------------ #
    def _measure_median(self, dt: float, t: float) -> Optional[float]:
        bpm = _fold_bpm(60.0 / dt, self.cfg.min_bpm, self.cfg.max_bpm)
        ibi = 60.0 / bpm
        # 外れ値除去（中央値比）
        if self._ibis:
            med = statistics.median(self._ibis)
            if abs(ibi - med) > self.cfg.outlier_ratio * med:
                self._last_beat_t = t   # 参照だけ進める（無視）
                return None
        self._ibis.append(ibi)
        self._last_beat_t = t
        return 60.0 / statistics.median(self._ibis)

    def _measure_pll(self, dt: float, t: float) -> Optional[float]:
        ibi = 60.0 / _fold_bpm(60.0 / dt, self.cfg.min_bpm, self.cfg.max_bpm)

        # シード期間: 最初の数 IBI の中央値で周期を初期化（単発の悪い IBI で
        # 半分/倍に固定されるのを防ぐ。plan の octave 連続性対策に対応）
        if self._period is None:
            self._seed_ibis.append(ibi)
            self._last_beat_t = t
            seed = statistics.median(self._seed_ibis)
            if len(self._seed_ibis) >= 3:
                self._period = seed       # 確定
            return 60.0 / seed            # 確定前も暫定値を返す

        # サブディビジョン/欠落ビートを整数比で吸収
        ratio = dt / self._period
        if ratio < 0.5:
            return None                   # 近すぎ（ゴースト/サブディビジョン）→ 無視（参照保持）
        n = max(1, round(ratio))
        candidate = dt / n                # 1 拍あたりに換算した観測周期
        self._last_beat_t = t

        # 外れ値除去。ただし同方向の不一致が続くならシードが誤りなので再シード
        if abs(candidate - self._period) > self.cfg.outlier_ratio * self._period:
            self._reject_run += 1
            if self._reject_run < 3:
                return None
            self._period = candidate      # 連続で外れ → 現実に合わせ直す
            self._reject_run = 0
        else:
            self._reject_run = 0
            # PLL: 周期を誤差で少しずつ更新（位相は観測ビートに再アンカー）
            self._period += self.cfg.pll_ki * (candidate - self._period)

        self._period = 60.0 / _fold_bpm(
            60.0 / self._period, self.cfg.min_bpm, self.cfg.max_bpm
        )
        return 60.0 / self._period

    # ------------------------------------------------------------------ #
    def _smooth(self, target: float) -> None:
        """スルーレート制限 → IIR → デッドバンド（plan §7-2）。"""
        if self.bpm_out is None:
            self.bpm_out = target
            return
        step = max(-self.cfg.max_step_bpm,
                   min(self.cfg.max_step_bpm, target - self.bpm_out))
        cand = self.bpm_out + self.cfg.iir_alpha * step
        if abs(cand - self.bpm_out) >= self.cfg.deadband_bpm:
            self.bpm_out = cand
