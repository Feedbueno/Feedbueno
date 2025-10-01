#!/usr/bin/env python3
"""
scripts/update_feeds.py

Actualiza feeds RSS a partir de un source.txt en cada carpeta.
Cada carpeta dentro de /public puede contener:
 - feed.xml (feed destino a actualizar)
 - source.txt (lista de feeds origen a fusionar)
"""

import os
import sys
import requests
from pathlib import Path
from lxml import etree

# --- Namespaces ---
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
}

# --- Utilidades XML ---
def parse_xml(text: str):
    """Parsear XML en árbol con lxml."""
    return etree.fromstring(text.encode("utf-8"))

def strip_cdata(text: str | None) -> str:
    """Elimina marcas CDATA de texto."""
    if not text:
        return ""
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()

def existing_keys_from_feed(feed_text: str) -> set[str]:
    """Devuelve los GUID o links de los ítems ya presentes en el feed destino."""
    try:
        root = parse_xml(feed_text)
    except Exception:
        return set()
    keys = set()
    for item in root.findall(".//item"):
        guid = item.findtext("guid")
        link = item.findtext("link")
        if guid:
            keys.add(guid.strip())
        elif link:
            keys.add(link.strip())
    return keys

def item_key_from_xml(item_xml: str) -> str:
    """Devuelve clave única de un ítem (guid o link)."""
    try:
        elem = parse_xml(item_xml)
    except Exception:
        return item_xml[:50]
    guid = elem.findtext("guid")
    link = elem.findtext("link")
    if guid:
        return guid.strip()
    if link:
        return link.strip()
    return etree.tostring(elem, encoding="unicode")[:50]

# --- Fetch remoto ---
def fetch_source_items(url: str) -> list[str]:
    """Descarga un feed y devuelve lista de ítems XML como string."""
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    xml = r.text
    root = parse_xml(xml)
    return [etree.tostring(it, encoding="unicode") for it in root.findall(".//item")]

# --- Procesamiento description ---
def process_description_block(title, link, img, desc, feed_img="", atom_link="", sec_id=""):
    """
    Reconstruye el bloque description para un ítem.
    Respeta etiquetas <img> o <a> ya existentes, no las duplica.
    """
    desc = strip_cdata(desc or "")
    title = strip_cdata(title or "")
    link = strip_cdata(link or "")
    img = strip_cdata(img or "")
    feed_img = strip_cdata(feed_img or "")

    block = desc

    # Si ya contiene <img> o <a>, no añadir de nuevo
    if ("<img" not in desc) and ("<a " not in desc):
        if img:
            block = f'<p><img src="{img}" /></p>\n' + block
        elif feed_img:
            block = f'<p><img src="{feed_img}" /></p>\n' + block

    if link and ("<a " not in desc):
        block += f'\n<p><a href="{link}">Más información</a></p>'

    return block

def replace_description(item_xml: str, new_desc: str, sec_id="", atom_link="") -> str:
    """
    Sustituye el contenido de <description> en un ítem XML.
    """
    try:
        root = parse_xml(item_xml)
    except Exception:
        return item_xml

    desc_elem = root.find("description")
    if desc_elem is None:
        desc_elem = etree.Element("description")
        root.append(desc_elem)

    desc_elem.text = etree.CDATA(new_desc)
    return etree.tostring(root, encoding="unicode")

# --- Procesar un feed destino ---
def process_feed(feed_file: Path, source_urls: list[str]):
    print(f"Processing feed: {feed_file}, sources: {source_urls}")

    feed_xml = feed_file.read_text(encoding="utf-8")
    root = parse_xml(feed_xml)

    channel = root.find("channel")
    if channel is None:
        print(f"❌ No <channel> en {feed_file}")
        return

    # Extraer datos del feed destino
    atom_link_el = channel.find("atom:link", namespaces=NS)
    atom_link = atom_link_el.get("href") if atom_link_el is not None else ""
    itunes_img_el = channel.find("itunes:image", namespaces=NS)
    feed_image = itunes_img_el.get("href") if itunes_img_el is not None else ""

    existing = existing_keys_from_feed(feed_xml)
    print(f" - Items existentes: {len(existing)}")

    new_items = []

    for src in source_urls:
        try:
            raw_items = fetch_source_items(src)
        except Exception as e:
            print(f"⚠️ Error obteniendo {src}: {e}")
            continue

        print(f" - {src}: {len(raw_items)} items")

        for raw in raw_items:
            key = item_key_from_xml(raw)
            if key in existing:
                continue

            # Extraer datos mínimos del item
            try:
                item_elem = parse_xml(raw)
            except Exception:
                continue

            title = item_elem.findtext("title") or ""
            link = item_elem.findtext("link") or ""
            img = None
            img_el = item_elem.find("itunes:image", namespaces=NS)
            if img_el is not None:
                img = img_el.get("href")
            thumb_el = item_elem.find("media:thumbnail", namespaces=NS)
            if thumb_el is not None:
                img = img or thumb_el.get("url")
            desc = item_elem.findtext("description") or ""

            # Construir nueva descripción
            new_desc = process_description_block(title, link, img, desc, feed_image, atom_link, "1")
            replaced = replace_description(raw, new_desc)

            new_items.append(replaced)
            existing.add(key)

    if not new_items:
        print("No se añadieron episodios nuevos.")
        return

    # Insertar nuevos ítems antes del primer <item>
    insertion_block = "\n".join(new_items)
    xml_str = etree.tostring(root, encoding="unicode")

    first_item = xml_str.find("<item")
    if first_item != -1:
        updated_xml = xml_str[:first_item] + insertion_block + "\n" + xml_str[first_item:]
    else:
        updated_xml = xml_str.replace("</channel>", insertion_block + "\n</channel>")

    feed_file.write_text(updated_xml, encoding="utf-8")
    print(f"✅ {feed_file}: añadidos {len(new_items)} nuevos items")

# --- Main ---
def main():
    base = Path("public")
    if not base.exists():
        print("❌ No existe carpeta public/")
        sys.exit(1)

    for folder in base.iterdir():
        if not folder.is_dir():
            continue

        feed_file = folder / "feed.xml"
        src_file = folder / "source.txt"

        print(f"Procesando carpeta: {folder}")
        print(f" - feed.xml existe: {feed_file.exists()}")
        print(f" - source.txt existe: {src_file.exists()}")

        if not feed_file.exists() or not src_file.exists():
            print(" - Se omite carpeta (faltan archivos necesarios)")
            continue

        srcs = [ln.strip() for ln in src_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        print(f" - URLs en source.txt: {srcs}")
        if not srcs:
            print(" - source.txt vacío")
            continue

        process_feed(feed_file, srcs)

if __name__ == "__main__":
    main()