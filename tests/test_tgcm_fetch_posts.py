import pytest

from conftest import tgcm


class TestParseTmePostsBasic:
    """Basic parsing of t.me/s/ HTML."""

    SAMPLE_HTML = """
    <div class="tgme_widget_message_wrap" data-post="testchannel/101">
      <div class="tgme_widget_message_text" dir="auto">
        This is the first post with enough text to pass the minimum length filter easily
      </div>
      <time datetime="2025-01-15T10:00:00+00:00"></time>
    </div>
    <div class="tgme_widget_message_wrap" data-post="testchannel/102">
      <div class="tgme_widget_message_text" dir="auto">
        Second post also has sufficient text content for the parser to pick it up correctly
      </div>
      <time datetime="2025-01-15T11:00:00+00:00"></time>
    </div>
    """

    def test_parses_two_posts(self):
        posts = tgcm.parse_tme_posts(self.SAMPLE_HTML)
        assert len(posts) == 2

    def test_extracts_msg_ids(self):
        posts = tgcm.parse_tme_posts(self.SAMPLE_HTML)
        ids = [p["msgId"] for p in posts]
        assert ids == [101, 102]

    def test_extracts_text(self):
        posts = tgcm.parse_tme_posts(self.SAMPLE_HTML)
        assert "first post" in posts[0]["text"]

    def test_extracts_date(self):
        posts = tgcm.parse_tme_posts(self.SAMPLE_HTML)
        assert posts[0]["date"] == "2025-01-15T10:00:00+00:00"


class TestParseTmePostsSkipsShort:
    """Posts shorter than 50 chars are skipped."""

    HTML = """
    <div data-post="ch/1">
      <div class="tgme_widget_message_text">Short</div>
      <time datetime="2025-01-01"></time>
    </div>
    <div data-post="ch/2">
      <div class="tgme_widget_message_text">
        This post has enough characters to pass the fifty character minimum threshold
      </div>
      <time datetime="2025-01-02"></time>
    </div>
    """

    def test_skips_short_post(self):
        posts = tgcm.parse_tme_posts(self.HTML)
        assert len(posts) == 1
        assert posts[0]["msgId"] == 2


class TestParseTmePostsExtractsLinks:
    """Links are extracted from post HTML."""

    HTML = """
    <div data-post="ch/10">
      <div class="tgme_widget_message_text">
        Check out this article about Python programming and machine learning
        <a href="https://example.com/article">link</a> and
        <a href="https://blog.example.com/post">another</a>
      </div>
      <time datetime="2025-01-01"></time>
    </div>
    """

    def test_extracts_links(self):
        posts = tgcm.parse_tme_posts(self.HTML)
        assert len(posts) == 1
        assert "https://example.com/article" in posts[0]["links"]
        assert "https://blog.example.com/post" in posts[0]["links"]


class TestParseTmePostsNestedDivs:
    """Text div with nested divs should capture full content."""

    HTML = """
    <div data-post="ch/5">
      <div class="tgme_widget_message_text" dir="auto">
        Opening paragraph with enough text to pass the minimum length filter.
        <div class="quote">This is a blockquote inside a nested div element.</div>
        And a closing paragraph after the nested div with more text content.
      </div>
      <time datetime="2025-01-01"></time>
    </div>
    """

    def test_captures_text_after_nested_div(self):
        posts = tgcm.parse_tme_posts(self.HTML)
        assert len(posts) == 1
        assert "closing paragraph" in posts[0]["text"]

    def test_captures_text_inside_nested_div(self):
        posts = tgcm.parse_tme_posts(self.HTML)
        assert "blockquote" in posts[0]["text"]


class TestStripHtmlTags:
    """strip_html_tags handles entities, <br>, nested tags, numeric entities."""

    def test_strips_tags(self):
        assert tgcm.strip_html_tags("<b>bold</b> text") == "bold text"

    def test_nested_tags(self):
        assert tgcm.strip_html_tags("<div><b>nested</b></div>") == "nested"

    def test_br_to_newline(self):
        result = tgcm.strip_html_tags("line1<br>line2")
        assert "line1\nline2" in result

    def test_br_self_closing(self):
        result = tgcm.strip_html_tags("line1<br/>line2")
        assert "line1\nline2" in result

    def test_named_entities(self):
        assert tgcm.strip_html_tags("&amp; &lt; &gt;") == "& < >"

    def test_numeric_decimal_entity(self):
        # &#169; = copyright sign
        assert tgcm.strip_html_tags("&#169;") == "\u00a9"

    def test_numeric_hex_entity(self):
        # &#x2014; = em dash
        assert tgcm.strip_html_tags("&#x2014;") == "\u2014"

    def test_mixed_entities(self):
        result = tgcm.strip_html_tags("&amp; &#38; &#x26;")
        # &amp; → &, &#38; → &, &#x26; → &
        assert result == "& & &"

    def test_collapses_multiple_newlines(self):
        result = tgcm.strip_html_tags("a<br><br><br><br>b")
        assert result == "a\n\nb"


class TestParseTmePostsEmpty:
    """Empty or no-post pages return empty list."""

    def test_empty_string(self):
        assert tgcm.parse_tme_posts("") == []

    def test_no_posts_html(self):
        html = "<html><body><div>No posts here</div></body></html>"
        assert tgcm.parse_tme_posts(html) == []
