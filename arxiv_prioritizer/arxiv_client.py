from __future__ import annotations

import xml.etree.ElementTree as ET
import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests


API_URL = "https://export.arxiv.org/api/query"
PAGE_SIZE = 1000
MIN_REQUEST_INTERVAL_SECONDS = 3
MAX_RETRIES = 5
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def fetch_arxiv_papers(
    category: str = "astro-ph",
    days: int = 7,
    max_results: int | None = None,
) -> list[dict]:
    """Fetch recent arXiv paper metadata for a category.

    If max_results is set, request and return no more than that many papers.
    Returns a list of dicts with title, summary, published, url, authors.
    """
    if max_results is not None and max_results < 1:
        raise ValueError("max_results must be positive")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    category_query = "astro-ph.*" if category == "astro-ph" else category
    date_range = (
        f"{cutoff.strftime('%Y%m%d%H%M')} TO "
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    )
    query = f"cat:{category_query} AND submittedDate:[{date_range}]"
    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "o": "http://a9.com/-/spec/opensearch/1.1/",
    }
    entries = []
    start = 0
    page_size = min(PAGE_SIZE, max_results) if max_results is not None else PAGE_SIZE
    next_request_at = 0.0

    with requests.Session() as session:
        session.headers.update({"User-Agent": "arxiv-prioritizer/1.0"})
        while True:
            params = {
                "search_query": query,
                "start": start,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            response, next_request_at = _request_page(
                session,
                params,
                next_request_at,
            )

            root = ET.fromstring(response.content)
            for entry in root.findall("a:entry", ns):
                title = entry.findtext("a:title", default="", namespaces=ns).strip().replace("\n", " ")
                summary = entry.findtext("a:summary", default="", namespaces=ns).strip().replace("\n", " ")
                published_text = entry.findtext("a:published", default="", namespaces=ns)
                published = (
                    datetime.fromisoformat(published_text.replace("Z", "+00:00"))
                    if published_text
                    else None
                )
                url = entry.find("a:id", ns)
                url = url.text if url is not None else ""
                authors = [
                    author.findtext("a:name", default="", namespaces=ns).strip()
                    for author in entry.findall("a:author", ns)
                    if author.findtext("a:name", default="", namespaces=ns).strip()
                ]

                if published is None or published < cutoff:
                    continue

                entries.append(
                    {
                        "title": title,
                        "summary": summary,
                        "published": published,
                        "url": url,
                        "authors": authors,
                    }
                )
                if max_results is not None and len(entries) >= max_results:
                    break

            total_results = int(root.findtext("o:totalResults", default="0", namespaces=ns))
            start += page_size
            if (
                (max_results is not None and len(entries) >= max_results)
                or start >= total_results
                or not root.findall("a:entry", ns)
            ):
                break

    return entries


def _request_page(
    session: requests.Session,
    params: dict[str, str | int],
    next_request_at: float,
) -> tuple[requests.Response, float]:
    for attempt in range(MAX_RETRIES):
        wait_seconds = next_request_at - time.monotonic()
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            response = session.get(API_URL, params=params, timeout=30)
        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise
            delay = MIN_REQUEST_INTERVAL_SECONDS * (2**attempt)
            logging.warning(
                "arXiv request failed; retrying in %s seconds (attempt %s/%s)",
                delay,
                attempt + 2,
                MAX_RETRIES,
            )
            next_request_at = time.monotonic() + delay
            continue

        next_request_at = time.monotonic() + MIN_REQUEST_INTERVAL_SECONDS
        if response.status_code not in TRANSIENT_STATUS_CODES:
            response.raise_for_status()
            return response, next_request_at

        if attempt == MAX_RETRIES - 1:
            response.raise_for_status()

        delay = max(
            MIN_REQUEST_INTERVAL_SECONDS * (2**attempt),
            _retry_after_seconds(response),
        )
        logging.warning(
            "arXiv returned HTTP %s; retrying in %s seconds (attempt %s/%s)",
            response.status_code,
            delay,
            attempt + 2,
            MAX_RETRIES,
        )
        next_request_at = time.monotonic() + delay

    raise RuntimeError("arXiv request retry loop exited unexpectedly")


def _retry_after_seconds(response: requests.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return 0
    try:
        return max(0, float(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return 0
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
