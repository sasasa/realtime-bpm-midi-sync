"""入力ソース（plan §5）。

共通インタフェース AudioSource: hop サイズのモノ float32 フレームを yield する。
- ArraySource:    numpy 配列（テスト/シミュレーション）
- FileSource:     WAV / yt-dlp 取得音源（バッチ高速 or 実時間）
- LiveSource:     sounddevice 入力（実機）
- LoopbackSource: システム音声ループバック（YouTube 実時間検証）
"""

from .array import ArraySource
from .base import AudioSource
from .file import FileSource

__all__ = ["AudioSource", "ArraySource", "FileSource"]
