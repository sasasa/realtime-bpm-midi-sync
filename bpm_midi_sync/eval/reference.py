"""グラウンドトゥルース（正解ビート/BPM）生成（plan §12-2）。

定常 BPM 曲は既知の値1つで足りる。揺れる曲は librosa/madmom（オフライン・高精度）で
ビート時刻を注釈し、軽量リアルタイム検出器の参照にする。librosa は遅延 import。
"""

from __future__ import annotations

from typing import List, Tuple


def beats_with_librosa(path: str) -> Tuple[float, List[float]]:
    """(推定 BPM, ビート時刻リスト[秒]) を返す。"""
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("reference には librosa が必要です: pip install librosa") from exc

    y, sr = librosa.load(path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return float(tempo), [float(t) for t in beat_times]
