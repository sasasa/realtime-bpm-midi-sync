"""システム音声ループバック入力（plan §12-1）。

ブラウザで再生した YouTube 等の音をそのまま入力に回す（ダウンロード不要）。

実装メモ: python-sounddevice が同梱する PortAudio は WASAPI loopback を持たない
（`WasapiSettings(loopback=...)` が無い）。そこで **soundcard** ライブラリの
ネイティブ WASAPI loopback を使う。これなら VB-CABLE 等の仮想ケーブル不要。
soundcard が無い場合は VB-CABLE/VoiceMeeter を LiveSource で指定する方法を案内する。

キャプチャは専用スレッドで途切れなく record() し続け、解析側はキューから取り出す
（処理の合間に録音が途切れる "data discontinuity" を避ける）。
"""

from __future__ import annotations

import queue
import threading
import warnings
from typing import Iterator, Optional

import numpy as np

from .base import AudioSource


class LoopbackSource(AudioSource):
    def __init__(self, samplerate: int, hop_size: int, speaker_name: Optional[str] = None):
        try:
            import soundcard as sc
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "ループバックには soundcard が必要です: pip install soundcard\n"
                "（代替: VB-CABLE/VoiceMeeter を入れ、その入力を `run` で使う）"
            ) from exc

        self._sc = sc
        self.samplerate = samplerate
        self.hop_size = hop_size
        self.speaker_name = speaker_name
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def frames(self) -> Iterator[np.ndarray]:
        sc = self._sc
        spk = sc.get_speaker(self.speaker_name) if self.speaker_name else sc.default_speaker()
        if spk is None:
            raise RuntimeError(f"スピーカー '{self.speaker_name}' が見つかりません")
        mic = sc.get_microphone(spk.name, include_loopback=True)

        q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=256)

        def capture() -> None:
            with warnings.catch_warnings():
                # 途切れ警告は想定内（解析が一時的に遅れた合図）。ノイズなので抑制
                warnings.simplefilter("ignore")
                with mic.recorder(samplerate=self.samplerate, channels=1,
                                  blocksize=self.hop_size) as rec:
                    while not self._stop:
                        data = rec.record(numframes=self.hop_size)
                        frame = data.mean(axis=1) if data.ndim == 2 else data
                        try:
                            q.put_nowait(np.asarray(frame, dtype=np.float32))
                        except queue.Full:
                            pass  # 解析が遅れている。最新を優先して落とす

        th = threading.Thread(target=capture, daemon=True)
        th.start()
        while not self._stop:
            try:
                yield q.get(timeout=0.5)
            except queue.Empty:
                continue
