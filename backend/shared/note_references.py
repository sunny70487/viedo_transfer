"""
Reference sources for study notes.

Turns user-supplied text and web pages into a budgeted block that can be
placed in an LLM prompt. Fetched pages are untrusted input: URLs are checked
against internal addresses on every hop, and only readable text is kept.
"""

import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit

import httpx

logger = logging.getLogger("note_references")

MAX_REFERENCE_URLS = 5
MAX_REFERENCE_CHARS = 20_000
# A chapter can also draw on pages linked from the reference pages. The two
# budgets add up, so the direct one is lowered when linked pages are used.
MAX_DIRECT_CHARS_WITH_LINKS = 12_000
MAX_LINKED_CHARS = 12_000
MAX_PAGE_LINKS = 60

_PASSAGE_CHARS = 600
_MAX_LINK_TITLE_CHARS = 120
_MAX_LINK_CONTEXT_CHARS = 300
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]{1,200})\]\((https?://[^)\s]+)\)")
# In a Markdown list, the description of a link ends where the next
# unindented item or heading begins.
_NEXT_TOP_ITEM_RE = re.compile(r"\n(?=[*\-+#] |\d+\. )")
_ACCOUNT_PATH_RE = re.compile(
    r"^/(?:s/)?(auth|login|logout|signin|sign-in|signup|sign-up|join|register|"
    r"account|settings|terms|privacy|pricing|about|release-notes|features)"
    r"(/|$)",
    re.IGNORECASE,
)
# A link's description ends at a blank line, a heading or a fenced block.
_CONTEXT_STOP_RE = re.compile(r"\n\s*\n|\n#{1,6} |\n:::|\n```")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>\n]*>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\([^)\s]*\)")
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_SITE_SUFFIX_RE = re.compile(r"\s+[-|–—]\s+HackMD\s*$")
_LATIN_WORD_RE = re.compile(r"[a-z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+")

_MAX_REDIRECTS = 3
_MIN_TEXT_CHARS = 50
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_TEXT_CONTENT_TYPES = ("text/html", "text/plain")
_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WhisperTransferNotes/1.0)",
    "Accept": "text/html,text/plain;q=0.9",
}

_ERR_SCHEME = "只支援 http 或 https 網址"
_ERR_INTERNAL = "不支援內部網路位址"
_ERR_DNS = "無法解析網址"

_SKIP_TAGS = frozenset({
    "script", "style", "noscript", "svg", "nav", "header", "footer", "aside",
    "form",
})
_BLOCK_TAGS = frozenset({
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd",
})
_META_CHARSET_RE = re.compile(rb"charset=[\"']?\s*([\w.:-]+)", re.IGNORECASE)
_CLOSING_TAG_RE = re.compile(r"</\s*reference\s*>", re.IGNORECASE)


class _FetchError(Exception):
    """A fetch failure with a message that is safe to show to the user."""


def _is_internal_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        not ip.is_global
        or ip.is_multicast
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
    )


def validate_reference_url(url: str) -> Tuple[bool, str]:
    """Check that *url* is http(s) and does not point at an internal host."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return False, _ERR_SCHEME
    if parts.scheme not in ("http", "https") or not host:
        return False, _ERR_SCHEME

    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            infos = socket.getaddrinfo(
                host, port or (443 if parts.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except (socket.gaierror, UnicodeError):
            return False, _ERR_DNS
        addresses = [info[4][0] for info in infos]
        if not addresses:
            return False, _ERR_DNS

    if any(_is_internal_address(address) for address in addresses):
        return False, _ERR_INTERNAL
    return True, ""


class _ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.title_parts: List[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.parts.append(data)


def extract_readable_text(html: str) -> Tuple[str, str]:
    """
    Return ``(title, text)`` with scripts, styles and page chrome removed.

    Line breaks inside text are kept (blank lines dropped): some sites, e.g.
    HackMD, serve a note as raw Markdown in a single element, where line
    breaks are the only structure and passage selection depends on them.
    """
    parser = _ReadableTextParser()
    parser.feed(html)
    parser.close()
    lines = (
        " ".join(line.split()) for line in "".join(parser.parts).split("\n")
    )
    text = "\n".join(line for line in lines if line)
    title = " ".join("".join(parser.title_parts).split())
    return title, text


class _LinkParser(HTMLParser):
    """Collects ``<a>`` links outside page chrome, each with the readable
    text that follows it (up to the next link), plus that same text stream
    so Markdown links left unrendered in the page can be found too."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[Dict[str, Any]] = []
        self.text_parts: List[str] = []
        self._skip_depth = 0
        self._open: Any = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "a" and not self._skip_depth:
            self._open = {
                "href": dict(attrs).get("href") or "", "title": [], "after": [],
            }
            self.anchors.append(self._open)
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag == "a":
            self._open = None
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.text_parts.append(data)
        if self._open is not None:
            self._open["title"].append(data)
        elif self.anchors:
            self.anchors[-1]["after"].append(data)


