from mcp_insight.lost_in_middle import LostInMiddleDetector, estimate_tokens


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1  # never zero, avoids div-by-zero downstream


def test_no_signal_for_small_ordinary_result():
    detector = LostInMiddleDetector()
    signal = detector.check_call("add_numbers", "Adds two numbers", {"a": 1, "b": 2}, {"sum": 3})
    assert signal is None


def test_flags_large_result_set_for_retrieval_tool():
    detector = LostInMiddleDetector()
    items = [{"text": f"chunk-{i}", "score": 0.9 - i * 0.01} for i in range(20)]
    signal = detector.check_call("vector_search", "Searches the vector index", {"q": "x"}, {"matches": items})
    assert signal is not None
    assert "large_result_set" in signal["risk_factors"]
    assert signal["result_count"] == 20


def test_flags_unranked_results():
    detector = LostInMiddleDetector()
    # Scores not in descending order -- best match isn't first.
    items = [{"text": "a", "score": 0.2}, {"text": "b", "score": 0.9}, {"text": "c", "score": 0.5},
             {"text": "d", "score": 0.1}, {"text": "e", "score": 0.7}, {"text": "f", "score": 0.3},
             {"text": "g", "score": 0.6}, {"text": "h", "score": 0.4}, {"text": "i", "score": 0.8},
             {"text": "j", "score": 0.15}, {"text": "k", "score": 0.55}, {"text": "l", "score": 0.25},
             {"text": "m", "score": 0.65}, {"text": "n", "score": 0.35}, {"text": "o", "score": 0.75},
             {"text": "p", "score": 0.45}]
    signal = detector.check_call("vector_search", "Searches things", {"q": "x"}, {"matches": items})
    assert signal is not None
    assert "unranked_results" in signal["risk_factors"]


def test_does_not_flag_properly_ranked_small_results():
    detector = LostInMiddleDetector()
    items = [{"text": "a", "score": 0.9}, {"text": "b", "score": 0.5}, {"text": "c", "score": 0.1}]
    signal = detector.check_call("vector_search", "Searches things", {"q": "x"}, {"matches": items})
    assert signal is None


def test_flags_repeated_query_after_large_context():
    detector = LostInMiddleDetector()
    big_result = {"text": "x" * 3000}
    args = {"q": "same question"}

    first = detector.check_call("search_docs", "Searches docs", args, big_result)
    assert first is None  # first call, nothing to compare against yet

    second = detector.check_call("search_docs", "Searches docs", args, {"text": "short"})
    assert second is not None
    assert "repeated_query_after_large_context" in second["risk_factors"]


def test_does_not_flag_repeated_query_with_different_arguments():
    detector = LostInMiddleDetector()
    big_result = {"text": "x" * 3000}
    detector.check_call("search_docs", "Searches docs", {"q": "question one"}, big_result)
    second = detector.check_call("search_docs", "Searches docs", {"q": "question two"}, {"text": "short"})
    assert second is None


def test_flags_size_outlier_after_baseline_established():
    detector = LostInMiddleDetector()
    for i in range(25):
        detector.check_call("summarize", "Summarizes text", {"i": i}, {"text": "normal " + "x" * (i % 3)})

    outlier_result = {"text": "y" * 10000}
    signal = detector.check_call("summarize", "Summarizes text", {"i": 999}, outlier_result)
    assert signal is not None
    assert "size_outlier" in signal["risk_factors"]
