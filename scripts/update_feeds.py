#!/usr/bin/env python3
"""
update_feeds.py

Procesa feeds locales en public/**/feeds.xml según reglas:

- Lee source.txt junto a cada feed.xml para obtener feeds de origen.
- Inserta items nuevos arriba (antes del primer item).
- Prefija enclosure con <op3> si existe en destino.
- Añade om:sec único.
- Reescribe description según reglas (con BeautifulSoup para respetar HTML ya existente).
- Añade om:des desde la parte de description tras el <hr/>.
"""

import sys
import os
import glob
import requests
import re
from lxml import etree
from pathlib import Path
from html import escape, unescape
from bs4 import BeautifulSoup, NavigableString

NS = {
    'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
    'atom': 'http://www.w3.org/2005/Atom',
    'om': 'http://example.org/om',  # ⚠️ Cambia si tienes namespace real
}

HR_HTML = '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'

# ======================== Funciones principales ========================

def find_feeds(base='public'):
    return [p for p in glob.glob(f'{base}/**/feeds.xml', recursive=True)]

def read_source_list(feed_dir):
    p = Path(feed_dir) / 'source.txt'
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def fetch_feed(url_or_path):
    if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
        r = requests.get(url_or_path, timeout=20)
        r.raise_for_status()
        return r.content
    else:
        return Path(url_or_path).read_bytes()

def parse_xml(content):
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    return etree.fromstring(content, parser=parser)

def first_item(elem):
    return elem.find('.//item')

def canonical_text(node):
    return ''.join(node.itertext()) if node is not None else ''

def get_existing_omsecs(channel_elem):
    return set([el.text for el in channel_elem.findall('.//{*}sec') if el is not None and el.text])

def prefix_enclosure_with_op3(item_elem, op3_value):
    enc = item_elem.find('enclosure')
    if enc is not None and 'url' in enc.attrib and op3_value:
        enc.set('url', op3_value + enc.get('url'))

def generate_om_sec(season, episode, used_set, title, description):
    if season and episode:
        candidate = f's{season}e{episode}'
        if candidate not in used_set:
            return candidate
    for text in (title, description):
        if not text:
            continue
        nums = re.findall(r'\b(\d{1,4})\b', text)
        for n in nums:
            if n not in used_set:
                return n
    base = 1
    while str(base) in used_set:
        base += 1
    return str(base)

def ensure_unique_omsec(used_set, candidate):
    if candidate not in used_set:
        used_set.add(candidate)
        return candidate
    i = 1
    while f'{candidate}-{i}' in used_set:
        i += 1
    final = f'{candidate}-{i}'
    used_set.add(final)
    return final

def strip_op3(url):
    m = re.search(r'https?://', url)
    return url[m.start():] if m else url

# ---------------- Description processing ----------------

def process_description_body(text):
    """Convierte texto plano a HTML respetando HTML existente."""
    if not text:
        return ""
    text = unescape(text)
    soup = BeautifulSoup(text, "html.parser")
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            raw = str(node)
            if not raw.strip():
                continue
            new_html = convert_inline_text(raw)
            if new_html != raw:
                frag = BeautifulSoup(new_html, "html.parser")
                node.replace_with(frag)
    return str(soup)

def convert_inline_text(text):
    """Detecta mails, urls, listas en texto plano."""
    # mails
    text = re.sub(r'([\w\.-]+@[\w\.-]+\.\w+)',
                  r'<a href="mailto:\1">\1</a>', text)
    # urls
    def url_repl(m):
        url = m.group(0)
        if re.search(r'\.(jpg|jpeg|png|gif|webp|svg)(\?|$)', url, re.I):
            return f'<a href="{url}"><img src="{url}" /></a>'
        else:
            return f'<a href="{url}">{url}</a>'
    text = re.sub(r'(https?://[^\s<>"]+)', url_repl, text)
    return text

def make_description(item_elem, channel_elem, orig_desc, itunes_image_href, atom_link_href, om_sec_value):
    has_hr = HR_HTML in orig_desc
    lines = []
    title = item_elem.findtext('title') or ''
    lines.append(escape(title))
    if not has_hr:
        if itunes_image_href:
            lines.append(f'<a href="{itunes_image_href}"><img src="{itunes_image_href}" /></a>')
        if atom_link_href:
            link = f'{atom_link_href}#{om_sec_value}'
            lines.append(f'Si no ves las imágenes entra en <a href="{link}">{link}</a>')
        lines.append(HR_HTML)
    body = process_description_body(orig_desc)
    lines.append(body)
    enc = item_elem.find('enclosure')
    if enc is not None and 'url' in enc.attrib:
        lines.append(f'<a href="{enc.get("url")}">{strip_op3(enc.get("url"))}</a>')
    return etree.CDATA("\n".join(lines))

def add_om_des(item_elem, description_html):
    om_des = item_elem.find('{%s}des' % NS['om'])
    if om_des is not None:
        item_elem.remove(om_des)
    new = etree.Element('{%s}des' % NS['om'])
    div = etree.Element('div')
    div.text = escape(description_html, quote=False)
    new.append(div)
    item_elem.append(new)

# ---------------- Feed processing ----------------

