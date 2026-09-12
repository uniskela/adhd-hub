"""Render saved Markdown without executing HTML or fetching embedded media."""

from html import escape

from markdown_it import MarkdownIt

_renderer = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def _image_as_text(tokens, idx, options, env):
    return f'<span class="image-description">[Image: {escape(tokens[idx].content)}]</span>'


def _is_external_href(href: str) -> bool:
    """True for absolute http(s) / protocol-relative URLs (other origins).

    Relative Hub routes (/ui/...), fragments, and local paths stay in-app.
    github.com and other forges are always external under this rule.
    """
    value = (href or "").strip().lower()
    return (
        value.startswith("https://")
        or value.startswith("http://")
        or value.startswith("//")
    )


def _link_open(tokens, idx, options, env):
    token = tokens[idx]
    href = token.attrGet("href") or ""
    if _is_external_href(href):
        token.attrSet("target", "_blank")
        token.attrSet("rel", "noopener noreferrer")
    return _renderer.renderer.renderToken(tokens, idx, options, env)


_renderer.renderer.rules["image"] = _image_as_text
_renderer.renderer.rules["link_open"] = _link_open


def render_markdown(content: str) -> str:
    # markdown-it validates link schemes (including encoded javascript/vbscript/data).
    # Raw HTML stays escaped; images display alt text, avoiding remote tracking.
    return _renderer.render(content)
