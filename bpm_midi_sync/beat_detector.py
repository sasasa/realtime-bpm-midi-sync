"""ビート/テンポ検出（plan §6）。

3 バックエンド:
- AutocorrTempoDetector（既定・推奨）: オンセット強度包絡の自己相関でテンポを直接推定。
  テンポ prior（期待 BPM）でオクターブ曖昧性を解消。フルミックスの実音源で最も頑健
  （territorial pissings 等の検証で IBI 方式の破綻を確認したため既定にした）。
  ビートイベントでなく **テンポ(BPM)ストリーム** を出す（`current_bpm`）。
- NumpyBeatDetector: スペクトルフラックスのオンセット検出 → ビートイベント。
  クリーンなクリック/単純なリズム向け。aubio が無くても動く。
- AubioBeatDetector: aubio.tempo によるビートトラッキング。

共通インタフェース:
- ``process(frame) -> list[float]``: フレーム内で検出したビート時刻[秒]（テンポ
  ストリーム型は []）。時刻は累積サンプル数 / sr。
- ``current_bpm``: テンポストリーム型の現在 BPM（イベント型は None）。
- ``set_prior(bpm)``: テンポ prior を更新（controller の現在テンポを供給）。
"""

from __future__ import annotations

import collections
from typing import List, Optional

import numpy as np

from .config import Config
from .tempogram import autocorr_tempo, spectral_flux


class BeatDetector:
    """検出器の共通インタフェース。"""

    def process(self, frame: np.ndarray) -> List[float]:  # pragma: no cover - 抽象
        raise NotImplementedError

    @property
    def time(self) -> float:
        raise NotImplementedError

    @property
    def current_bpm(self) -> Optional[float]:
        return None

    def set_prior(self, bpm: Optional[float]) -> None:
        pass


def _fit_hop(frame: np.ndarray, hop: int) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    if frame.ndim == 2:
        frame = frame.mean(axis=1)
    if len(frame) < hop:
        frame = np.pad(frame, (0, hop - len(frame)))
    elif len(frame) > hop:
        frame = frame[:hop]
    return frame


class AutocorrTempoDetector(BeatDetector):
    """オンセット包絡の自己相関 + テンポ prior（既定）。"""

    def __init__(self, config: Config):
        self.cfg = config
        self.sr = config.samplerate
        self.hop = config.hop_size
        self._n_samples = 0
        self._window = np.hanning(self.hop).astype(np.float32)
        self._prev_mag: Optional[np.ndarray] = None
        self._sr_env = self.sr / self.hop
        self._env: collections.deque[float] = collections.deque(
            maxlen=max(16, int(self._sr_env * config.tempo_window_s))
        )
        self._update_frames = max(1, int(self._sr_env * config.tempo_update_s))
        self._since_update = 0
        self._bpm: Optional[float] = None
        self._prefer = config.prefer_bpm

    @property
    def time(self) -> float:
        return self._n_samples / self.sr

    @property
    def current_bpm(self) -> Optional[float]:
        return self._bpm

    def set_prior(self, bpm: Optional[float]) -> None:
        if bpm is not None and bpm > 0:
            self._prefer = float(bpm)

    def process(self, frame: np.ndarray) -> List[float]:
        frame = _fit_hop(frame, self.hop)
        self._n_samples += self.hop
        flux, self._prev_mag = spectral_flux(frame, self._prev_mag, self._window)
        self._env.append(flux)
        self._since_update += 1
        if self._since_update >= self._update_frames:
            self._since_update = 0
            bpm = autocorr_tempo(
                np.fromiter(self._env, dtype=np.float64), self._sr_env,
                self.cfg.min_bpm, self.cfg.max_bpm, self._prefer, self.cfg.prior_sigma,
            )
            if bpm is not None:
                self._bpm = bpm
        return []


class NumpyBeatDetector(BeatDetector):
    """スペクトルフラックス + 適応閾値のオンセット検出（ビートイベント型）。"""

    def __init__(self, config: Config):
        self.cfg = config
        self.sr = config.samplerate
        self.hop = config.hop_size
        self._n_samples = 0
        self._window = np.hanning(self.hop).astype(np.float32)
        self._prev_mag: Optional[np.ndarray] = None
        self._frame_rate = self.sr / self.hop
        self._flux_hist: collections.deque[float] = collections.deque(
            maxlen=max(8, int(self._frame_rate * 1.5))
        )
        self._last_onset_t = -1e9
        self._armed = True

    @property
    def time(self) -> float:
        return self._n_samples / self.sr

    def process(self, frame: np.ndarray) -> List[float]:
        frame = _fit_hop(frame, self.hop)
        self._n_samples += self.hop
        flux, self._prev_mag = spectral_flux(frame, self._prev_mag, self._window)
        beats = self._pick(flux) if self._prev_mag is not None else []
        return beats

    def _pick(self, flux: float) -> List[float]:
        beats: List[float] = []
        if len(self._flux_hist) >= 16:
            arr = np.fromiter(self._flux_hist, dtype=np.float64)
            threshold = np.median(arr) + self.cfg.onset_sensitivity * arr.std()
            t = self.time
            above = flux > threshold and flux > 0
            if above and self._armed and (t - self._last_onset_t) >= self.cfg.min_onset_interval_s:
                beats.append(t)
                self._last_onset_t = t
                self._armed = False
            elif not above:
                self._armed = True
        self._flux_hist.append(flux)
        return beats


class AubioBeatDetector(BeatDetector):
    """aubio.tempo ラッパ（aubio が import できる場合のみ）。"""

    def __init__(self, config: Config):
        import aubio

        self.cfg = config
        self.sr = config.samplerate
        self.hop = config.hop_size
        self._n_samples = 0
        self._tempo = aubio.tempo("default", config.win_size, config.hop_size, config.samplerate)

    @property
    def time(self) -> float:
        return self._n_samples / self.sr

    def process(self, frame: np.ndarray) -> List[float]:
        frame = _fit_hop(frame, self.hop).astype(np.float32)
        self._n_samples += self.hop
        if self._tempo(frame):
            return [float(self._tempo.get_last_s())]
        return []


def make_detector(config: Config) -> BeatDetector:
    if config.detector == "aubio":
        try:
            return AubioBeatDetector(config)
        except Exception as exc:  # noqa: BLE001 - フォールバックを明示
            print(f"[beat_detector] aubio 不可 ({exc}); autocorr 検出にフォールバック")
            return AutocorrTempoDetector(config)
    if config.detector == "numpy":
        return NumpyBeatDetector(config)
    return AutocorrTempoDetector(config)
