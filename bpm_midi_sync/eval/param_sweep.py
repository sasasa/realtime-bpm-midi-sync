"""パラメータ自動探索（plan §12-5。= ここでの「学習」）。

検証ケース（合成クリック等）に対し推定/平滑/追従のパラメータを総当たりし、
多目的（定常ジッタ↓・追従誤差↓・整定時間↓・要ロック）でスコアづけして最良を返す。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ..config import Config
from .batch_eval import evaluate_array


@dataclass
class SweepResult:
    overrides: Dict[str, float]
    score: float
    detail: List[dict]


def _score(results, jitter_w=1.0, error_w=1.0, settle_w=0.05) -> float:
    """小さいほど良いコスト。ロック失敗や追従不能は大きく罰する。"""
    total = 0.0
    for r in results:
        if not r.locked or r.tracking_error is None:
            total += 1000.0
            continue
        jitter = r.jitter if r.jitter is not None else 5.0
        settle = r.settling_time if r.settling_time is not None else 30.0
        total += error_w * r.tracking_error + jitter_w * jitter + settle_w * settle
    return total / max(1, len(results))


def grid_search(base: Config, cases: Sequence[Tuple[np.ndarray, float]],
                grid: Dict[str, Sequence]) -> SweepResult:
    """cases = [(samples, true_bpm), ...]、grid = {param: [候補,...]}。"""
    keys = list(grid.keys())
    best: SweepResult | None = None
    detail: List[dict] = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        overrides = dict(zip(keys, combo))
        cfg = base.replace(**overrides)
        results = [evaluate_array(cfg, s, bpm) for s, bpm in cases]
        score = _score(results)
        detail.append({"overrides": overrides, "score": score})
        if best is None or score < best.score:
            best = SweepResult(overrides=overrides, score=score, detail=[])
    assert best is not None
    best.detail = detail
    return best
