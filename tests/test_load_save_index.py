import json

from conftest import dedup_check


class TestLoadIndex:
    def test_missing_file_returns_empty_list(self, tmp_path):
        result = dedup_check.load_index(str(tmp_path / "nonexistent.json"))
        assert result == []

    def test_loads_valid_json(self, populated_index_file):
        result = dedup_check.load_index(str(populated_index_file))
        assert len(result) == 2
        assert result[0]["msgId"] == 101

    def test_preserves_unicode(self, tmp_path):
        data = [{"msgId": 1, "topic": "Kubernetes: \u043e\u0431\u0437\u043e\u0440", "links": [], "keywords": []}]
        f = tmp_path / "index.json"
        f.write_text(json.dumps(data, ensure_ascii=False))
        result = dedup_check.load_index(str(f))
        assert result[0]["topic"] == "Kubernetes: \u043e\u0431\u0437\u043e\u0440"

    def test_returns_list_type(self, populated_index_file):
        result = dedup_check.load_index(str(populated_index_file))
        assert isinstance(result, list)

    def test_preserves_all_fields(self, populated_index_file):
        result = dedup_check.load_index(str(populated_index_file))
        post = result[0]
        assert "msgId" in post
        assert "topic" in post
        assert "links" in post
        assert "keywords" in post

    def test_empty_array_file(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("[]")
        result = dedup_check.load_index(str(f))
        assert result == []


class TestSaveIndex:
    def test_creates_file(self, tmp_path):
        f = tmp_path / "out.json"
        dedup_check.save_index(str(f), [{"msgId": 1}])
        assert f.exists()

    def test_valid_json_output(self, tmp_path):
        f = tmp_path / "out.json"
        data = [{"msgId": 1, "topic": "test"}]
        dedup_check.save_index(str(f), data)
        loaded = json.loads(f.read_text())
        assert loaded == data

    def test_ensure_ascii_false(self, tmp_path):
        f = tmp_path / "out.json"
        data = [{"msgId": 1, "topic": "\u041f\u0440\u0438\u0432\u0435\u0442"}]
        dedup_check.save_index(str(f), data)
        raw = f.read_text()
        assert "\u041f\u0440\u0438\u0432\u0435\u0442" in raw
        assert "\\u" not in raw

    def test_indent_two(self, tmp_path):
        f = tmp_path / "out.json"
        dedup_check.save_index(str(f), [{"a": 1}])
        raw = f.read_text()
        assert "  " in raw

    def test_overwrites_existing_file(self, tmp_path):
        f = tmp_path / "out.json"
        dedup_check.save_index(str(f), [{"msgId": 1}])
        dedup_check.save_index(str(f), [{"msgId": 2}])
        loaded = json.loads(f.read_text())
        assert len(loaded) == 1
        assert loaded[0]["msgId"] == 2


class TestVersionedFormat:
    def test_load_versioned_returns_posts(self, tmp_path):
        f = tmp_path / "index.json"
        data = {"version": 1, "posts": [{"msgId": 1, "topic": "t", "links": [], "keywords": []}]}
        f.write_text(json.dumps(data))
        result = dedup_check.load_index(str(f))
        assert isinstance(result, list)
        assert result[0]["msgId"] == 1

    def test_load_versioned_empty_posts(self, tmp_path):
        f = tmp_path / "index.json"
        f.write_text(json.dumps({"version": 1, "posts": []}))
        result = dedup_check.load_index(str(f))
        assert result == []

    def test_save_preserves_version_wrapper(self, tmp_path):
        f = tmp_path / "index.json"
        f.write_text(json.dumps({"version": 1, "posts": []}))
        dedup_check.save_index(str(f), [{"msgId": 5, "topic": "new"}])
        raw = json.loads(f.read_text())
        assert raw["version"] == 1
        assert raw["posts"] == [{"msgId": 5, "topic": "new"}]

    def test_save_flat_stays_flat(self, tmp_path):
        f = tmp_path / "index.json"
        f.write_text(json.dumps([{"msgId": 1}]))
        dedup_check.save_index(str(f), [{"msgId": 2}])
        raw = json.loads(f.read_text())
        assert isinstance(raw, list)
        assert raw == [{"msgId": 2}]

    def test_save_new_file_is_flat(self, tmp_path):
        f = tmp_path / "new.json"
        dedup_check.save_index(str(f), [{"msgId": 1}])
        raw = json.loads(f.read_text())
        assert isinstance(raw, list)

    def test_roundtrip_versioned(self, tmp_path):
        f = tmp_path / "index.json"
        f.write_text(json.dumps({"version": 1, "posts": []}))
        posts = [{"msgId": 10, "topic": "test", "links": [], "keywords": ["test"]}]
        dedup_check.save_index(str(f), posts)
        loaded = dedup_check.load_index(str(f))
        assert loaded == posts


class TestRoundtrip:
    def test_save_then_load_identical(self, tmp_path, sample_index):
        f = tmp_path / "roundtrip.json"
        dedup_check.save_index(str(f), sample_index)
        loaded = dedup_check.load_index(str(f))
        assert loaded == sample_index
