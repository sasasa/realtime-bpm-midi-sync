"""MIDI クロック送出スレッド（plan §8）。

0xF8 を 24 PPQN で送る。``interval = 60 / (bpm * 24)``。
- 理想時刻を累積（next_t += interval）して長時間ドリフトを排除。
- sleep で粗く待ち、最後はスピンで合わせるハイブリッド。
- Windows はタイマ分解能を 1ms に上げる（timeBeginPeriod）。

mido / python-rtmidi は遅延 import（テストや batch では不要）。
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional


def list_output_ports() -> List[str]:
    import mido

    return list(mido.get_output_names())


def _resolve_port_name(name: Optional[str]) -> str:
    import mido

    ports = mido.get_output_names()
    if not ports:
        raise RuntimeError("MIDI 出力ポートが見つかりません（loopMIDI 等を起動してください）")
    if name is None:
        return ports[0]
    for p in ports:
        if name.lower() in p.lower():
            return p
    raise RuntimeError(f"MIDI ポート '{name}' が見つかりません。候補: {ports}")


class _WinTimer:
    """Windows のタイマ分解能を 1ms に上げる context manager。"""

    def __enter__(self):
        self._winmm = None
        try:
            import ctypes

            self._winmm = ctypes.WinDLL("winmm")
            self._winmm.timeBeginPeriod(1)
        except Exception:  # noqa: BLE001 - 非 Windows では無視
            self._winmm = None
        return self

    def __exit__(self, *exc):
        if self._winmm is not None:
            try:
                self._winmm.timeEndPeriod(1)
            except Exception:  # noqa: BLE001
                pass


class MidiClock(threading.Thread):
    def __init__(self, port_name: Optional[str] = None, bpm: float = 120.0, ppqn: int = 24):
        super().__init__(daemon=True)
        import mido  # 早期に失敗させる

        self._mido = mido
        self._port_name = _resolve_port_name(port_name)
        self._port = None
        self._bpm = max(20.0, float(bpm))
        self._ppqn = ppqn
        self._running = True

    @property
    def port_name(self) -> str:
        return self._port_name

    def set_bpm(self, bpm: Optional[float]) -> None:
        if bpm is not None:
            self._bpm = max(20.0, float(bpm))

    def send_start(self) -> None:
        if self._port is not None:
            self._port.send(self._mido.Message("start"))

    def send_stop(self) -> None:
        if self._port is not None:
            self._port.send(self._mido.Message("stop"))

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        clock = self._mido.Message("clock")
        with _WinTimer():
            self._port = self._mido.open_output(self._port_name)
            try:
                next_t = time.perf_counter()
                while self._running:
                    self._port.send(clock)
                    interval = 60.0 / (self._bpm * self._ppqn)
                    next_t += interval
                    delay = next_t - time.perf_counter()
                    if delay > 0.002:
                        time.sleep(delay - 0.001)
                    # 残りはスピンで詰める
                    while time.perf_counter() < next_t:
                        pass
                    # BPM 急変で next_t が過去になりすぎたら追従
                    if time.perf_counter() - next_t > 0.05:
                        next_t = time.perf_counter()
            finally:
                self._port.close()
                self._port = None
