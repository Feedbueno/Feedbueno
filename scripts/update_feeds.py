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

# -------------- detección de HTML "fuerte" --------------

def has_html(text: str) -> bool:
    if not text:
        return False
    return re.search(r"<(a|img|ul|ol|li|h[1-6]|p|br)\b", text, flags=re.IGNORECASE) is not None

# -------------- transformaciones de bloques planos --------------

def transform_plain_block(text: str) -> str:
    """Transforma un bloque de texto plano en HTML enriquecido"""

    # Emails → mailto:
    text = re.sub(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="mailto:\1">\1</a>', text)

    # Imágenes → <a><img>
    def repl_image(m):
        url = m.group(1)
        return f'<a href="{url}"><img src="{url}" /></a>'
    text = re.sub(
        r'(?<!href=")(https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif)(?:\?[^\s<>"\']*)?)',
        repl_image, text)

    # Enlaces normales (ignora imágenes ya convertidas)
    def repl_link(m):
        url = m.group(1)
        return f'<a href="{url}">{url}</a>'
    text = re.sub(
        r'(?<!href=")(https?://[^\s<>"\']+)',
        repl_link, text)

    return text

def detect_lists(lines: list[str]) -> str:
    """Detecta y convierte listas en <ol> o <ul>"""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Lista ordenada tipo "n. texto" o "n - texto"
        m = re.match(r"^(\d+)[\.\-]\s+(.*)", line)
        if m:
            start_num = int(m.group(1))
            ol_items = []
            while i < len(lines):
                mm = re.match(r"^(\d+)[\.\-]\s+(.*)", lines[i])
                if not mm:
                    break
                ol_items.append(f"<li>{transform_plain_block(mm.group(2))}</li>")
                i += 1
            result.append(f'<ol start="{start_num}">' + "".join(ol_items) + "</ol>")
            continue

        # Lista desordenada tipo "- texto"
        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            ul_items = []
            while i < len(lines):
                mm = re.match(r"^[-*]\s+(.*)", lines[i])
                if not mm:
                    break
                ul_items.append(f"<li>{transform_plain_block(mm.group(1))}</li>")
                i += 1
            result.append("<ul>" + "".join(ul_items) + "</ul>")
            continue

        # Si no es lista, párrafo normal
        result.append(f"<p>{transform_plain_block(line)}</p>")
        i += 1

    return "\n".join(result)

def process_description_block(title_txt: str, link_txt: str, image_url: str, description_inner: str) -> str:
    header = ""
    if title_txt:
        header += f"<h3>{title_txt}</h3>\n"
    if image_url and link_txt:
        header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n'
    header += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    body = strip_cdata(description_inner or "")

    # Dividir en bloques <p> o similares
    parts = re.split(r"(<[^>]+>)", body)
    rebuilt = []
    buffer_plain = []

    def flush_plain():
        nonlocal buffer_plain
        if buffer_plain:
            lines = [ln.strip() for ln in buffer_plain if ln.strip()]
            if lines:
                rebuilt.append(detect_lists(lines))
        buffer_plain = []

    for part in parts:
        if part.strip().startswith("<"):
            flush_plain()
            rebuilt.append(part)
        else:
            buffer_plain.append(part)

    flush_plain()
    final_html = header + "".join(rebuilt)
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