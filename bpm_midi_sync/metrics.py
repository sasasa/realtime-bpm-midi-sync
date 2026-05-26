"""検証用メトリクス（plan §12）。

検出 BPM / 出力 BPM の時系列を記録し、整定時間・追従誤差・定常ジッタを計算する。
"""

from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from datetime import datetime
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


class DeviationLogger:
    """検出 BPM が期待テンポから閾値超ズレた事象を CSV に記録（あとで分析用）。

    曲調チェンジでテンポが落ちた等を後から追えるよう、ズレ継続中は interval ごとに
    1 行だけ記録する（スパム防止）。期待値が未設定/検出 None のときは何もしない。
    """

    def __init__(self, path: str | Path, threshold_pct: float = 0.08,
                 interval_s: float = 1.0, warmup_s: float = 0.0, min_sustain_s: float = 0.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold_pct
        self.interval = interval_s
        self.warmup_s = warmup_s
        self.min_sustain_s = min_sustain_s
        self._f = self.path.open("w", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        self._w.writerow(["wall_time", "t_s", "song", "expected_bpm",
                          "detected_bpm", "target_bpm", "dev_bpm", "dev_pct", "state"])
        self._f.flush()
        self._last_log_t = -1e9
        self._dev_since: Optional[float] = None   # 連続ズレの開始時刻
        self.count = 0

    def record(self, t: float, detected: Optional[float], target: Optional[float],
               state: str, song: Optional[str], expected: Optional[float]) -> bool:
        """ズレを判定し、ウォームアップ後かつ min_sustain_s 継続したら（throttle して）記録。
        戻り値は「現在ズレ中か」（GUI の⚠表示用、記録の有無とは独立）。"""
        if expected is None or detected is None or expected <= 0:
            self._dev_since = None
            return False
        dev = detected - expected
        pct = abs(dev) / expected
        over = pct > self.threshold
        # ウォームアップ中は記録もズレ継続カウントもしない（解析窓が未充填で不安定）
        if t < self.warmup_s:
            self._dev_since = None
            return over
        if not over:
            self._dev_since = None
            return False
        # ここから over（ズレ中）。継続時間が min_sustain を超えたら記録
        if self._dev_since is None:
            self._dev_since = t
        sustained = (t - self._dev_since) >= self.min_sustain_s
        if (sustained and (t - self._last_log_t) >= self.interval):
            self._w.writerow([
                datetime.now().isoformat(timespec="seconds"), f"{t:.2f}",
                song or "", f"{expected:.1f}", f"{detected:.1f}",
                f"{target:.1f}" if target else "", f"{dev:+.1f}",
                f"{pct * 100:.1f}", state,
            ])
            self._f.flush()
            self._last_log_t = t
            self.count += 1
        return over

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:  # noqa: BLE001
            pass
