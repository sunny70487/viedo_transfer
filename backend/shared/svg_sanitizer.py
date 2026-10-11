"""Allow-list style cleanup for LLM-generated SVG animations."""
import logging
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger("svg_sanitizer")

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_SVG_BYTES = 200 * 1024

_FORBIDDEN_TAGS = {
    "script", "foreignobject", "iframe", "object", "embed", "image",
}
_HREF_ATTRS = {"href", f"{{{XLINK_NS}}}href"}
_DOCTYPE_RE = re.compile(r"<!\s*(doctype|entity)", re.IGNORECASE)
_EXTERNAL_CSS_RE = re.compile(
    r"@import|url\(\s*['\"]?\s*(?!#)", re.IGNORECASE
)

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_attributes(el: ET.Element) -> None:
    is_anchor = _local_name(el.tag).lower() == "a"
    for name in list(el.attrib):
        local = _local_name(name).lower()
        value = el.attrib[name]
        if local.startswith("on"):
            del el.attrib[name]
        elif name in _HREF_ATTRS and (
            is_anchor or not value.strip().startswith("#")
        ):
            del el.attrib[name]
        elif _EXTERNAL_CSS_RE.search(value) or "javascript:" in value.lower():
            del el.attrib[name]


def _animates_href(el: ET.Element) -> bool:
    if _local_name(el.tag).lower() not in {"animate", "set"}:
        return False
    target = _local_name(el.attrib.get("attributeName", "")).lower()
    return target == "href" or target.endswith(":href")


def _clean_tree(parent: ET.Element) -> None:
    for child in list(parent):
        if not isinstance(child.tag, str):
            parent.remove(child)
            continue
        name = _local_name(child.tag).lower()
        if name in _FORBIDDEN_TAGS or _animates_href(child):
            parent.remove(child)
            continue
        if name == "style" and _EXTERNAL_CSS_RE.search(child.text or ""):
            parent.remove(child)
            continue
        _clean_attributes(child)
        _clean_tree(child)


def _ensure_svg_namespace(root: ET.Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and not el.tag.startswith("{"):
            el.tag = f"{{{SVG_NS}}}{el.tag}"


def sanitize_svg(raw: str) -> str:
    """Return a cleaned SVG string, or raise ValueError if it is unusable."""
    if not raw or len(raw.encode("utf-8")) > MAX_SVG_BYTES:
        raise ValueError("SVG is empty or too large")
    if _DOCTYPE_RE.search(raw):
        raise ValueError("SVG must not declare DOCTYPE or ENTITY")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"SVG is not well-formed XML: {exc}") from exc
    if _local_name(root.tag).lower() != "svg":
        raise ValueError("Root element must be <svg>")

    _clean_attributes(root)
    _clean_tree(root)
    _ensure_svg_namespace(root)
    return ET.tostring(root, encoding="unicode")
