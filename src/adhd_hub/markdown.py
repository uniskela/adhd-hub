"""Render saved Markdown without executing HTML or fetching embedded media."""

from html import escape

from markdown_it import MarkdownIt

_renderer = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def _image_as_text(tokens, idx, options, env):
    return f'<span class="image-description">[Image: {escape(tokens[idx].content)}]</span>'


_renderer.renderer.rules["image"] = _image_as_text


def render_markdown(content: str) -> str:
    # markdown-it validates link schemes (including encoded javascript/vbscript/data).
    # Raw HTML stays escaped; images display alt text, avoiding remote tracking.
    return _renderer.render(content)
