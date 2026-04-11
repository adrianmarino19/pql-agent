#!/usr/bin/env python3
"""Scrape Celonis PQL docs seeded from the root page sidebar.

The crawler behavior is intentionally constrained:
- Discover URLs only from the root page sidebar/nav.
- Fetch discovered pages in the discovered order.
- Include comments.html, then stop.

Output is JSONL with one record per page, including `full_content` for embedding.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_START_URL = "https://docs.celonis.com/en/pql---process-query-language.html"
DEFAULT_STOP_URL = "https://docs.celonis.com/en/comments.html"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
TARGET_DOMAIN = "docs.celonis.com"
TARGET_PREFIX = "/en/"
PQL_TAXONOMY_CLASS = "taxonomy_celonis_pql"
DEFAULT_WORKERS = 8
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 0.5

_THREAD_LOCAL = threading.local()

LEADING_NOISE_LINES = {"Prev", "Next"}
SEARCH_FEEDBACK_BLOCK = [
    "Search results",
    "No results found",
    "Was this helpful?",
    "Yes",
    "No",
    "Would you like to provide feedback? Just click here to suggest edits.",
]


@dataclass
class PageRecord:
    url: str
    source: str
    position: int
    status_code: int | None
    fetched_at_utc: str
    title: str
    full_content: str
    content_hash_sha256: str
    word_count: int
    error: str | None = None

    def to_json(self) -> str:
        """Convert the record to a JSON string."""
        return json.dumps(self.__dict__, ensure_ascii=False)


def now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 formatted string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonicalize_url(url: str) -> str:
    """Normalize a URL by removing fragments and query parameters."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def is_allowed_doc_page(url: str) -> bool:
    """Check if a URL belongs to the target Celonis documentation domain and path."""
    parts = urlsplit(url)
    return (
        parts.scheme in {"http", "https"}
        and parts.netloc == TARGET_DOMAIN
        and parts.path.startswith(TARGET_PREFIX)
        and parts.path.endswith(".html")
    )


def unique_in_order(items: Iterable[str]) -> list[str]:
    """Return a list of unique items preserving their original order."""
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def select_sidebar_container(soup: BeautifulSoup, base_url: str) -> Tag | None:
    """Find the HTML element containing the sidebar navigation links."""
    selector_candidates = [
        "aside",
        "nav",
        "[role='navigation']",
        "[class*='sidebar']",
        "[id*='sidebar']",
        "[class*='toc']",
        "[id*='toc']",
    ]

    containers: list[Tag] = []
    for selector in selector_candidates:
        containers.extend(soup.select(selector))

    best: Tag | None = None
    best_score = -1
    for container in containers:
        links = container.find_all("a", href=True)
        score = sum(
            1
            for link in links
            if is_allowed_doc_page(canonicalize_url(urljoin(base_url, link["href"])))
        )
        if score > best_score:
            best = container
            best_score = score
    return best


def extract_sidebar_urls(root_html: str, start_url: str) -> list[str]:
    """Extract all valid documentation URLs from the sidebar of the root page."""
    soup = BeautifulSoup(root_html, "html.parser")
    container = select_sidebar_container(soup, start_url)
    if container is None:
        raise RuntimeError("Could not find a sidebar/nav container on the root page.")

    urls: list[str] = []
    for anchor in container.find_all("a", href=True):
        classes = anchor.get("class", [])
        if PQL_TAXONOMY_CLASS not in classes:
            continue
        absolute = canonicalize_url(urljoin(start_url, anchor["href"]))
        if is_allowed_doc_page(absolute):
            urls.append(absolute)
    urls = unique_in_order(urls)

    start_url_canonical = canonicalize_url(start_url)
    if start_url_canonical not in urls:
        urls.insert(0, start_url_canonical)
    return urls


