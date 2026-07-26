from mcp_insight.retrieval_signals import extract_retrieval_signal, looks_like_retrieval_tool


def test_looks_like_retrieval_tool_matches_common_names():
    assert looks_like_retrieval_tool("vector_search", None)
    assert looks_like_retrieval_tool("search_docs", None)
    assert looks_like_retrieval_tool("lookup_kb", None)
    assert looks_like_retrieval_tool("add_numbers", "embeds a query and retrieves similar chunks")
    assert not looks_like_retrieval_tool("add_numbers", "Adds two numbers")


def test_extract_signal_none_for_non_retrieval_tool():
    result = extract_retrieval_signal("add_numbers", "Adds two numbers", {"sum": 3})
    assert result is None


def test_extract_signal_none_when_result_not_list_shaped():
    result = extract_retrieval_signal("vector_search", "Searches vectors", {"status": "ok"})
    assert result is None


def test_extract_signal_counts_top_level_list_result():
    result = extract_retrieval_signal("search", "Search tool", [{"text": "a"}, {"text": "b"}])
    assert result["result_count"] == 2
    assert result["empty"] is False


def test_extract_signal_detects_empty_results():
    result = extract_retrieval_signal("search", "Search tool", {"results": []})
    assert result["result_count"] == 0
    assert result["empty"] is True


def test_extract_signal_computes_score_stats():
    result = extract_retrieval_signal(
        "vector_search", "Vector search",
        {"matches": [{"score": 0.9}, {"score": 0.5}, {"score": 0.7}]},
    )
    assert result["result_count"] == 3
    assert result["top_score"] == 0.9
    assert result["min_score"] == 0.5
    assert round(result["avg_score"], 3) == round((0.9 + 0.5 + 0.7) / 3, 3)


def test_extract_signal_handles_missing_scores_gracefully():
    result = extract_retrieval_signal("search", "Search", {"documents": [{"text": "a"}, {"text": "b"}]})
    assert result["result_count"] == 2
    assert "top_score" not in result