def process_feed(destination_path, source_list):
    dest_bytes = Path(destination_path).read_bytes()
    dest_root = parse_xml(dest_bytes)
    channel = dest_root.find('channel')
    op3_elem = channel.find('op3') if channel is not None else None
    op3_val = op3_elem.text if op3_elem is not None else ''
    atom_link = channel.find('{%s}link' % NS['atom'])
    atom_href = atom_link.get('href') if atom_link is not None else None
    itunes_img = channel.find('itunes:image')
    itunes_href = itunes_img.get('href') if itunes_img is not None else None
    used_omsecs = get_existing_omsecs(channel)
    first_item_elem = first_item(channel)
    insert_index = list(channel).index(first_item_elem) if first_item_elem is not None else len(channel)

    new_items = []
    for src in source_list:
        try:
            src_bytes = fetch_feed(src)
        except Exception as e:
            print(f'Warning: failed to fetch {src}: {e}', file=sys.stderr)
            continue
        src_root = parse_xml(src_bytes)
        src_channel = src_root.find('channel')
        if src_channel is None:
            continue
        for item in src_channel.findall('item'):
            guid = item.findtext('guid') or item.findtext('link') or ''
            if channel.find(f".//item[guid='{guid}']") is not None:
                continue
            new_item = etree.fromstring(etree.tostring(item))
            if op3_val:
                prefix_enclosure_with_op3(new_item, op3_val)
            season = new_item.findtext('{%s}season' % NS['itunes']) or new_item.findtext('season')
            episode = new_item.findtext('{%s}episode' % NS['itunes']) or new_item.findtext('episode')
            title = new_item.findtext('title') or ''
            descr = canonical_text(new_item.find('description')) or ''
            candidate = generate_om_sec(season, episode, used_omsecs, title, descr)
            unique = ensure_unique_omsec(used_omsecs, candidate)
            om_sec_elem = etree.Element('{%s}sec' % NS['om'])
            om_sec_elem.text = unique
            new_item.append(om_sec_elem)
            orig_desc = new_item.findtext('description') or ''
            new_desc_cdata = make_description(new_item, channel, orig_desc, itunes_href, atom_href, unique)
            desc_elem = new_item.find('description')
            if desc_elem is None:
                desc_elem = etree.Element('description')
                new_item.append(desc_elem)
            desc_elem.text = new_desc_cdata
            tail = orig_desc.split(HR_HTML, 1)[1] if HR_HTML in orig_desc else orig_desc
            add_om_des(new_item, tail)
            new_items.append(new_item)

    for new_item in reversed(new_items):
        channel.insert(insert_index, new_item)
    out = etree.tostring(dest_root, encoding='utf-8', pretty_print=True, xml_declaration=True)
    Path(destination_path).write_bytes(out)
    print(f'Updated {destination_path} with {len(new_items)} new items.')

def main():
    args = sys.argv[1:]
    if not args or args[0] == '--all':
        targets = find_feeds()
    else:
        targets = [args[0]]
    for t in targets:
        srcs = read_source_list(Path(t).parent)
        if not srcs:
            print(f'No source.txt for {t}', file=sys.stderr)
            continue
        process_feed(t, srcs)

# ======================== Capa de compatibilidad ========================

def strip_cdata(text: str) -> str:
    if not text:
        return ""
    return text.replace("<![CDATA[", "").replace("]]>", "")

def find_tag_text(xml_or_str, tag: str) -> str:
    if isinstance(xml_or_str, str):
        try:
            root = parse_xml(xml_or_str.encode("utf-8"))
        except Exception:
            return ""
    else:
        root = xml_or_str
    elem = root.find(f".//{tag}", namespaces=NS)
    return elem.text if elem is not None else ""

def find_attr(xml_or_str, tag: str, attr: str) -> str:
    if isinstance(xml_or_str, str):
        try:
            root = parse_xml(xml_or_str.encode("utf-8"))
        except Exception:
            return ""
    else:
        root = xml_or_str
    elem = root.find(f".//{tag}", namespaces=NS)
    return elem.get(attr) if elem is not None and elem.get(attr) else ""

def existing_keys_from_feed(xml_str: str):
    try:
        root = parse_xml(xml_str.encode("utf-8"))
    except Exception:
        return set()
    keys = set()
    for it in root.findall(".//item"):
        guid = it.findtext("guid") or it.findtext("link") or ""
        if guid:
            keys.add(guid)
    return keys

def item_key_from_xml(item_xml: str):
    try:
        root = parse_xml(item_xml.encode("utf-8"))
    except Exception:
        return ""
    guid = root.findtext(".//guid") or root.findtext(".//link") or ""
    return guid

def fetch_source_items(url: str):
    xml_bytes = fetch_feed(url)
    root = parse_xml(xml_bytes)
    items = []
    for it in root.findall(".//item"):
        items.append(etree.tostring(it, encoding="unicode"))
    return items

def process_description_block(title, link, image, desc, feed_image="", atom_link="", sec_id=""):
    dummy_item = etree.Element("item")
    etree.SubElement(dummy_item, "title").text = title
    etree.SubElement(dummy_item, "link").text = link
    etree.SubElement(dummy_item, "description").text = desc
    return make_description(
        dummy_item,
        None,
        desc,
        feed_image,
        atom_link,
        sec_id
    )

def replace_description(item_xml: str, new_desc: str, sec_id="", atom_link=""):
    try:
        root = parse_xml(item_xml.encode("utf-8"))
    except Exception:
        return item_xml
    desc_elem = root.find("description")
    if desc_elem is None:
        desc_elem = etree.Element("description")
        root.append(desc_elem)
    desc_elem.text = etree.CDATA(new_desc)
    return etree.tostring(root, encoding="unicode")

# ======================== Ejecutable ========================

if __name__ == '__main__':
    main()