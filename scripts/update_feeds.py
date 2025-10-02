#!/usr/bin/env python3
"""
scripts/update_feeds.py

Actualiza feeds locales en /public/**/feed.xml a partir de URLs en source.txt.
Añade items nuevos arriba, aplica transformaciones en description,
gestiona om:sec único, prefijo op3 en enclosure y genera om:des.

Autor: Adaptado según requisitos de Feedbueno
"""

import os
import re
import requests
from lxml import etree
from bs4 import BeautifulSoup

# Namespaces
NSMAP = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "om": "https://omrey86.neocities.org/"
}

# ------------------ Utilidades XML ------------------

def parse_xml(text: str):
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(text.encode("utf-8"), parser=parser)

def tostring_xml(elem) -> str:
    return etree.tostring(elem, encoding="unicode")

def fetch_url(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def strip_cdata(text: str) -> str:
    if text is None:
        return ""
    return re.sub(r"^<!\[CDATA\[|\]\]>$", "", text.strip())

# ------------------ Procesar descripción ------------------

def auto_link_and_format(text: str) -> str:
    """Convierte texto plano en HTML: enlaces, mails, imágenes, listas."""
    soup = BeautifulSoup(text, "html.parser")

    # Enlaces y mails
    for t in soup.find_all(string=True):
        if not t.strip():
            continue
        new_html = t
        # mails
        new_html = re.sub(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
                          r'<a href="mailto:\1">\1</a>', new_html)
        # urls imágenes
        new_html = re.sub(r"(https?://\S+\.(?:jpg|jpeg|png|gif))",
                          r'<a href="\1"><img src="\1" /></a>', new_html)
        # urls normales
        new_html = re.sub(r"(?<![\"'>])(https?://[^\s<]+)",
                          r'<a href="\1">\1</a>', new_html)
        if new_html != t:
            t.replace_with(BeautifulSoup(new_html, "html.parser"))

    # Listas numeradas
    lines = soup.decode().splitlines()
    out = []
    i = 0
    while i < len(lines):
        m = re.match(r"\s*(\d+)[\.\-\)]?\s+(.*)", lines[i])
        if m:
            start = int(m.group(1))
            items = []
            while i < len(lines):
                m2 = re.match(r"\s*(\d+)[\.\-\)]?\s+(.*)", lines[i])
                if not m2:
                    break
                items.append(m2.group(2))
                i += 1
            ol = "<ol start=\"%d\">\n" % start
            for it in items:
                ol += f"<li>{it}</li>\n"
            ol += "</ol>"
            out.append(ol)
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)

def build_description(title, img_url, atom_link, sec_id, enclosure_url, op3_prefix, original_desc):
    """Construye nueva description con título, imagen, aviso, hr y enlace al audio."""
    desc = strip_cdata(original_desc)

    if "<hr style=\"border:0;border-top:1px dashed #ccc" in desc:
        body = desc
    else:
        parts = []
        if title:
            parts.append(f"<p>{title}</p>")
        if img_url:
            parts.append(f'<a href="{img_url}"><img src="{img_url}" /></a>')
        if atom_link and sec_id:
            link = f"{atom_link}#{sec_id}"
            parts.append(f'Si no ves las imágenes entra en <a href="{link}">{link}</a>')
        parts.append('<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />')
        parts.append(desc)
        body = "\n".join(parts)

    # añadir enlace final al audio
    if enclosure_url:
        final_url = (op3_prefix or "") + enclosure_url
        body += f'\n<a href="{final_url}">{enclosure_url}</a>'

    # formatear html
    body = auto_link_and_format(body)

    return etree.CDATA(body)

def build_om_des(description: str):
    """Construye un elemento <om:des> escapando solo texto, no etiquetas."""
    if "<hr" in description:
        parts = description.split('<hr', 1)
        after_hr = "<hr" + parts[1]
        clean_html = auto_link_and_format(after_hr)
        des_elem = etree.Element("{https://omrey86.neocities.org/}des")
        div_elem = etree.Element("div")
        div_elem.text = clean_html
        des_elem.append(div_elem)
        return des_elem
    return None

# ------------------ Procesar feed ------------------

