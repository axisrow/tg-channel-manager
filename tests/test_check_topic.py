import pytest

from conftest import dedup_check


class TestCheckTopicEmptyCases:
    def test_empty_index(self):
        assert dedup_check.check_topic("python asyncio tutorial", []) == []

    def test_empty_topic(self, sample_index):
        assert dedup_check.check_topic("", sample_index) == []

    def test_only_stopwords(self, sample_index):
        assert dedup_check.check_topic("this that with from have been", sample_index) == []

    def test_only_short_words(self, sample_index):
        assert dedup_check.check_topic("go is at on to", sample_index) == []

    def test_mixed_short_and_stopwords(self, sample_index):
        assert dedup_check.check_topic("the is and with from", sample_index) == []

    def test_post_with_empty_keywords(self):
        index = [{"msgId": 1, "topic": "test", "links": [], "keywords": []}]
        assert dedup_check.check_topic("python asyncio tutorial", index) == []


class TestCheckTopicThresholds:
    """Score >= 0.4 AND overlap >= 2 required for a match."""

    def test_exact_match_above_threshold(self, sample_index):
        matches = dedup_check.check_topic("python asyncio tutorial beginners", sample_index)
        assert len(matches) >= 1
        assert matches[0]["msgId"] == 101

    def test_single_word_overlap_no_match(self, sample_index):
        """1 overlapping word: overlap < 2, so no match."""
        matches = dedup_check.check_topic("python web framework", sample_index)
        assert len(matches) == 0

    def test_two_word_overlap_matches(self, sample_index):
        """2 overlapping words out of 3 topic words: score=0.67, overlap=2."""
        matches = dedup_check.check_topic("python asyncio framework", sample_index)
        assert len(matches) >= 1

    def test_score_below_04_no_match(self):
        """1 overlap out of 3 topic words: score=0.33 < 0.4."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["alpha", "beta", "gamma"]}]
        matches = dedup_check.check_topic("alpha delta epsilon", index)
        assert len(matches) == 0

    def test_score_exactly_04_matches(self):
        """2 overlap out of 5 topic words: score=0.4, overlap=2."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["alpha", "beta", "gamma", "delta", "epsilon"]}]
        matches = dedup_check.check_topic("alpha beta zeta theta iota", index)
        assert len(matches) == 1
        assert matches[0]["score"] == 0.4

    @pytest.mark.parametrize(
        "topic, keywords, expect_match",
        [
            # 2/5 = 0.4 -> match
            ("alpha beta xxxxx yyyyy zzzzz", ["alpha", "beta", "gamma", "delta", "epsilon"], True),
            # 1/3 = 0.33 -> no match
            ("alpha xxxxx yyyyy", ["alpha", "beta", "gamma"], False),
            # 2/4 = 0.5 -> match
            ("alpha beta xxxxx yyyyy", ["alpha", "beta", "gamma", "delta"], True),
            # 2/2 = 1.0 -> match
            ("alpha beta", ["alpha", "beta", "gamma"], True),
            # 1/1 = 1.0 but overlap=1 < 2 -> no match
            ("alpha", ["alpha", "beta"], False),
        ],
        ids=["2of5", "1of3", "2of4", "2of2_full", "1of1_single"],
    )
    def test_threshold_parametrized(self, topic, keywords, expect_match):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": keywords}]
        matches = dedup_check.check_topic(topic, index)
        assert (len(matches) > 0) == expect_match


class TestCheckTopicExactMatch:
    def test_case_insensitive(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["Python", "Asyncio"]}]
        matches = dedup_check.check_topic("python asyncio guide", index)
        assert len(matches) >= 1

    def test_overlap_words_in_result(self, sample_index):
        matches = dedup_check.check_topic("python asyncio deep dive", sample_index)
        assert len(matches) >= 1
        overlap = matches[0]["overlap"]
        assert "python" in overlap or "asyncio" in overlap


class TestCheckTopicStemMatch:
    def test_stem_matching_first_5_chars(self):
        """'deployment' and 'deploying' share stem 'deplo'."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["deployment", "strategies"]}]
        matches = dedup_check.check_topic("deploying strategic planning", index)
        assert len(matches) >= 1

    def test_stem_marker_in_overlap(self):
        """Stem-only matches should have * marker."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["deployment", "configuration"]}]
        matches = dedup_check.check_topic("deploying configuring systems", index)
        assert len(matches) >= 1
        overlap = matches[0]["overlap"]
        starred = [w for w in overlap if w.endswith("*")]
        assert len(starred) > 0

    def test_short_words_skip_stemming(self):
        """Words < 5 chars don't participate in stem matching."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["code", "test"]}]
        # 'code' and 'test' are 4 chars, no stem matching
        # 'coding' stem 'codin' != 'code' (4 chars, not stemmed)
        matches = dedup_check.check_topic("coding testing framework", index)
        # exact overlap is 0 (code!=coding, test!=testing)
        # stem: 'codin' from coding (5chars), 'testi' from testing (7chars)
        # post stems: none (code=4chars, test=4chars)
        assert len(matches) == 0

    def test_stem_takes_best_of_exact_and_stem(self):
        """Score uses max(exact_overlap, stem_overlap)."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["running", "jumping", "swimming"]}]
        # 'runner' stem 'runne' vs 'running' stem 'runni' -> different stems!
        # 'jumper' stem 'jumpe' vs 'jumping' stem 'jumpi' -> different stems!
        # Let's use words that actually share stems
        matches = dedup_check.check_topic("running jumping quickly", index)
        # exact match: running, jumping -> overlap=2
        assert len(matches) >= 1


