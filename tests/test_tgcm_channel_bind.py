import json

from conftest import tgcm


class TestChannelBind:
    def test_bind_success(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        assert tgcm.channel_bind(str(tmp_path), "testchan", "-100999") == 0

    def test_updates_channel_json(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        tgcm.channel_bind(str(tmp_path), "testchan", "-100999")
        meta = tgcm.load_channel_meta(tgcm.get_channel_dir(str(tmp_path), "testchan"))
        assert meta["channelId"] == "-100999"
        assert meta["status"] == "connected"

    def test_nonexistent_channel_fails(self, tmp_path):
        assert tgcm.channel_bind(str(tmp_path), "nosuch", "-100999") == 1

    def test_already_bound_fails(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        tgcm.channel_bind(str(tmp_path), "testchan", "-100999")
        assert tgcm.channel_bind(str(tmp_path), "testchan", "-100111") == 1

    def test_preserves_name_and_created(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        meta_before = tgcm.load_channel_meta(
            tgcm.get_channel_dir(str(tmp_path), "testchan")
        )
        tgcm.channel_bind(str(tmp_path), "testchan", "-100999")
        meta_after = tgcm.load_channel_meta(
            tgcm.get_channel_dir(str(tmp_path), "testchan")
        )
        assert meta_after["name"] == meta_before["name"]
        assert meta_after["createdAt"] == meta_before["createdAt"]
