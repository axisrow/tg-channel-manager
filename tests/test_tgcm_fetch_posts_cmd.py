import json
from unittest.mock import patch, MagicMock

import pytest

from conftest import tgcm


SAMPLE_HTML = """
<div data-post="testchan/1">
  <div class="tgme_widget_message_text">
    This is a sample post with enough text to pass the minimum length filter requirement
  </div>
  <time datetime="2025-01-01"></time>
</div>
<div data-post="testchan/2">
  <div class="tgme_widget_message_text">
    Another sample post with sufficient text content for the parser to accept it properly
  </div>
  <time datetime="2025-01-02"></time>
</div>
"""


class TestFetchPostsCmdChannelNotFound:
    def test_returns_1(self, tmp_path, capsys):
        rc = tgcm.fetch_posts_cmd(str(tmp_path), "nosuch", None, 5, False)
        assert rc == 1
        assert "not found" in capsys.readouterr().err


class TestFetchPostsCmdNotBound:
    def test_returns_1(self, tmp_path, capsys):
        tgcm.channel_init(str(tmp_path), "mychan")
        rc = tgcm.fetch_posts_cmd(str(tmp_path), "mychan", None, 5, False)
        assert rc == 1
        assert "not bound" in capsys.readouterr().err


class TestFetchPostsCmdNoToken:
    def test_returns_1(self, tgcm_workspace, monkeypatch, capsys):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.chdir(tgcm_workspace)
        with patch.object(tgcm, "find_openclaw_config", return_value=None):
            rc = tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", None, 5, False)
        assert rc == 1
        assert "bot token" in capsys.readouterr().err.lower()


class TestFetchPostsCmdPrivateChannel:
    def test_returns_1_no_username(self, tgcm_workspace, capsys):
        api_results = {
            "getChat": {"type": "channel", "title": "Private"},
        }
        def mock_api(token, method, params=None):
            return api_results.get(method)
        with patch.object(tgcm, "tg_api_call", side_effect=mock_api):
            rc = tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", "fake-tok", 5, False)
        assert rc == 1
        assert "no @username" in capsys.readouterr().err.lower()


class TestFetchPostsCmdDryRun:
    def test_dry_run_does_not_modify_index(self, tgcm_workspace, capsys):
        def mock_api(token, method, params=None):
            if method == "getChat":
                return {"type": "channel", "title": "T", "username": "testchan"}
            return None

        with patch.object(tgcm, "tg_api_call", side_effect=mock_api), \
             patch.object(tgcm, "fetch_tme_page", return_value=SAMPLE_HTML):
            rc = tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", "fake-tok", 1, True)

        assert rc == 0
        out = capsys.readouterr().out
        assert "Would add" in out

        index_path = tgcm_workspace / "tgcm" / "test-chan" / "content-index.json"
        data = json.loads(index_path.read_text())
        posts = data["posts"] if isinstance(data, dict) else data
        assert len(posts) == 0


class TestFetchPostsCmdAddsToIndex:
    def test_adds_new_posts(self, tgcm_workspace, capsys):
        def mock_api(token, method, params=None):
            if method == "getChat":
                return {"type": "channel", "title": "T", "username": "testchan"}
            return None

        with patch.object(tgcm, "tg_api_call", side_effect=mock_api), \
             patch.object(tgcm, "fetch_tme_page", return_value=SAMPLE_HTML):
            rc = tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", "fake-tok", 1, False)

        assert rc == 0
        out = capsys.readouterr().out
        assert "Added 2 new posts" in out

        index_path = tgcm_workspace / "tgcm" / "test-chan" / "content-index.json"
        data = json.loads(index_path.read_text())
        assert len(data["posts"]) == 2


class TestFetchPostsCmdSkipsDuplicates:
    def test_skips_existing_ids(self, tgcm_workspace, capsys):
        # Pre-populate index with msgId 1
        index_path = tgcm_workspace / "tgcm" / "test-chan" / "content-index.json"
        index_path.write_text(json.dumps({
            "version": 1,
            "posts": [{"msgId": 1, "topic": "old", "links": [], "keywords": ["old"]}]
        }))

        def mock_api(token, method, params=None):
            if method == "getChat":
                return {"type": "channel", "title": "T", "username": "testchan"}
            return None

        with patch.object(tgcm, "tg_api_call", side_effect=mock_api), \
             patch.object(tgcm, "fetch_tme_page", return_value=SAMPLE_HTML):
            rc = tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", "fake-tok", 1, False)

        assert rc == 0
        out = capsys.readouterr().out
        assert "Added 1 new posts" in out
        assert "1 already existed" in out


class TestFetchPostsCmdPagination:
    def test_stops_on_small_page(self, tgcm_workspace, capsys):
        call_count = [0]
        def mock_fetch(username, before=None):
            call_count[0] += 1
            return SAMPLE_HTML  # < MIN_PAGE_SIZE posts → stops after page 1

        def mock_api(token, method, params=None):
            if method == "getChat":
                return {"type": "channel", "title": "T", "username": "testchan"}
            return None

        with patch.object(tgcm, "tg_api_call", side_effect=mock_api), \
             patch.object(tgcm, "fetch_tme_page", side_effect=mock_fetch):
            tgcm.fetch_posts_cmd(str(tgcm_workspace), "test-chan", "fake-tok", 5, False)

        # Only 2 posts per page < MIN_PAGE_SIZE(10), should stop after 1 page
        assert call_count[0] == 1