class TestCheckTopicScoring:
    def test_score_is_ratio(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["alpha", "beta", "gamma", "delta"]}]
        matches = dedup_check.check_topic("alpha beta xxxx yyyy", index)
        assert matches[0]["score"] == 0.5  # 2/4

    def test_uses_min_of_topic_and_post_words(self):
        """Score denominator is min(topic_words, post_words)."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["alpha", "beta"]}]
        matches = dedup_check.check_topic("alpha beta gamma delta epsilon", index)
        # overlap=2, min(5, 2)=2, score=1.0
        assert matches[0]["score"] == 1.0

    def test_sorted_by_score_descending(self):
        index = [
            {"msgId": 1, "topic": "t1", "links": [], "keywords": ["alpha", "beta", "gamma", "delta", "epsilon"]},
            {"msgId": 2, "topic": "t2", "links": [], "keywords": ["alpha", "beta"]},
        ]
        matches = dedup_check.check_topic("alpha beta zeta theta", index)
        assert len(matches) == 2
        assert matches[0]["score"] >= matches[1]["score"]

    def test_result_contains_msgid_topic_score_overlap(self, sample_index):
        matches = dedup_check.check_topic("python asyncio deep dive", sample_index)
        assert len(matches) >= 1
        m = matches[0]
        assert "msgId" in m
        assert "topic" in m
        assert "score" in m
        assert "overlap" in m

    def test_topic_truncated_to_100(self):
        long_topic = "word " * 30
        index = [{"msgId": 1, "topic": long_topic, "links": [], "keywords": ["alpha", "beta"]}]
        matches = dedup_check.check_topic("alpha beta gamma", index)
        assert len(matches[0]["topic"]) <= 100


class TestCheckTopicUnicode:
    def test_cyrillic_words_extracted(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["\u043f\u0438\u0442\u043e\u043d", "\u0430\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u043d\u043e\u0441\u0442\u044c"]}]
        matches = dedup_check.check_topic("\u043f\u0438\u0442\u043e\u043d \u0430\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u043d\u043e\u0441\u0442\u044c \u043e\u0431\u0437\u043e\u0440", index)
        assert len(matches) >= 1

    def test_digits_not_extracted(self):
        """Words with only digits are not extracted by regex."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["python", "tutorial"]}]
        # '2024' has no letter chars
        matches = dedup_check.check_topic("2024 python tutorial update", index)
        assert len(matches) >= 1

    def test_chinese_chars_extracted_with_enough_overlap(self):
        """CJK characters are valid Unicode word chars and are extracted by the regex."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["\u6d4b\u8bd5\u4e3b\u9898\u5185\u5bb9", "\u5176\u4ed6\u5185\u5bb9\u6587\u672c"]}]
        matches = dedup_check.check_topic("\u6d4b\u8bd5\u4e3b\u9898\u5185\u5bb9 \u5176\u4ed6\u5185\u5bb9\u6587\u672c \u65b0\u7684\u4fe1\u606f\u5185\u5bb9", index)
        assert len(matches) >= 1

    def test_single_cjk_word_no_match_due_to_threshold(self):
        """One CJK keyword overlap doesn't meet the >= 2 overlap threshold."""
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["\u6d4b\u8bd5\u4e3b\u9898\u5185\u5bb9"]}]
        matches = dedup_check.check_topic("\u6d4b\u8bd5\u4e3b\u9898\u5185\u5bb9 \u5176\u4ed6\u5185\u5bb9\u6587\u672c", index)
        assert len(matches) == 0

    def test_mixed_latin_cyrillic(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["python", "\u043e\u0431\u0437\u043e\u0440"]}]
        matches = dedup_check.check_topic("python \u043e\u0431\u0437\u043e\u0440 guide", index)
        assert len(matches) >= 1


class TestCheckTopicStopwords:
    def test_agent_is_stopword(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["agent", "platform"]}]
        # 'agent' is a stopword, 'agents' too
        matches = dedup_check.check_topic("agent agents platform system", index)
        # only 'platform' overlaps (1 word) -> no match (need >= 2)
        assert len(matches) == 0

    def test_agents_is_stopword(self):
        index = [{"msgId": 1, "topic": "t", "links": [], "keywords": ["agents", "framework"]}]
        matches = dedup_check.check_topic("agents framework testing", index)
        # 'agents' stopped, only 'framework' overlaps
        # But wait - 'framework' is in topic_words and post_words
        # topic_words after stop: {framework, testing}
        # post_words after stop: {framework}
        # overlap=1, score=1.0 but overlap < 2
        assert len(matches) == 0
