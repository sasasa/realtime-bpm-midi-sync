"""ビート検出（plan §6）。

共通インタフェース ``process(frame) -> list[float]``:
hop サイズのモノ float32 フレームを受け取り、そのフレーム内で検出したビート
（オンセット）時刻のリスト [秒] を返す。時刻は **累積サンプル数 / sr** で持つ
（壁時計でなくサンプル基準。plan §6）。

2 バックエンド:
- NumpyBeatDetector: スペクトルフラックスのオンセット検出（依存 numpy のみ）。
  クリック/ドラム主体に対して堅牢で、aubio が入らない環境でも動く。
- AubioBeatDetector: aubio.tempo によるビートトラッキング（インストールできれば）。
"""

from __future__ import annotations

import collections
from typing import List, Optional

import numpy as np

from .config import Config


class BeatDetector:
    """検出器の共通インタフェース。"""

    def process(self, frame: np.ndarray) -> List[float]:  # pragma: no cover - 抽象
        raise NotImplementedError

    @property
    def time(self) -> float:
        """これまでに処理した音声の終端時刻 [秒]。"""
        raise NotImplementedError


class NumpyBeatDetector(BeatDetector):
    """スペクトルフラックス + 適応閾値のオンセット検出。"""

    def __init__(self, config: Config):
        self.cfg = config
        self.sr = config.samplerate
        self.hop = config.hop_size
        self._n_samples = 0
        self._window = np.hanning(self.hop).astype(np.float32)
        self._prev_mag: Optional[np.ndarray] = None
        # 直近 ~1.5 秒のフラックス（適応閾値用）
        self._frame_rate = self.sr / self.hop
        self._flux_hist: collections.deque[float] = collections.deque(
            maxlen=max(8, int(self._frame_rate * 1.5))
        )
        self._last_onset_t: float = -1e9
        self._armed = True  # 立ち上がりエッジ検出用

    @property
    def time(self) -> float:
        return self._n_samples / self.sr

    def process(self, frame: np.ndarray) -> List[float]:
        frame = _to_mono(frame)
        if len(frame) < self.hop:
            frame = np.pad(frame, (0, self.hop - len(frame)))
        elif len(frame) > self.hop:
            frame = frame[: self.hop]
        self._n_samples += self.hop

        mag = np.abs(np.fft.rfft(frame * self._window))
        beats: List[float] = []
        if self._prev_mag is not None:
            # 半波整流したスペクトル差分の総和（spectral flux）
            flux = float(np.sum(np.maximum(0.0, mag - self._prev_mag)))
            beats = self._pick(flux)
        self._prev_mag = mag
        return beats

    def _pick(self, flux: float) -> List[float]:
        beats: List[float] = []
        if len(self._flux_hist) >= 16:
            arr = np.fromiter(self._flux_hist, dtype=np.float64)
            # 中央値ベースライン（スパイク自身に引っ張られにくい）+ k*std
            threshold = np.median(arr) + self.cfg.onset_sensitivity * arr.std()
            t = self.time
            above = flux > threshold and flux > 0
            if above and self._armed and (t - self._last_onset_t) >= self.cfg.min_onset_interval_s:
                beats.append(t)
                self._last_onset_t = t
                self._armed = False
            elif not above:
                self._armed = True  # 一度閾値を下回ってから次の立ち上がりを拾う
        self._flux_hist.append(flux)
        return beats


class AubioBeatDetector(BeatDetector):
    """aubio.tempo ラッパ（aubio が import できる場合のみ）。"""

    def __init__(self, config: Config):
        import aubio  # 遅延 import（無くても numpy 検出は動く）

        self.cfg = config
        self.sr = config.samplerate
        self.hop = config.hop_size
        self._n_samples = 0
        self._tempo = aubio.tempo("default", config.win_size, config.hop_size, config.samplerate)

    @property
    def time(self) -> float:
        return self._n_samples / self.sr

    def process(self, frame: np.ndarray) -> List[float]:
        frame = _to_mono(frame).astype(np.float32)
        if len(frame) < self.hop:
            frame = np.pad(frame, (0, self.hop - len(frame)))
        elif len(frame) > self.hop:
            frame = frame[: self.hop]
        self._n_samples += self.hop
        if self._tempo(frame):
            # aubio はサンプル基準の最終ビート時刻を返す
            return [float(self._tempo.get_last_s())]
        return []


def _to_mono(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    if frame.ndim == 2:
        frame = frame.mean(axis=1)
    return frame


def make_detector(config: Config) -> BeatDetector:
    if config.detector == "aubio":
        try:
            return AubioBeatDetector(config)
        except Exception as exc:  # noqa: BLE001 - フォールバックを明示
            print(f"[beat_detector] aubio 不可 ({exc}); numpy 検出にフォールバック")
    return NumpyBeatDetector(config)
