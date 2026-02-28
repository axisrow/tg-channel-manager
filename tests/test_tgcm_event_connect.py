import json

from conftest import tgcm


class TestEventConnect:
    def test_outputs_new_channel_json(self, tmp_path, capsys):
        result = tgcm.event_connect(str(tmp_path), "-100123")
        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "new_channel"
        assert out["channelId"] == "-100123"
        assert "-100123" in out["instructions"]

    def test_includes_channel_title(self, tmp_path, capsys):
        tgcm.event_connect(
            str(tmp_path), "-100123", channel_title="My Channel",
        )
        out = json.loads(capsys.readouterr().out)
        assert "My Channel" in out["instructions"]

    def test_already_connected(self, tmp_path, capsys):
        tgcm.channel_init(str(tmp_path), "testchan")
        tgcm.channel_bind(str(tmp_path), "testchan", "-100123")
        capsys.readouterr()  # clear

        result = tgcm.event_connect(str(tmp_path), "-100123")
        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "already_connected"
        assert out["channel"] == "testchan"

    def test_no_tgcm_dir_still_works(self, tmp_path, capsys):
        result = tgcm.event_connect(str(tmp_path), "-100999")
        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "new_channel"
