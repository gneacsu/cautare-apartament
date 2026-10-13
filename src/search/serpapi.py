"""Google organic results through SerpApi; no AI-selected citations or secret logging."""
import time
from urllib.parse import parse_qs, urlsplit

import requests

from src.analyzers.provider import ProviderError
from src.config import ConfigurationError
from src.models import SearchBatch, SearchCall, SearchHit
from src.utils.urls import InvalidURL, canonical_url


class SerpApiSearch:
    def __init__(self, settings, session=None):
        self.settings = settings
        self.session = session or requests.Session()
        self.calls = []

    def close(self):
        self.session.close()

    def search(self, query, timeout, start=0):
        if not self.settings.serpapi_key:
            raise ConfigurationError("Lipsește SERPAPI_API_KEY. Adaugă cheia în .env lângă app.py.")
        call = SearchCall(query=query, start=start)
        self.calls.append(call)
        began = time.monotonic()
        try:
            # Do not follow pagination URLs: they may include credentials. Rebuild fixed endpoint params.
            response = self.session.get("https://serpapi.com/search.json", params={
                "engine": "google", "q": query, "hl": "ro", "gl": "ro", "start": start,
                "api_key": self.settings.serpapi_key,
            }, timeout=min(timeout, self.settings.search_seconds), allow_redirects=False)
            call.http_status = response.status_code
            if response.status_code in (401, 403):
                raise ProviderError("SerpApi a refuzat accesul. Verifică cheia și planul contului.")
            if response.status_code == 429:
                raise ProviderError("Cota sau limita de cereri SerpApi a fost atinsă. Verifică planul contului.")
            if response.status_code != 200:
                raise ProviderError(f"SerpApi nu a finalizat căutarea (HTTP {response.status_code}).")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            status = data.get("search_metadata", {}).get("status")
            # SerpApi can return a Success response with this explicit no-results message.
            empty = data.get("error") == "Google hasn't returned any results for this query."
            if status != "Success" or (data.get("error") and not empty):
                raise ProviderError("SerpApi a returnat o căutare nefinalizată sau o eroare. Poți reîncerca.")
            rows = data.get("organic_results", [])
            if not isinstance(rows, list):
                raise ValueError
            hits = []
            seen = set()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("link"), str):
                    raise ValueError
                try:
                    url = canonical_url(row["link"])
                except InvalidURL:
                    continue
                if url not in seen:
                    seen.add(url)
                    hits.append(SearchHit(url=url, title=str(row.get("title", ""))[:300],
                                          snippet=str(row.get("snippet", ""))[:2000]))
            if rows and not hits:
                raise ProviderError("Rezultatele SerpApi nu conțin linkuri publice utilizabile.")
            pagination = data.get("serpapi_pagination", {})
            next_start = None
            if pagination.get("next"):
                raw = parse_qs(urlsplit(pagination["next"]).query).get("start", [])
                if raw and raw[0].isdigit() and start < int(raw[0]) <= 1000:
                    next_start = int(raw[0])
            call.outcome = "completed"
            call.result_count = len(hits)
            return SearchBatch(hits=hits, completed=True, executed_queries=[query], next_start=next_start)
        except requests.RequestException:
            raise ProviderError("SerpApi nu poate fi accesat sau a depășit timpul disponibil.") from None
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("SerpApi a returnat un răspuns invalid. Verificarea nu este finalizată.") from None
        finally:
            call.elapsed_seconds = round(time.monotonic() - began, 2)
