"""設定（デバイス/検出/推定/制御/MIDI のパラメータ）。

JSON で永続化できる単一のデータクラス。CLI と eval の双方が同じ既定値を共有する。
パラメータの意味は docs/realtime-bpm-midi-sync-plan.md の §6〜§9 に対応。
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    # --- オーディオ ---
    samplerate: int = 48000
    hop_size: int = 512          # 検出の解析単位（= sources が yield するフレーム長）
    win_size: int = 1024         # aubio 用 FFT 窓
    channels: int = 1            # 入力チャンネル数（モノにダウンミックス）
    input_device: Optional[int] = None   # sounddevice デバイス番号（None=既定）

    # --- 検出（beat_detector） ---
    detector: str = "autocorr"   # "autocorr"(推奨) | "numpy"(onset/IBI) | "aubio"
    onset_sensitivity: float = 1.0   # numpy 検出のオンセット閾値感度（median + k*std）
    min_onset_interval_s: float = 0.06  # 連続オンセットの最小間隔（ゴースト除去）
    # autocorr 検出
    prefer_bpm: float = 120.0    # テンポ prior の中心（オクターブ曖昧性の解消。seed/現テンポで上書き）
    prior_sigma: float = 0.9     # prior の広がり（log2 単位。小さいほど prefer_bpm に強く拘束）
    tempo_lock_range_pct: float = 0.0  # >0 で検出を prefer_bpm±この割合に拘束（期待値が信頼できる時）。
                                       # 2倍/半分のオクターブ跳びを排除。GUI/expected-bpm で 0.35 に。
    tempo_window_s: float = 8.0  # 自己相関の解析窓長
    tempo_update_s: float = 0.25 # テンポ再推定の間隔

    # --- テンポ推定（tempo_estimator） ---
    estimator: str = "pll"       # "pll" | "median"
    min_bpm: float = 60.0
    max_bpm: float = 200.0
    median_n: int = 6            # median 法のリングバッファ長
    outlier_ratio: float = 0.30  # 中央値/予測比 ±この割合超は外れ値として無視
    max_step_bpm: float = 1.0    # 1 ビート更新あたりの最大変化（スルーレート）
    deadband_bpm: float = 0.3    # この未満の変化は無視（微振動カット）
    iir_alpha: float = 0.2       # 一次 IIR の係数
    pll_ki: float = 0.10         # PLL の周期更新ゲイン

    # --- コントローラ（controller） ---
    acquire_beats: int = 8       # ACQUIRING → LOCKED に必要なビート数
    follow_max_bps: float = 1.0  # 低ゲイン追従の最大スルー（BPM/秒）
    lock_tolerance: float = 0.25 # ロック後、現テンポ ±この割合外の検出は無視（octave 対策）
    silence_timeout_s: float = 2.0  # ビートが途切れたら HOLD に入るまでの秒
    target_max_drift_pct: float = 0.0  # >0 で送出 BPM を seed(期待値)±この割合に固定（暴走防止）。GUI で 0.15

    # --- MIDI（midi_clock） ---
    midi_port: Optional[str] = None  # 出力ポート名（部分一致）。None=最初の出力
    ppqn: int = 24
    initial_bpm: float = 120.0   # タップ/手入力の初期 BPM（ACQUIRING の保険）

    # --- ズレログ（期待テンポからの逸脱記録。GUI 用） ---
    deviation_log_pct: float = 0.08      # 検出が期待 BPM からこの割合超ズレたら記録（8%）
    deviation_log_interval_s: float = 1.0  # ズレ継続中の記録間隔（スパム防止）

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(dataclasses.asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def replace(self, **kwargs) -> "Config":
        return dataclasses.replace(self, **kwargs)
