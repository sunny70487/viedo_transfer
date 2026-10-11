import pytest

from backend.shared.svg_sanitizer import sanitize_svg

NS = 'xmlns="http://www.w3.org/2000/svg"'
XLINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def _svg(body, extra=""):
    return f'<svg {NS} {extra} viewBox="0 0 800 450">{body}</svg>'


def test_keeps_css_animation_and_shapes():
    raw = _svg(
        "<style>@keyframes p{from{opacity:0}to{opacity:1}}"
        ".a{animation:p 4s infinite}</style>"
        '<rect width="800" height="450" fill="#fff"/>'
        '<circle class="a" cx="10" cy="10" r="5"/>'
        "<text x=\"10\" y=\"40\">三向交握</text>"
    )
    out = sanitize_svg(raw)
    assert "@keyframes p" in out
    assert "<circle" in out
    assert "三向交握" in out
    assert 'xmlns="http://www.w3.org/2000/svg"' in out


def test_adds_svg_namespace_when_missing():
    out = sanitize_svg('<svg viewBox="0 0 10 10"><rect width="1"/></svg>')
    assert out.startswith("<svg")
    assert 'xmlns="http://www.w3.org/2000/svg"' in out
    assert "<rect" in out


@pytest.mark.parametrize(
    "tag",
    [
        "<script>alert(1)</script>",
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div>'
        "</foreignObject>",
        '<image href="http://evil/x.png"/>',
        '<iframe src="http://evil"/>',
        '<object data="x"/>',
        '<embed src="x"/>',
    ],
)
def test_removes_dangerous_elements(tag):
    out = sanitize_svg(_svg(tag + '<rect width="1"/>'))
    for name in ("script", "foreignObject", "image", "iframe", "object", "embed"):
        assert f"<{name}" not in out
    assert "<rect" in out


def test_removes_event_handlers():
    out = sanitize_svg(_svg('<rect width="1" onclick="x()" onLoad="y()"/>'))
    assert "onclick" not in out.lower()
    assert "onload" not in out.lower()


def test_strips_external_href_keeps_internal_reference():
    raw = _svg(
        '<defs><path id="p" d="M0 0"/></defs>'
        '<use href="#p"/><use xlink:href="http://evil/x#p"/>',
        extra=XLINK,
    )
    out = sanitize_svg(raw)
    assert 'href="#p"' in out
    assert "evil" not in out


def test_removes_animation_that_rewrites_href():
    raw = _svg(
        '<a><animate attributeName="href" values="#x"/>'
        '<set attributeName="xlink:href" to="#y"/>'
        '<animate attributeName="opacity" values="0;1"/><text>t</text></a>'
    )
    out = sanitize_svg(raw)
    assert 'attributeName="href"' not in out
    assert "xlink:href" not in out
    assert 'attributeName="opacity"' in out


def test_anchor_keeps_children_but_drops_href():
    out = sanitize_svg(_svg('<a href="javascript:alert(1)"><text>hi</text></a>'))
    assert "javascript" not in out
    assert "hi" in out


@pytest.mark.parametrize(
    "css",
    [
        "@import url(http://evil/x.css);",
        ".a{background:url(http://evil/x.png)}",
        ".a{fill:url( 'https://evil/x' )}",
    ],
)
def test_removes_style_with_external_resources(css):
    out = sanitize_svg(_svg(f"<style>{css}</style><rect width=\"1\"/>"))
    assert "<style" not in out
    assert "evil" not in out


def test_keeps_style_with_internal_url_reference():
    out = sanitize_svg(_svg("<style>.a{fill:url(#grad)}</style>"))
    assert "url(#grad)" in out


def test_strips_external_url_in_inline_style_attribute():
    out = sanitize_svg(_svg('<rect style="fill:url(http://evil/x)"/>'))
    assert "evil" not in out


@pytest.mark.parametrize(
    "raw",
    [
        '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>',
        '<!doctype svg [<!ENTITY x "y">]><svg/>',
        "<svg><rect></svg>",
        '<html xmlns="http://www.w3.org/1999/xhtml"/>',
        "",
    ],
)
def test_rejects_invalid_or_unsafe_documents(raw):
    with pytest.raises(ValueError):
        sanitize_svg(raw)


def test_rejects_oversized_input():
    big = _svg("<text>" + "a" * (200 * 1024) + "</text>")
    with pytest.raises(ValueError):
        sanitize_svg(big)
