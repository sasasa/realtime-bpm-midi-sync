"""システム音声ループバック入力（plan §12-1）。

ブラウザで再生した YouTube 等の音をそのまま入力に回す。ダウンロード不要。
Windows は WASAPI loopback（sounddevice の extra_settings）を使う。VB-CABLE /
VoiceMeeter を入れている場合はそのデバイスを LiveSource で選んでもよい。
"""

from __future__ import annotations

from typing import Iterator, Optional

import numpy as np

from .base import AudioSource
from .live import LiveSource


class LoopbackSource(AudioSource):
    def __init__(self, samplerate: int, hop_size: int, device: Optional[int] = None,
                 channels: int = 2):
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("LoopbackSource には sounddevice が必要です") from exc

        self._sd = sd
        self.samplerate = samplerate
        self.hop_size = hop_size
        self.channels = channels
        # WASAPI loopback: 既定の出力デバイスを録音対象にする
        try:
            wasapi = sd.WasapiSettings(loopback=True)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "WASAPI loopback を使えません。VB-CABLE/VoiceMeeter を LiveSource で指定してください"
            ) from exc
        self._inner = LiveSource(samplerate, hop_size, device=device, channels=channels)
        self._inner_extra = wasapi

    def stop(self) -> None:
        self._inner.stop()

    def frames(self) -> Iterator[np.ndarray]:
        # LiveSource の InputStream に extra_settings を渡すため簡易に再実装
        sd = self._sd
        import queue

        q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=64)

        def cb(indata, frames, time_info, status):  # noqa: ANN001
            mono = indata.mean(axis=1) if indata.ndim == 2 else indata
            try:
                q.put_nowait(mono.copy())
            except queue.Full:
                pass

        buf = np.zeros(0, dtype=np.float32)
        with sd.InputStream(samplerate=self.samplerate, channels=self.channels,
                            blocksize=self.hop_size, dtype="float32",
                            extra_settings=self._inner_extra, callback=cb):
            while True:
                try:
                    block = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                buf = np.concatenate([buf, block])
                while len(buf) >= self.hop_size:
                    yield buf[: self.hop_size]
                    buf = buf[self.hop_size :]
