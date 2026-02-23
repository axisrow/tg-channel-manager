import json
import os

import pytest

from conftest import tgcm


class TestChannelInit:
    def test_creates_directory(self, tmp_path):
        assert tgcm.channel_init(str(tmp_path), "testchan") == 0
        assert os.path.isdir(tmp_path / "tgcm" / "testchan")

    def test_creates_content_index(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        index_file = tmp_path / "tgcm" / "testchan" / "content-index.json"
        assert index_file.exists()
        data = json.loads(index_file.read_text())
        assert data == {"version": 1, "posts": []}

    def test_creates_content_queue(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        queue_file = tmp_path / "tgcm" / "testchan" / "content-queue.md"
        assert queue_file.exists()
        assert queue_file.read_text() == ""

    def test_creates_channel_json(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        meta_file = tmp_path / "tgcm" / "testchan" / "channel.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert meta["name"] == "testchan"
        assert meta["channelId"] is None
        assert meta["status"] == "initialized"
        assert "createdAt" in meta

    def test_duplicate_name_fails(self, tmp_path):
        tgcm.channel_init(str(tmp_path), "testchan")
        assert tgcm.channel_init(str(tmp_path), "testchan") == 1


class TestValidateChannelName:
    @pytest.mark.parametrize("name", [
        "mychan", "test-chan", "chan_1", "a", "a" * 63, "0start",
    ])
    def test_valid_names(self, name):
        assert tgcm.validate_channel_name(name) is None

    @pytest.mark.parametrize("name", [
        "", "-start", "_start", "UPPER", "has space", "a" * 64,
        "special!", "my.chan",
    ])
    def test_invalid_names(self, name):
        assert tgcm.validate_channel_name(name) is not None

    def test_invalid_name_blocks_init(self, tmp_path):
        assert tgcm.channel_init(str(tmp_path), "INVALID") == 1
        assert not os.path.isdir(tmp_path / "tgcm" / "INVALID")
