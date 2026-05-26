"""CLI（plan §11）。

サブコマンド:
  list-devices  オーディオデバイス一覧
  list-midi     MIDI 出力ポート一覧
  selftest      合成クリックで検出〜追従を検証（実機不要）
  simulate      閉ループ安定性シミュレーション（実機不要）
  sweep         合成ケースでパラメータ自動探索
  file          音源ファイルを検出 → （任意で）MIDI クロック送出
  run           ライブ入力（sounddevice）→ MIDI クロック送出
  loopback      システム音声ループバック → MIDI クロック送出
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from .config import Config


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="設定 JSON のパス")
    p.add_argument("--detector", choices=["numpy", "aubio"])
    p.add_argument("--estimator", choices=["pll", "median"])
    p.add_argument("--samplerate", type=int)
    p.add_argument("--hop", type=int, dest="hop_size")
    p.add_argument("--device", type=int, dest="input_device",
                   help="入力デバイス番号（list-devices 参照）")
    p.add_argument("--midi-port", dest="midi_port",
                   help="MIDI 出力ポート名（部分一致。list-midi 参照）")
    p.add_argument("--expected-bpm", type=float, dest="prefer_bpm",
                   help="期待テンポ（autocorr のオクターブ prior 中心。概テンポが分かる時に指定）")
    p.add_argument("--lock-range", type=float, dest="tempo_lock_range_pct",
                   help="検出を期待テンポ±この割合に拘束（例 0.35）。オクターブ跳びを排除")


def _load_config(args) -> Config:
    cfg = Config.load(args.config) if getattr(args, "config", None) else Config()
    for key in ("detector", "estimator", "samplerate", "hop_size",
                "input_device", "midi_port", "prefer_bpm", "tempo_lock_range_pct"):
        val = getattr(args, key, None)
        if val is not None:
            cfg = cfg.replace(**{key: val})
    # 期待テンポ(expected/seed)を与えたら既定で±35%拘束（オクターブ安定）
    seedish = getattr(args, "prefer_bpm", None) or getattr(args, "seed", None)
    if seedish is not None and cfg.tempo_lock_range_pct == 0.0:
        cfg = cfg.replace(tempo_lock_range_pct=0.35)
    return cfg


# --------------------------------------------------------------------- #
def cmd_list_devices(_args) -> int:
    import sounddevice as sd

    print(sd.query_devices())
    return 0


def cmd_list_midi(_args) -> int:
    from .midi_clock import list_output_ports

    ports = list_output_ports()
    if not ports:
        print("MIDI 出力ポートなし（loopMIDI 等を起動してください）")
    for p in ports:
        print(p)
    return 0


def cmd_selftest(args) -> int:
    from .eval.batch_eval import evaluate_array
    from .eval.synth import click_track

    cfg = _load_config(args)
    bpm = args.bpm
    samples = click_track(bpm, args.duration, cfg.samplerate, jitter_ms=args.jitter)
    res = evaluate_array(cfg, samples, bpm)
    print(f"true_bpm      : {res.true_bpm}")
    print(f"final_bpm     : {res.final_bpm}")
    print(f"tracking_error: {res.tracking_error}")
    print(f"jitter(std)   : {res.jitter}")
    print(f"settling_time : {res.settling_time}")
    print(f"locked        : {res.locked}")
    if res.tracking_error is not None:
        print(f"error_percent : {100 * res.tracking_error / bpm:.2f}%")
    # hop 量子化バイアス（hop/sr 秒）はデッドバンドで固定されるため、許容は相対 3%
    ok = (res.locked and res.tracking_error is not None
          and res.tracking_error < 0.03 * bpm + 0.5)
    print("RESULT:", "OK" if ok else "NG")
    return 0 if ok else 1


def cmd_simulate(args) -> int:
    from .eval.sim_drummer import simulate_closed_loop

    cfg = _load_config(args)
    r = simulate_closed_loop(cfg, intended_bpm=args.bpm, entrain_gain=args.gain,
                             latency_s=args.latency, duration_s=args.duration)
    print(f"intended_bpm  : {args.bpm}")
    print(f"final_target  : {r.final_target()}")
    print(f"final_drummer : {r.final_drummer()}")
    print(f"diverged      : {r.diverged}")
    return 1 if r.diverged else 0


def cmd_sweep(args) -> int:
    from .eval.param_sweep import grid_search
    from .eval.synth import click_track

    cfg = _load_config(args)
    cases = [
        (click_track(100.0, 16.0, cfg.samplerate, jitter_ms=4.0), 100.0),
        (click_track(140.0, 16.0, cfg.samplerate, jitter_ms=4.0), 140.0),
    ]
    grid = {
        "iir_alpha": [0.1, 0.2, 0.3],
        "max_step_bpm": [0.5, 1.0, 2.0],
        "pll_ki": [0.05, 0.1, 0.2],
    }
    best = grid_search(cfg, cases, grid)
    print("best overrides:", best.overrides)
    print("best score    :", round(best.score, 4))
    return 0


def _run_with_midi(cfg: Config, source, use_midi: bool, seed_bpm: Optional[float]) -> int:
    from .engine import Engine
    from .metrics import MetricsLog

    engine = Engine(cfg, MetricsLog())
    if seed_bpm is not None:
        engine.seed_tempo(seed_bpm)

    midi = None
    if use_midi:
        from .midi_clock import MidiClock

        midi = MidiClock(cfg.midi_port, bpm=seed_bpm or cfg.initial_bpm, ppqn=cfg.ppqn)
        engine.attach_midi(midi)
        midi.start()
        print(f"MIDI クロック送出中: ポート='{midi.port_name}'")

    # 4Hz に間引いて現在値を1行更新表示
    last = {"q": -1}

    def status(t, detected, target, state):
        q = int(t * 4)
        if q == last["q"]:
            return
        last["q"] = q
        d = f"{detected:6.1f}" if detected is not None else "  --  "
        tg = f"{target:6.1f}" if target is not None else "  --  "
        sys.stdout.write(f"\r[{state:9}] t={t:6.1f}s  検出={d}  送出={tg} BPM   ")
        sys.stdout.flush()

    print("Ctrl-C で停止")
    try:
        engine.run(source, status_cb=status)
    except KeyboardInterrupt:
        print("\n停止します")
    finally:
        if midi is not None:
            midi.stop()
            time.sleep(0.1)
    print(f"最終 BPM: {engine.controller.target_bpm}  状態: {engine.controller.state.value}")
    return 0


def cmd_file(args) -> int:
    from .sources.file import FileSource

    cfg = _load_config(args)
    source = FileSource(args.path, cfg.samplerate, cfg.hop_size, realtime=args.realtime)
    return _run_with_midi(cfg, source, use_midi=args.midi, seed_bpm=args.seed)


def cmd_run(args) -> int:
    from .sources.live import LiveSource

    cfg = _load_config(args)
    source = LiveSource(cfg.samplerate, cfg.hop_size, device=cfg.input_device,
                        channels=cfg.channels)
    return _run_with_midi(cfg, source, use_midi=not args.no_midi, seed_bpm=args.seed)


def cmd_loopback(args) -> int:
    from .sources.loopback import LoopbackSource

    cfg = _load_config(args)
    source = LoopbackSource(cfg.samplerate, cfg.hop_size)
    return _run_with_midi(cfg, source, use_midi=not args.no_midi, seed_bpm=args.seed)


def cmd_gui(args) -> int:
    from .gui import run_gui

    return run_gui(args.setlist, _load_config(args))


# --------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bpm-midi-sync", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-devices").set_defaults(func=cmd_list_devices)
    sub.add_parser("list-midi").set_defaults(func=cmd_list_midi)

    p = sub.add_parser("selftest", help="合成クリックで検証")
    _add_common(p)
    p.add_argument("--bpm", type=float, default=120.0)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--jitter", type=float, default=4.0, help="打点ゆらぎ[ms]")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("simulate", help="閉ループ安定性シミュレーション")
    _add_common(p)
    p.add_argument("--bpm", type=float, default=120.0)
    p.add_argument("--gain", type=float, default=0.2, help="ドラマーの引き込みゲイン")
    p.add_argument("--latency", type=float, default=0.15, help="聴取遅延[秒]")
    p.add_argument("--duration", type=float, default=30.0)
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("sweep", help="パラメータ自動探索")
    _add_common(p)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("file", help="音源ファイルを検出")
    _add_common(p)
    p.add_argument("path")
    p.add_argument("--realtime", action="store_true", help="実時間ペースで再生")
    p.add_argument("--midi", action="store_true", help="MIDI クロックを送出")
    p.add_argument("--seed", type=float, help="初期 BPM（タップ相当）")
    p.set_defaults(func=cmd_file)

    p = sub.add_parser("run", help="ライブ入力 → MIDI クロック")
    _add_common(p)
    p.add_argument("--no-midi", action="store_true")
    p.add_argument("--seed", type=float, help="初期 BPM（タップ相当）")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("loopback", help="システム音声ループバック → MIDI クロック")
    _add_common(p)
    p.add_argument("--no-midi", action="store_true")
    p.add_argument("--seed", type=float, help="初期 BPM")
    p.set_defaults(func=cmd_loopback)

    p = sub.add_parser("gui", help="セットリスト型 GUI（曲選択で expected-bpm 切替）")
    _add_common(p)
    p.add_argument("--setlist", help="セットリスト JSON（既定: ./setlist.json）")
    p.set_defaults(func=cmd_gui)

    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
