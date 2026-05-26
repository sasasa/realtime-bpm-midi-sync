"""入力ソースの抽象基底。"""

from __future__ import annotations

import abc
from typing import Iterator

import numpy as np


class AudioSource(abc.ABC):
    """hop サイズのモノ float32 フレームを供給する。"""

    samplerate: int
    hop_size: int

    @abc.abstractmethod
    def frames(self) -> Iterator[np.ndarray]:
        """長さ hop_size のモノ float32 フレームを順に yield する。"""
        raise NotImplementedError
