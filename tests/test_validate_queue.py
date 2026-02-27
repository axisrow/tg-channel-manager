"""Tests for validate-queue.py"""

import json
import subprocess
import sys

import pytest

from conftest import validate_queue, VALIDATE_SCRIPT_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_3_POSTS = """\
### 1
- **Status:** draft
- **Rubric:** 👗 Гардероб
- **Topic:** ChatGPT как стилист: капсульный гардероб
- **Source:** https://example.com/article1
- **Text:**

Текст первого поста.

### 2
- **Status:** pending
- **Rubric:** 🏠 Дом
- **Topic:** ИИ для интерьера: идеи и варианты
- **Source:** https://example.com/article2
- **Image:** https://example.com/img.jpg
- **Text:**

Текст второго поста.

### 3
- **Status:** draft
- **Rubric:** 💰 Финансы
- **Topic:** Как ИИ помогает с бюджетом
- **Source:** https://example.com/article3
- **Text:**

Текст третьего поста.
"""

SUBHEADING_POST = """\
### 1
- **Status:** draft
- **Rubric:** 👗 Гардероб
- **Topic:** ChatGPT как стилист
- **Source:** https://example.com/article
- **Text:**

Вступление.

### Почему ИИ справляется с гардеробом лучше

Объяснение.

### Как это сделать за 10 минут

Шаги.
"""