def _clean_link_context(raw: str) -> str:
    """Turn the Markdown/HTML that follows a link into a plain description."""
    text = _CONTEXT_STOP_RE.split(raw, 1)[0]
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MARKDOWN_IMAGE_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = text.replace("==", "").replace("`", "")
    return " ".join(text.split())[:_MAX_LINK_CONTEXT_CHARS]


def _same_site_target(href: str, base: Any, base_url: str) -> str:
    """Absolute, fragment-free URL of *href* if it is another page on the
    same host as the page it was found on; otherwise an empty string."""
    try:
        target = urlsplit(urljoin(base_url, href.strip()))
        if target.scheme not in ("http", "https"):
            return ""
        if (target.hostname or "").lower() != (base.hostname or "").lower():
            return ""
        if target.path.rstrip("/") == base.path.rstrip("/"):
            return ""
        if _ACCOUNT_PATH_RE.match(target.path):
            return ""
        return target._replace(fragment="").geturl()
    except ValueError:
        return ""


def extract_page_links(html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Links from a page to other pages on the same site, in page order.

    Returns ``[{"url", "title", "context"}]`` where ``context`` is the text
    that follows the link (what an index page says about the linked page).
    Both ``<a>`` elements and Markdown ``[title](url)`` links still present
    in the text are read. Duplicates, other hosts, fragments and the page
    itself are dropped; at most ``MAX_PAGE_LINKS`` are returned.
    """
    try:
        base = urlsplit(base_url)
    except ValueError:
        return []
    if base.scheme not in ("http", "https") or not base.hostname:
        return []

    parser = _LinkParser()
    parser.feed(html)
    parser.close()

    found = [
        (anchor["href"], "".join(anchor["title"]), "".join(anchor["after"]))
        for anchor in parser.anchors
    ]
    text = "".join(parser.text_parts)
    # Images and links to other sites are part of a description, not the
    # start of the next entry, so only same-site page links count here.
    matches = [
        match for match in _MARKDOWN_LINK_RE.finditer(text)
        if text[max(match.start() - 1, 0)] != "!"
        and _same_site_target(match.group(2), base, base_url)
    ]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        rest = text[match.end():end]
        sibling = _NEXT_TOP_ITEM_RE.search(rest)
        if sibling:
            rest = rest[:sibling.start()]
        found.append((match.group(2), match.group(1), rest))

    by_url: Dict[str, Dict[str, str]] = {}
    for href, raw_title, raw_context in found:
        url = _same_site_target(href, base, base_url)
        title = " ".join(raw_title.split())[:_MAX_LINK_TITLE_CHARS]
        if not url or not title:
            continue
        context = _clean_link_context(raw_context)
        known = by_url.get(url)
        if known is None:
            if len(by_url) < MAX_PAGE_LINKS:
                by_url[url] = {"url": url, "title": title, "context": context}
        elif len(context) > len(known["context"]):
            # A page often links the same target twice (breadcrumb, then the
            # list entry); the longer description says more about it.
            known.update(title=title, context=context)
    return list(by_url.values())


def _resolve_fetch_url(url: str) -> str:
    """
    Map a URL to the page that actually holds its content.

    HackMD "book mode" links (``hackmd.io/@owner/book/<encoded note>``) serve
    an empty shell and load the note with JavaScript; the note itself is
    plain HTML at the address encoded in the last path segment. Only targets
    on hackmd.io are followed, and the result is validated like any other
    URL before it is requested.
    """
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "").lower() != "hackmd.io":
            return url
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) != 3 or not segments[0].startswith("@"):
            return url
        target = unquote(segments[2])
        if target.startswith("/") and not target.startswith("//"):
            return f"https://hackmd.io{target}"
        note = urlsplit(target)
        if note.scheme == "https" and (note.hostname or "").lower() == "hackmd.io":
            return target
    except ValueError:
        pass
    return url


def _build_client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=False)


def _decode_body(body: bytes, header_charset: Any) -> str:
    charset = header_charset
    if not charset:
        match = _META_CHARSET_RE.search(body[:2048])
        charset = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _download(
    url: str, *, timeout: float, max_bytes: int
) -> Tuple[str, str, List[Dict[str, str]]]:
    """Fetch *url*; returns ``(title, text, same-site links)``."""
    current = url
    with _build_client(timeout) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            ok, error = validate_reference_url(current)
            if not ok:
                raise _FetchError(error)
            with client.stream(
                "GET", current, headers=_REQUEST_HEADERS
            ) as response:
                status = response.status_code
                location = response.headers.get("location")
                if status in _REDIRECT_STATUSES and location:
                    current = urljoin(current, location)
                    continue
                if status != 200:
                    raise _FetchError(f"網站回應 HTTP {status}")

                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0].strip().lower()
                )
                if content_type not in _TEXT_CONTENT_TYPES:
                    raise _FetchError(
                        f"不支援的內容類型：{content_type or '未知'}"
                    )

                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise _FetchError("內容過大")
                raw = _decode_body(bytes(body), response.charset_encoding)

            if content_type == "text/html":
                title, text = extract_readable_text(raw)
                title = _SITE_SUFFIX_RE.sub("", title)
                return title, text, extract_page_links(raw, current)
            return "", raw.strip(), []
    raise _FetchError("轉址次數過多")


def fetch_reference_url(
    url: str,
    *,
    timeout: float = 10.0,
    max_bytes: int = 2_000_000,
    max_chars: Optional[int] = MAX_REFERENCE_CHARS,
) -> Dict[str, Any]:
    """
    Download one reference page and extract its readable text.

    The result also lists the page's same-site ``links`` (see
    ``extract_page_links``). *max_chars* caps the stored text; pass None to
    keep the whole page when passages will be selected from it later.

    Never raises: failures are reported as ``{"ok": False, "error": ...}``.
    Redirects are followed manually (at most 3) so every hop is validated.
    """
    url = url.strip()
    result: Dict[str, Any] = {
        "url": url, "title": "", "text": "", "ok": False, "error": "",
        "links": [],
    }
    try:
        title, text, links = _download(
            _resolve_fetch_url(url), timeout=timeout, max_bytes=max_bytes
        )
    except _FetchError as exc:
        result["error"] = str(exc)
        return result
    except httpx.TimeoutException:
        result["error"] = "連線逾時"
        return result
    except httpx.HTTPError as exc:
        logger.warning("Reference fetch failed for %s: %s", url, exc)
        result["error"] = "無法連線到網站"
        return result
    except Exception as exc:
        logger.warning(
            "Reference fetch crashed for %s: %s", url, exc, exc_info=True
        )
        result["error"] = "無法讀取網頁內容"
        return result

    if len(text) < _MIN_TEXT_CHARS:
        result["error"] = "擷取不到內文，請改用貼上文字"
        return result
    result.update(
        title=title,
        text=text if max_chars is None else text[:max_chars],
        ok=True,
        links=links,
    )
    return result


def resolve_reference_sources(
    urls: List[str], cached: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Build the source list for *urls*, in order and without duplicates.

    URLs already present in *cached* are reused as-is (including failed
    ones — remove and re-add a URL to retry it); the rest are fetched.
    Successful entries saved before pages' links were recorded are fetched
    once more so their sub-pages become available.
    """
    by_url = {source.get("url"): source for source in cached}
    sources: List[Dict[str, Any]] = []
    seen = set()
    for raw in urls:
        url = raw.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        known = by_url.get(url)
        if known and not (known.get("ok") and "links" not in known):
            sources.append(known)
        else:
            sources.append(fetch_reference_url(url))
    return sources


