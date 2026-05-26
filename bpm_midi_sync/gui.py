"""セットリスト型 GUI（Tkinter・追加依存なし）。

曲を選ぶと expected-bpm（テンポ prior）が切り替わり、その曲のテンポでロックし直す。
入力はループバック（システム音声）かライブ入力（マイク）。MIDI 出力ポートも選べる。

起動: python -m bpm_midi_sync gui
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import List, Optional

from .config import Config
from .engine import Engine
from .metrics import DeviationLogger

NO_MIDI = "（MIDIなし）"
DEFAULT_SONGS = [
    {"name": "インブルーム", "bpm": 79},
    {"name": "ブリード", "bpm": 159},
    {"name": "スクール", "bpm": 82},
    {"name": "リチウム", "bpm": 123},
    {"name": "ラウンジアクト", "bpm": 151},
    {"name": "スメルズライクティーンスピリット", "bpm": 117},
]


def load_setlist(path: Optional[str]) -> List[dict]:
    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data.get("songs", DEFAULT_SONGS)
    default = Path("setlist.json")
    if default.exists():
        return json.loads(default.read_text(encoding="utf-8")).get("songs", DEFAULT_SONGS)
    return DEFAULT_SONGS


class EngineRunner:
    """別スレッドで Engine を回し、状態をキューへ流す。expected-bpm を随時切替。"""

    def __init__(self, cfg: Config, source_kind: str, midi_port: Optional[str],
                 status_q: "queue.Queue", record_input: bool = False):
        self.cfg = cfg
        self.q = status_q
        self.engine = Engine(cfg)
        self.input_wav: Optional[Path] = None
        if record_input:
            self.input_wav = Path("logs") / f"input_{datetime.now():%Y%m%d_%H%M%S}.wav"
        self._source = self._make_source(source_kind)
        self._midi = None
        self._thread: Optional[threading.Thread] = None
        self.expected_bpm: Optional[float] = None
        self.song_name: Optional[str] = None
        self.log_path = Path("logs") / f"deviation_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._devlog = DeviationLogger(self.log_path, cfg.deviation_log_pct,
                                       cfg.deviation_log_interval_s)
        if midi_port and midi_port != NO_MIDI:
            from .midi_clock import MidiClock
            self._midi = MidiClock(midi_port, bpm=cfg.prefer_bpm, ppqn=cfg.ppqn)
            self.engine.attach_midi(self._midi)

    def _make_source(self, kind: str):
        if kind == "live":
            from .sources.live import LiveSource
            return LiveSource(self.cfg.samplerate, self.cfg.hop_size,
                              device=self.cfg.input_device, channels=self.cfg.channels)
        from .sources.loopback import LoopbackSource
        return LoopbackSource(self.cfg.samplerate, self.cfg.hop_size,
                              record_path=str(self.input_wav) if self.input_wav else None)

    def set_expected_bpm(self, bpm: float, name: Optional[str] = None) -> None:
        self.expected_bpm = bpm
        self.song_name = name
        self.engine.seed_tempo(bpm)  # prior 更新 + その BPM で再ロック
        if self._midi is not None:
            self._midi.set_bpm(bpm)

    def start(self) -> None:
        if self._midi is not None:
            self._midi.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _status(self, t, d, tg, st) -> None:
        deviating = self._devlog.record(t, d, tg, st, self.song_name, self.expected_bpm)
        self.q.put((t, d, tg, st, deviating))

    def _run(self) -> None:
        try:
            self.engine.run(self._source, status_cb=self._status)
        except Exception as exc:  # noqa: BLE001
            self.q.put(("error", str(exc), None, "ERROR", False))

    def stop(self) -> None:
        try:
            self._source.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._midi is not None:
            self._midi.stop()
        self._devlog.close()


class App:
    def __init__(self, root: tk.Tk, songs: List[dict], cfg: Config):
        self.root = root
        self.cfg = cfg
        self.songs = songs
        self.runner: Optional[EngineRunner] = None
        self.q: "queue.Queue" = queue.Queue()
        root.title("BPM Sync — セットリスト")
        root.geometry("520x460")
        self._build()
        self.root.after(100, self._poll)

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="入力:").grid(row=0, column=0, sticky="w")
        self.src_var = tk.StringVar(value="ループバック(システム音声)")
        ttk.Combobox(top, textvariable=self.src_var, state="readonly", width=22,
                     values=["ループバック(システム音声)", "ライブ入力(マイク)"]).grid(row=0, column=1, sticky="w")

        ttk.Label(top, text="MIDI:").grid(row=1, column=0, sticky="w", pady=4)
        self.midi_var = tk.StringVar(value=NO_MIDI)
        ttk.Combobox(top, textvariable=self.midi_var, state="readonly", width=30,
                     values=self._midi_ports()).grid(row=1, column=1, columnspan=2, sticky="w")

        self.btn = ttk.Button(top, text="開始", command=self._toggle)
        self.btn.grid(row=0, column=2, padx=8)

        self.rec_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="入力録音(診断)", variable=self.rec_var).grid(row=2, column=1, sticky="w")

        # 現在値表示
        mid = ttk.Frame(self.root, padding=8)
        mid.pack(fill="x")
        self.state_lbl = ttk.Label(mid, text="停止中", font=("", 11))
        self.state_lbl.pack(anchor="w")
        self.bpm_lbl = ttk.Label(mid, text="-- BPM", font=("", 40, "bold"))
        self.bpm_lbl.pack(anchor="w")
        self.detail_lbl = ttk.Label(mid, text="検出 -- / 送出 --", font=("", 11))
        self.detail_lbl.pack(anchor="w")
        self.song_lbl = ttk.Label(mid, text="曲: 未選択", font=("", 12, "bold"), foreground="#1565c0")
        self.song_lbl.pack(anchor="w", pady=4)
        self.dev_lbl = ttk.Label(mid, text="", font=("", 11, "bold"), foreground="#c62828")
        self.dev_lbl.pack(anchor="w")
        self.log_lbl = ttk.Label(mid, text="", font=("", 9), foreground="#666")
        self.log_lbl.pack(anchor="w")

        # セットリスト
        body = ttk.Frame(self.root, padding=8)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="セットリスト（クリックで expected-bpm 切替）:").pack(anchor="w")
        self.listbox = tk.Listbox(body, font=("", 14), height=8, activestyle="dotbox")
        for s in self.songs:
            self.listbox.insert("end", f"{s['name']}　—　{s['bpm']} BPM")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _midi_ports(self) -> List[str]:
        try:
            from .midi_clock import list_output_ports
            return [NO_MIDI] + list_output_ports()
        except Exception:  # noqa: BLE001
            return [NO_MIDI]

    def _toggle(self) -> None:
        if self.runner is None:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        kind = "live" if self.src_var.get().startswith("ライブ") else "loopback"
        try:
            self.runner = EngineRunner(self.cfg, kind, self.midi_var.get(), self.q,
                                       record_input=self.rec_var.get())
            self.runner.start()
        except Exception as exc:  # noqa: BLE001
            self.state_lbl.config(text=f"起動失敗: {exc}", foreground="red")
            self.runner = None
            return
        self.btn.config(text="停止")
        self.state_lbl.config(text="起動中…", foreground="black")
        logtxt = f"ズレログ: {self.runner.log_path}"
        if self.runner.input_wav:
            logtxt += f"\n入力録音: {self.runner.input_wav}"
        self.log_lbl.config(text=logtxt)
        # 既に選択済みの曲があれば prior を適用
        sel = self.listbox.curselection()
        if sel:
            s = self.songs[sel[0]]
            self.runner.set_expected_bpm(float(s["bpm"]), s["name"])

    def _stop(self) -> None:
        if self.runner:
            self.runner.stop()
        self.runner = None
        self.btn.config(text="開始")
        self.state_lbl.config(text="停止中")
        self.bpm_lbl.config(text="-- BPM")

    def _on_select(self, _event) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        song = self.songs[sel[0]]
        self.song_lbl.config(text=f"曲: {song['name']}（expected {song['bpm']} BPM）")
        if self.runner:
            self.runner.set_expected_bpm(float(song["bpm"]), song["name"])

    def _poll(self) -> None:
        last = None
        try:
            while True:
                last = self.q.get_nowait()
        except queue.Empty:
            pass
        if last is not None:
            t, d, tg, st, deviating = last
            if st == "ERROR":
                self.state_lbl.config(text=f"エラー: {d}", foreground="red")
            else:
                self.state_lbl.config(text=f"状態: {st}   t={t:.0f}s", foreground="black")
                self.bpm_lbl.config(text=f"{tg:.1f} BPM" if tg else "-- BPM")
                ds = f"{d:.1f}" if d else "--"
                ts = f"{tg:.1f}" if tg else "--"
                self.detail_lbl.config(text=f"検出 {ds} / 送出 {ts}")
                if deviating and self.runner and self.runner.expected_bpm:
                    diff = (d or 0) - self.runner.expected_bpm
                    self.dev_lbl.config(text=f"⚠ 期待値から {diff:+.0f} BPM ズレ（記録中）")
                else:
                    self.dev_lbl.config(text="")
        self.root.after(100, self._poll)


def run_gui(setlist_path: Optional[str], cfg: Config) -> int:
    # セットリストの BPM は信頼できる期待値。検出を ±25% に拘束（オクターブ＋
    # 近傍の競合ピーク=例 79 に対する 100 を排除）し、送出は期待値±15% に固定して暴走防止。
    if cfg.tempo_lock_range_pct == 0.0:
        cfg = cfg.replace(tempo_lock_range_pct=0.25)
    if cfg.target_max_drift_pct == 0.0:
        cfg = cfg.replace(target_max_drift_pct=0.15)
    songs = load_setlist(setlist_path)
    root = tk.Tk()
    App(root, songs, cfg)
    root.mainloop()
    return 0
