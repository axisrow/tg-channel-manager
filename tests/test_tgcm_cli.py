import json

from conftest import run_tgcm_cli


class TestCliInit:
    def test_exit_code_zero(self, tmp_path):
        r = run_tgcm_cli("init", "testchan", workspace=str(tmp_path))
        assert r.returncode == 0

    def test_creates_files(self, tmp_path):
        run_tgcm_cli("init", "testchan", workspace=str(tmp_path))
        assert (tmp_path / "tgcm" / "testchan" / "channel.json").exists()
        assert (tmp_path / "tgcm" / "testchan" / "content-index.json").exists()

    def test_invalid_name_exit_1(self, tmp_path):
        r = run_tgcm_cli("init", "INVALID", workspace=str(tmp_path))
        assert r.returncode == 1

    def test_duplicate_exit_1(self, tmp_path):
        run_tgcm_cli("init", "testchan", workspace=str(tmp_path))
        r = run_tgcm_cli("init", "testchan", workspace=str(tmp_path))
        assert r.returncode == 1


class TestCliList:
    def test_empty_list(self, tmp_path):
        r = run_tgcm_cli("list", workspace=str(tmp_path))
        assert r.returncode == 0
        assert "No channels found" in r.stdout

    def test_shows_channel(self, tmp_path):
        run_tgcm_cli("init", "alpha", workspace=str(tmp_path))
        r = run_tgcm_cli("list", workspace=str(tmp_path))
        assert "alpha" in r.stdout


class TestCliBind:
    def test_bind_success(self, tmp_path):
        run_tgcm_cli("init", "testchan", workspace=str(tmp_path))
        r = run_tgcm_cli(
            "bind", "testchan", "--channel-id", "-100999",
            workspace=str(tmp_path),
        )
        assert r.returncode == 0

    def test_bind_nonexistent_exit_1(self, tmp_path):
        r = run_tgcm_cli(
            "bind", "nosuch", "--channel-id", "-100999",
            workspace=str(tmp_path),
        )
        assert r.returncode == 1


class TestCliConnect:
    def test_outputs_json(self, tmp_path):
        r = run_tgcm_cli(
            "connect", "--channel-id", "-100123",
            workspace=str(tmp_path),
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["status"] == "new_channel"


class TestCliGetId:
    def test_missing_bot_token_exit_1(self, tmp_path):
        r = run_tgcm_cli("get-id", "@testchannel", workspace=str(tmp_path))
        assert r.returncode == 1
        assert "bot token" in r.stderr.lower()

    def test_parser_accepts_username(self):
        from conftest import tgcm
        parser = tgcm.build_parser()
        args = parser.parse_args(["--bot-token", "fake", "get-id", "@mychan"])
        assert args.command == "get-id"
        assert args.identifier == "@mychan"
        assert args.bot_token == "fake"

    def test_parser_accepts_numeric_id(self):
        from conftest import tgcm
        parser = tgcm.build_parser()
        args = parser.parse_args(["--bot-token", "fake", "get-id", "-100123456"])
        assert args.command == "get-id"
        assert args.identifier == "-100123456"


class TestCliNoArgs:
    def test_no_args_exit_1(self, tmp_path):
        r = run_tgcm_cli(workspace=str(tmp_path))
        assert r.returncode == 1
