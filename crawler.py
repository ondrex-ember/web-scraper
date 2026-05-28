import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urlparse, urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

SKIP_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.ico', '.svg', '.webp', '.mp4', '.mp3')


def normalize_url(url: str) -> str:
    return url.split('#')[0].rstrip('/')


def should_skip(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS)


def matches_keywords(text_sources: list, keywords: list) -> bool:
    """Vrátí True pokud alespoň jeden keyword se vyskytuje v alespoň jednom zdroji."""
    return any(kw in source for kw in keywords for source in text_sources)


def crawl(
    start_url: str,
    keywords_url: list,
    keywords_heading: list,
    keywords_element: list,
    css_selector: str,
    negative_keywords: list,
    max_pages: int,
    delay: float,
    progress_callback=None,
    stop_check=None,
    found_callback=None,
) -> list:
    """
    BFS crawler. Vrací list dict: [{url, kategorie, zdroj_shody}]

    progress_callback(visited_count, queue_len, found_count, current_url)
    """
    parsed_start = urlparse(start_url)
    allowed_domain = parsed_start.netloc

    queue = [normalize_url(start_url)]
    visited = set()
    found = []

    while queue and len(visited) < max_pages:
        # STOP check
        if stop_check and stop_check():
            break

        current_url = queue.pop(0)

        if current_url in visited:
            continue
        visited.add(current_url)

        if progress_callback:
            progress_callback(len(visited), len(queue), len(found), current_url)

        try:
            if len(visited) > 1:
                time.sleep(delay)

            response = requests.get(current_url, headers=HEADERS, timeout=10)

            if response.status_code != 200:
                continue
            if "text/html" not in response.headers.get("Content-Type", ""):
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Textové zdroje pro matching
            title_el = soup.find('title')
            h1_el = soup.find('h1')
            element_el = soup.select_one(css_selector) if css_selector else None

            title_text = title_el.get_text(separator=" ").lower() if title_el else ""
            h1_text = h1_el.get_text(separator=" ").lower() if h1_el else ""
            element_text = element_el.get_text(separator=" ").lower() if element_el else ""
            url_lower = current_url.lower()

            all_texts = [url_lower, title_text, h1_text, element_text]

            # Negativní filtr
            if negative_keywords and matches_keywords(all_texts, negative_keywords):
                continue

            # Pozitivní matching
            match_sources = []
            match_category = "ostatni"

            for kw in keywords_url:
                if kw in url_lower:
                    match_sources.append("URL")
                    match_category = kw
                    break

            for kw in keywords_heading:
                if kw in title_text or kw in h1_text:
                    match_sources.append("Nadpis")
                    if match_category == "ostatni":
                        match_category = kw
                    break

            for kw in keywords_element:
                if kw in element_text:
                    match_sources.append("Prvek")
                    if match_category == "ostatni":
                        match_category = kw
                    break

            if match_sources:
                new_item = {
                    "url": current_url,
                    "kategorie": match_category,
                    "zdroj_shody": ", ".join(match_sources)
                }
                found.append(new_item)
                if found_callback:
                    found_callback(new_item, found)

            # Přidej nové linky do fronty
            for a_tag in soup.find_all('a', href=True):
                abs_url = normalize_url(urljoin(current_url, a_tag['href']))
                parsed = urlparse(abs_url)
                if (
                    parsed.netloc == allowed_domain
                    and abs_url not in visited
                    and abs_url not in queue
                    and not should_skip(abs_url)
                ):
                    queue.append(abs_url)

        except Exception:
            continue

    return found
