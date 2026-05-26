"""sounddevice によるライブ入力（plan §3）。

PortAudio コールバックは **コピーしてキューに入れるだけ**（重い処理を置かない）。
別スレッド（= frames() を回す呼び出し側）が hop 単位に取り出す。
sounddevice を遅延 import。
"""

from __future__ import annotations

import queue
from typing import Iterator, Optional

import numpy as np

from .base import AudioSource


class LiveSource(AudioSource):
    def __init__(self, samplerate: int, hop_size: int, device: Optional[int] = None,
                 channels: int = 1, blocksize: Optional[int] = None):
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("LiveSource には sounddevice が必要です: pip install sounddevice") from exc

        self._sd = sd
        self.samplerate = samplerate
        self.hop_size = hop_size
        self.device = device
        self.channels = channels
        self.blocksize = blocksize or hop_size
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=64)
        self._stop = False

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        if status:
            print(f"[live] {status}")
        mono = indata.mean(axis=1) if indata.ndim == 2 else indata
        try:
            self._q.put_nowait(mono.copy())   # 必ずコピー（PortAudio がバッファ再利用）
        except queue.Full:
            pass  # 解析が遅れている。最新を優先して落とす

    def stop(self) -> None:
        self._stop = True

    def frames(self) -> Iterator[np.ndarray]:
        sd = self._sd
        buf = np.zeros(0, dtype=np.float32)
        with sd.InputStream(samplerate=self.samplerate, device=self.device,
                            channels=self.channels, blocksize=self.blocksize,
                            dtype="float32", callback=self._callback):
            while not self._stop:
                try:
                    block = self._q.get(timeout=0.5)
                except queue.Empty:
                    continue
                buf = np.concatenate([buf, block])
                while len(buf) >= self.hop_size:
                    yield buf[: self.hop_size]
                    buf = buf[self.hop_size :]
