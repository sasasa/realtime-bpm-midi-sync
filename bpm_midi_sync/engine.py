"""配線（source → detector → estimator → controller →[midi]）。

オーディオ経路（live/file/loopback）でもオフライン（batch/sim）でも同じ配線を使う。
時間軸は detector のサンプル基準時刻を正とする（plan §6）。MIDI クロックは
別スレッド（実時間）で、controller.target_bpm を共有変数として読む。
"""

from __future__ import annotations

from typing import Callable, Optional

from .beat_detector import make_detector
from .config import Config
from .controller import Controller
from .metrics import MetricsLog
from .sources.base import AudioSource
from .tempo_estimator import TempoEstimator


class Engine:
    def __init__(self, config: Config, metrics: Optional[MetricsLog] = None):
        self.cfg = config
        self.detector = make_detector(config)
        self.estimator = TempoEstimator(config)
        self.controller = Controller(config)
        self.metrics = metrics or MetricsLog()
        self.midi = None  # MidiClock（live/loopback でのみ設定）

    def attach_midi(self, midi) -> None:
        self.midi = midi

    def seed_tempo(self, bpm: float) -> None:
        self.controller.seed(bpm)

    def run(self, source: AudioSource,
            status_cb: Optional[Callable[[float, Optional[float], Optional[float], str], None]] = None
            ) -> MetricsLog:
        """source を消費し終えるまで回す（file/batch は自然に終了）。

        status_cb があればフレーム毎に (時刻, 検出BPM, 目標BPM, 状態) を渡す
        （live/loopback の現在値表示用）。
        """
        dt = self.cfg.hop_size / self.cfg.samplerate
        for frame in source.frames():
            for beat_t in self.detector.process(frame):
                bpm = self.estimator.on_beat(beat_t)
                self.controller.on_beat(beat_t, bpm)
            t = self.detector.time
            target = self.controller.tick(t, dt)
            if self.midi is not None:
                self.midi.set_bpm(target)
            self.metrics.log(t, self.estimator.bpm_out, target, self.controller.state.value)
            if status_cb is not None:
                status_cb(t, self.estimator.bpm_out, target, self.controller.state.value)
        return self.metrics
