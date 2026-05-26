from bpm_midi_sync.metrics import MetricsLog


def test_settling_and_jitter():
    m = MetricsLog()
    # 0-2s は誤差大、その後 120 に張り付く
    t = 0.0
    while t < 2.0:
        m.log(t, 110.0, 110.0, "LOCKED")
        t += 0.1
    while t < 8.0:
        m.log(t, 120.0, 120.0, "LOCKED")
        t += 0.1
    assert m.final_bpm() == 120.0
    settle = m.settling_time(120.0, tol=0.5)
    assert settle is not None and 1.9 < settle < 2.2
    jitter = m.steady_state_jitter(last_seconds=3.0)
    assert jitter is not None and jitter < 1e-6
    err = m.tracking_error(120.0, skip_seconds=3.0)
    assert err is not None and err < 1e-6
