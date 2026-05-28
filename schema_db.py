import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "mappings.db")

PRESETS = {
    "🍳 Recepty": {
        "description": "Název, ingredience a postup přípravy",
        "fields": [
            {"key": "nazev", "label": "Název receptu", "css": "", "jsonld": "name"},
            {"key": "ingredience", "label": "Ingredience", "css": "", "jsonld": "recipeIngredient"},
            {"key": "postup", "label": "Postup přípravy", "css": "", "jsonld": "recipeInstructions"},
            {"key": "cas_pripravy", "label": "Čas přípravy", "css": "", "jsonld": "totalTime"},
            {"key": "porce", "label": "Počet porcí", "css": "", "jsonld": "recipeYield"},
        ],
        "jsonld_type": "Recipe"
    },
    "🛒 Produkty": {
        "description": "Název, cena, popis a SKU produktu",
        "fields": [
            {"key": "nazev", "label": "Název produktu", "css": "", "jsonld": "name"},
            {"key": "cena", "label": "Cena", "css": "", "jsonld": "price"},
            {"key": "popis", "label": "Popis", "css": "", "jsonld": "description"},
            {"key": "sku", "label": "SKU / Kód", "css": "", "jsonld": "sku"},
            {"key": "znacka", "label": "Značka", "css": "", "jsonld": "brand"},
        ],
        "jsonld_type": "Product"
    },
    "📰 Články": {
        "description": "Titulek, autor, datum a obsah článku",
        "fields": [
            {"key": "titulek", "label": "Titulek", "css": "h1", "jsonld": "headline"},
            {"key": "autor", "label": "Autor", "css": "", "jsonld": "author"},
            {"key": "datum", "label": "Datum publikace", "css": "", "jsonld": "datePublished"},
            {"key": "perex", "label": "Perex / Úvod", "css": "", "jsonld": "description"},
            {"key": "obsah", "label": "Obsah článku", "css": "article", "jsonld": "articleBody"},
        ],
        "jsonld_type": "Article"
    },
    "⚙️ Vlastní schema": {
        "description": "Definuj vlastní pole a CSS selektory",
        "fields": [],
        "jsonld_type": None
    }
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS domain_mappings (
            domain TEXT PRIMARY KEY,
            preset TEXT,
            fields TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_mapping(domain: str, preset: str, fields: list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO domain_mappings (domain, preset, fields, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(domain) DO UPDATE SET
            preset=excluded.preset,
            fields=excluded.fields,
            updated_at=CURRENT_TIMESTAMP
    """, (domain, preset, json.dumps(fields, ensure_ascii=False)))
    conn.commit()
    conn.close()


def load_mapping(domain: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT preset, fields FROM domain_mappings WHERE domain = ?", (domain,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"preset": row[0], "fields": json.loads(row[1])}
    return None


def list_saved_domains():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT domain, preset, updated_at FROM domain_mappings ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


init_db()
