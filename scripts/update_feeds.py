#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_feeds.py — Action de GitHub para actualizar feeds RSS sin alterar su estructura.
Cumple los requisitos de procesar description, op3, om:sec y om:des.

Autor: GPT-5 (basado en tus especificaciones)
"""

import os
import re
import html
import requests
import hashlib
from html import escape

# ===============================================================
# Utilidades generales
# ===============================================================

def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def fetch_xml(url, timeout=20):
    """Descarga un XML y devuelve el texto."""
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Feedbueno-Updater/1.0"})
    r.raise_for_status()
    return r.text

# ===============================================================
# Extracción básica de etiquetas
# ===============================================================

ITEM_RE = re.compile(r"<item\b[^>]*>.*?</item>", re.IGNORECASE | re.DOTALL)

def extract_items(xml_text):
    return ITEM_RE.findall(xml_text)

def extract_tag_text(xml, tag):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    text = m.group(1).strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        text = text[9:-3].strip()
    return text

def find_attr(xml, tag, attr):
    m = re.search(rf"<{tag}\b[^>]*\b{attr}=\"([^\"]+)\"", xml, re.IGNORECASE)
    return m.group(1) if m else None

def strip_cdata(txt):
    if not txt:
        return ""
    if txt.startswith("<![CDATA[") and txt.endswith("]]>"):
        return txt[9:-3].strip()
    return txt.strip()

def extract_enclosure_url(item_xml):
    m = re.search(r'<enclosure\b[^>]*url="([^"]+)"', item_xml, re.IGNORECASE)
    return m.group(1) if m else None

def item_key_from_xml(item_xml):
    guid = extract_tag_text(item_xml, "guid")
    if guid:
        return f"guid::{guid}"
    link = extract_tag_text(item_xml, "link")
    if link:
        return f"link::{link}"
    enc = extract_enclosure_url(item_xml)
    if enc:
        return f"encl::{enc}"
    return "hash::" + hashlib.md5(item_xml.encode("utf-8", errors="ignore")).hexdigest()

def existing_keys_from_feed(feed_xml):
    return {item_key_from_xml(it) for it in extract_items(feed_xml)}

# ===============================================================
# Limpieza y procesamiento de description
# ===============================================================

def clean_html_desc(desc):
    """Limpia y convierte el HTML conservando estructura básica, convierte imágenes, links, listas y mails."""
    if not desc:
        return ""

    # Reemplazar <img> y <a> por sus URLs puras
    desc = re.sub(r'<img\b[^>]*\bsrc="([^"]+)"[^>]*/?>', r'\1', desc, flags=re.IGNORECASE)
    desc = re.sub(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>.*?</a>', r'\1', desc, flags=re.IGNORECASE)

    # Quitar otras etiquetas HTML dejando contenido interno
    desc = re.sub(r"</?(?!ol|ul|li|br|hr)\w+[^>]*>", "", desc)

    # Mantener saltos de línea
    desc = desc.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

    # Sustituir mails por mailto:
    desc = re.sub(r"([\w\.-]+@[\w\.-]+\.\w+)", r"mailto:\1", desc)

    # Detectar URLs
    desc = re.sub(r"(https?://[^\s<>\"]+)", r"<a href='\1'>\1</a>", desc)

    # Detectar imágenes
    desc = re.sub(r"(<a href='(https?://[^']+\.(?:jpg|png|jpeg|gif)[^']*)'>)\2(</a>)",
                  r"<a href='\2'><img src='\2' /></a>", desc, flags=re.IGNORECASE)

    # Detectar listas numeradas
    lines = desc.splitlines()
    formatted = []
    i = 0
    while i < len(lines):
        if re.match(r"\s*\d+[\.\-:]*\s+\S", lines[i]) and not re.match(r"\d{1,2}:\d{2}:\d{2}", lines[i]):
            group = [lines[i]]
            j = i + 1
            while j < len(lines) and re.match(r"\s*\d+[\.\-:]*\s+\S", lines[j]):
                group.append(lines[j])
                j += 1
            if len(group) > 1:
                start = re.match(r"\s*(\d+)", group[0]).group(1)
                formatted.append(f"<ol start='{start}'>")
                for g in group:
                    formatted.append(f"<li>{re.sub(r'^\s*\d+[\.\-:]*\s*', '', g)}</li>")
                formatted.append("</ol>")
                i = j
                continue
        formatted.append(lines[i])
        i += 1
    desc = "\n".join(formatted)

    # Añadir <p> a párrafos sueltos
    parts = [p.strip() for p in re.split(r"\n\s*\n", desc) if p.strip()]
    desc = "".join(f"<p>{p}</p>" if not p.startswith("<") else p for p in parts)

    return desc.strip()

# ===============================================================
# Generación de om:sec y om:des
# ===============================================================

def generate_unique_sec(existing_secs, season=None, episode=None, title=None, desc=None):
    """Genera un identificador om:sec único."""
    base = None
    if season and episode:
        base = f"s{season}e{episode}"
    elif season:
        base = f"s{season}"
    elif episode:
        base = f"e{episode}"
    elif title:
        m = re.search(r"\d+", title)
        if m:
            base = m.group(0)
    elif desc:
        m = re.search(r"\d+", desc)
        if m:
            base = m.group(0)
    if not base:
        base = str(len(existing_secs) + 1)
    sec = base
    counter = 1
    while sec in existing_secs:
        sec = f"{base}-{counter}"
        counter += 1
    existing_secs.add(sec)
    return sec

def build_om_des(desc):
    """Construye el bloque <om:des> escapando el texto pero manteniendo etiquetas."""
    if not desc:
        return "<om:des><div></div></om:des>"
    parts = []
    for part in re.split(r"(<[^>]+>)", desc):
        if part.startswith("<") and part.endswith(">"):
            parts.append(part)
        else:
            parts.append(escape(part))
    return f"<om:des><div>{''.join(parts)}</div></om:des>"

# ===============================================================
# Procesamiento principal de ítem
# ===============================================================

def process_item(it, op3_prefix, existing_secs, atom_link, feed_image):
    title = extract_tag_text(it, "title") or ""
    desc = extract_tag_text(it, "description") or ""
    season = extract_tag_text(it, "itunes:season")
    episode = extract_tag_text(it, "itunes:episode")

    # Enclosure con OP3
    if op3_prefix:
        it = re.sub(
            r'(<enclosure\b[^>]*url=")([^"]+)(")',
            rf'\1{op3_prefix}\2\3',
            it,
            flags=re.IGNORECASE,
        )

    # Generar om:sec
    sec = generate_unique_sec(existing_secs, season, episode, title, desc)
    it = re.sub(r"</item>", f"<om:sec>{sec}</om:sec>\n</item>", it, flags=re.IGNORECASE)

    # Procesar descripción
    new_desc = clean_html_desc(desc)

    # Añadir bloque inicial si no hay <hr>
    if not re.search(r'<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;"', new_desc):
        img_html = f"<a href='{feed_image}'><img src='{feed_image}' /></a>" if feed_image else ""
        link_html = f"<a href='{atom_link}#{sec}'>{atom_link}#{sec}</a>"
        header = (
            f"{title}\n{img_html}\n"
            f"Si no ves las imágenes entra en {link_html}\n"
            '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'
        )
        new_desc = header + new_desc

    # Añadir enlace final al audio
    encl = extract_enclosure_url(it)
    if encl:
        encl_with_prefix = op3_prefix + encl if op3_prefix else encl
        new_desc += f"\n<a href='{encl_with_prefix}'>{encl}</a>"

    # Sustituir descripción
    it = re.sub(
        r"<description\b[^>]*>.*?</description>",
        f"<description><![CDATA[{new_desc}]]></description>",
        it,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Añadir om:des
    om_des = build_om_des(new_desc)
    if "<om:des>" in it:
        it = re.sub(r"<om:des>.*?</om:des>", om_des, it, flags=re.IGNORECASE | re.DOTALL)
    else:
        it = re.sub(r"</item>", om_des + "\n</item>", it, flags=re.IGNORECASE)

    return it

# ===============================================================
# Lógica principal
# ===============================================================

def update_one_feed(podcast_dir):
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "source.txt")
    dest_file = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️ {podcast_dir}: falta source.txt o feed.xml")
        return

    sources = [ln.strip() for ln in read_text(source_file).splitlines() if ln.strip()]
    if not sources:
        print(f"ℹ️ {podcast_dir}: source.txt vacío")
        return

    dest_xml = read_text(dest_file)
    op3_prefix = extract_tag_text(dest_xml, "op3") or ""
    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    feed_image = find_attr(dest_xml, "itunes:image", "href") or ""
    existing = existing_keys_from_feed(dest_xml)
    existing_secs = set(re.findall(r"<om:sec>(.*?)</om:sec>", dest_xml, flags=re.IGNORECASE))

    new_items = []
    for url in sources:
        try:
            src_xml = fetch_xml(url)
            for it in extract_items(src_xml):
                key = item_key_from_xml(it)
                if key not in existing:
                    new_it = process_item(it, op3_prefix, existing_secs, atom_link, feed_image)
                    new_items.append(new_it)
                    existing.add(key)
        except Exception as e:
            print(f"❌ {podcast_dir}: error con {url}: {e}")

    if not new_items:
        print(f"ℹ️ {podcast_dir}: sin ítems nuevos")
        return

    first_item = re.search(r"<item\b", dest_xml, re.IGNORECASE)
    if first_item:
        pos = first_item.start()
        updated = dest_xml[:pos] + "\n".join(new_items) + "\n" + dest_xml[pos:]
    else:
        updated = re.sub(r"</channel>", "\n".join(new_items) + "\n</channel>", dest_xml, flags=re.IGNORECASE)

    write_text(dest_file, updated)
    print(f"✅ {podcast_dir}: añadidos {len(new_items)} ítems nuevos")

def main():
    root = "public"
    for d in os.listdir(root):
        if os.path.isdir(os.path.join(root, d)):
            update_one_feed(d)

if __name__ == "__main__":
    main()