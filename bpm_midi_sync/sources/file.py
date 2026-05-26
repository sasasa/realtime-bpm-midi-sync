"""WAV / yt-dlp 取得音源を入力ソースにする。

- realtime=False: バッチ高速処理（係数チューニング・大量評価。plan §12-1）
- realtime=True : 実時間で再生ペースに合わせて yield（MIDI/レイテンシ込みの検証）
soundfile を遅延 import（無ければ分かりやすく失敗）。
"""

from __future__ import annotations

import time
from typing import Iterator

import numpy as np

from .base import AudioSource


class FileSource(AudioSource):
    def __init__(self, path: str, samplerate: int, hop_size: int, realtime: bool = False):
        try:
            import soundfile as sf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("FileSource には soundfile が必要です: pip install soundfile") from exc

        data, sr = sf.read(path, dtype="float32", always_2d=False)
        if data.ndim == 2:
            data = data.mean(axis=1)
        if sr != samplerate:
            data = _resample_linear(data, sr, samplerate)
        self._samples = data.astype(np.float32)
        self.samplerate = samplerate
        self.hop_size = hop_size
        self.realtime = realtime

    def frames(self) -> Iterator[np.ndarray]:
        hop_dt = self.hop_size / self.samplerate
        n = len(self._samples)
        next_t = time.perf_counter()
        for start in range(0, n, self.hop_size):
            chunk = self._samples[start : start + self.hop_size]
            if len(chunk) < self.hop_size:
                chunk = np.pad(chunk, (0, self.hop_size - len(chunk)))
            yield chunk
            if self.realtime:
                next_t += hop_dt
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)


def _resample_linear(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """簡易線形リサンプル（検証用。高品質が要るなら soxr/librosa を）。"""
    if sr_in == sr_out:
        return data
    n_out = int(round(len(data) * sr_out / sr_in))
    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.float32)
