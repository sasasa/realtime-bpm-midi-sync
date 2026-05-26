import csv

from bpm_midi_sync.metrics import DeviationLogger


def test_deviation_logging(tmp_path):
    path = tmp_path / "dev.csv"
    log = DeviationLogger(path, threshold_pct=0.10, interval_s=1.0)

    # 期待 120。閾値 10% 以内は記録しない
    assert log.record(0.0, 121.0, 121.0, "LOCKED", "songA", 120.0) is False
    # 16.7% ズレ → 記録
    assert log.record(0.0, 140.0, 120.0, "LOCKED", "songA", 120.0) is True
    # interval 内（0.5s）は再記録しない
    assert log.record(0.5, 140.0, 120.0, "LOCKED", "songA", 120.0) is True
    # interval 経過後は再記録
    log.record(1.2, 140.0, 120.0, "LOCKED", "songA", 120.0)
    # 期待 None / 検出 None は無視
    assert log.record(2.0, 140.0, 120.0, "LOCKED", "songA", None) is False
    assert log.record(2.0, None, 120.0, "LOCKED", "songA", 120.0) is False
    log.close()

    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "wall_time"            # ヘッダ
    assert len(rows) - 1 == 2                    # 記録は 2 件（throttle 済み）
    assert rows[1][2] == "songA" and rows[1][3] == "120.0"
