"""検証用メトリクス（plan §12）。

検出 BPM / 出力 BPM の時系列を記録し、整定時間・追従誤差・定常ジッタを計算する。
"""

from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class MetricsLog:
    # (time, detected_bpm, target_bpm, state)
    rows: List[Tuple[float, Optional[float], Optional[float], str]] = field(default_factory=list)

    def log(self, t: float, detected: Optional[float], target: Optional[float], state: str) -> None:
        self.rows.append((t, detected, target, state))

    # ------------------------------------------------------------------ #
    def target_series(self) -> List[Tuple[float, float]]:
        return [(t, tg) for t, _d, tg, _s in self.rows if tg is not None]

    def steady_state_jitter(self, last_seconds: float = 5.0) -> Optional[float]:
        """末尾 last_seconds の出力 BPM 標準偏差（=「ガタつき」の定量）。"""
        series = self.target_series()
        if len(series) < 3:
            return None
        t_end = series[-1][0]
        tail = [bpm for t, bpm in series if t >= t_end - last_seconds]
        if len(tail) < 3:
            return None
        return statistics.pstdev(tail)

    def tracking_error(self, true_bpm: float, skip_seconds: float = 3.0) -> Optional[float]:
        """skip_seconds 以降の出力 BPM の真値からの平均絶対誤差。"""
        series = [(t, bpm) for t, bpm in self.target_series() if t >= skip_seconds]
        if not series:
            return None
        return statistics.mean(abs(bpm - true_bpm) for _t, bpm in series)

    def settling_time(self, true_bpm: float, tol: float = 0.5) -> Optional[float]:
        """出力が以後ずっと ±tol BPM に収まり続ける最初の時刻。"""
        series = self.target_series()
        if not series:
            return None
        settle_t: Optional[float] = None
        for t, bpm in series:
            if abs(bpm - true_bpm) <= tol:
                if settle_t is None:
                    settle_t = t
            else:
                settle_t = None
        return settle_t

    def final_bpm(self) -> Optional[float]:
        series = self.target_series()
        return series[-1][1] if series else None

    def write_csv(self, path: str | Path) -> None:
        with Path(path).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time_s", "detected_bpm", "target_bpm", "state"])
            for row in self.rows:
                w.writerow(row)
