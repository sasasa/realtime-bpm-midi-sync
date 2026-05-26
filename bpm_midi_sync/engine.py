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
        self.detector.set_prior(bpm)   # seed はオクターブ prior も兼ねる

    def run(self, source: AudioSource,
            status_cb: Optional[Callable[[float, Optional[float], Optional[float], str], None]] = None
            ) -> MetricsLog:
        """source を消費し終えるまで回す（file/batch は自然に終了）。

        status_cb があればフレーム毎に (時刻, 検出BPM, 目標BPM, 状態) を渡す
        （live/loopback の現在値表示用）。
        """
        dt = self.cfg.hop_size / self.cfg.samplerate
        # prior は config.prefer_bpm（= expected-bpm / seed）を一貫して使う。
        # target で上書きすると初期の誤ロックを自己強化するため行わない。
        for frame in source.frames():
            for beat_t in self.detector.process(frame):
                bpm = self.estimator.on_beat(beat_t)
                self.controller.on_beat(beat_t, bpm)
            cur = self.detector.current_bpm
            if cur is not None:                       # テンポストリーム型（autocorr）
                self.controller.on_tempo(self.detector.time, cur)
            t = self.detector.time
            target = self.controller.tick(t, dt)
            if self.midi is not None:
                self.midi.set_bpm(target)
            detected = cur if cur is not None else self.estimator.bpm_out
            self.metrics.log(t, detected, target, self.controller.state.value)
            if status_cb is not None:
                status_cb(t, detected, target, self.controller.state.value)
        return self.metrics
