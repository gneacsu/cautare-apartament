"""Bounded HTTP reads and removal of page furniture; never execute JavaScript."""

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.config import Settings
from src.extractors.images import image_urls
from src.models import Source
from src.utils.urls import InvalidURL, public_url


class PageError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_html(html: str, max_chars: int) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Anunț"
    # Only root listing/product JSON-LD, never offers from ItemList recommendations.
    structured = []
    allowed = {"Apartment", "House", "Residence", "RealEstateListing", "Product", "Offer"}

    def read_node(node):
        if isinstance(node, list):
            for item in node:
                read_node(item)
        elif isinstance(node, dict):
            kind = node.get("@type", "")
            kinds = set(kind if isinstance(kind, list) else [kind])
            if kinds & allowed and isinstance(node.get("description"), str):
                fields = {key: node[key] for key in (
                    "name", "description", "address", "floorSize", "numberOfRooms",
                    "floorLevel", "yearBuilt", "offers", "seller") if key in node}
                structured.append(json.dumps(fields, ensure_ascii=False))
            if "@graph" in node:
                read_node(node["@graph"])

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            read_node(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError, RecursionError):
            continue
    for node in soup.select("script, style, nav, footer, header, aside, form, noscript, iframe, svg"):
        node.decompose()
    for node in list(soup.select("[class], [id]")):
        if node.attrs is None:
            continue
        labels = " ".join(node.get("class", [])) + " " + node.get("id", "")
        if re.search(r"recommend|related|cookie|newsletter|advertisement|similar-list", labels, re.I):
            node.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    paragraphs = list(dict.fromkeys(line.strip() for line in root.get_text("\n", strip=True).splitlines() if line.strip()))
    text = "\n".join((structured if len(structured) == 1 else []) + paragraphs)
    # A blocked page may return HTTP 200. Do not send challenge/login text as a listing.
    short_text = text.casefold()
    if len(text) < 80 or (len(text) < 1500 and any(marker in short_text for marker in (
        "verify you are human", "checking your browser", "access denied", "enable javascript",
        "just a moment", "captcha", "log in to continue", "autentifică-te pentru"))):
        raise PageError("Pagina nu oferă o descriere accesibilă. Copiază descrierea în câmpul alternativ.")
    return title[:300], text[:max_chars]


class PageReader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def read(self, url: str, deadline: float, max_chars: int | None = None) -> Source:
        original = url
        try:
            for _ in range(4):
                if time.monotonic() >= deadline:
                    raise PageError("Limita de timp a verificării a fost atinsă.")
                url = public_url(url)
                timeout = max(0.1, min(self.settings.http_seconds, deadline - time.monotonic()))
                with requests.get(url, headers={"User-Agent": "ApartmentSearch/1.0 (personal research)",
                                               "Accept": "text/html,application/xhtml+xml"},
                                  timeout=timeout, allow_redirects=False, stream=True) as response:
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise PageError("Redirecționare fără destinație.")
                        url = urljoin(url, location)
                        continue
                    if response.status_code >= 400:
                        raise PageError(f"Pagina nu poate fi citită (HTTP {response.status_code}). Copiază descrierea manual.")
                    content_type = response.headers.get("Content-Type", "").lower()
                    if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml")):
                        raise PageError("Linkul nu furnizează o pagină HTML.")
                    data = bytearray()
                    for chunk in response.iter_content(16384):
                        if time.monotonic() >= deadline:
                            raise PageError("Limita de timp a verificării a fost atinsă.")
                        data.extend(chunk)
                        if len(data) > self.settings.max_page_bytes:
                            raise PageError("Pagina depășește limita de descărcare. Copiază descrierea manual.")
                    # Let Beautiful Soup inspect the declared HTML encoding when needed.
                    html = str(BeautifulSoup(bytes(data), "html.parser"))
                    title, text = extract_html(html, max_chars or self.settings.max_input_chars)
                    return Source(url=original, final_url=url, title=title, text=text, images=image_urls(html, url),
                                  links=source_links(html, url),
                                  access="page", accessed_at=now())
            raise PageError("Pagina are prea multe redirecționări.")
        except requests.RequestException:
            raise PageError("Pagina nu poate fi accesată în acest moment. Copiază descrierea manual sau reîncearcă.") from None
        except InvalidURL as exc:
            raise PageError(str(exc)) from None


def source_links(html, base_url):
    """Only explicitly labelled source links; never crawl the whole site navigation."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a[href]"):
        label = a.get_text(" ", strip=True).lower()
        if any(word in label for word in ("anunțul original", "anuntul original", "vezi sursa", "sursa anunțului", "sursa anuntului")):
            from src.utils.urls import canonical_url
            try:
                link = canonical_url(urljoin(base_url, a["href"]))
                if link not in links:
                    links.append(link)
            except InvalidURL:
                pass
    return links[:5]