def run_validate_cli(*args, base_dir=None):
    cmd = [sys.executable, str(VALIDATE_SCRIPT_PATH)]
    if base_dir is not None:
        cmd += ["--base-dir", str(base_dir)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseValidQueue:
    def test_parse_3_posts(self, tmp_path):
        queue = tmp_path / "content-queue.md"
        queue.write_text(VALID_3_POSTS)
        index = tmp_path / "content-index.json"
        index.write_text(json.dumps({"version": 1, "posts": []}))

        posts = validate_queue.parse_queue(VALID_3_POSTS)
        assert len(posts) == 3
        assert posts[0].number == 1
        assert posts[1].number == 2
        assert posts[2].number == 3
        assert posts[0].fields['Status'] == 'draft'
        assert posts[1].fields['Status'] == 'pending'
        assert posts[0].fields['Rubric'].startswith('\U0001f457')

        errors, warnings = validate_queue.validate_format(posts)
        assert len(errors) == 0


class TestSubheadingsNotSplit:
    def test_subheadings_inside_text(self):
        posts = validate_queue.parse_queue(SUBHEADING_POST)
        assert len(posts) == 1
        assert posts[0].number == 1
        assert '### Почему' in posts[0].text
        assert '### Как это' in posts[0].text


class TestMissingRequiredFields:
    def test_missing_status_topic_source(self):
        content = """\
### 1
- **Rubric:** 👗 Мода
- **Text:**

Текст поста.
"""
        posts = validate_queue.parse_queue(content)
        errors, _ = validate_queue.validate_format(posts)
        messages = [e[3] for e in errors]
        assert any('Status' in m for m in messages)
        assert any('Topic' in m for m in messages)
        assert any('Source' in m for m in messages)


class TestInvalidStatusValue:
    def test_unknown_status(self):
        content = """\
### 1
- **Status:** готово
- **Rubric:** 👗 Мода
- **Topic:** Тест
- **Source:** https://example.com
- **Text:**

Текст.
"""
        posts = validate_queue.parse_queue(content)
        errors, _ = validate_queue.validate_format(posts)
        assert any('invalid Status' in e[3] for e in errors)


class TestInvalidUrl:
    def test_bad_source_url(self):
        content = """\
### 1
- **Status:** draft
- **Rubric:** 👗 Мода
- **Topic:** Тест
- **Source:** not-a-url
- **Text:**

Текст.
"""
        posts = validate_queue.parse_queue(content)
        errors, _ = validate_queue.validate_format(posts)
        assert any('invalid Source URL' in e[3] for e in errors)


class TestStatusMismatchFoundInIndex:
    def test_draft_but_in_index(self):
        content = """\
### 1
- **Status:** draft
- **Rubric:** 👗 Мода
- **Topic:** Python asyncio tutorial for beginners
- **Source:** https://example.com/asyncio-guide
- **Text:**

Текст.
"""
        index = [
            {
                "msgId": 101,
                "topic": "Python asyncio tutorial for beginners",
                "links": ["https://example.com/asyncio-guide"],
                "keywords": ["python", "asyncio", "tutorial", "beginners"],
            }
        ]
        posts = validate_queue.parse_queue(content)
        warnings, fixes, index_adds = validate_queue.check_statuses(posts, index)
        assert len(warnings) == 1
        assert 'found in index' in warnings[0][3]
        assert len(fixes) == 1
        assert len(index_adds) == 0


class TestPublishedNotInIndexSync:
    def test_published_not_in_index_adds_to_index(self, tmp_path):
        content = """\
### 1
- **Status:** published
- **Rubric:** 👗 Гардероб
- **Topic:** ChatGPT как стилист: капсульный гардероб
- **Source:** https://example.com/article1
- **Text:**

Текст поста.
"""
        queue = tmp_path / "content-queue.md"
        queue.write_text(content)
        index_file = tmp_path / "content-index.json"
        index_file.write_text(json.dumps({"version": 1, "posts": []}))

        result = run_validate_cli("--base-dir", str(tmp_path))
        assert result.returncode == 0

        # Index should now contain the synced post
        data = json.loads(index_file.read_text())
        assert 'posts' in data
        assert len(data['posts']) == 1
        entry = data['posts'][0]
        assert entry['msgId'] == 0
        assert entry['topic'] == 'ChatGPT как стилист: капсульный гардероб'
        assert entry['links'] == ['https://example.com/article1']
        assert len(entry['keywords']) > 0

        # No warning emoji in output for this post
        assert '\u26a0\ufe0f' not in result.stdout or 'published but post not found' not in result.stdout

        # Summary mentions sync
        assert 'synced 1 post(s) to index' in result.stdout

    def test_published_sync_unit(self):
        """Unit test: check_statuses returns index_adds, no warnings."""
        content = """\
### 1
- **Status:** published
- **Rubric:** 👗 Гардероб
- **Topic:** ChatGPT как стилист: капсульный гардероб
- **Source:** https://example.com/article1
- **Text:**

Текст поста.
"""
        posts = validate_queue.parse_queue(content)
        warnings, fixes, index_adds = validate_queue.check_statuses(posts, [])
        assert len(warnings) == 0
        assert len(fixes) == 0
        assert len(index_adds) == 1
        assert index_adds[0]['msgId'] == 0
        assert index_adds[0]['topic'] == 'ChatGPT как стилист: капсульный гардероб'
        assert index_adds[0]['links'] == ['https://example.com/article1']


class TestFixUpdatesStatus:
    def test_fix_changes_draft_to_published(self, tmp_path):
        content = """\
### 1
- **Status:** draft
- **Rubric:** 👗 Мода
- **Topic:** Python asyncio tutorial for beginners
- **Source:** https://example.com/asyncio-guide
- **Text:**

Текст.
"""
        queue = tmp_path / "content-queue.md"
        queue.write_text(content)
        index_file = tmp_path / "content-index.json"
        index_file.write_text(json.dumps({"version": 1, "posts": [
            {
                "msgId": 101,
                "topic": "Python asyncio tutorial for beginners",
                "links": ["https://example.com/asyncio-guide"],
                "keywords": ["python", "asyncio", "tutorial", "beginners"],
            }
        ]}))

        result = run_validate_cli("--base-dir", str(tmp_path), "--fix")
        updated = queue.read_text()
        assert '**Status:** published' in updated
        assert '**Status:** draft' not in updated


class TestCliExitCodes:
    def test_exit_0_no_errors(self, tmp_path):
        queue = tmp_path / "content-queue.md"
        queue.write_text(VALID_3_POSTS)
        index = tmp_path / "content-index.json"
        index.write_text(json.dumps({"version": 1, "posts": []}))

        result = run_validate_cli("--base-dir", str(tmp_path))
        assert result.returncode == 0

    def test_exit_1_with_errors(self, tmp_path):
        content = """\
### 1
- **Rubric:** Без эмодзи
- **Text:**

Текст.
"""
        queue = tmp_path / "content-queue.md"
        queue.write_text(content)
        index = tmp_path / "content-index.json"
        index.write_text(json.dumps({"version": 1, "posts": []}))

        result = run_validate_cli("--base-dir", str(tmp_path))
        assert result.returncode == 1
