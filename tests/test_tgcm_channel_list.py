import json
import os

from conftest import tgcm


class TestChannelList:
    def test_empty_list(self, tmp_path, capsys):
        tgcm.channel_list(str(tmp_path))
        assert "No channels found" in capsys.readouterr().out

    def test_no_tgcm_dir(self, tmp_path, capsys):
        tgcm.channel_list(str(tmp_path))
        assert "No channels found" in capsys.readouterr().out

    def test_single_channel(self, tmp_path, capsys):
        tgcm.channel_init(str(tmp_path), "alpha")
        tgcm.channel_list(str(tmp_path))
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "status=initialized" in out

    def test_multiple_channels_sorted(self, tmp_path, capsys):
        tgcm.channel_init(str(tmp_path), "beta")
        tgcm.channel_init(str(tmp_path), "alpha")
        capsys.readouterr()  # clear init output
        tgcm.channel_list(str(tmp_path))
        out = capsys.readouterr().out
        lines = [l for l in out.strip().split("\n") if l.strip()]
        assert lines[0].startswith("alpha")
        assert lines[1].startswith("beta")

    def test_connected_channel_shows_id(self, tmp_path, capsys):
        tgcm.channel_init(str(tmp_path), "testchan")
        tgcm.channel_bind(str(tmp_path), "testchan", "-100123")
        tgcm.channel_list(str(tmp_path))
        out = capsys.readouterr().out
        assert "-100123" in out
        assert "status=connected" in out

    def test_returns_zero(self, tmp_path):
        assert tgcm.channel_list(str(tmp_path)) == 0
