import os
import re
import requests
import uuid

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

def replace_description(item_xml: str, new_desc_html_cdata: str, new_content_html_cdata: str, om_sec: str) -> str:
    # description
    if re.search(r"<description\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<description\b[^>]*>.*?</description>",
            f"<description>{new_desc_html_cdata}</description>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"<description>{new_desc_html_cdata}</description>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    # content:encoded
    if re.search(r"<content:encoded\b", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"<content:encoded\b[^>]*>.*?</content:encoded>",
            f"<content:encoded>{new_content_html_cdata}</content:encoded>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    else:
        item_xml = re.sub(
            r"</item>\s*$",
            f"<content:encoded>{new_content_html_cdata}</content:encoded>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    # om:sec
    if not re.search(r"<om:sec>", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(
            r"</item>\s*$",
            f"<om:sec>{om_sec}</om:sec>\n</item>",
            item_xml,
            flags=re.IGNORECASE | re.DOTALL
        )
    return item_xml

# -------------- detección de HTML "fuerte" --------------

def has_rich_html(text: str) -> bool:
    if not text:
        return False
    return re.search(r"<(a|img|ul|ol|li|h[1-6]|p|br)\b", text, flags=re.IGNORECASE) is not None

# -------------- construcción de la descripción --------------

def process_description_block(title_txt: str, link_txt: str, image_url: str,
                              description_inner: str, atom_link: str, om_sec: str,
                              feed_image: str) -> str:
    header = ""
    if title_txt:
        header += f"<h3>{title_txt}</h3>\n"
    if image_url and image_url != feed_image and link_txt:
        header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n'

    # aviso antes del hr
    aviso = f'<p>Si no ves las imágenes, entra en {atom_link}#{om_sec}</p>\n'
    header += aviso
    header += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    body = strip_cdata(description_inner or "")

    if has_rich_html(body):
        final_html = header + body
        return enc_cdata(final_html)

    # Caso "texto plano": aplicar transformaciones
    # 1) Emails → mailto:
    body = re.sub(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="mailto:\1">\1</a>', body)

    # 2) Enlaces a imágenes → <img> clicable
    def repl_image(m):
        url = m.group(1)
        return f'<a href="{url}"><img src="{url}" /></a>'
    body = re.sub(
        r'(?<!href=")(https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif)(?:\?[^\s<>"\']*)?)',
        repl_image, body)

    # 3) Enlaces normales
    def repl_link(m):
        url = m.group(1)
        return f'<a href="{url}">{url}</a>'
    body = re.sub(
        r'(?<!href=")(https?://[^\s<>"\']+)',
        repl_link, body)

    # 4) Listas
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    new_body_lines = []
    i = 0
    while i < len(lines):
        # lista no ordenada
        if re.match(r"^[-*]\s+", lines[i]):
            ul = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                ul.append("<li>" + re.sub(r"^[-*]\s+", "", lines[i]) + "</li>")
                i += 1
            new_body_lines.append("<ul>" + "".join(ul) + "</ul>")
        # lista ordenada 1. o 1 -
        elif re.match(r"^\d+\s*[-\.]\s+", lines[i]):
            ol = []
            start_num = int(re.match(r"^(\d+)", lines[i]).group(1))
            while i < len(lines) and re.match(r"^\d+\s*[-\.]\s+", lines[i]):
                txt = re.sub(r"^\d+\s*[-\.]\s+", "", lines[i])
                ol.append("<li>" + txt + "</li>")
                i += 1
            new_body_lines.append(f"<ol start=\"{start_num}\">" + "".join(ol) + "</ol>")
        else:
            new_body_lines.append("<p>" + lines[i] + "</p>")
            i += 1
    body = "\n".join(new_body_lines)

    final_html = header + body
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

    # datos del feed destino
    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    feed_image = find_attr(dest_xml, "itunes:image", "href") or ""
    op3_prefix = find_tag_text(dest_xml, "op3")

    om_counter = 1

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

                om_sec = str(om_counter)
                om_counter += 1

                new_desc = process_description_block(
                    strip_cdata(title_inner),
                    strip_cdata(link_inner),
                    img,
                    desc_inner,
                    atom_link,
                    om_sec,
                    feed_image
                )
                new_item = replace_description(raw_item, new_desc, new_desc, om_sec)

                # prefijo OP3 en enclosure
                if op3_prefix:
                    def repl_enclosure(m):
                        url = m.group(1)
                        length = m.group(2)
                        type_ = m.group(3)
                        new_url = op3_prefix + url
                        return f'<enclosure url="{new_url}" length="{length}" type="{type_}"/>'
                    new_item = re.sub(
                        r'<enclosure url="([^"]+)" length="([^"]+)" type="([^"]+)"/>',
                        repl_enclosure,
                        new_item,
                        flags=re.IGNORECASE
                    )

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