import io
import json
import sys
from unittest.mock import patch

from conftest import run_tgcm_cli, tgcm


def _make_msg(message_id):
    return {"message_id": message_id, "chat": {"id": -100999}}


class TestPublishPostShortTextNoPhoto:
    def test_sends_message(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(1)) as mock:
            result = tgcm.publish_post("tok", "-100", "hello")
        assert result == [_make_msg(1)]
        mock.assert_called_once()
        call_args = mock.call_args
        assert call_args[0][1] == "sendMessage"
        assert call_args[1]["json_body"]["text"] == "hello"


class TestPublishPostShortTextWithPhoto:
    def test_sends_photo(self):
        text = "short caption"
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(2)) as mock:
            result = tgcm.publish_post("tok", "-100", text, photo_url="http://img.jpg")
        assert result == [_make_msg(2)]
        mock.assert_called_once()
        call_args = mock.call_args
        assert call_args[0][1] == "sendPhoto"
        assert call_args[1]["json_body"]["caption"] == text


class TestPublishPostLongTextWithPhotoSplits:
    def test_two_api_calls(self):
        text = "A" * 500 + "\n\n" + "B" * 600
        msgs = [_make_msg(3), _make_msg(4)]
        with patch.object(tgcm, "tg_api_call", side_effect=msgs) as mock:
            result = tgcm.publish_post("tok", "-100", text, photo_url="http://img.jpg")
        assert len(result) == 2
        assert mock.call_count == 2
        assert mock.call_args_list[0][0][1] == "sendPhoto"
        assert mock.call_args_list[1][0][1] == "sendMessage"


class TestSplitAtParagraphBoundary:
    def test_splits_at_double_newline(self):
        head, tail = tgcm._split_text("A" * 500 + "\n\n" + "B" * 600, 1024)
        assert head == "A" * 500
        assert tail == "B" * 600

    def test_prefers_paragraph_over_newline(self):
        text = "A" * 400 + "\n" + "B" * 50 + "\n\n" + "C" * 800
        head, tail = tgcm._split_text(text, 1024)
        assert head == "A" * 400 + "\n" + "B" * 50
        assert tail == "C" * 800

    def test_no_orphaned_header_at_end(self):
        """Header at the end of head is pushed to tail with its content."""
        text = "A" * 400 + "\n\n### Section\n\n" + "B" * 700
        head, tail = tgcm._split_text(text, 1024)
        assert head == "A" * 400
        assert tail == "### Section\n\n" + "B" * 700

    def test_orphaned_header_no_earlier_break(self):
        """If no earlier paragraph break exists, keep original split."""
        text = "### Title\n\n" + "B" * 600
        head, tail = tgcm._split_text(text, 20)
        assert head == "### Title"
        assert tail == "B" * 600


class TestSplitAtNewlineIfNoParagraph:
    def test_splits_at_newline(self):
        text = "A" * 500 + "\n" + "B" * 600
        head, tail = tgcm._split_text(text, 1024)
        assert head == "A" * 500
        assert tail == "B" * 600


class TestSplitAtSpaceIfNoNewline:
    def test_splits_at_space(self):
        text = "A" * 500 + " " + "B" * 600
        head, tail = tgcm._split_text(text, 1024)
        assert head == "A" * 500
        assert tail == "B" * 600


class TestApiErrorReturnsNone:
    def test_sendmessage_error(self):
        with patch.object(tgcm, "tg_api_call", return_value=None):
            result = tgcm.publish_post("tok", "-100", "hello")
        assert result is None

    def test_sendphoto_error(self):
        with patch.object(tgcm, "tg_api_call", return_value=None):
            result = tgcm.publish_post("tok", "-100", "hi", photo_url="http://img.jpg")
        assert result is None

    def test_second_message_error(self):
        text = "A" * 500 + "\n\n" + "B" * 600
        with patch.object(tgcm, "tg_api_call", side_effect=[_make_msg(1), None]):
            result = tgcm.publish_post("tok", "-100", text, photo_url="http://img.jpg")
        assert result is None


