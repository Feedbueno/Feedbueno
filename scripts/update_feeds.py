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
    """
    Busca atributo en una etiqueta, p.ej. find_attr(xml, "atom:link", "href")
    """
    m = re.search(
        rf"<{tag}\b[^>]*\b{attr}=\"([^\"]+)\"[^>]*/?>",
        xml,
        flags=re.IGNORECASE | re.DOTALL
    )
    return m.group(1) if m else ""

# -------------- helpers para mantener HTML mixto --------------

TOKEN_RE = re.compile(r"\[\[BLOCK(\d+)\]\]")

def protect_blocks(html_text: str):
    tokens = []
    def _store(m):
        tokens.append(m.group(0))
        return f"[[BLOCK{len(tokens)-1}]]"
    t = html_text or ""
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

# -------------- transformaciones inline --------------

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
    if not text:
        return ""
    text = EMAIL_RE.sub(r'<a href="mailto:\1">\1</a>', text)
    def repl_image(m): return f'<a href="{m.group(1)}"><img src="{m.group(1)}" /></a>'
    text = IMG_URL_RE.sub(repl_image, text)
    def repl_link(m): return f'<a href="{m.group(1)}">{m.group(1)}</a>'
    text = LINK_URL_RE.sub(repl_link, text)
    return text

# -------------- listas / reconstrucción --------------

NUM_LIST_LINE = re.compile(r"^(\d+)\s*([)\.\-])\s+(.*)$")
UL_LIST_LINE = re.compile(r"^[-*•]\s+(.*)$")

