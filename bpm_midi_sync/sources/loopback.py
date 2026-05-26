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
import wave
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

from .base import AudioSource


class LoopbackSource(AudioSource):
    def __init__(self, samplerate: int, hop_size: int, speaker_name: Optional[str] = None,
                 record_path: Optional[str] = None):
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
        self.record_path = record_path
        self.drops = 0          # 解析が遅れて落としたフレーム数（診断用）
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
                # 取り込みは大きめブロックで（record 呼び出しのオーバーヘッド/取りこぼし低減）
                block = max(self.hop_size, 2048)
                with mic.recorder(samplerate=self.samplerate, channels=1,
                                  blocksize=block) as rec:
                    while not self._stop:
                        data = rec.record(numframes=block)
                        mono = data.mean(axis=1) if data.ndim == 2 else data
                        mono = np.asarray(mono, dtype=np.float32)
                        for i in range(0, len(mono), self.hop_size):
                            chunk = mono[i:i + self.hop_size]
                            if len(chunk) < self.hop_size:
                                break
                            try:
                                q.put_nowait(chunk)
                            except queue.Full:
                                self.drops += 1  # 解析が遅れている。落とした数を記録

        writer = None
        if self.record_path:
            Path(self.record_path).parent.mkdir(parents=True, exist_ok=True)
            writer = wave.open(str(self.record_path), "wb")
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(self.samplerate)

        th = threading.Thread(target=capture, daemon=True)
        th.start()
        try:
            while not self._stop:
                try:
                    frame = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if writer is not None:
                    writer.writeframes((np.clip(frame, -1, 1) * 32767).astype("<i2").tobytes())
                yield frame
        finally:
            if writer is not None:
                writer.close()