class TestCliPublishExit0:
    def test_success(self, tgcm_workspace):
        captured = io.StringIO()
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(10)):
            with patch.object(tgcm, "resolve_bot_token", return_value="fake-token"):
                with patch("sys.stdout", captured):
                    rc = tgcm.main([
                        "--workspace", str(tgcm_workspace),
                        "publish", "test-chan", "--text", "hello world",
                    ])
        assert rc == 0
        data = json.loads(captured.getvalue())
        assert data["ok"] is True
        assert 10 in data["message_ids"]


class TestCliPublishMissingTextExit1:
    def test_missing_text_arg(self, tgcm_workspace):
        r = run_tgcm_cli(
            "publish", "test-chan",
            workspace=str(tgcm_workspace),
        )
        assert r.returncode != 0


class TestPublishParseMode:
    def test_parse_mode_passed(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(5)) as mock:
            tgcm.publish_post("tok", "-100", "hi", parse_mode="HTML")
        assert mock.call_args[1]["json_body"]["parse_mode"] == "HTML"

    def test_no_parse_mode_omitted(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(6)) as mock:
            tgcm.publish_post("tok", "-100", "hi")
        assert "parse_mode" not in mock.call_args[1]["json_body"]


# --- Markdown → Telegram HTML tests ---


class TestEscapeHtml:
    def test_ampersand(self):
        assert tgcm._escape_html("A & B") == "A &amp; B"

    def test_angle_brackets(self):
        assert tgcm._escape_html("<tag>") == "&lt;tag&gt;"

    def test_combined(self):
        assert tgcm._escape_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_no_special_chars(self):
        assert tgcm._escape_html("plain text") == "plain text"


class TestMdToTgHtml:
    def test_header_to_bold(self):
        assert tgcm.md_to_tg_html("### Header") == "<b>Header</b>"

    def test_header_strips_inner_bold(self):
        assert tgcm.md_to_tg_html("### **Bold Header**") == "<b>Bold Header</b>"

    def test_bold(self):
        assert tgcm.md_to_tg_html("some **bold** text") == "some <b>bold</b> text"

    def test_inline_code(self):
        assert tgcm.md_to_tg_html("use `grep` here") == "use <code>grep</code> here"

    def test_blockquote_single(self):
        assert tgcm.md_to_tg_html("> hello") == "<blockquote>hello</blockquote>"

    def test_blockquote_multiline(self):
        text = "> line one\n> line two"
        assert tgcm.md_to_tg_html(text) == "<blockquote>line one\nline two</blockquote>"

    def test_html_escaping_in_text(self):
        assert tgcm.md_to_tg_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_html_escaping_in_header(self):
        assert tgcm.md_to_tg_html("### A & B") == "<b>A &amp; B</b>"

    def test_html_escaping_in_blockquote(self):
        assert tgcm.md_to_tg_html("> a < b") == "<blockquote>a &lt; b</blockquote>"

    def test_em_dash_list_unchanged(self):
        text = "— item one\n— item two"
        result = tgcm.md_to_tg_html(text)
        assert "— item one" in result
        assert "— item two" in result

    def test_paragraph_breaks_preserved(self):
        text = "para one\n\npara two"
        result = tgcm.md_to_tg_html(text)
        assert result == "para one\n\npara two"

    def test_plain_text_unchanged(self):
        text = "just plain text"
        assert tgcm.md_to_tg_html(text) == text

    def test_real_post_snippet(self):
        text = (
            "### **AI-новость дня**\n"
            "\n"
            "Google выпустил **Gemini 2.0** — мультимодальную модель.\n"
            "\n"
            "> Попробуй промпт:\n"
            "> `расскажи о себе`\n"
            "\n"
            "— Быстрее GPT-4\n"
            "— Дешевле Claude"
        )
        result = tgcm.md_to_tg_html(text)
        assert "<b>AI-новость дня</b>" in result
        assert "<b>Gemini 2.0</b>" in result
        assert "<blockquote>" in result
        assert "<code>расскажи о себе</code>" in result
        assert "— Быстрее GPT-4" in result

    def test_h1_and_h2_headers(self):
        assert tgcm.md_to_tg_html("# Title") == "<b>Title</b>"
        assert tgcm.md_to_tg_html("## Subtitle") == "<b>Subtitle</b>"

    def test_blockquote_flush_before_regular_line(self):
        text = "> quote\nregular"
        result = tgcm.md_to_tg_html(text)
        assert result == "<blockquote>quote</blockquote>\nregular"


