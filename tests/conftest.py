import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "dedup-check.py"
TGCM_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "tgcm.py"

spec = importlib.util.spec_from_file_location("dedup_check", SCRIPT_PATH)
dedup_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dedup_check)

tgcm_spec = importlib.util.spec_from_file_location("tgcm", TGCM_SCRIPT_PATH)
tgcm = importlib.util.module_from_spec(tgcm_spec)
tgcm_spec.loader.exec_module(tgcm)

VALIDATE_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "validate-queue.py"
vq_spec = importlib.util.spec_from_file_location("validate_queue", VALIDATE_SCRIPT_PATH)
validate_queue = importlib.util.module_from_spec(vq_spec)
vq_spec.loader.exec_module(validate_queue)


@pytest.fixture()
def sample_index():
    return [
        {
            "msgId": 101,
            "topic": "Python asyncio tutorial for beginners",
            "links": ["https://example.com/asyncio-guide"],
            "keywords": ["python", "asyncio", "tutorial", "beginners"],
        },
        {
            "msgId": 202,
            "topic": "Kubernetes deployment strategies overview",
            "links": [
                "https://example.com/k8s-deploy",
                "https://blog.example.com/kubernetes",
            ],
            "keywords": ["kubernetes", "deployment", "strategies", "overview"],
        },
    ]


@pytest.fixture()
def populated_index_file(tmp_path, sample_index):
    index_file = tmp_path / "content-index.json"
    index_file.write_text(json.dumps(sample_index, ensure_ascii=False, indent=2))
    return index_file


def run_cli(*args, base_dir=None):
    cmd = [sys.executable, str(SCRIPT_PATH)]
    if base_dir is not None:
        cmd += ["--base-dir", str(base_dir)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def run_tgcm_cli(*args, workspace=None, dm_chat_id=None):
    cmd = [sys.executable, str(TGCM_SCRIPT_PATH)]
    if workspace is not None:
        cmd += ["--workspace", str(workspace)]
    if dm_chat_id is not None:
        cmd += ["--dm-chat-id", str(dm_chat_id)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


@pytest.fixture()
def tgcm_workspace(tmp_path):
    """Initialized workspace with one bound channel 'test-chan'."""
    ws = tmp_path
    tgcm.channel_init(str(ws), "test-chan")
    tgcm.channel_bind(str(ws), "test-chan", "-100999")
    return ws
