import json
import re
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; compatible; TexxAssistant/0.1)"
TIMEOUT = 8


class OnlineError(Exception):
    pass


def _fetch(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OnlineError(f"network unavailable ({e.__class__.__name__})") from e


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").strip()


class WebSearchProvider:
    """DuckDuckGo Lite endpoint — no API key required."""

    name = "web"

    def search(self, query: str, max_results: int = 6) -> list[dict]:
        url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
        html = _fetch(url)
        results = self._parse(html)
        if not results:
            raise OnlineError("no results parsed (endpoint may have changed)")
        return results[:max_results]

    @staticmethod
    def _parse(html: str) -> list[dict]:
        results = []
        snippets = [
            _strip_tags(s)[:200] for s in re.findall(
                r'class=["\']result-snippet["\'][^>]*>(.*?)</td>', html, re.DOTALL
            )
        ] or [
            _strip_tags(s)[:200] for s in re.findall(
                r'class=["\']result__snippet["\'][^>]*>(.*?)</a>', html, re.DOTALL
            )
        ]
        idx = 0
        for attrs, title in re.findall(r"<a\b([^>]*)>(.*?)</a>", html, re.DOTALL):
            if "result-link" not in attrs and "result__a" not in attrs:
                continue
            href_m = re.search(r'href="([^"]+)"', attrs) or re.search(r"href='([^']+)'", attrs)
            if not href_m:
                continue
            real_url = href_m.group(1)
            uddg = re.search(r"[?&]uddg=([^&\"]+)", real_url)
            if uddg:
                real_url = urllib.parse.unquote(uddg.group(1))
            results.append({
                "title": _strip_tags(title),
                "url": real_url,
                "snippet": snippets[idx] if idx < len(snippets) else "",
            })
            idx += 1
        return results

    @staticmethod
    def fetch_page_text(url: str, max_chars: int = 4000) -> str:
        """Minimal article extraction (ArticleExtractor interface per spec §13).
        Replaceable by newspaper4k later without touching callers."""
        raw = _fetch(url)
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.DOTALL | re.I)
        text = _strip_tags(raw)
        return text[:max_chars]


class WikipediaProvider:
    name = "wikipedia"

    def summary(self, topic: str) -> dict:
        title = self._resolve_title(topic)
        url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(title.replace(" ", "_")))
        data = json.loads(_fetch(url))
        if data.get("type") == "standard":
            return {
                "title": data.get("title", topic),
                "extract": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", url),
            }
        raise OnlineError(f"no Wikipedia article for '{topic}'")

    def _resolve_title(self, topic: str) -> str:
        url = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
               f"&srsearch={urllib.parse.quote(topic)}&format=json&srlimit=1")
        data = json.loads(_fetch(url))
        hits = data.get("query", {}).get("search", [])
        if not hits:
            raise OnlineError(f"no Wikipedia results for '{topic}'")
        return hits[0]["title"]