def detect_lists_from_lines(lines):
    out, i = [], 0
    while i < len(lines):
        stripped = (lines[i] or "").strip()
        if TOKEN_RE.fullmatch(stripped):
            out.append(stripped); i += 1; continue
        m = NUM_LIST_LINE.match(stripped)
        if m:
            start_num = int(m.group(1))
            items = [f"<li>{transform_inline(m.group(3))}</li>"]
            i += 1
            while i < len(lines):
                nxt = (lines[i] or "").strip()
                mm = NUM_LIST_LINE.match(nxt) if nxt else None
                if not mm: break
                items.append(f"<li>{transform_inline(mm.group(3))}</li>"); i += 1
            out.append(f'<ol start="{start_num}">' + "".join(items) + "</ol>")
            continue
        m = UL_LIST_LINE.match(stripped)
        if m:
            items = [f"<li>{transform_inline(m.group(1))}</li>"]
            i += 1
            while i < len(lines):
                nxt = (lines[i] or "").strip()
                mm = UL_LIST_LINE.match(nxt) if nxt else None
                if not mm: break
                items.append(f"<li>{transform_inline(mm.group(1))}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if stripped:
            out.append(f"<p>{transform_inline(stripped)}</p>")
        i += 1
    return "\n".join(out)

# -------------- process_description_block (compatible con variantes) --------------

def process_description_block(title_txt: str, link_txt: str, image_url: str,
                              description_inner: str, feed_img: str = None) -> str:
    """
    Devuelve el HTML combinado (header + body) como cadena sin CDATA.
    Esta firma es la esperada por update_iniciativas.py; update_iniciativas
    usa try_call para intentar variantes y mantener compatibilidad.
    """
    header = ""
    if title_txt: header += f"<h3>{title_txt}</h3>\n"
    if image_url and link_txt and feed_img is not None and image_url != feed_img:
        header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n'
    elif image_url and link_txt and feed_img is None:
        # variante donde no se pasa feed_img: igualmente añadimos la imagen
        header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n'

    header += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    body = strip_cdata(description_inner or "")
    protected, tokens = protect_blocks(body)
    protected = re.sub(r"</p\s*>", "\n", protected, flags=re.IGNORECASE)
    protected = re.sub(r"<p\b[^>]*>", "", protected, flags=re.IGNORECASE)
    protected = re.sub(r"<br\s*/?>", "\n", protected, flags=re.IGNORECASE)
    protected = re.sub(r"(\[\[BLOCK\d+\]\])", r"\n\1\n", protected)
    lines = protected.splitlines()
    rebuilt = detect_lists_from_lines(lines)
    rebuilt = unprotect_blocks(rebuilt, tokens)

    return header + rebuilt

# -------------- util para om:des --------------

def escape_text_but_keep_tags(s: str) -> str:
    """Escapa &, <, > pero intenta no romper etiquetas simples."""
    if not s:
        return ""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    # revertir etiquetas simples <tag ...> y </tag>
    s = re.sub(r"&lt;(/?\w+[^&]*)&gt;", r"<\1>", s)
    return s

# -------------- replace_description (compatible con múltiples firmas) --------------

def replace_description(item_xml: str, *args):
    """
    Flexible:
      - replace_description(item_xml, new_desc_html, sec_id, atom_link)
      - replace_description(item_xml, new_desc_html)
      - replace_description(item_xml, sec_id, atom_link)
    Detecta qué se le pasó y actúa:
      - Si recibe new_desc (parece HTML), lo usa para reemplazar <description>.
      - Si no recibe new_desc, usa la descripción original del item.
    No crea content:encoded; respeta el content:encoded existente.
    """
    # interpretar args
    new_desc = None
    sec_id = None
    atom_link = ""

    # heurística: si el segundo argumento contiene '<' o 'hr' lo tratamos como new_desc
    if len(args) == 0:
        # nada pasado: no modificamos
        return item_xml
    if len(args) == 1:
        a = args[0]
        # si parece HTML -> new_desc; si parece sec_id -> sec_id
        if isinstance(a, str) and ("<" in a or "hr" in a or "<h" in a or "<p" in a):
            new_desc = a
        else:
            sec_id = str(a)
    elif len(args) == 2:
        a, b = args
        # caso probable: (new_desc, sec_id) OR (sec_id, atom_link)
        if isinstance(a, str) and ("<" in a or "hr" in a or "<h" in a or "<p" in a):
            new_desc = a
            sec_id = str(b)
        else:
            sec_id = str(a)
            atom_link = str(b) if b is not None else ""
    elif len(args) >= 3:
        a, b, c = args[:3]
        if isinstance(a, str) and ("<" in a or "hr" in a or "<h" in a or "<p" in a):
            new_desc = a
            sec_id = str(b)
            atom_link = str(c) if c is not None else ""
        else:
            # fallback: assume (sec_id, atom_link, ...)
            sec_id = str(a)
            atom_link = str(b) if b is not None else ""

    # Si sec_id sigue siendo None, intentar extraer om:sec del item
    if not sec_id:
        existing = strip_cdata(find_tag_text(item_xml, "om:sec"))
        sec_id = existing or ""

    link = f"{atom_link}#{sec_id}" if atom_link else f"#{sec_id}" if sec_id else "#"

    # si new_desc está dado, usarlo; si no, usar la descripción original del item
    if new_desc:
        inner_html = strip_cdata(new_desc)
    else:
        inner_html = strip_cdata(find_tag_text(item_xml, "description"))

    # Aviso antes del <hr>
    inner_html_with_aviso = inner_html.replace(
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
        f'<p>Si no ves las imágenes, entra en <a href="{link}">{link}</a></p>\n'
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'
    )

    # Reemplazar <description> con CDATA del inner_html_with_aviso
    desc_cdata = enc_cdata(inner_html_with_aviso)
    if re.search(r"<description\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<description\b[^>]*>.*?</description>",
            f"<description>{desc_cdata}</description>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"<description>{desc_cdata}</description>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Extraer la parte después del <hr> para om:des (usamos inner_html original, no el aviso)
    parts = inner_html.split('<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />', 1)
    extra_part = parts[1] if len(parts) > 1 else ""
    extra_part_escaped = escape_text_but_keep_tags(extra_part.strip())
    om_des_tag = f"<om:des><div>{extra_part_escaped}</div></om:des>"

    if re.search(r"<om:des\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<om:des\b[^>]*>.*?</om:des>",
            om_des_tag,
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"{om_des_tag}\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Añadir/reemplazar om:sec si sec_id presente
    if sec_id:
        if re.search(r"<om:sec\b", item_xml, flags=re.IGNORECASE):
            item_xml = re.sub(
                r"<om:sec\b[^>]*>.*?</om:sec>",
                f"<om:sec>{sec_id}</om:sec>",
                item_xml,
                flags=re.IGNORECASE | re.DOTALL
            )
        else:
            item_xml = re.sub(
                r"</item>\s*$",
                f"<om:sec>{sec_id}</om:sec>\n</item>",
                item_xml,
                flags=re.IGNORECASE | re.DOTALL
            )

    # Respetamos cualquier <content:encoded> que ya exista en item_xml (no lo tocamos)

    return item_xml

# -------------- generación de om:sec --------------

def extract_unique_sec_id(item_xml: str, dest_xml: str, fallback_counter: int) -> str:
    # 0. Respetar si ya existe om:sec en el ítem de origen
    existing_sec = strip_cdata(find_tag_text(item_xml, "om:sec"))
    if existing_sec:
        candidate = existing_sec
    else:
        # 1. Usar season y episode si existen
        season = strip_cdata(find_tag_text(item_xml, "itunes:season"))
        episode = strip_cdata(find_tag_text(item_xml, "itunes:episode"))
        if season and episode:
            candidate = f"s{season}e{episode}"
        else:
            # 2. Buscar número en título o descripción (solo el número)
            title = strip_cdata(find_tag_text(item_xml, "title"))
            desc = strip_cdata(find_tag_text(item_xml, "description"))
            m = re.search(r"\d+", title or "") or re.search(r"\d+", desc or "")
            candidate = m.group(0) if m else str(fallback_counter)

    # 3. Evitar colisiones (con otros om:sec ya en dest_xml)
    existing_secs = set(re.findall(r"<om:sec>(.*?)</om:sec>", dest_xml, flags=re.IGNORECASE))
    while candidate in existing_secs:
        if candidate.isdigit():
            candidate = str(int(candidate) + 1)
        else:
            candidate = candidate + "_x"

    return candidate

# -------------------- utilidades de feed --------------------

def item_key_from_xml(item_xml: str) -> str:
    guid = strip_cdata(find_tag_text(item_xml, "guid"))
    if guid:
        return "guid:" + guid
    link = strip_cdata(find_tag_text(item_xml, "link"))
    if link:
        return "link:" + link
    title = strip_cdata(find_tag_text(item_xml, "title"))
    pub = strip_cdata(find_tag_text(item_xml, "pubDate"))
    return "tp:" + title + "|" + pub

def existing_keys_from_feed(xml: str) -> set:
    return {item_key_from_xml(x) for x in findall_items(xml)}

def fetch_source_items(url: str) -> list:
    r = requests.get(url, timeout=20, headers={"User-Agent": "FeedbuenoUpdater/1.0"})
    r.raise_for_status()
    return findall_items(r.text)

# -------------- actualización por carpeta (usa source.txt / feed.xml) --------------

def update_feed_dir(feed_dir: str):
    source_file = os.path.join(feed_dir, "source.txt")
    dest_file   = os.path.join(feed_dir, "feed.xml")

    if not (os.path.exists(source_file) and os.path.exists(dest_file)):
        print(f"⏭️  Omitido {feed_dir}: falta source.txt o feed.xml")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [ln.strip() for ln in f if ln.strip()]
    if not source_urls: print(f"ℹ️  {feed_dir}: source.txt vacío"); return

    with open(dest_file, "r", encoding="utf-8") as f:
        dest_xml = f.read()

    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    existing = existing_keys_from_feed(dest_xml)
    new_items, sec_counter = [], 1

    for url in source_urls:
        try:
            for raw_item in fetch_source_items(url):
                key = item_key_from_xml(raw_item)
                if key in existing: continue
                sec_id = extract_unique_sec_id(raw_item, dest_xml, sec_counter)
                sec_counter += 1
                # no llamamos a process_description_block aquí; quien llame (update_iniciativas)
                # puede hacerlo y pasar new_desc a replace_description. Para el flujo normal
                # usamos la descripción original del item.
                new_item = replace_description(raw_item, sec_id, atom_link)
                new_items.append(new_item)
                existing.add(key)
        except Exception as e:
            print(f"⚠️  Error leyendo {url}: {e}")

    if not new_items: print(f"= {feed_dir}: sin nuevos episodios"); return

    insertion_block = "\n".join(new_items)
    first_item = re.search(r"<item\b", dest_xml, flags=re.IGNORECASE)
    updated_xml = (
        dest_xml[:first_item.start()] + insertion_block + "\n" + dest_xml[first_item.start():]
        if first_item else
        re.sub(r"</channel>\s*$", insertion_block + "\n</channel>", dest_xml, flags=re.IGNORECASE | re.DOTALL)
    )

    with open(dest_file, "w", encoding="utf-8") as f: f.write(updated_xml)
    print(f"✅ {feed_dir}: añadidos {len(new_items)} episodios nuevos")

# -------------- main --------------

def main():
    base = os.path.join(os.getcwd(), "public")
    if not os.path.isdir(base):
        print("❌ No existe la carpeta 'public'")
        return
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path): update_feed_dir(path)

if __name__ == "__main__":
    main()