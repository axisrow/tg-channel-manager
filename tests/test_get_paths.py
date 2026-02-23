import os
from conftest import dedup_check


class TestGetPaths:
    def test_returns_dict_with_expected_keys(self):
        result = dedup_check.get_paths("/tmp")
        assert set(result.keys()) == {"index", "perf_log"}

    def test_index_filename(self):
        result = dedup_check.get_paths("/tmp")
        assert os.path.basename(result["index"]) == "content-index.json"

    def test_perf_log_filename(self):
        result = dedup_check.get_paths("/tmp")
        assert os.path.basename(result["perf_log"]) == "content-perf.log"

    def test_paths_are_absolute(self):
        result = dedup_check.get_paths(".")
        assert os.path.isabs(result["index"])
        assert os.path.isabs(result["perf_log"])

    def test_uses_base_dir(self, tmp_path):
        result = dedup_check.get_paths(str(tmp_path))
        assert result["index"] == os.path.join(str(tmp_path), "content-index.json")
        assert result["perf_log"] == os.path.join(str(tmp_path), "content-perf.log")
