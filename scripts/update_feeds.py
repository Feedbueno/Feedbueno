# scripts/update_feeds.py

import os
import re
import requests

# -------------- utilidades de texto --------------

CDATA_OPEN = "<![CDATA["
CDATA_CLOSE = "]]>"

def strip_cdata(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    if s.startswith(CDATA_OPEN) and s.endswith(CDATA_CLOSE):
        return s[len(CDATA_OPEN):-len(CDATA_CLOSE)]
    return s

def enc_cdata(s: str) -> str:
    return f"{CDATA_OPEN}{s}{CDATA_CLOSE}"

def findall_items(xml: str):
    return re.findall(r"<item\b[^>]*>.*?</item>", xml, flags=re.IGNORECASE | re.DOTALL)

def find_tag_text(xml: str, tag: str):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else ""

def find_attr(xml: str, tag: str, attr: str):
    m = re.search(rf"<{tag}\b[^>]*\b{attr}=\"([^\"]+)\"[^>]*/?>", xml, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else ""

def replace_description(item_xml: str, new_desc_html_cdata: str) -> str:
    if re.search(r"<description\b", item_xml, flags=re.IGNORECASE):
        return re.sub(
            r"<description\b[^>]*>.*?</description>",
            f"<description>{new_desc_html_cdata}</description>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        return re.sub(
            r"</item>\s*$",
            f"<description>{new_desc_html_cdata}</description>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

# -------------- helpers HTML mixto --------------

TOKEN_RE = re.compile(r"\[\[BLOCK(\d+)\]\]")

def protect_blocks(html_text: str):
    """
    Sustituye bloques HTML que no queremos tocar por tokens temporales.
    Protegemos: <ol>...</ol>, <ul>...</ul>, <a>...</a>, <pre>...</pre>, <code>...</code>
    """
    tokens = []

    def _store(m):
        tokens.append(m.group(0))
        return f"[[BLOCK{len(tokens)-1}]]"

    t = html_text
    # Orden importa: listas antes que <a> (para no trocear enlaces dentro de listas)
    t = re.sub(r"<ol\b[^>]*>.*?</ol>", _store, t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<ul\b[^>]*>.*?</ul>", _store, t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<a\b[^>]*>.*?</a>", _store, t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<pre\b[^>]*>.*?</pre>", _store, t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<code\b[^>]*>.*?</code>", _store, t, flags=re.IGNORECASE | re.DOTALL)
    return t, tokens

def unprotect_blocks(text: str, tokens):
    def replace_token(m):
        idx = int(m.group(1))
        return tokens[idx] if 0 <= idx < len(tokens) else m.group(0)
    return TOKEN_RE.sub(replace_token, text)

# -------------- enriquecidos inline --------------

IMG_URL_RE = re.compile(
    r'(?<!href=")(https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s<>"\']*)?)',
    flags=re.IGNORECASE
)
LINK_URL_RE = re.compile(
    r'(?<!href=")(https?://[^\s<>"\']+)',
    flags=re.IGNORECASE
)
EMAIL_RE = re.compile(
    r'(?<![>\w@])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
)

def transform_inline(text: str) -> str:
    # Emails → mailto:
    text = EMAIL_RE.sub(r'<a href="mailto:\1">\1</a>', text)

    # Enlaces a imágenes → <a><img></a>
    def repl_image(m):
        url = m.group(1)
        return f'<a href="{url}"><img src="{url}" /></a>'
    text = IMG_URL_RE.sub(repl_image, text)

    # Enlaces normales (evita los que ya tienen href="")
    def repl_link(m):
        url = m.group(1)
        return f'<a href="{url}">{url}</a>'
    text = LINK_URL_RE.sub(repl_link, text)

    return text

# -------------- detección de listas --------------

NUM_LIST_LINE = re.compile(r"^(\d+)\s*([)\.\-])\s+(.*)$")  # soporta "n)", "n.", "n-"/"n -"
UL_LIST_LINE = re.compile(r"^[-*•]\s+(.*)$")

def detect_lists_from_lines(lines):
    """
    Convierte secuencias de líneas en <ol>/<ul>.
    - Permite líneas en blanco entre ítems.
    - <ol start="N"> se fija con el primer número detectado.
    - Las líneas que sean solo [[BLOCK#]] se insertan tal cual.
    """
    out = []
    i = 0
    while i < len(lines):
        stripped = (lines[i] or "").strip()

        # Si es un bloque protegido, lo añadimos tal cual
        if TOKEN_RE.fullmatch(stripped):
            out.append(stripped)
            i += 1
            continue

        # Lista ordenada
        m = NUM_LIST_LINE.match(stripped)
        if m:
            start_num = int(m.group(1))
            items = [f"<li>{transform_inline(m.group(3))}</li>"]
            i += 1
            while i < len(lines):
                nxt = (lines[i] or "").strip()
                if not nxt:
                    i += 1
                    continue
                mm = NUM_LIST_LINE.match(nxt)
                if not mm:
                    break
                items.append(f"<li>{transform_inline(mm.group(3))}</li>")
                i += 1
            out.append(f'<ol start="{start_num}">' + "".join(items) + "</ol>")
            continue

        # Lista desordenada
        m = UL_LIST_LINE.match(stripped)
        if m:
            items = [f"<li>{transform_inline(m.group(1))}</li>"]
            i += 1
            while i < len(lines):
                nxt = (lines[i] or "").strip()
                if not nxt:
                    i += 1
                    continue
                mm = UL_LIST_LINE.match(nxt)
                if not mm:
                    break
                items.append(f"<li>{transform_inline(mm.group(1))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Párrafo normal (si hay texto)
        if stripped:
            out.append(f"<p>{transform_inline(stripped)}</p>")
        i += 1

    return "\n".join(out)

# -------------- construcción de la descripción (modo mixto robusto) --------------

def process_description_block(title_txt: str, link_txt: str, image_url: str, description_inner: str) -> str:
    # Cabecera
    header = ""
    if title_txt:
        header += f"<h3>{title_txt}</h3>\n"
    if image_url and link_txt:
        header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n'
    header += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    body = strip_cdata(description_inner or "")

    # 1) Proteger bloques HTML que ya vienen bien formados
    protected, tokens = protect_blocks(body)

    # 2) Pasar <p> y <br> a saltos de línea; quitar tags <p>
    protected = re.sub(r"</p\s*>", "\n", protected, flags=re.IGNORECASE)
    protected = re.sub(r"<p\b[^>]*>", "", protected, flags=re.IGNORECASE)
    protected = re.sub(r"<br\s*/?>", "\n", protected, flags=re.IGNORECASE)

    # 3) Asegurar que los tokens queden en líneas separadas (para no envolverlos en <p>)
    protected = re.sub(r"(\[\[BLOCK\d+\]\])", r"\n\1\n", protected)

    # 4) Partir a líneas y convertir a HTML con listas y párrafos
    lines = protected.splitlines()
    rebuilt = detect_lists_from_lines(lines)

    # 5) Restaurar bloques protegidos
    rebuilt = unprotect_blocks(rebuilt, tokens)

    final_html = header + rebuilt
    return enc_cdata(final_html)

# -------------- claves para deduplicar --------------

def normalize_inner(t: str) -> str:
    t = strip_cdata(t or "")
    return re.sub(r"\s+", " ", t).strip().lower()

def item_key_from_xml(item_xml: str) -> str:
    guid = normalize_inner(find_tag_text(item_xml, "guid"))
    if guid:
        return "guid:" + guid
    link = normalize_inner(find_tag_text(item_xml, "link"))
    if link:
        return "link:" + link
    title = normalize_inner(find_tag_text(item_xml, "title"))
    pub = normalize_inner(find_tag_text(item_xml, "pubDate"))
    return "tp:" + title + "|" + pub

def existing_keys_from_feed(xml: str) -> set:
    return {item_key_from_xml(it) for it in findall_items(xml)}

# -------------- obtención de ítems del feed origen (crudos) --------------

def fetch_source_items(url: str) -> list:
    r = requests.get(url, timeout=20, headers={
        "User-Agent": "FeedbuenoUpdater/1.0 (+https://feedbueno.es)"
    })
    r.raise_for_status()
    return findall_items(r.text)

# -------------- actualización por carpeta --------------

def update_feed_dir(feed_dir: str):
    source_file = os.path.join(feed_dir, "source.txt")
    dest_file = os.path.join(feed_dir, "feed.xml")

    if not (os.path.exists(source_file) and os.path.exists(dest_file)):
        print(f"⏭️  Omitido {feed_dir}: falta source.txt o feed.xml")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [ln.strip() for ln in f if ln.strip()]

    if not source_urls:
        print(f"ℹ️  {feed_dir}: source.txt vacío")
        return

    with open(dest_file, "r", encoding="utf-8") as f:
        dest_xml = f.read()

    existing = existing_keys_from_feed(dest_xml)
    new_items = []

    for url in source_urls:
        try:
            for raw_item in fetch_source_items(url):
                key = item_key_from_xml(raw_item)
                if key in existing:
                    continue

                title_inner = find_tag_text(raw_item, "title")
                link_inner  = find_tag_text(raw_item, "link")
                img = (
                    find_attr(raw_item, "itunes:image", "href")
                    or find_attr(raw_item, "media:thumbnail", "url")
                    or ""
                )
                desc_inner = find_tag_text(raw_item, "description")
                new_desc = process_description_block(
                    strip_cdata(title_inner),
                    strip_cdata(link_inner),
                    img,
                    desc_inner
                )
                new_item = replace_description(raw_item, new_desc)

                new_items.append(new_item)
                existing.add(key)
        except Exception as e:
            print(f"⚠️  Error leyendo {url}: {e}")

    if not new_items:
        print(f"= {feed_dir}: sin nuevos episodios")
        return

    # Insertar arriba (antes del primer <item>)
    insertion_block = "\n".join(new_items)
    first_item = re.search(r"<item\b", dest_xml, flags=re.IGNORECASE)
    if first_item:
        insert_pos = first_item.start()
        updated_xml = dest_xml[:insert_pos] + insertion_block + "\n" + dest_xml[insert_pos:]
    else:
        updated_xml = re.sub(r"</channel>\s*$", insertion_block + "\n</channel>", dest_xml,
                             flags=re.IGNORECASE | re.DOTALL)

    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(updated_xml)

    print(f"✅ {feed_dir}: añadidos {len(new_items)} episodios nuevos (insertados arriba)")

# -------------- main --------------

def main():
    base = os.path.join(os.getcwd(), "public")
    if not os.path.isdir(base):
        print("❌ No existe la carpeta 'public'")
        return

    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            update_feed_dir(path)

if __name__ == "__main__":
    main()