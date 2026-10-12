import re
import unicodedata


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"\w+", text))


def contains_quote(text: str, quote: str) -> bool:
    return bool(normalized(quote)) and normalized(quote) in normalized(text)
