import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class InvalidURL(ValueError):
    pass


def canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            raise ValueError
        host = parsed.hostname.encode("idna").decode().lower()
        if any(char.isspace() for char in value) or host == "localhost":
            raise ValueError
        try:
            if not ipaddress.ip_address(host).is_global:
                raise InvalidURL("Sunt acceptate numai adrese web publice.")
        except ValueError as exc:
            if isinstance(exc, InvalidURL):
                raise
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        netloc = f"[{host}]" if ":" in host else host
        if parsed.port and parsed.port != (443 if parsed.scheme == "https" else 80):
            netloc += f":{parsed.port}"
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urlencode(query), ""))
    except (ValueError, UnicodeError):
        raise InvalidURL("Introdu un URL HTTP sau HTTPS valid, către o pagină publică.") from None


def public_url(value: str) -> str:
    url = canonical_url(value)
    host = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise InvalidURL("Domeniul paginii nu poate fi găsit.") from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise InvalidURL("Sunt acceptate numai adrese web publice.")
    return url


def is_facebook(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.com"