class TestPublishWithFormatMd:
    def test_md_format_converts_and_sets_html(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(20)) as mock:
            tgcm.publish_post("tok", "-100", "### Title", text_format="md")
        body = mock.call_args[1]["json_body"]
        assert body["text"] == "<b>Title</b>"
        assert body["parse_mode"] == "HTML"

    def test_no_format_no_conversion(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(21)) as mock:
            tgcm.publish_post("tok", "-100", "### Title")
        body = mock.call_args[1]["json_body"]
        assert body["text"] == "### Title"
        assert "parse_mode" not in body

    def test_plain_format_no_conversion(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(22)) as mock:
            tgcm.publish_post("tok", "-100", "### Title", text_format="plain")
        body = mock.call_args[1]["json_body"]
        assert body["text"] == "### Title"

    def test_md_format_with_photo_short(self):
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(23)) as mock:
            tgcm.publish_post(
                "tok", "-100", "**bold**",
                photo_url="http://img.jpg", text_format="md",
            )
        body = mock.call_args[1]["json_body"]
        assert body["caption"] == "<b>bold</b>"
        assert body["parse_mode"] == "HTML"

    def test_md_format_with_photo_split(self):
        head_md = "### Head\n" + "A" * 500
        tail_md = "### Tail\n" + "B" * 600
        text = head_md + "\n\n" + tail_md
        msgs = [_make_msg(24), _make_msg(25)]
        with patch.object(tgcm, "tg_api_call", side_effect=msgs) as mock:
            tgcm.publish_post(
                "tok", "-100", text,
                photo_url="http://img.jpg", text_format="md",
            )
        caption = mock.call_args_list[0][1]["json_body"]["caption"]
        text2 = mock.call_args_list[1][1]["json_body"]["text"]
        assert "<b>Head</b>" in caption
        assert "<b>Tail</b>" in text2
        assert mock.call_args_list[0][1]["json_body"]["parse_mode"] == "HTML"
        assert mock.call_args_list[1][1]["json_body"]["parse_mode"] == "HTML"


class TestCliPublishFormatMd:
    def test_default_format_md_converts(self, tgcm_workspace):
        captured = io.StringIO()
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(30)) as mock:
            with patch.object(tgcm, "resolve_bot_token", return_value="fake-token"):
                with patch("sys.stdout", captured):
                    rc = tgcm.main([
                        "--workspace", str(tgcm_workspace),
                        "publish", "test-chan",
                        "--text", "### Hello",
                    ])
        assert rc == 0
        body = mock.call_args[1]["json_body"]
        assert body["text"] == "<b>Hello</b>"
        assert body["parse_mode"] == "HTML"

    def test_explicit_plain_no_conversion(self, tgcm_workspace):
        captured = io.StringIO()
        with patch.object(tgcm, "tg_api_call", return_value=_make_msg(31)) as mock:
            with patch.object(tgcm, "resolve_bot_token", return_value="fake-token"):
                with patch("sys.stdout", captured):
                    rc = tgcm.main([
                        "--workspace", str(tgcm_workspace),
                        "publish", "test-chan",
                        "--text", "### Hello",
                        "--format", "plain",
                    ])
        assert rc == 0
        body = mock.call_args[1]["json_body"]
        assert body["text"] == "### Hello"