def generate_unique_sec(existing_secs, season, episode, title, desc):
    """Genera om:sec único."""
    if season and episode:
        candidate = f"s{season}e{episode}"
        if candidate not in existing_secs:
            return candidate
    m = re.search(r"\d+", title or desc or "")
    if m:
        candidate = m.group(0)
        if candidate not in existing_secs:
            return candidate
    i = 1
    while True:
        candidate = f"auto{i}"
        if candidate not in existing_secs:
            return candidate
        i += 1

def process_feed(feed_path: str, sources: list[str]):
    print(f"Processing feed: {feed_path}, sources: {sources}")
    with open(feed_path, "r", encoding="utf-8") as f:
        feed_xml = f.read()

    root = parse_xml(feed_xml)
    channel = root.find("channel")
    atom_link = channel.find("atom:link")
    atom_link_href = atom_link.get("href") if atom_link is not None else ""
    itunes_img = channel.find("itunes:image", namespaces=NSMAP)
    channel_img_url = itunes_img.get("href") if itunes_img is not None else ""
    op3_elem = channel.find("op3")
    op3_prefix = op3_elem.text.strip() if op3_elem is not None else ""

    existing_secs = {sec.text for sec in channel.findall(".//om:sec", namespaces=NSMAP)}
    existing_guids = {guid.text for guid in channel.findall("item/guid")}

    print(f" - Items existentes: {len(existing_guids)}")

    new_items = []
    for src in sources:
        try:
            src_xml = fetch_url(src)
            src_root = parse_xml(src_xml)
            items = src_root.findall("channel/item")
            print(f" - {src}: {len(items)} items")
            for item in items:
                guid = item.findtext("guid")
                if guid in existing_guids:
                    continue

                title = item.findtext("title") or ""
                desc = item.findtext("description") or ""
                enclosure = item.find("enclosure")
                enclosure_url = enclosure.get("url") if enclosure is not None else ""

                season = item.findtext("itunes:season", namespaces=NSMAP)
                episode = item.findtext("itunes:episode", namespaces=NSMAP)

                sec_id = generate_unique_sec(existing_secs, season, episode, title, desc)
                existing_secs.add(sec_id)

                new_desc = build_description(title, channel_img_url, atom_link_href,
                                             sec_id, enclosure_url, op3_prefix, desc)

                # reemplazar description
                desc_elem = item.find("description")
                if desc_elem is None:
                    desc_elem = etree.Element("description")
                    item.append(desc_elem)
                desc_elem.text = new_desc

                # añadir om:sec
                sec_elem = etree.Element("{https://omrey86.neocities.org/}sec")
                sec_elem.text = sec_id
                item.append(sec_elem)

                # añadir/actualizar om:des
                om_des = build_om_des(new_desc)
                if om_des is not None:
                    old = item.find("om:des", namespaces=NSMAP)
                    if old is not None:
                        item.remove(old)
                    item.append(om_des)

                # prefijo OP3 en enclosure
                if op3_prefix and enclosure is not None and enclosure_url:
                    enclosure.set("url", op3_prefix + enclosure_url)

                new_items.append(item)
                existing_guids.add(guid)
        except Exception as e:
            print(f"   ⚠️ Error en {src}: {e}")

    if not new_items:
        print(" - No hay ítems nuevos.")
        return

    # Insertar antes del primer item
    first_item = channel.find("item")
    for it in reversed(new_items):
        if first_item is not None:
            channel.insert(channel.index(first_item), it)
        else:
            channel.append(it)

    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(tostring_xml(root))

    print(f"✅ {feed_path}: añadidos {len(new_items)} nuevos items")

# ------------------ Main ------------------

def main():
    base = os.path.join(os.getcwd(), "public")
    for subdir in os.listdir(base):
        path = os.path.join(base, subdir)
        if not os.path.isdir(path):
            continue
        feed_file = os.path.join(path, "feed.xml")
        source_file = os.path.join(path, "source.txt")
        print(f"Procesando carpeta: {path}")
        print(f" - feed.xml existe: {os.path.exists(feed_file)}")
        print(f" - source.txt existe: {os.path.exists(source_file)}")
        if not os.path.exists(feed_file) or not os.path.exists(source_file):
            print(" - Se omite carpeta (faltan archivos necesarios)")
            continue
        with open(source_file, "r", encoding="utf-8") as f:
            srcs = [ln.strip() for ln in f if ln.strip()]
        if not srcs:
            print(" - source.txt vacío")
            continue
        process_feed(feed_file, srcs)

if __name__ == "__main__":
    main()