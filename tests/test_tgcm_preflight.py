import json
from unittest.mock import patch

import pytest

from conftest import tgcm


def _mock_api_ok(method_results):
    """Return a side_effect function for tg_api_call that maps method→result."""
    def side_effect(token, method, params=None):
        return method_results.get(method)
    return side_effect


class TestPreflightNoToken:
    def test_fail_when_no_token(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        with patch.object(tgcm, "find_openclaw_config", return_value=None):
            rc = tgcm.preflight_check(str(tmp_path), None)
        assert rc == 1
        out = capsys.readouterr().out
        assert "[fail] Bot token" in out


class TestPreflightGetMeFails:
    def test_fail_when_getme_fails(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("BOT_TOKEN", "bad-token")
        with patch.object(tgcm, "tg_api_call", return_value=None):
            rc = tgcm.preflight_check(str(tmp_path), None)
        assert rc == 1
        out = capsys.readouterr().out
        assert "[fail] Bot: getMe failed" in out


class TestPreflightSearxng:
    def test_warn_when_no_searxng(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        tgcm.preflight_check(str(tmp_path), None)
        out = capsys.readouterr().out
        assert "[warn] SEARXNG_URL" in out

    def test_ok_when_searxng_set(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        tgcm.preflight_check(str(tmp_path), None)
        out = capsys.readouterr().out
        assert "[ok]   SEARXNG_URL" in out


class TestPreflightChannelNotBound:
    def test_warn_unbound_channel(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        monkeypatch.chdir(tmp_path)
        tgcm.channel_init(str(tmp_path), "mychan")
        tgcm.preflight_check(str(tmp_path), None)
        out = capsys.readouterr().out
        assert '[warn] Channel "mychan": not bound' in out


class TestPreflightBotNotAdmin:
    def test_fail_bot_not_admin(self, tgcm_workspace, monkeypatch, capsys):
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        api = _mock_api_ok({
            "getMe": {"id": 1, "username": "testbot", "is_bot": True},
            "getChat": {"type": "channel", "title": "T"},
            "getChatMember": {"status": "member"},
        })
        with patch.object(tgcm, "tg_api_call", side_effect=api):
            rc = tgcm.preflight_check(str(tgcm_workspace), "fake-tok")
        assert rc == 1
        out = capsys.readouterr().out
        assert "not admin" in out


class TestPreflightBotIsAdmin:
    def test_ok_bot_admin(self, tgcm_workspace, monkeypatch, capsys):
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        api = _mock_api_ok({
            "getMe": {"id": 1, "username": "testbot", "is_bot": True},
            "getChat": {"type": "channel", "title": "T"},
            "getChatMember": {"status": "administrator"},
        })
        with patch.object(tgcm, "tg_api_call", side_effect=api):
            rc = tgcm.preflight_check(str(tgcm_workspace), "fake-tok")
        assert rc == 0
        out = capsys.readouterr().out
        assert "[ok]" in out
        assert "bot is administrator" in out


class TestPreflightWrongChatType:
    def test_fail_not_channel(self, tgcm_workspace, monkeypatch, capsys):
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        api = _mock_api_ok({
            "getMe": {"id": 1, "username": "testbot", "is_bot": True},
            "getChat": {"type": "group", "title": "T"},
            "getChatMember": {"status": "administrator"},
        })
        with patch.object(tgcm, "tg_api_call", side_effect=api):
            rc = tgcm.preflight_check(str(tgcm_workspace), "fake-tok")
        assert rc == 1
        out = capsys.readouterr().out
        assert "type=group" in out
