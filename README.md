# realtime-bpm-midi-sync

生ドラムのリアルタイム BPM 検出 → **BOSS ルーパー（RC-600）へ MIDI クロック送出**してテンポ同期する PC 常駐ツール。

設計の詳細・背景は [`docs/realtime-bpm-midi-sync-plan.md`](docs/realtime-bpm-midi-sync-plan.md)。

## これは何か

ドラマーが**クリックを聴かず自由に叩く**テンポを検出し、ルーパーへ MIDI クロック（0xF8, 24 PPQN）を送って追従させる。鍵は「**ルーパーを低ゲイン・強減衰の追従器にする**」こと（ドラマーは自分のループ再生を聴くので系は閉ループになり、追従ゲインが高いと発散する）。1 打ごとのゆらぎは平滑化して無視し、狙ったテンポの遅い変化だけ追う。

```
[Audio IF] → 検出(onset/tempo) → テンポ推定+平滑化(PLL/中央値)
          → コントローラ(状態機械+低ゲイン追従) → MIDIクロック → ルーパー
```

## インストール

aubio の wheel 事情から **Python 3.10 を推奨**（plan §14）。

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[audio,midi]      # 実機用（音声入力 + MIDI 送出）
pip install -e .[detect]          # aubio を使う場合（任意。無ければ numpy 検出に自動フォールバック）
pip install -e .[dev]             # テスト
```

最小（検出ロジックの検証だけ）なら `pip install numpy` だけで動く。

## 使い方

依存は venv にのみ入れているので、**venv の python を使う**。
- bash (Git Bash): `./.venv/Scripts/python.exe -m bpm_midi_sync ...`（下記の形）
- PowerShell: `.\.venv\Scripts\python.exe -m bpm_midi_sync ...`
- 有効化すれば以降は素の `python -m bpm_midi_sync ...` でも可
  （bash: `source .venv/Scripts/activate` / PowerShell: `.\.venv\Scripts\Activate.ps1`）

```bash
# 実機不要の検証（合成クリックで検出〜追従を確認）
./.venv/Scripts/python.exe -m bpm_midi_sync selftest --bpm 128 --jitter 5

# 閉ループ安定性シミュレーション（反応するドラマー模擬。実機不要）
./.venv/Scripts/python.exe -m bpm_midi_sync simulate --bpm 120 --gain 0.3 --latency 0.15

# パラメータ自動探索（=「学習」）
./.venv/Scripts/python.exe -m bpm_midi_sync sweep

# 音源ファイルを検出（--midi で実際にクロック送出、--realtime で実時間ペース）
./.venv/Scripts/python.exe -m bpm_midi_sync file path/to/drums.wav --realtime --midi --seed 120

# デバイス/ポート確認
./.venv/Scripts/python.exe -m bpm_midi_sync list-devices
./.venv/Scripts/python.exe -m bpm_midi_sync list-midi

# ライブ入力 → MIDI クロック（実機）。--device は list-devices、--midi-port は list-midi 参照
./.venv/Scripts/python.exe -m bpm_midi_sync run --device 15 --midi-port loopMIDI --seed 120

# ブラウザ等のシステム音声をループバック入力（YouTube 検証。DL 不要）
./.venv/Scripts/python.exe -m bpm_midi_sync loopback --midi-port loopMIDI
./.venv/Scripts/python.exe -m bpm_midi_sync loopback --no-midi          # 検出だけ見る
```

## 構成

| モジュール | 役割 |
|---|---|
| `bpm_midi_sync/sources/` | 入力ソース抽象（live / file / loopback / array） |
| `beat_detector.py` | スペクトルフラックスのオンセット検出（numpy）/ aubio ラッパ |
| `tempo_estimator.py` | テンポ推定 + 平滑化（PLL / 中央値 IBI、octave 補正、スルーレート/IIR/デッドバンド） |
| `controller.py` | 状態機械（IDLE/ACQUIRING/LOCKED/HOLD）+ 低ゲイン追従 |
| `midi_clock.py` | MIDI クロック送出スレッド（累積時刻・スピン待ち・Windows timeBeginPeriod） |
| `engine.py` | 上記の配線（オーディオでもオフラインでも同一） |
| `metrics.py` | 整定時間・追従誤差・定常ジッタの計測 |
| `eval/` | 合成信号・バッチ評価・パラメータ探索・閉ループ模擬・参照ビート生成 |

## テスト

```powershell
pip install -e .[dev]
pytest -q
```

## 既知の制約（v1）

- numpy 検出は**オンセットベース**。複雑な生ドラムでは aubio バックエンド推奨。
- 出力 BPM には hop 量子化（hop/sr 秒）由来の微小バイアスがあり、デッドバンドで固定される（安定性優先の設計トレードオフ。plan §7）。
- **位相（小節頭）同期は未実装**（テンポ追従のみ。plan の段階 12）。
- 閉ループ安定性は録音では測れないため `simulate`（模擬ドラマー）で確認する。

## ハードウェア（plan §2.5）

- ルーパー: **BOSS RC-600**。MIDI Sync を外部クロックに。録音ループが外部クロックで追従するかは要実機確認（最重要プレミス）。
- オーディオ IF: **ZOOM UAC-232**（MIDI I/O あり）。経路 A: PC→USB→UAC-232 MIDI OUT→RC-600 MIDI IN で 1 台完結。
- マイク: キック用ダイナミック 1 本で十分（テンポ検出にはキックのトランジェントが安定）。
