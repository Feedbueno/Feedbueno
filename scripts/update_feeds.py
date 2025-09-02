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

def replace_description(item_xml: str, new_desc_html_cdata: str, sec_id: str, atom_link: str) -> str:
    """
    Reemplaza <description>, añade <content:encoded> y <om:sec>.
    También inyecta el aviso de 'Si no ves las imágenes...' con enlace.
    """
    link = f"{atom_link}#{sec_id}"
    desc_html = strip_cdata(new_desc_html_cdata)
    desc_html = desc_html.replace(
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
        f'<p>Si no ves las imágenes, entra en <a href="{link}">{link}</a></p>\n'
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'
    )
    desc_html_cdata = enc_cdata(desc_html)

    # Reemplazar <description>
    if re.search(r"<description\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<description\b[^>]*>.*?</description>",
            f"<description>{desc_html_cdata}</description>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"<description>{desc_html_cdata}</description>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Añadir <content:encoded>
    if re.search(r"<content:encoded\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<content:encoded\b[^>]*>.*?</content:encoded>",
            f"<content:encoded>{desc_html_cdata}</content:encoded>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"<content:encoded>{desc_html_cdata}</content:encoded>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Añadir <om:sec>
    if not re.search(r"<om:sec>", item_xml):
        item_xml = re.sub(
            r"</item>\s*$",
            f"<om:sec>{sec_id}</om:sec>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )

    return item_xml

# -------------- helpers HTML mixto --------------

TOKEN_RE = re.compile(r"\[\[BLOCK(\d+)\]\]")

def protect_blocks(html_text: str):
    tokens = []
    def _store(m):
        tokens.append(m.group(0))
        return f"[[BLOCK{len(tokens)-1}]]"
    t = html_text
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
    text = EMAIL_RE.sub(r'<a href="mailto:\1">\1</a>', text)
    def repl_image(m): return f'<a href="{m.group(1)}"><img src="{m.group(1)}" /></a>'
    text = IMG_URL_RE.sub(repl_image, text)
    def repl_link(m): return f'<a href="{m.group(1)}">{m.group(1)}</a>'
    text = LINK_URL_RE.sub(repl_link, text)
    return text

# -------------- listas --------------

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

# -------------- descripción híbrida --------------

def process_description_block(title_txt: str, link_txt: str, image_url: str,
                              description_inner: str, feed_img: str) -> str:
    header = ""
    if title_txt: header += f"<h3>{title_txt}</h3>\n"
    if image_url and link_txt and image_url != feed_img:
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

    return enc_cdata(header + rebuilt)

# -------------- claves / fetch --------------

def normalize_inner(t: str) -> str:
    t = strip_cdata(t or "")
    return re.sub(r"\s+", " ", t).strip().lower()

def item_key_from_xml(item_xml: str) -> str:
    guid = normalize_inner(find_tag_text(item_xml, "guid"))
    if guid: return "guid:" + guid
    link = normalize_inner(find_tag_text(item_xml, "link"))
    if link: return "link:" + link
    title = normalize_inner(find_tag_text(item_xml, "title"))
    pub = normalize_inner(find_tag_text(item_xml, "pubDate"))
    return "tp:" + title + "|" + pub

def existing_keys_from_feed(xml: str) -> set:
    return {item_key_from_xml(it) for it in findall_items(xml)}

def fetch_source_items(url: str) -> list:
    r = requests.get(url, timeout=20, headers={"User-Agent": "FeedbuenoUpdater/1.0"})
    r.raise_for_status()
    return findall_items(r.text)

# -------------- actualización --------------

def update_feed_dir(feed_dir: str):
    source_file = os.path.join(feed_dir, "source.txt")
    dest_file   = os.path.join(feed_dir, "feed.xml")

    if not (os.path.exists(source_file) and os.path.exists(dest_file)):
        print(f"⏭️  Omitido {feed_dir}: falta source.txt o feed.xml"); return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [ln.strip() for ln in f if ln.strip()]
    if not source_urls: print(f"ℹ️  {feed_dir}: source.txt vacío"); return

    with open(dest_file, "r", encoding="utf-8") as f:
        dest_xml = f.read()

    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    feed_img  = find_attr(dest_xml, "itunes:image", "href") or ""
    op3_prefix = find_tag_text(dest_xml, "op3")

    existing = existing_keys_from_feed(dest_xml)
    new_items, sec_counter = [], 1

    for url in source_urls:
        try:
            for raw_item in fetch_source_items(url):
                key = item_key_from_xml(raw_item)
                if key in existing: continue
                title_inner = find_tag_text(raw_item, "title")
                link_inner  = find_tag_text(raw_item, "link")
                img = find_attr(raw_item, "itunes:image", "href") or find_attr(raw_item, "media:thumbnail", "url") or ""
                desc_inner  = find_tag_text(raw_item, "description")
                new_desc = process_description_block(
                    strip_cdata(title_inner),
                    strip_cdata(link_inner),
                    img,
                    desc_inner,
                    feed_img
                )
                new_item = replace_description(raw_item, new_desc, str(sec_counter), atom_link)

                # Prefix OP3
                if op3_prefix:
                    m = re.search(r'<enclosure\b([^>]*)url="([^"]+)"([^>]*)/>', new_item, flags=re.IGNORECASE)
                    if m:
                        new_url = op3_prefix.strip() + m.group(2)
                        new_item = re.sub(
                            r'(<enclosure\b[^>]*url=")[^"]+(")',
                            rf'\1{new_url}\2',
                            new_item, flags=re.IGNORECASE
                        )

                new_items.append(new_item)
                existing.add(key)
                sec_counter += 1
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
    if not os.path.isdir(base): print("❌ No existe la carpeta 'public'"); return
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path): update_feed_dir(path)

if __name__ == "__main__":
    main()