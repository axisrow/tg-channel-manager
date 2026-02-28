import json
import os
from unittest.mock import patch

import pytest

from conftest import tgcm


class TestResolveBotToken:
    """resolve_bot_token priority: CLI → .env → env → openclaw.json → .config.json."""

    def test_cli_arg_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-tok")
        result = tgcm.resolve_bot_token("cli-tok", str(tmp_path))
        assert result == "cli-tok"

    def test_dotenv_second(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=dotenv-tok\n")
        result = tgcm.resolve_bot_token(None, str(tmp_path))
        assert result == "dotenv-tok"

    def test_env_var_third(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-tok")
        result = tgcm.resolve_bot_token(None, str(tmp_path))
        assert result == "env-tok"

    def test_openclaw_json_fourth(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        oc = tmp_path / "openclaw.json"
        oc.write_text(json.dumps({"channels": {"telegram": {"botToken": "oc-tok"}}}))
        monkeypatch.chdir(tmp_path)
        result = tgcm.resolve_bot_token(None, str(tmp_path))
        assert result == "oc-tok"

    def test_local_config_fifth(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        tgcm_root = tmp_path / "tgcm"
        tgcm_root.mkdir()
        cfg = tgcm_root / ".config.json"
        cfg.write_text(json.dumps({"botToken": "local-tok"}))
        with patch.object(tgcm, "find_openclaw_config", return_value=None):
            result = tgcm.resolve_bot_token(None, str(tmp_path))
        assert result == "local-tok"

    def test_returns_none_when_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        with patch.object(tgcm, "find_openclaw_config", return_value=None):
            result = tgcm.resolve_bot_token(None, str(tmp_path))
        assert result is None


class TestResolveTokenSource:
    """resolve_token_source returns (token, source_label) or (None, None)."""

    def test_cli_arg_label(self, tmp_path):
        tok, src = tgcm.resolve_token_source("my-tok", str(tmp_path))
        assert tok == "my-tok"
        assert src == "--bot-token arg"

    def test_dotenv_label(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=dotenv-tok\n")
        tok, src = tgcm.resolve_token_source(None, str(tmp_path))
        assert tok == "dotenv-tok"
        assert src == ".env"

    def test_env_label(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-tok")
        tok, src = tgcm.resolve_token_source(None, str(tmp_path))
        assert tok == "env-tok"
        assert src == "TELEGRAM_BOT_TOKEN env"

    def test_none_none_when_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        with patch.object(tgcm, "find_openclaw_config", return_value=None):
            tok, src = tgcm.resolve_token_source(None, str(tmp_path))
        assert tok is None
        assert src is None


class TestLoadDotenvFile:
    """Unit tests for load_dotenv_file parser."""

    def test_parses_key_value(self, tmp_path):
        (tmp_path / ".env").write_text("FOO=bar\nBAZ=qux\n")
        result = tgcm.load_dotenv_file(str(tmp_path))
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_ignores_comments_and_blanks(self, tmp_path):
        (tmp_path / ".env").write_text("# comment\n\nKEY=val\n")
        result = tgcm.load_dotenv_file(str(tmp_path))
        assert result == {"KEY": "val"}

    def test_strips_quotes(self, tmp_path):
        (tmp_path / ".env").write_text('A="double"\nB=\'single\'\n')
        result = tgcm.load_dotenv_file(str(tmp_path))
        assert result == {"A": "double", "B": "single"}

    def test_returns_empty_on_missing_file(self, tmp_path):
        result = tgcm.load_dotenv_file(str(tmp_path))
        assert result == {}
