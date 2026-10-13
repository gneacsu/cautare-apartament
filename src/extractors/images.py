"""Transient photo access and conservative matching; nothing is uploaded to Lens automatically."""
import hashlib
import io
import json
import time
import warnings
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

from src.models import ImageMatch, ImageSignature
from src.utils.urls import InvalidURL, canonical_url, public_url


class ImageError(ValueError):
    pass


def image_urls(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    values = []
    for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        values.append(meta.get("content", ""))
    def visit(node):
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            if isinstance(kinds, str):
                kinds = [kinds]
            if any(k in {"Apartment", "House", "Residence", "RealEstateListing", "Product", "Offer"} for k in kinds):
                images = node.get("image", [])
                if not isinstance(images, list):
                    images = [images]
                for item in images:
                    values.append(item if isinstance(item, str) else item.get("contentUrl", item.get("url", "")) if isinstance(item, dict) else "")
            if "@graph" in node:
                visit(node["@graph"])
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            pass
    for node in list(soup.select('[class*="recommend"], [class*="related"], [class*="similar"], aside, nav, footer, header')):
        node.decompose()
    root = soup.find("main") or soup.find("article")
    if root:
        for img in root.select("img"):
            labels = " ".join(img.get("class", [])) + " " + img.get("alt", "")
            if any(word in labels.lower() for word in ("logo", "avatar", "icon", "recomand", "similar")):
                continue
            values.append(img.get("data-src") or img.get("src") or "")
    result = []
    for value in values:
        if not isinstance(value, str) or not value or value.startswith("data:"):
            continue
        try:
            url = canonical_url(urljoin(base_url, value))
            if url not in result:
                result.append(url)
        except InvalidURL:
            pass
    return result[:30]


def decode_image(data):
    if len(data) > 8_000_000:
        raise ImageError("Imaginea depășește 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data))
            if im.width * im.height > 20_000_000:
                raise ImageError("Imaginea depășește 20 megapixeli.")
            im.load()
            return ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageError("Fișierul nu este o fotografie PNG, JPEG sau WebP validă.") from None


def signature(data, url):
    im = decode_image(data)
    if min(im.size) < 160 or max(ImageStat.Stat(im).stddev) < 8:
        raise ImageError("Imagine prea mică sau fără detalii suficiente pentru comparare.")
    small = list(im.convert("L").resize((17, 16)).tobytes())
    bits = ''.join('1' if small[y*17+x] > small[y*17+x+1] else '0' for y in range(16) for x in range(16))
    # Pixel digest ignores file metadata and compression container, but not visual changes.
    digest = hashlib.sha256(str(im.size).encode() + im.tobytes()).hexdigest()
    return ImageSignature(url=url, sha256=digest, dhash=f'{int(bits, 2):064x}', width=im.width, height=im.height)


def match_images(references, candidates):
    matches = []
    for candidate in candidates:
        for ref in references:
            if ref.sha256 == candidate.sha256:
                kind = "identical"
            elif abs(ref.width/ref.height - candidate.width/candidate.height) < .1 and (int(ref.dhash,16)^int(candidate.dhash,16)).bit_count() <= 8:
                kind = "similar"
            else:
                continue
            matches.append(ImageMatch(reference_url=ref.url, candidate_url=candidate.url, kind=kind))
            break
    return matches


def fetch_image(url, settings, deadline):
    try:
        for _ in range(4):
            if time.monotonic() >= deadline:
                raise ImageError("Timpul pentru citirea imaginii a expirat.")
            target = public_url(url)
            with requests.get(target, timeout=min(settings.http_seconds, max(.1, deadline-time.monotonic())),
                              allow_redirects=False, stream=True) as response:
                if response.is_redirect:
                    url = urljoin(target, response.headers.get("Location", ""))
                    continue
                if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                    raise ImageError("Fotografia nu poate fi citită. Folosește o captură sau deschide pagina în browser.")
                data = bytearray()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data) > settings.max_image_bytes or time.monotonic() >= deadline:
                        raise ImageError("Fotografia depășește limita de transfer sau de timp.")
                decode_image(bytes(data))
                return bytes(data)
        raise ImageError("Prea multe redirecționări pentru fotografie.")
    except (requests.RequestException, InvalidURL):
        raise ImageError("Fotografia nu poate fi accesată automat.") from None


def collect_signatures(urls, settings, deadline):
    results, errors = [], []
    for url in urls[:settings.max_images_per_listing]:
        if time.monotonic() >= deadline:
            break
        try:
            item = signature(fetch_image(url, settings, deadline), url)
            if item.sha256 not in {v.sha256 for v in results}:
                results.append(item)
        except ImageError as exc:
            errors.append(str(exc))
    return results, list(dict.fromkeys(errors))