def choose_main_content_container(soup: BeautifulSoup) -> Tag:
    """Identify the main HTML container holding the core documentation content."""
    selector_candidates = [
        "main",
        "article",
        "[role='main']",
        "#content",
        ".content",
        ".topic-content",
        ".documentation-content",
    ]
    containers: list[Tag] = []
    for selector in selector_candidates:
        containers.extend(soup.select(selector))

    if not containers:
        body = soup.body
        if body is None:
            raise RuntimeError("Missing body element.")
        return body

    def score(container: Tag) -> int:
        text = container.get_text(" ", strip=True)
        return len(text)

    return max(containers, key=score)


def clean_text(text: str) -> str:
    """Normalize whitespace and strip boilerplate from extracted text."""
    text = text.replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    lines = strip_boilerplate_lines(lines)
    normalized = " ".join(lines)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized.strip()


def strip_boilerplate_lines(lines: list[str]) -> list[str]:
    """Remove common navigation and feedback text blocks from the content lines."""
    cleaned = list(lines)

    while cleaned and cleaned[0] in LEADING_NOISE_LINES:
        cleaned.pop(0)

    block_len = len(SEARCH_FEEDBACK_BLOCK)
    i = 0
    while i <= len(cleaned) - block_len:
        if cleaned[i : i + block_len] == SEARCH_FEEDBACK_BLOCK:
            del cleaned[i : i + block_len]
            continue
        i += 1

    return cleaned


def extract_full_content(html: str) -> tuple[str, str]:
    """Extract the page title and clean main content from the raw HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for element in soup(["script", "style", "noscript", "svg", "iframe"]):
        element.decompose()

    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    container = choose_main_content_container(soup)

    for noisy in container.select(
        "nav, aside, footer, header, [class*='breadcrumb'], [class*='sidebar'], [class*='toc']"
    ):
        noisy.decompose()

    full_content = clean_text(container.get_text("\n", strip=True))
    return title, full_content


def get_thread_session(user_agent: str) -> requests.Session:
    """Get or create a thread-local requests Session with the specified user agent."""
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})
        _THREAD_LOCAL.session = session
    return session


def is_retryable_error(exc: Exception) -> bool:
    """Determine if a network exception should trigger a retry attempt."""
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is None:
            return True
        return response.status_code == 429 or response.status_code >= 500
    return False


def fetch_url_with_retries(
    url: str,
    timeout: float,
    user_agent: str,
    retries: int = RETRY_ATTEMPTS,
    backoff_base_seconds: float = RETRY_BACKOFF_BASE_SECONDS,
) -> requests.Response:
    """Fetch a URL using a thread-local session, retrying on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            session = get_thread_session(user_agent)
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == retries or not is_retryable_error(exc):
                raise
            sleep_seconds = (backoff_base_seconds * (2 ** (attempt - 1))) + random.uniform(0, 0.2)
            time.sleep(sleep_seconds)

    if last_exc is None:
        raise RuntimeError("Unexpected retry state without exception.")
    raise last_exc


