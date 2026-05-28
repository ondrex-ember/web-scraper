import requests
from bs4 import BeautifulSoup
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_page(url: str, timeout: int = 10):
    """Stáhne stránku a vrátí BeautifulSoup objekt."""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')


def extract_jsonld(soup: BeautifulSoup, jsonld_type: str = None) -> dict:
    """
    Extrahuje JSON-LD structured data ze stránky.
    Pokud je zadán jsonld_type, hledá konkrétní @type (např. 'Recipe', 'Product').
    """
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            clean = script.string or script.text
            data = json.loads(clean.strip())

            # Rozbal @graph pokud existuje
            items = data.get('@graph', data) if isinstance(data, dict) else data
            if isinstance(items, dict):
                items = [items]

            for item in items:
                if jsonld_type is None or item.get('@type') == jsonld_type:
                    return item
        except (json.JSONDecodeError, AttributeError):
            continue
    return {}


def strip_html(text: str) -> str:
    """Odstraní HTML tagy z textu pomocí BeautifulSoup."""
    if not text:
        return text
    return BeautifulSoup(text, 'html.parser').get_text(separator=" ", strip=True)


def clean_instructions(raw) -> list:
    """Normalizuje recipeInstructions — pole stringů nebo HowToStep objektů. Stripuje HTML tagy."""
    if isinstance(raw, str):
        return [strip_html(raw)]
    result = []
    for step in raw:
        if isinstance(step, dict):
            result.append(strip_html(step.get('text', '')))
        elif isinstance(step, str):
            result.append(strip_html(step))
    return [s for s in result if s]


def extract_field_value(soup: BeautifulSoup, jsonld_data: dict, field: dict):
    """
    Extrahuje hodnotu jednoho pole.
    Priorita: JSON-LD → CSS selektor → None
    Vrací (hodnota, zdroj)
    """
    jsonld_key = field.get("jsonld", "")
    css_selector = field.get("css", "").strip()

    # 1. Zkus JSON-LD
    if jsonld_key and jsonld_key in jsonld_data:
        raw = jsonld_data[jsonld_key]

        # Speciální handling pro instrukce
        if jsonld_key == "recipeInstructions":
            return clean_instructions(raw), "json-ld"

        # Speciální handling pro author (může být objekt)
        if isinstance(raw, dict):
            return raw.get("name", str(raw)), "json-ld"
        if isinstance(raw, list) and len(raw) > 0:
            if isinstance(raw[0], dict):
                return raw[0].get("name", str(raw[0])), "json-ld"
            return raw, "json-ld"

        return raw, "json-ld"

    # 2. Zkus CSS selektor
    if css_selector:
        try:
            el = soup.select_one(css_selector)
            if el:
                return el.get_text(separator=" ", strip=True), "css"
        except Exception:
            pass

    # 3. Speciální fallback pro počet porcí — hledá .main-point obsahující číslo + "porcí/porce"
    if field.get("key") == "porce" and not css_selector:
        for el in soup.select(".main-point"):
            text = el.get_text(strip=True)
            if any(word in text.lower() for word in ("porcí", "porce", "portion")):
                return text, "css-fallback"

    # 4. Fallback — zkus h1 pro název pokud nic jiného
    if field.get("key") in ("nazev", "titulek", "name") and not css_selector:
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True), "h1-fallback"

    return None, "missing"


def extract_from_url(url: str, fields: list, jsonld_type: str = None) -> dict:
    """
    Hlavní extrakční funkce.
    Vrací dict s hodnotami a metadaty (zdroj, confidence).
    """
    try:
        soup = fetch_page(url)
    except Exception as e:
        return {"_error": str(e), "_url": url}

    jsonld_data = extract_jsonld(soup, jsonld_type)

    result = {"_url": url, "_source_type": "json-ld" if jsonld_data else "css-only"}
    meta = {}

    for field in fields:
        key = field.get("key")
        if not key:
            continue
        value, source = extract_field_value(soup, jsonld_data, field)
        result[key] = value
        meta[key] = source

    result["_meta"] = meta

    # Spočítej confidence — kolik polí bylo úspěšně extrahováno
    total = len(fields)
    found = sum(1 for k, v in meta.items() if v != "missing")
    result["_confidence"] = round(found / total, 2) if total > 0 else 0.0

    return result


def preview_extraction(url: str, fields: list, jsonld_type: str = None) -> dict:
    """
    Stejné jako extract_from_url, ale zachytí všechny chyby pro UI preview.
    """
    try:
        return extract_from_url(url, fields, jsonld_type)
    except Exception as e:
        return {"_error": str(e), "_url": url, "_confidence": 0.0}
