import streamlit as st
import json
import csv
import io
import time
import copy
from urllib.parse import urlparse

from schema_db import PRESETS, save_mapping, load_mapping, list_saved_domains
from extractor import preview_extraction, extract_from_url
from crawler import crawl

st.set_page_config(
    page_title="Universal Web Scraper",
    page_icon="🕷️",
    layout="wide"
)

# ── Styl ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; padding: 0.5rem 1.2rem; }
    .field-row { background: #f8f9fa; border-radius: 8px; padding: 0.5rem; margin-bottom: 0.4rem; }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
    .source-badge {
        display: inline-block; font-size: 0.7rem; padding: 1px 6px;
        border-radius: 10px; margin-left: 6px;
        background: #e9ecef; color: #495057;
    }
</style>
""", unsafe_allow_html=True)

st.title("🕷️ Universal Web Scraper")
st.markdown("Skenuj weby, extrahuj strukturovaná data a exportuj do JSON — bez kódu.")

# ── Session state init ────────────────────────────────────────────────────────
if "fields" not in st.session_state:
    st.session_state.fields = []
if "preset_name" not in st.session_state:
    st.session_state.preset_name = list(PRESETS.keys())[0]
if "crawl_results" not in st.session_state:
    st.session_state.crawl_results = []
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = []
if "stop_crawl" not in st.session_state:
    st.session_state.stop_crawl = False
if "stop_extract" not in st.session_state:
    st.session_state.stop_extract = False
if "crawl_running" not in st.session_state:
    st.session_state.crawl_running = False
if "extract_running" not in st.session_state:
    st.session_state.extract_running = False


def parse_keywords(text: str) -> list:
    if not text.strip():
        return []
    return [kw.strip().lower() for kw in text.split(',') if kw.strip()]


def get_jsonld_type() -> str | None:
    preset = PRESETS.get(st.session_state.preset_name, {})
    return preset.get("jsonld_type")


def render_confidence(score: float) -> str:
    pct = int(score * 100)
    cls = "confidence-high" if score >= 0.6 else "confidence-low"
    return f'<span class="{cls}">{pct}%</span>'


# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs([
    "🎯 Krok 1 — Co chceš vytáhnout?",
    "🔍 Krok 2 — Skenování webu",
    "⬇️  Krok 3 — Extrakce & Export"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCHEMA DEFINITION
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Co chceš z webových stránek vytáhnout?")

    # ── Preset výběr ──────────────────────────────────────────────────────────
    col_preset, col_info = st.columns([2, 3])
    with col_preset:
        preset_choice = st.selectbox(
            "Vyber typ dat nebo vlastní schema:",
            options=list(PRESETS.keys()),
            key="preset_name"
        )
    with col_info:
        st.info(f"ℹ️ {PRESETS[preset_choice]['description']}")

    # ── Načtení polí z presetu ────────────────────────────────────────────────
    if preset_choice != "⚙️ Vlastní schema":
        if st.button("Použít tento preset", type="primary"):
            st.session_state.fields = copy.deepcopy(PRESETS[preset_choice]["fields"])
            st.success(f"✅ Načteno {len(st.session_state.fields)} polí z presetu.")

    # ── Vlastní schema — paste JSON nebo manuální ─────────────────────────────
    if preset_choice == "⚙️ Vlastní schema":
        st.markdown("**Vlastní schema** — vlož příklad výstupního JSON nebo přidej pole ručně:")

        json_example = st.text_area(
            "Příklad cílového JSON (volitelné):",
            placeholder='{"nazev": "", "cena": "", "popis": ""}',
            height=100
        )

        if st.button("Načíst pole z JSON"):
            try:
                parsed = json.loads(json_example)
                st.session_state.fields = [
                    {"key": k, "label": k.replace("_", " ").title(), "css": "", "jsonld": ""}
                    for k in parsed.keys()
                ]
                st.success(f"✅ Načteno {len(st.session_state.fields)} polí z JSON.")
            except json.JSONDecodeError:
                st.error("❌ Neplatný JSON formát.")

        if st.button("➕ Přidat pole ručně"):
            st.session_state.fields.append(
                {"key": f"pole_{len(st.session_state.fields)+1}", "label": "", "css": "", "jsonld": ""}
            )

    # ── Zobrazení a editace polí ──────────────────────────────────────────────
    if st.session_state.fields:
        st.markdown("---")
        st.markdown("### 📋 Definice polí a CSS mapování")
        st.caption("Pro každé pole můžeš zadat CSS selektor (např. `h1.title`, `span.price`, `#sku`). JSON-LD se použije automaticky pokud existuje.")

        fields_to_delete = []

        for i, field in enumerate(st.session_state.fields):
            cols = st.columns([1.5, 1.5, 2, 2, 0.5])
            with cols[0]:
                field["key"] = st.text_input(
                    "Klíč (výstup JSON)", value=field["key"],
                    key=f"key_{i}", label_visibility="collapsed" if i > 0 else "visible"
                ) if i == 0 else st.text_input("Klíč", value=field["key"], key=f"key_{i}", label_visibility="collapsed")
            with cols[1]:
                field["label"] = st.text_input(
                    "Popis pole", value=field.get("label", ""),
                    key=f"label_{i}", label_visibility="collapsed"
                )
            with cols[2]:
                field["css"] = st.text_input(
                    "CSS selektor", value=field.get("css", ""),
                    placeholder="např. h1, .price, #sku",
                    key=f"css_{i}", label_visibility="collapsed"
                )
            with cols[3]:
                field["jsonld"] = st.text_input(
                    "JSON-LD klíč", value=field.get("jsonld", ""),
                    placeholder="např. name, price, sku",
                    key=f"jsonld_{i}", label_visibility="collapsed"
                )
            with cols[4]:
                if st.button("🗑️", key=f"del_{i}"):
                    fields_to_delete.append(i)

            # Záhlaví sloupců jen pro první řádek
            if i == 0:
                st.caption("Klíč &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Popis &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; CSS selektor &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; JSON-LD klíč")

        for idx in reversed(fields_to_delete):
            st.session_state.fields.pop(idx)

        # ── Live preview na testovací URL ─────────────────────────────────────
        st.markdown("---")
        st.markdown("### 🧪 Otestuj na jedné URL")
        st.caption("Zadej jednu URL stránky pro ověření, že extrakce funguje správně.")

        col_test, col_btn = st.columns([3, 1])
        with col_test:
            test_url = st.text_input("Testovací URL", placeholder="https://...")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            run_test = st.button("▶ Spustit test", type="primary")

        if run_test and test_url:
            with st.spinner("Extrahuji data..."):
                result = preview_extraction(
                    test_url,
                    st.session_state.fields,
                    get_jsonld_type()
                )

            if "_error" in result:
                st.error(f"❌ Chyba: {result['_error']}")
            else:
                meta = result.get("_meta", {})
                confidence = result.get("_confidence", 0)

                col_conf, col_src = st.columns(2)
                with col_conf:
                    st.markdown(f"**Úspěšnost extrakce:** {render_confidence(confidence)}", unsafe_allow_html=True)
                with col_src:
                    source_type = result.get("_source_type", "—")
                    st.markdown(f"**Hlavní zdroj dat:** `{source_type}`")

                st.markdown("**Výsledek extrakce:**")
                for field in st.session_state.fields:
                    key = field["key"]
                    value = result.get(key)
                    source = meta.get(key, "missing")

                    badge_color = {"json-ld": "🟢", "css": "🔵", "h1-fallback": "🟡", "missing": "🔴"}
                    icon = badge_color.get(source, "⚪")

                    label = field.get("label") or key
                    if value is None:
                        st.markdown(f"{icon} **{label}**: *nenalezeno*")
                    elif isinstance(value, list):
                        st.markdown(f"{icon} **{label}** ({len(value)} položek): `{source}`")
                        with st.expander("Zobrazit"):
                            for v in value[:5]:
                                st.write(f"• {v}")
                    else:
                        preview_val = str(value)[:200] + ("…" if len(str(value)) > 200 else "")
                        st.markdown(f"{icon} **{label}**: {preview_val} `{source}`")

                # Ulož mapování pro tuto doménu
                domain = urlparse(test_url).netloc
                if domain:
                    save_mapping(domain, preset_choice, st.session_state.fields)
                    st.caption(f"💾 Mapování uloženo pro doménu: `{domain}`")

    # ── Uložená mapování ──────────────────────────────────────────────────────
    saved = list_saved_domains()
    if saved:
        with st.expander(f"📂 Uložená mapování ({len(saved)} domén)"):
            for domain, preset, updated in saved:
                col_d, col_p, col_load = st.columns([2, 1.5, 1])
                with col_d:
                    st.write(f"**{domain}**")
                with col_p:
                    st.write(preset)
                with col_load:
                    if st.button("Načíst", key=f"load_{domain}"):
                        mapping = load_mapping(domain)
                        if mapping:
                            st.session_state.fields = mapping["fields"]
                            st.session_state.preset_name = mapping["preset"]
                            st.success(f"✅ Načteno mapování pro {domain}")
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CRAWLER
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Skenování webu")

    col_url, col_delay = st.columns([3, 1])
    with col_url:
        start_url = st.text_input("Startovací URL", placeholder="https://example.com/kategorie")
    with col_delay:
        delay = st.slider("Zpoždění (s)", 0.5, 5.0, 1.0, 0.5)

    # Auto-načtení mapování při zadání URL
    if start_url:
        domain = urlparse(start_url).netloc
        saved_mapping = load_mapping(domain)
        if saved_mapping and saved_mapping["fields"] != st.session_state.fields:
            st.info(f"💡 Pro doménu `{domain}` máme uložené mapování ({saved_mapping['preset']}). Chceš ho načíst?")
            if st.button("Načíst uložené mapování"):
                st.session_state.fields = saved_mapping["fields"]
                st.session_state.preset_name = saved_mapping["preset"]
                st.success("✅ Mapování načteno.")
                st.rerun()

    st.markdown("### 🎯 Filtry pro skenování")
    col3, col4, col5 = st.columns(3)
    with col3:
        kw_url = st.text_input("Hledat v URL (klíčová slova)", placeholder="kruti, hovezi, kureci")
    with col4:
        kw_heading = st.text_input("Hledat v nadpisech", placeholder="krůt, hověz, kuř")
    with col5:
        kw_element = st.text_input("Hledat v prvku stránky", placeholder="krůt, hověz, kuř")
        css_filter = st.text_input("CSS selektor prvku pro filtrování", placeholder=".ingredients-box")

    neg_filter = st.text_input("❌ Negativní filtr — vyloučit stránky s těmito slovy", placeholder="krutony, reklama")
    max_pages = st.number_input("Max. počet stránek ke skenování", 1, 50000, 200)

    if not st.session_state.fields:
        st.warning("⚠️ Nejdřív v Kroku 1 definuj co chceš extrahovat.")

    # ── Start + Stop checkbox ─────────────────────────────────────────────────
    btn_col1, btn_col2 = st.columns([2, 1])
    with btn_col1:
        start_crawl = st.button(
            "🚀 Spustit skenování", type="primary",
            disabled=(not start_url)
        )
    with btn_col2:
        stop_crawl_check = st.checkbox(
            "⏹️ Zastavit skenování",
            key="stop_crawl_checkbox",
            help="Zaškrtni během běhu pro zastavení na konci aktuální stránky"
        )
        if stop_crawl_check:
            st.session_state.stop_crawl = True

    if start_crawl:
        st.session_state.stop_crawl = False
        st.session_state.crawl_results = []

        progress_bar = st.progress(0)
        col_m1, col_m2, col_m3 = st.columns(3)
        m_visited = col_m1.empty()
        m_queue = col_m2.empty()
        m_found = col_m3.empty()
        status = st.empty()
        stop_flag_placeholder = st.empty()
        # Živá tabulka všech nalezených URL
        table_header = st.empty()
        results_table = st.empty()

        live_found = []

        def update_progress(visited, queue_len, found_count, current_url):
            if st.session_state.stop_crawl:
                return
            progress_bar.progress(min(visited / max_pages, 1.0))
            m_visited.metric("Prohledáno", f"{visited} / {max_pages}")
            m_queue.metric("Ve frontě", queue_len)
            m_found.metric("Nalezeno", found_count)
            status.text(f"🔍 {current_url}")

        def on_found(new_item, all_found):
            """Zavolá se okamžitě při každém nálezu — aktualizuje živou tabulku."""
            table_header.markdown(f"**🔴 LIVE — Nalezené URL ({len(all_found)}):**")
            results_table.dataframe(all_found, use_container_width=True, height=min(400, 60 + len(all_found) * 35))

        def stop_check():
            return st.session_state.stop_crawl

        live_found = crawl(
            start_url=start_url,
            keywords_url=parse_keywords(kw_url),
            keywords_heading=parse_keywords(kw_heading),
            keywords_element=parse_keywords(kw_element),
            css_selector=css_filter,
            negative_keywords=parse_keywords(neg_filter),
            max_pages=max_pages,
            delay=delay,
            progress_callback=update_progress,
            stop_check=stop_check,
            found_callback=on_found,
        )

        st.session_state.crawl_results = live_found
        st.session_state.crawl_running = False

        stopped_early = st.session_state.stop_crawl
        st.session_state.stop_crawl = False

        if stopped_early:
            status.warning(f"⏹️ Skenování zastaveno — nalezeno {len(live_found)} stránek.")
        else:
            status.success(f"🏁 Skenování dokončeno — nalezeno {len(live_found)} stránek.")

    # Výsledky vždy zobrazeny pokud existují (mimo if start_crawl blok)

    if st.session_state.crawl_results:
        st.markdown(f"**Nalezené URL ({len(st.session_state.crawl_results)}):**")
        st.dataframe(st.session_state.crawl_results, use_container_width=True, height=400)

        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=["url", "kategorie", "zdroj_shody"])
        writer.writeheader()
        writer.writerows(st.session_state.crawl_results)
        st.download_button(
            "⬇️ Stáhnout nalezené URL (CSV)",
            data=csv_buf.getvalue(),
            file_name="nalezene_url.csv",
            mime="text/csv",
            key="dl_crawl_csv"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — EXTRAKCE & EXPORT
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Extrakce dat & Export")

    crawl_count = len(st.session_state.crawl_results)
    fields_count = len(st.session_state.fields)

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        if crawl_count > 0:
            st.success(f"✅ Připraveno {crawl_count} URL ze skeneru")
        else:
            st.warning("⚠️ Nejdřív spusť skenování v Kroku 2")
    with col_info2:
        if fields_count > 0:
            st.success(f"✅ Definováno {fields_count} polí ke extrakci")
        else:
            st.warning("⚠️ Nejdřív definuj schema v Kroku 1")

    # ── Copy/paste URL input ──────────────────────────────────────────────────
    with st.expander("📋 Zadat URL ručně (copy/paste, max 50)"):
        pasted_urls = st.text_area(
            "Vlož URL adresy — každá na novém řádku:",
            placeholder="https://example.com/stranka-1\nhttps://example.com/stranka-2\n...",
            height=180,
            key="pasted_urls_input"
        )
        if st.button("✅ Použít tyto URL", key="btn_paste_urls"):
            lines = [l.strip() for l in pasted_urls.splitlines() if l.strip().startswith("http")]
            if not lines:
                st.error("❌ Nebyly nalezeny žádné platné URL (musí začínat http).")
            else:
                capped = lines[:50]
                st.session_state.crawl_results = [
                    {"url": u, "kategorie": "manual", "zdroj_shody": "paste"}
                    for u in capped
                ]
                if len(lines) > 50:
                    st.warning(f"⚠️ Vloženo {len(lines)} URL, použito prvních 50.")
                else:
                    st.success(f"✅ Načteno {len(capped)} URL.")
                st.rerun()

    # ── CSV upload fallback ───────────────────────────────────────────────────
    with st.expander("📂 Nebo nahraj CSV s URL"):
        uploaded_csv = st.file_uploader("CSV soubor (sloupec 'url' nebo 'Nalezená URL')", type=["csv"])
        if uploaded_csv:
            content = uploaded_csv.getvalue().decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            url_key = "url" if "url" in (rows[0].keys() if rows else []) else "Nalezená URL"
            st.session_state.crawl_results = [
                {"url": r.get(url_key, ""), "kategorie": r.get("kategorie", ""), "zdroj_shody": ""}
                for r in rows if r.get(url_key)
            ]
            st.success(f"✅ Načteno {len(st.session_state.crawl_results)} URL z CSV")

    # ── Start + Stop checkbox ─────────────────────────────────────────────────
    btn_e1, btn_e2 = st.columns([2, 1])
    with btn_e1:
        start_extract = st.button(
            "⛏️ Spustit extrakci dat", type="primary",
            disabled=(len(st.session_state.crawl_results) == 0 or fields_count == 0)
        )
    with btn_e2:
        stop_extract_check = st.checkbox(
            "⏹️ Zastavit extrakci",
            key="stop_extract_checkbox",
            help="Zaškrtni během běhu pro zastavení po aktuální URL"
        )
        if stop_extract_check:
            st.session_state.stop_extract = True

    if start_extract:
        st.session_state.stop_extract = False

        total = len(st.session_state.crawl_results)
        progress = st.progress(0)
        status = st.empty()
        log = st.empty()

        extracted = []
        errors = 0

        for i, item in enumerate(st.session_state.crawl_results):
            # STOP check
            if st.session_state.stop_extract:
                status.warning(f"⏹️ Extrakce zastavena po {i} záznamech.")
                break

            url = item["url"]
            status.text(f"⏳ Extrahuji ({i+1}/{total}): {url}")

            if i > 0:
                time.sleep(1.0)

            result = preview_extraction(url, st.session_state.fields, get_jsonld_type())

            if "_error" in result:
                errors += 1
                log.warning(f"⚠️ Chyba u {url}: {result['_error']}")
            else:
                result["_kategorie"] = item.get("kategorie", "")
                extracted.append(result)

            progress.progress((i + 1) / total)

        st.session_state.extracted_data = extracted
        st.session_state.extract_running = False
        st.session_state.stop_extract = False

        if not status.empty:
            status.success(f"🏁 Hotovo! Extrahováno {len(extracted)} záznamů, {errors} chyb.")

    # ── Výsledky ──────────────────────────────────────────────────────────────
    if st.session_state.extracted_data:
        data = st.session_state.extracted_data
        total = len(data)
        avg_confidence = sum(d.get("_confidence", 0) for d in data) / total if total > 0 else 0

        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Celkem záznamů", total)
        col_s2.metric("Průměrná úspěšnost", f"{int(avg_confidence*100)}%")
        col_s3.metric("Chybějící data", sum(1 for d in data if d.get("_confidence", 1) < 0.5))

        st.markdown("**Náhled výsledků (posledních 5):**")
        preview_rows = []
        for d in data[-5:]:
            row = {"URL": d.get("_url", ""), "Úspěšnost": f"{int(d.get('_confidence',0)*100)}%"}
            for field in st.session_state.fields:
                k = field["key"]
                v = d.get(k)
                if isinstance(v, list):
                    row[k] = f"[{len(v)} položek]"
                else:
                    row[k] = str(v)[:80] if v else "—"
            preview_rows.append(row)
        st.dataframe(preview_rows, use_container_width=True)

        st.markdown("### ⬇️ Export dat")
        col_e1, col_e2 = st.columns(2)

        with col_e1:
            clean_data = []
            for d in data:
                clean = {f["key"]: d.get(f["key"]) for f in st.session_state.fields}
                clean["_url"] = d.get("_url")
                clean["_kategorie"] = d.get("_kategorie", "")
                clean_data.append(clean)

            st.download_button(
                "⬇️ Stáhnout JSON (čistá data)",
                data=json.dumps(clean_data, ensure_ascii=False, indent=2),
                file_name="extrahovana_data.json",
                mime="application/json",
                type="primary"
            )

        with col_e2:
            st.download_button(
                "⬇️ Stáhnout JSON (s metadaty)",
                data=json.dumps(data, ensure_ascii=False, indent=2),
                file_name="extrahovana_data_meta.json",
                mime="application/json"
            )