def save_raw_html(raw_dir: Path, content_hash: str, html: str) -> None:
    """Save the raw HTML content to disk using its hash as the filename."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{content_hash}.html").write_text(html, encoding="utf-8")


def process_page(
    position: int,
    url: str,
    timeout: float,
    delay: float,
    user_agent: str,
    raw_dir: Path | None = None,
) -> PageRecord:
    """Fetch, parse, and extract content from a single documentation page."""
    fetched_at = now_utc_iso()
    if delay > 0:
        time.sleep(delay)
    try:
        response = fetch_url_with_retries(url=url, timeout=timeout, user_agent=user_agent)
        title, full_content = extract_full_content(response.text)
        content_hash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
        word_count = len(full_content.split())
        if raw_dir is not None:
            save_raw_html(raw_dir, content_hash, response.text)
        return PageRecord(
            url=url,
            source="root_sidebar",
            position=position,
            status_code=response.status_code,
            fetched_at_utc=fetched_at,
            title=title,
            full_content=full_content,
            content_hash_sha256=content_hash,
            word_count=word_count,
        )
    except Exception as exc:  # noqa: BLE001
        status_code = None
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code
        return PageRecord(
            url=url,
            source="root_sidebar",
            position=position,
            status_code=status_code,
            fetched_at_utc=fetched_at,
            title="",
            full_content="",
            content_hash_sha256="",
            word_count=0,
            error=str(exc),
        )


def run_scrape(
    start_url: str,
    stop_url: str,
    out_path: Path,
    delay: float,
    timeout: float,
    max_pages: int | None,
    user_agent: str,
    workers: int,
    raw_dir: Path | None = None,
) -> None:
    """Orchestrate the scraping process: discover URLs, fetch concurrently, and save records."""
    print(f"Fetching root page: {start_url}")
    root_response = fetch_url_with_retries(url=start_url, timeout=timeout, user_agent=user_agent)
    sidebar_urls = extract_sidebar_urls(root_response.text, start_url)
    print(f"Discovered {len(sidebar_urls)} sidebar URLs on root page.")

    stop_url = canonicalize_url(stop_url)
    if stop_url in sidebar_urls:
        stop_index = sidebar_urls.index(stop_url)
        sidebar_urls = sidebar_urls[: stop_index + 1]
        print(f"Stop URL found. Truncated URL list to {len(sidebar_urls)} entries.")
    else:
        print("Stop URL not present in sidebar list. Using all discovered entries.")

    if max_pages is not None:
        sidebar_urls = sidebar_urls[:max_pages]
        print(f"Applied max-pages={max_pages}. Processing {len(sidebar_urls)} entries.")

    if workers < 1:
        raise ValueError("--workers must be >= 1")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    records_by_position: dict[int, PageRecord] = {}
    successes = 0
    failures = 0
    total = len(sidebar_urls)
    print(f"Fetching pages with workers={workers}...")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_page = {
            executor.submit(process_page, position, url, timeout, delay, user_agent, raw_dir): (position, url)
            for position, url in enumerate(sidebar_urls, start=1)
        }
        completed = 0
        for future in as_completed(future_to_page):
            position, url = future_to_page[future]
            completed += 1
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001
                record = PageRecord(
                    url=url,
                    source="root_sidebar",
                    position=position,
                    status_code=None,
                    fetched_at_utc=now_utc_iso(),
                    title="",
                    full_content="",
                    content_hash_sha256="",
                    word_count=0,
                    error=f"Unhandled worker exception: {exc}",
                )

            records_by_position[position] = record
            if record.error:
                failures += 1
            else:
                successes += 1
            print(f"[{completed}/{total}] Completed {url}")

    with out_path.open("w", encoding="utf-8") as handle:
        for position in range(1, total + 1):
            handle.write(records_by_position[position].to_json() + "\n")

    print(f"Wrote JSONL to: {out_path}")
    print(f"Done. success={successes} failure={failures} total={total}")


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments for the scraper."""
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Celonis docs pages discovered from the root page sidebar "
            "and write one JSON record per page."
        )
    )
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--stop-url", default=DEFAULT_STOP_URL)
    parser.add_argument(
        "--out",
        default="data/scrape/pql_docs.jsonl",
        help="Path to output JSONL file.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Sleep duration in seconds between requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional cap on number of pages processed.",
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of parallel workers for page fetch/extract.",
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help="Optional directory to archive raw HTML per page (e.g. data/raw/). Filename is <content_hash>.html.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the scraper script."""
    args = parse_args()
    run_scrape(
        start_url=canonicalize_url(args.start_url),
        stop_url=canonicalize_url(args.stop_url),
        out_path=Path(args.out),
        delay=args.delay,
        timeout=args.timeout,
        max_pages=args.max_pages,
        user_agent=args.user_agent,
        workers=args.workers,
        raw_dir=Path(args.raw_dir) if args.raw_dir else None,
    )


if __name__ == "__main__":
    main()