def candidate_links(sources: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Sub-pages a chapter may draw on: the links of every successfully fetched
    source, in order, without duplicates and without pages that are already
    reference sources themselves.
    """
    taken = {source.get("url") for source in sources}
    links: List[Dict[str, str]] = []
    for source in sources:
        if not source.get("ok"):
            continue
        for link in source.get("links") or []:
            url = link.get("url") if isinstance(link, dict) else None
            if not isinstance(url, str) or not url or url in taken:
                continue
            taken.add(url)
            links.append({
                "url": url,
                "title": str(link.get("title") or ""),
                "context": str(link.get("context") or ""),
            })
    return links


def query_terms(text: str) -> set:
    """
    Search terms for keyword matching: lower-cased Latin words/numbers of at
    least two characters, and every pair of adjacent CJK characters (CJK text
    has no word boundaries, so bigrams stand in for words).
    """
    lowered = text.lower()
    terms = {word for word in _LATIN_WORD_RE.findall(lowered) if len(word) >= 2}
    for run in _CJK_RUN_RE.findall(lowered):
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return terms


def _passages(text: str, size: int) -> List[str]:
    """Cut *text* into passages of at most *size* chars on line boundaries."""
    passages: List[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > size:
            if current:
                passages.append(current)
                current = ""
            passages.append(line[:size])
            line = line[size:]
        if current and len(current) + 1 + len(line) > size:
            passages.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        passages.append(current)
    return passages


def select_passages(
    text: str, query: str, *, max_chars: int
) -> Tuple[str, bool]:
    """
    Keep the parts of *text* most related to *query*, within *max_chars*.

    Purely lexical: the text is cut into passages, each scored by how many
    distinct query terms it contains (repeats count a little), and the best
    ones are kept in their original order. Without any match the start of
    the text is returned. Returns ``(text, was_cut)``.
    """
    if len(text) <= max_chars:
        return text, False
    # Front matter (title, tags) repeats the page's keywords without saying
    # anything, so it would outscore the passages that explain them.
    text = _FRONT_MATTER_RE.sub("", text, count=1)
    if len(text) <= max_chars:
        return text, True
    terms = query_terms(query)
    passages = _passages(text, min(_PASSAGE_CHARS, max_chars))

    scored = []
    for index, passage in enumerate(passages):
        lowered = passage.lower()
        counts = [lowered.count(term) for term in terms]
        distinct = sum(1 for count in counts if count)
        if distinct:
            scored.append((distinct * 10 + min(sum(counts), 9), index))
    if not scored:
        return text[:max_chars], True

    chosen = []
    budget = max_chars
    for _, index in sorted(scored, key=lambda item: (-item[0], item[1])):
        cost = len(passages[index]) + (1 if chosen else 0)
        if cost <= budget:
            chosen.append(index)
            budget -= cost
    return "\n".join(passages[index] for index in sorted(chosen)), True


def build_linked_block(
    pages: List[Dict[str, Any]],
    query: str,
    *,
    max_chars: int = MAX_LINKED_CHARS,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Render linked sub-pages as ``<reference>`` blocks for one chapter.

    Each page gets a fair share of *max_chars*; pages longer than their
    share are reduced with ``select_passages`` using *query* (the chapter's
    titles and summaries). Returns ``(block, pages_used)``.
    """
    usable = [page for page in pages if page.get("ok") and page.get("text")]
    allocation = _allocate([len(page["text"]) for page in usable], max_chars)

    blocks: List[str] = []
    used: List[Dict[str, Any]] = []
    for page, size in zip(usable, allocation):
        if not size:
            continue
        text, _ = select_passages(page["text"], query, max_chars=size)
        title = page.get("title") or ""
        url = page.get("url") or ""
        label = f"{title} ({url})" if title else url
        blocks.append(_reference_tag(f"延伸閱讀：{label}", text))
        used.append(page)
    return "\n\n".join(blocks), used


def _allocate(lengths: List[int], budget: int) -> List[int]:
    """Split *budget* across items; short items free up room for long ones."""
    allocation = [0] * len(lengths)
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    for position, index in enumerate(order):
        share = budget // (len(order) - position)
        allocation[index] = min(lengths[index], share)
        budget -= allocation[index]
    return allocation


def _reference_tag(label: str, text: str) -> str:
    safe_label = " ".join(label.replace('"', "'").split())
    safe_text = _CLOSING_TAG_RE.sub("", text)
    return f'<reference source="{safe_label}">\n{safe_text}\n</reference>'


def build_reference_block(
    text: str,
    sources: List[Dict[str, Any]],
    *,
    max_chars: int = MAX_REFERENCE_CHARS,
) -> Tuple[str, int, bool]:
    """
    Render pasted text and fetched pages as ``<reference>`` blocks.

    Returns ``(block, used_chars, truncated)``. Pasted text is served first;
    the remaining budget is shared between successfully fetched sources.
    """
    pasted = text.strip()
    usable = [s for s in sources if s.get("ok") and s.get("text")]

    pasted_used = pasted[:max_chars]
    lengths = [len(s["text"]) for s in usable]
    allocation = _allocate(lengths, max_chars - len(pasted_used))

    blocks: List[str] = []
    if pasted_used:
        blocks.append(_reference_tag("使用者提供的文字", pasted_used))
    for source, size in zip(usable, allocation):
        if not size:
            continue
        title = source.get("title") or ""
        url = source.get("url") or ""
        label = f"{title} ({url})" if title else url
        blocks.append(_reference_tag(label, source["text"][:size]))

    used = len(pasted_used) + sum(allocation)
    truncated = len(pasted) > len(pasted_used) or allocation != lengths
    return "\n\n".join(blocks), used, truncated


def summarize_references(
    text: str, sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Describe stored references for the UI, without the page text."""
    _, used, truncated = build_reference_block(text, sources)
    return {
        "text": text,
        "sources": [
            {
                "url": source.get("url") or "",
                "title": source.get("title") or "",
                "chars": len(source.get("text") or ""),
                "ok": bool(source.get("ok")),
                "error": source.get("error") or "",
                "links": len(source.get("links") or []),
            }
            for source in sources
        ],
        "used_chars": used,
        "truncated": truncated,
    }
