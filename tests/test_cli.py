import json
import re
import sys

import pytest

from conftest import SCRIPT_PATH, run_cli


class TestCliRebuild:
    def test_exit_code_zero(self, tmp_path):
        r = run_cli("--rebuild", base_dir=str(tmp_path))
        assert r.returncode == 0

    def test_prints_instructions(self, tmp_path):
        r = run_cli("--rebuild", base_dir=str(tmp_path))
        assert "rebuild" in r.stdout.lower() or "index" in r.stdout.lower()

    def test_includes_channel_id(self, tmp_path):
        r = run_cli("--rebuild", "--channel-id", "-100123", base_dir=str(tmp_path))
        assert "-100123" in r.stdout

    def test_default_channel_id_placeholder(self, tmp_path):
        r = run_cli("--rebuild", base_dir=str(tmp_path))
        assert "<channelId>" in r.stdout


class TestCliAdd:
    def test_exit_code_zero(self, tmp_path):
        r = run_cli("--add", "123", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert r.returncode == 0

    def test_creates_index_file(self, tmp_path):
        run_cli("--add", "123", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert (tmp_path / "content-index.json").exists()

    def test_success_message(self, tmp_path):
        r = run_cli("--add", "123", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert "123" in r.stdout
        assert "added" in r.stdout.lower()

    def test_duplicate_warning(self, tmp_path):
        run_cli("--add", "123", "--topic", "Test topic here", base_dir=str(tmp_path))
        r = run_cli("--add", "123", "--topic", "Another topic here", base_dir=str(tmp_path))
        assert "already" in r.stdout.lower()

    def test_with_links(self, tmp_path):
        run_cli("--add", "123", "--topic", "Test topic here",
                "--links", "https://example.com", base_dir=str(tmp_path))
        data = json.loads((tmp_path / "content-index.json").read_text())
        assert data[0]["links"] == ["https://example.com"]

    def test_msgid_zero(self, tmp_path):
        """--add 0 should correctly add a post with msgId=0."""
        r = run_cli("--add", "0", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert r.returncode == 0
        assert "added" in r.stdout.lower()
        index_file = tmp_path / "content-index.json"
        assert index_file.exists()
        data = json.loads(index_file.read_text())
        assert any(p["msgId"] == 0 for p in data)


class TestCliCheck:
    def test_no_args_exit_1(self, tmp_path):
        r = run_cli(base_dir=str(tmp_path))
        assert r.returncode == 1

    def test_no_topic_no_links_exit_1(self, tmp_path):
        r = run_cli(base_dir=str(tmp_path))
        assert "provide" in r.stdout.lower() or r.returncode == 1

    def test_topic_only_exit_0(self, tmp_path):
        r = run_cli("--topic", "some test topic here", base_dir=str(tmp_path))
        assert r.returncode == 0

    def test_links_only_exit_0(self, tmp_path):
        r = run_cli("--links", "https://example.com", base_dir=str(tmp_path))
        assert r.returncode == 0

    def test_no_duplicates_message(self, tmp_path):
        r = run_cli("--topic", "unique topic words here", base_dir=str(tmp_path))
        assert "no duplicates" in r.stdout.lower()

    def test_duplicates_found_message(self, tmp_path):
        # Create index with a known entry
        run_cli("--add", "1", "--topic", "python asyncio tutorial beginners", base_dir=str(tmp_path))
        r = run_cli("--topic", "python asyncio tutorial guide", base_dir=str(tmp_path))
        assert "duplicates found" in r.stdout.lower() or "possible" in r.stdout.lower()

    def test_link_duplicate_found(self, tmp_path):
        run_cli("--add", "1", "--topic", "test topic here",
                "--links", "https://example.com/article", base_dir=str(tmp_path))
        r = run_cli("--links", "https://example.com/article", base_dir=str(tmp_path))
        assert "duplicates found" in r.stdout.lower() or "link" in r.stdout.lower()

    def test_check_exit_0_even_with_matches(self, tmp_path):
        """Check mode always exits 0, even when duplicates are found."""
        run_cli("--add", "1", "--topic", "python asyncio tutorial beginners", base_dir=str(tmp_path))
        r = run_cli("--topic", "python asyncio tutorial guide", base_dir=str(tmp_path))
        assert r.returncode == 0


class TestCliPerfLog:
    def test_perf_log_created(self, tmp_path):
        run_cli("--topic", "some test topic here", base_dir=str(tmp_path))
        assert (tmp_path / "content-perf.log").exists()

    def test_perf_log_contains_ms(self, tmp_path):
        run_cli("--topic", "some test topic here", base_dir=str(tmp_path))
        content = (tmp_path / "content-perf.log").read_text()
        assert re.search(r"\d+ms", content)

    def test_perf_log_not_created_for_add(self, tmp_path):
        run_cli("--add", "1", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert not (tmp_path / "content-perf.log").exists()

    def test_perf_log_not_created_for_rebuild(self, tmp_path):
        run_cli("--rebuild", base_dir=str(tmp_path))
        assert not (tmp_path / "content-perf.log").exists()


class TestCliBaseDir:
    def test_explicit_base_dir(self, tmp_path):
        run_cli("--add", "1", "--topic", "Test topic here", base_dir=str(tmp_path))
        assert (tmp_path / "content-index.json").exists()

    def test_relative_base_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = run_cli("--add", "1", "--topic", "Test topic here", base_dir=".")
        assert r.returncode == 0
        assert (tmp_path / "content-index.json").exists()
