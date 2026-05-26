"""バッチ評価（plan §12-1, §12-3）。

音源（配列/ファイル）を faster-than-real-time で検出器に通し、既知 BPM に対する
追従誤差・整定時間・定常ジッタ・最終 BPM を返す。MIDI は載せない（純アルゴリズム）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..config import Config
from ..engine import Engine
from ..metrics import MetricsLog
from ..sources.array import ArraySource


@dataclass
class EvalResult:
    true_bpm: float
    final_bpm: Optional[float]
    tracking_error: Optional[float]
    jitter: Optional[float]
    settling_time: Optional[float]
    locked: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def evaluate_array(config: Config, samples: np.ndarray, true_bpm: float) -> EvalResult:
    engine = Engine(config, MetricsLog())
    source = ArraySource(samples, config.samplerate, config.hop_size)
    m = engine.run(source)
    return EvalResult(
        true_bpm=true_bpm,
        final_bpm=m.final_bpm(),
        tracking_error=m.tracking_error(true_bpm),
        jitter=m.steady_state_jitter(),
        settling_time=m.settling_time(true_bpm),
        locked=engine.controller.state.value in ("LOCKED", "HOLD"),
    )


def evaluate_file(config: Config, path: str, true_bpm: float) -> EvalResult:
    from ..sources.file import FileSource

    engine = Engine(config, MetricsLog())
    source = FileSource(path, config.samplerate, config.hop_size, realtime=False)
    m = engine.run(source)
    return EvalResult(
        true_bpm=true_bpm,
        final_bpm=m.final_bpm(),
        tracking_error=m.tracking_error(true_bpm),
        jitter=m.steady_state_jitter(),
        settling_time=m.settling_time(true_bpm),
        locked=engine.controller.state.value in ("LOCKED", "HOLD"),
    )
