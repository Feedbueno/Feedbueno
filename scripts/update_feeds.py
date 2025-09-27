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
    Busca un atributo dentro de una etiqueta en un XML.
    Ejemplo: <atom:link href="https://ejemplo.com" />
    find_attr(xml, "atom:link", "href") -> "https://ejemplo.com"
    """
    m = re.search(
        rf"<{tag}\b[^>]*\b{attr}=\"([^\"]+)\"[^>]*/?>",
        xml,
        flags=re.IGNORECASE | re.DOTALL
    )
    return m.group(1) if m else ""

# -------------- utilidades para om:des --------------

def escape_text_but_keep_tags(s: str) -> str:
    """Escapa texto plano pero respeta las etiquetas HTML básicas."""
    if not s:
        return ""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    # revertir etiquetas simples
    s = re.sub(r"&lt;(/?\w+[^&]*)&gt;", r"<\1>", s)
    return s

# -------------- modificación de replace_description --------------

def replace_description(item_xml: str, sec_id: str, atom_link: str) -> str:
    """
    Modifica <description>, añade o reemplaza <om:des> y <om:sec>.
    Respeta <content:encoded> si ya existe en el feed de origen.
    """
    link = f"{atom_link}#{sec_id}" if atom_link else f"#{sec_id}"

    # 1) Obtener contenido de <description>
    desc_inner = strip_cdata(find_tag_text(item_xml, "description"))

    # 2) Insertar aviso antes del <hr>
    desc_with_aviso = desc_inner.replace(
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
        f'<p>Si no ves las imágenes, entra en <a href="{link}">{link}</a></p>\n'
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'
    )

    # 3) Reemplazar <description>
    desc_cdata = enc_cdata(desc_with_aviso)
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

    # 4) Extraer parte después del <hr> y crear <om:des>
    parts = desc_inner.split('<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />', 1)
    extra_part = parts[1] if len(parts) > 1 else ""
    extra_part_escaped = escape_text_but_keep_tags(extra_part.strip())
    om_des_tag = f"<om:des><div>{extra_part_escaped}</div></om:des>"

    if re.search(r"<om:des>", item_xml, flags=re.IGNORECASE):
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

    # 5) Añadir o reemplazar <om:sec>
    if re.search(r"<om:sec>", item_xml, flags=re.IGNORECASE):
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
            # 2. Buscar número en título o descripción
            title = strip_cdata(find_tag_text(item_xml, "title"))
            desc = strip_cdata(find_tag_text(item_xml, "description"))
            m = re.search(r"\d+", title or "") or re.search(r"\d+", desc or "")
            candidate = m.group(0) if m else str(fallback_counter)

    # 3. Evitar colisiones
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
    return guid or strip_cdata(find_tag_text(item_xml, "link")) or strip_cdata(find_tag_text(item_xml, "title"))

def existing_keys_from_feed(xml: str) -> set:
    return {item_key_from_xml(x) for x in findall_items(xml)}

def fetch_source_items(url: str):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return findall_items(r.text)
    except Exception as e:
        print(f"[ERROR] No pude obtener {url}: {e}")
        return []

def update_feed_dir(dir_path: str):
    meta_file = os.path.join(dir_path, "feed_source.txt")
    dest_file = os.path.join(dir_path, "feed.xml")

    if not os.path.exists(meta_file):
        print(f"[WARN] No hay feed_source.txt en {dir_path}")
        return

    source_url = open(meta_file).read().strip()
    if not source_url:
        return

    print(f"[INFO] Actualizando {dir_path} desde {source_url}")

    # cargar destino
    dest_xml = open(dest_file).read() if os.path.exists(dest_file) else "<rss><channel></channel></rss>"

    dest_items = findall_items(dest_xml)
    existing_keys = {item_key_from_xml(x) for x in dest_items}

    source_items = fetch_source_items(source_url)

    counter = 1
    for src_item in source_items:
        key = item_key_from_xml(src_item)
        if key in existing_keys:
            continue
        sec_id = extract_unique_sec_id(src_item, dest_xml, counter)
        counter += 1
        src_item = replace_description(src_item, sec_id, source_url)
        dest_xml = re.sub(r"</channel>", src_item + "\n</channel>", dest_xml, flags=re.IGNORECASE)

    with open(dest_file, "w") as f:
        f.write(dest_xml)

def main():
    base = os.getcwd()
    for entry in os.listdir(base):
        path = os.path.join(base, entry)
        if os.path.isdir(path):
            update_feed_dir(path)

if __name__ == "__main__":
    main()