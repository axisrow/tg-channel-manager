import json

import pytest

from conftest import dedup_check


class TestAddPostBasic:
    def test_creates_index_file(self, tmp_path):
        f = tmp_path / "content-index.json"
        result = dedup_check.add_post(str(f), 1, "Test topic here", ["https://example.com"])
        assert result is True
        assert f.exists()

    def test_returns_true_on_success(self, tmp_path):
        f = tmp_path / "content-index.json"
        assert dedup_check.add_post(str(f), 1, "Test topic here") is True

    def test_returns_false_on_duplicate_msgid(self, populated_index_file):
        result = dedup_check.add_post(str(populated_index_file), 101, "Different topic")
        assert result is False

    def test_duplicate_does_not_modify_index(self, populated_index_file):
        before = json.loads(populated_index_file.read_text())
        dedup_check.add_post(str(populated_index_file), 101, "Different topic")
        after = json.loads(populated_index_file.read_text())
        assert before == after

    def test_appends_to_existing_index(self, populated_index_file):
        dedup_check.add_post(str(populated_index_file), 303, "New topic here")
        data = dedup_check.load_index(str(populated_index_file))
        assert len(data) == 3


class TestAddPostFields:
    def test_stores_msgid(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 42, "Test topic here")
        data = json.loads(f.read_text())
        assert data[0]["msgId"] == 42

    def test_stores_topic(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "My great topic")
        data = json.loads(f.read_text())
        assert data[0]["topic"] == "My great topic"

    def test_stores_links(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Test topic here", links=["https://a.com", "https://b.com"])
        data = json.loads(f.read_text())
        assert data[0]["links"] == ["https://a.com", "https://b.com"]

    def test_none_links_stored_as_empty_list(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Test topic here", links=None)
        data = json.loads(f.read_text())
        assert data[0]["links"] == []


class TestAddPostKeywords:
    def test_auto_extracts_keywords_when_none(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Python asyncio tutorial beginners")
        data = json.loads(f.read_text())
        kw = set(data[0]["keywords"])
        assert "python" in kw
        assert "asyncio" in kw
        assert "tutorial" in kw

    def test_auto_extracts_keywords_when_empty_list(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Python asyncio tutorial beginners", keywords=[])
        data = json.loads(f.read_text())
        assert len(data[0]["keywords"]) > 0

    def test_uses_provided_keywords(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Topic text here", keywords=["custom", "words"])
        data = json.loads(f.read_text())
        assert set(data[0]["keywords"]) == {"custom", "words"}

    def test_auto_keywords_skip_short_words(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "go is at python test")
        data = json.loads(f.read_text())
        kw = data[0]["keywords"]
        assert "go" not in kw
        assert "is" not in kw
        assert "python" in kw

    def test_auto_keywords_are_lowercase(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Python Asyncio Tutorial")
        data = json.loads(f.read_text())
        for kw in data[0]["keywords"]:
            assert kw == kw.lower()


class TestAddPostSorting:
    def test_sorted_by_msgid(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 300, "Third post here")
        dedup_check.add_post(str(f), 100, "First post here")
        dedup_check.add_post(str(f), 200, "Second post here")
        data = json.loads(f.read_text())
        ids = [p["msgId"] for p in data]
        assert ids == [100, 200, 300]

    def test_insert_between_existing(self, populated_index_file):
        # sample_index has 101, 202
        dedup_check.add_post(str(populated_index_file), 150, "Middle post here")
        data = json.loads(populated_index_file.read_text())
        ids = [p["msgId"] for p in data]
        assert ids == [101, 150, 202]


class TestAddPostPersistence:
    def test_roundtrip_through_disk(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "Test topic here", ["https://example.com"], ["test", "topic"])
        loaded = dedup_check.load_index(str(f))
        assert loaded[0]["msgId"] == 1
        assert loaded[0]["topic"] == "Test topic here"
        assert loaded[0]["links"] == ["https://example.com"]

    def test_unicode_topic_persisted(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "\u041e\u0431\u0437\u043e\u0440 Kubernetes \u043a\u043b\u0430\u0441\u0442\u0435\u0440\u043e\u0432")
        loaded = dedup_check.load_index(str(f))
        assert "\u041e\u0431\u0437\u043e\u0440" in loaded[0]["topic"]

    def test_unicode_keywords_persisted(self, tmp_path):
        f = tmp_path / "content-index.json"
        dedup_check.add_post(str(f), 1, "\u043f\u0438\u0442\u043e\u043d \u0430\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u043d\u043e\u0441\u0442\u044c \u043e\u0431\u0443\u0447\u0435\u043d\u0438\u0435")
        loaded = dedup_check.load_index(str(f))
        kw = loaded[0]["keywords"]
        assert any("\u043f\u0438\u0442\u043e\u043d" in w for w in kw) or any("\u0430\u0441\u0438\u043d" in w for w in kw)
