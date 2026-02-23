import pytest

from conftest import dedup_check


class TestCheckLinksEmptyCases:
    def test_empty_index(self):
        assert dedup_check.check_links(["https://example.com"], []) == []

    def test_empty_links(self, sample_index):
        assert dedup_check.check_links([], sample_index) == []

    def test_post_without_links_field(self):
        index = [{"msgId": 1, "topic": "test", "keywords": []}]
        assert dedup_check.check_links(["https://example.com"], index) == []

    def test_post_with_empty_links(self):
        index = [{"msgId": 1, "topic": "test", "links": [], "keywords": []}]
        assert dedup_check.check_links(["https://example.com"], index) == []


class TestCheckLinksNormalization:
    @pytest.mark.parametrize(
        "input_link, stored_link",
        [
            ("https://example.com/path", "https://example.com/path"),
            ("http://example.com/path", "https://example.com/path"),
            ("https://www.example.com/path", "https://example.com/path"),
            ("http://www.example.com/path", "https://example.com/path"),
            ("https://example.com/path/", "https://example.com/path"),
            ("http://www.example.com/path/", "https://example.com/path"),
        ],
        ids=["exact", "http_vs_https", "www_strip", "http_www", "trailing_slash", "all_combined"],
    )
    def test_url_normalization_matches(self, input_link, stored_link):
        index = [{"msgId": 1, "topic": "test", "links": [stored_link], "keywords": []}]
        matches = dedup_check.check_links([input_link], index)
        assert len(matches) == 1

    def test_different_paths_no_match(self):
        index = [{"msgId": 1, "topic": "test", "links": ["https://example.com/a"], "keywords": []}]
        matches = dedup_check.check_links(["https://example.com/b"], index)
        assert len(matches) == 0

    def test_different_domains_no_match(self):
        index = [{"msgId": 1, "topic": "test", "links": ["https://foo.com/path"], "keywords": []}]
        matches = dedup_check.check_links(["https://bar.com/path"], index)
        assert len(matches) == 0


class TestCheckLinksResults:
    def test_result_contains_msgid(self, sample_index):
        matches = dedup_check.check_links(["https://example.com/asyncio-guide"], sample_index)
        assert matches[0]["msgId"] == 101

    def test_result_contains_topic(self, sample_index):
        matches = dedup_check.check_links(["https://example.com/asyncio-guide"], sample_index)
        assert "topic" in matches[0]

    def test_result_link_is_from_index(self):
        """The link in result comes from the index, not from the query."""
        stored = "https://example.com/original"
        index = [{"msgId": 1, "topic": "test", "links": [stored], "keywords": []}]
        matches = dedup_check.check_links(["http://www.example.com/original/"], index)
        assert matches[0]["link"] == stored

    def test_topic_truncated_to_100(self):
        long_topic = "x" * 200
        index = [{"msgId": 1, "topic": long_topic, "links": ["https://example.com/a"], "keywords": []}]
        matches = dedup_check.check_links(["https://example.com/a"], index)
        assert len(matches[0]["topic"]) <= 100


class TestCheckLinksMultiple:
    def test_multiple_links_checked(self, sample_index):
        matches = dedup_check.check_links(
            ["https://example.com/asyncio-guide", "https://example.com/k8s-deploy"],
            sample_index,
        )
        assert len(matches) == 2

    def test_one_match_one_miss(self, sample_index):
        matches = dedup_check.check_links(
            ["https://example.com/asyncio-guide", "https://example.com/nonexistent"],
            sample_index,
        )
        assert len(matches) == 1
        assert matches[0]["msgId"] == 101

    def test_link_matches_second_post_link(self, sample_index):
        """Post 202 has two links, match on the second one."""
        matches = dedup_check.check_links(
            ["https://blog.example.com/kubernetes"],
            sample_index,
        )
        assert len(matches) == 1
        assert matches[0]["msgId"] == 202
