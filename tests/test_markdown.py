from adhd_hub.markdown import render_markdown


def test_markdown_renders_common_syntax_without_raw_html_or_remote_images():
    rendered = render_markdown(
        "# Heading\n\n- **bold**\n- [docs](https://example.com)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n![tracking](https://evil.test/pixel)\n\n<script>alert(1)</script>"
    )
    assert "<h1>Heading</h1>" in rendered
    assert "<strong>bold</strong>" in rendered
    assert (
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer">docs</a>'
        in rendered
    )
    assert "<table>" in rendered
    assert "[Image: tracking]" in rendered
    assert "evil.test" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_markdown_does_not_allow_javascript_links():
    rendered = render_markdown("[bad](javascript:alert(1))")
    assert "<a" not in rendered


def test_markdown_external_links_open_in_new_tab_including_github():
    rendered = render_markdown(
        "[gh](https://github.com/uniskela/adhd-hub) "
        "[http](http://example.com) "
        "[proto](//cdn.example.com/x) "
        "[hub](/ui/) "
        "[frag](#section) "
        "[rel](./notes.md)"
    )
    assert (
        '<a href="https://github.com/uniskela/adhd-hub" target="_blank" '
        'rel="noopener noreferrer">gh</a>' in rendered
    )
    assert 'href="http://example.com" target="_blank" rel="noopener noreferrer"' in rendered
    assert 'href="//cdn.example.com/x" target="_blank" rel="noopener noreferrer"' in rendered
    assert '<a href="/ui/">hub</a>' in rendered
    assert '<a href="#section">frag</a>' in rendered
    assert '<a href="./notes.md">rel</a>' in rendered
    # Internal Hub routes / fragments / relative paths stay in-app
    assert 'href="/ui/" target=' not in rendered
    assert 'href="#section" target=' not in rendered
    assert 'href="./notes.md" target=' not in rendered
