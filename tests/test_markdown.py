from adhd_hub.markdown import render_markdown


def test_markdown_renders_common_syntax_without_raw_html_or_remote_images():
    rendered = render_markdown(
        "# Heading\n\n- **bold**\n- [docs](https://example.com)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n![tracking](https://evil.test/pixel)\n\n<script>alert(1)</script>"
    )
    assert "<h1>Heading</h1>" in rendered
    assert "<strong>bold</strong>" in rendered
    assert '<a href="https://example.com">docs</a>' in rendered
    assert "<table>" in rendered
    assert "[Image: tracking]" in rendered
    assert "evil.test" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_markdown_does_not_allow_javascript_links():
    rendered = render_markdown("[bad](javascript:alert(1))")
    assert "<a" not in rendered
