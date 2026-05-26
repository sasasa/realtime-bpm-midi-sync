"""コントローラ（状態機械 + 低ゲイン追従）。plan §9。

クリック無し・ドラマー主導前提。開始はドラマーが叩き始めることで起こる。

状態:
- IDLE:      まだ何も検出していない
- ACQUIRING: ビートを集めて初期テンポを獲得中（cold-start）
- LOCKED:    クロック送出中。検出値へ「ゆっくり」追従（低ゲイン）
- HOLD:      ビートが途切れた。最後のテンポを維持（Stop は送らない）

低ゲイン追従が安定性の肝（plan §0）。検出値へ毎秒 follow_max_bps 以内でしか動かさない。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from .config import Config


class State(str, Enum):
    IDLE = "IDLE"
    ACQUIRING = "ACQUIRING"
    LOCKED = "LOCKED"
    HOLD = "HOLD"


class Controller:
    def __init__(self, config: Config):
        self.cfg = config
        self.state = State.IDLE
        self.target_bpm: Optional[float] = None   # ルーパーへ送る内部テンポ状態
        self._detected_bpm: Optional[float] = None
        self._beat_count = 0
        self._last_beat_t: Optional[float] = None

    # ------------------------------------------------------------------ #
    def seed(self, bpm: float) -> None:
        """タップ/手入力で初期テンポを与え、即 LOCKED にする（ACQUIRING の保険）。"""
        self.target_bpm = bpm
        self._detected_bpm = bpm
        self.state = State.LOCKED

    def on_beat(self, t: float, bpm: Optional[float]) -> None:
        """estimator がビートから BPM を出したら呼ぶ。"""
        self._last_beat_t = t
        self._beat_count += 1

        if self.state == State.HOLD:
            self.state = State.LOCKED
        if self.state == State.IDLE:
            self.state = State.ACQUIRING

        if (self.state == State.ACQUIRING and bpm is not None
                and self._beat_count >= self.cfg.acquire_beats):
            self.state = State.LOCKED
            if self.target_bpm is None:
                self.target_bpm = bpm

        # ロック後は現テンポ ±tol 内の検出のみ採用（octave/誤検出を無視）
        if bpm is not None and self._within_tolerance(bpm):
            self._detected_bpm = bpm

    def tick(self, t: float, dt: float) -> Optional[float]:
        """フレーム毎に呼ぶ。沈黙判定と低ゲイン追従を進め、目標 BPM を返す。"""
        if (self._last_beat_t is not None
                and t - self._last_beat_t > self.cfg.silence_timeout_s
                and self.state in (State.LOCKED, State.ACQUIRING)):
            self.state = State.HOLD

        if (self.state == State.LOCKED and self._detected_bpm is not None
                and self.target_bpm is not None):
            max_delta = self.cfg.follow_max_bps * dt
            diff = self._detected_bpm - self.target_bpm
            if diff > max_delta:
                diff = max_delta
            elif diff < -max_delta:
                diff = -max_delta
            self.target_bpm += diff

        return self.target_bpm

    # ------------------------------------------------------------------ #
    def _within_tolerance(self, bpm: float) -> bool:
        if self.target_bpm is None:
            return True
        tol = self.cfg.lock_tolerance * self.target_bpm
        return abs(bpm - self.target_bpm) <= tol
