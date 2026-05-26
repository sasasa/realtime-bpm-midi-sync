"""numpy 配列を入力ソースにする（テスト/シミュレーション用）。"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from .base import AudioSource


class ArraySource(AudioSource):
    def __init__(self, samples: np.ndarray, samplerate: int, hop_size: int):
        self.samplerate = samplerate
        self.hop_size = hop_size
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        self._samples = samples

    def frames(self) -> Iterator[np.ndarray]:
        n = len(self._samples)
        for start in range(0, n, self.hop_size):
            chunk = self._samples[start : start + self.hop_size]
            if len(chunk) < self.hop_size:
                chunk = np.pad(chunk, (0, self.hop_size - len(chunk)))
            yield chunk
