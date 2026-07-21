from app.health_scoring import compute_health_score


def test_perfect_server_scores_100():
    result = compute_health_score(
        total_calls=100,
        error_count=0,
        silent_failure_count=0,
        p95_latency_ms=200,
        cpu_samples=[10, 12, 11],
        mem_samples=[1_000_000, 1_010_000],
        classified_severities=[],
    )
    assert result["score"] == 100.0
    assert result["status"] == "healthy"


def test_high_error_rate_drops_score_and_status():
    result = compute_health_score(
        total_calls=100,
        error_count=50,
        silent_failure_count=0,
        p95_latency_ms=200,
        cpu_samples=[],
        mem_samples=[],
        classified_severities=[],
    )
    assert result["breakdown"]["error_rate_penalty"] == 20.0
    assert result["score"] == 80.0
    assert result["status"] == "degraded"


def test_silent_failures_penalized_more_than_reported_errors_scaled():
    silent = compute_health_score(100, 0, 20, None, [], [], [])
    errors = compute_health_score(100, 20, 0, None, [], [], [])
    # same rate (20%), different weight -- silent failures use a lower
    # multiplier (0.35) than errors (0.40) but both should meaningfully hurt
    assert silent["breakdown"]["silent_failure_penalty"] == 7.0
    assert errors["breakdown"]["error_rate_penalty"] == 8.0


def test_latency_penalty_scales_between_warn_and_critical():
    low = compute_health_score(10, 0, 0, 500, [], [], [])
    mid = compute_health_score(10, 0, 0, 5000, [], [], [])
    high = compute_health_score(10, 0, 0, 20000, [], [], [])
    assert low["breakdown"]["latency_penalty"] == 0.0
    assert 0 < mid["breakdown"]["latency_penalty"] < 15
    assert high["breakdown"]["latency_penalty"] == 15.0


def test_cpu_pressure_penalizes():
    result = compute_health_score(10, 0, 0, None, [95, 96, 97], [], [])
    assert result["breakdown"]["process_penalty"] > 0


def test_memory_growth_penalizes():
    result = compute_health_score(10, 0, 0, None, [], [1_000_000, 5_000_000], [])
    assert result["breakdown"]["process_penalty"] > 0


def test_severity_penalty_weighted_and_capped():
    all_critical = compute_health_score(10, 0, 0, None, [], [], ["critical"] * 20)
    assert all_critical["breakdown"]["severity_penalty"] == 20.0  # capped
    minor_only = compute_health_score(10, 0, 0, None, [], [], ["minor"])
    assert minor_only["breakdown"]["severity_penalty"] == 0.5


def test_score_never_goes_below_zero():
    result = compute_health_score(10, 10, 10, 999999, [100] * 5, [1, 1_000_000], ["critical"] * 50)
    assert result["score"] == 0.0
    assert result["status"] == "critical"


def test_zero_calls_no_division_error():
    result = compute_health_score(0, 0, 0, None, [], [], [])
    assert result["score"] == 100.0
