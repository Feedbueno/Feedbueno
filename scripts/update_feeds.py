#!/usr/bin/env python3
"""
update_feeds.py

Recorre public/*, para cada carpeta con feed.xml + source.txt:
- Descarga feeds origen listados en source.txt
- Extrae items nuevos y los inserta arriba del feed destino (feed.xml)
- Aplica prefijo op3 a enclosure si existe en feed destino
- Genera un om:sec único por item (preferencia sXeY, luego números en title/desc, luego incremental)
- Reescribe description según las reglas indicadas y lo guarda como CDATA
- Añade om:des con el fragmento posterior al HR (escapando solo texto fuera de tags)
- Logs detallados
- Exporta funciones de compatibilidad para ser importadas por otros scripts
"""

from __future__ import annotations
import sys
import os
import re
import requests
from pathlib import Path
from typing import List, Optional, Set
from lxml import etree
from bs4 import BeautifulSoup, NavigableString, Tag
import html

# ---------------- Config / Namespaces ----------------
NS_ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
NS_ATOM = "http://www.w3.org/2005/Atom"
NS_MEDIA = "http://search.yahoo.com/mrss/"
NS_OM = "http://example.org/om"   # cambia si tienes otro namespace real

NSMAP = {
    'itunes': NS_ITUNES,
    'atom': NS_ATOM,
    'media': NS_MEDIA,
    'om': NS_OM,
}

HR_HTML = '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'

# ----------------- Helpers XML -----------------

def parse_xml_bytes(content: bytes):
    """Parse bytes into lxml Element using recover to tolerate some errors."""
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    return etree.fromstring(content, parser=parser)

def parse_xml_text(text: str):
    return parse_xml_bytes(text.encode('utf-8'))

def to_string(elem) -> str:
    return etree.tostring(elem, encoding='unicode')

def ensure_qname(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"

# ----------------- File discovery -----------------

def find_feed_paths(base: str = "public") -> List[Path]:
    basep = Path(base)
    if not basep.exists():
        return []
    return [p for p in basep.rglob("feed.xml")]

def read_source_list_for_folder(folder: Path) -> List[str]:
    p = folder / "source.txt"
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]

# ----------------- Fetching -----------------

def fetch_feed_content(url_or_path: str) -> Optional[bytes]:
    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            r = requests.get(url_or_path, timeout=30)
            r.raise_for_status()
            return r.content
        else:
            p = Path(url_or_path)
            if p.exists():
                return p.read_bytes()
    except Exception as e:
        print(f"  ⚠️ fetch error for {url_or_path}: {e}")
    return None

# ----------------- om:sec generation -----------------

def get_existing_omsecs(channel_elem) -> Set[str]:
    found = set()
    for el in channel_elem.findall('.//{%s}sec' % NS_OM):
        if el is not None and el.text:
            found.add(el.text.strip())
    # also accept plain <om:sec> without namespace if present
    for el in channel_elem.findall('.//sec'):
        if el is not None and el.text:
            found.add(el.text.strip())
    return found

def generate_candidate_from_season_episode(item_elem) -> Optional[str]:
    # try namespaced itunes
    season = item_elem.findtext('{%s}season' % NS_ITUNES) or item_elem.findtext('season')
    episode = item_elem.findtext('{%s}episode' % NS_ITUNES) or item_elem.findtext('episode')
    if season and episode:
        try:
            s = int(season)
            e = int(episode)
            return f's{s}e{e}'
        except Exception:
            return None
    return None

def find_first_number_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'\b(\d{1,5})\b', text)
    if m:
        return m.group(1)
    return None

def make_unique_omsec(used: Set[str], candidate: str) -> str:
    base = candidate
    if base == '':
        base = '1'
    if base not in used:
        used.add(base)
        return base
    i = 1
    while True:
        cand = f"{base}-{i}"
        if cand not in used:
            used.add(cand)
            return cand
        i += 1

def create_omsec_for_item(item_elem, used_set: Set[str]) -> str:
    # 1) season/episode
    c = generate_candidate_from_season_episode(item_elem)
    if c and c not in used_set:
        used_set.add(c)
        return c
    # 2) try numbers in title or description
    title = (item_elem.findtext('title') or '') + ' '
    desc = ''.join(item_elem.findtext('description') or '')
    for text in (title, desc):
        num = find_first_number_in_text(text)
        if num and num not in used_set:
            used_set.add(num)
            return num
    # 3) fallback incremental number (max numeric in used_set +1) or '1', ensure unique
    numeric_parts = [int(re.sub(r'\D', '', s)) for s in used_set if re.search(r'\d', s)]
    base = (max(numeric_parts) + 1) if numeric_parts else 1
    candidate = str(base)
    while candidate in used_set:
        base += 1
        candidate = str(base)
    used_set.add(candidate)
    return candidate

# ----------------- Description processing -----------------

def contains_hr(text: str) -> bool:
    if not text:
        return False
    return HR_HTML in text

def convert_inline_text_to_html(text: str) -> str:
    """
    Convert plain text to HTML:
    - emails -> mailto
    - urls -> <a>, image urls -> <a><img/>
    - keep link text same (except emails)
    """
    if not text:
        return ''
    # replace mails
    text = re.sub(r'([\w\.-]+@[\w\.-]+\.\w+)', r'<a href="mailto:\1">\1</a>', text)
    # url -> link or image
    def url_repl(m):
        url = m.group(0)
        if re.search(r'\.(jpg|jpeg|png|gif|webp|svg)(?:\?|$)', url, re.I):
            return f'<a href="{url}"><img src="{url}" /></a>'
        else:
            return f'<a href="{url}">{url}</a>'
    text = re.sub(r'(https?://[^\s<>"]+)', url_repl, text)
    return text

def lines_to_list_html(lines: List[str]) -> Optional[str]:
    """
    Detect consecutive numbered lines and build <ol start="X"> or <ul>.
    Returns HTML string or None if not transformed.
    """
    # normalize line starts
    items = []
    for ln in lines:
        mnum = re.match(r'^\s*(\d+)[\.\-\)\s]*\s*(.*)$', ln)
        if mnum:
            items.append(('ol', int(mnum.group(1)), mnum.group(2).strip()))
        else:
            mbul = re.match(r'^\s*[-\*\u2022]\s*(.*)$', ln)
            if mbul:
                items.append(('ul', None, mbul.group(1).strip()))
            else:
                items.append((None, None, ln.strip()))
    # detect runs of ol or ul
    out_parts = []
    i = 0
    n = len(items)
    changed = False
    while i < n:
        typ, start, content = items[i]
        if typ == 'ol':
            # collect run
            start_num = start
            ol_items = []
            j = i
            while j < n and items[j][0] == 'ol':
                ol_items.append((items[j][1], items[j][2]))
                j += 1
            # build ol with start = first's number
            changed = True
            out = [f'<ol start="{ol_items[0][0]}">']
            for _, txt in ol_items:
                out.append(f'<li>{convert_inline_text_to_html(html.escape(txt))}</li>')
            out.append('</ol>')
            out_parts.append('\n'.join(out))
            i = j
            continue
        elif typ == 'ul':
            j = i
            ul_items = []
            while j < n and items[j][0] == 'ul':
                ul_items.append(items[j][2])
                j += 1
            changed = True
            out = ['<ul>']
            for txt in ul_items:
                out.append(f'<li>{convert_inline_text_to_html(html.escape(txt))}</li>')
            out.append('</ul>')
            out_parts.append('\n'.join(out))
            i = j
            continue
        else:
            # normal paragraph
            if content != '':
                out_parts.append(f'<p>{convert_inline_text_to_html(html.escape(content))}</p>')
            i += 1
    if changed:
        return '\n'.join(out_parts)
    return None

def process_description_fragment(orig_desc: str, feed_image_href: Optional[str], atom_link_href: Optional[str], om_sec_value: str) -> str:
    """
    Build final description as CDATA string following rules:
    - Unescape if escaped and wrap in CDATA at the end
    - First line: title will be prepended by caller
    - Second line: itunes image as <a><img/></a> (use feed_image_href)
    - Third line: "Si no ves..." with atom:link + # + om:sec
    - Fourth line: HR_HTML
    - Then original body processed: keep existing tags, only transform plain text nodes
    - Final line: enclosure link (prefixed URL as href, unprefixed as text)
    """
    body_orig = orig_desc or ''
    # We'll parse body_orig with BeautifulSoup and transform only text nodes
    soup = BeautifulSoup(body_orig, "html.parser")
    # If the entire body was plain text (no tags), soup will have .strings only; we'll split lines and handle lists
    has_tags = any(isinstance(ch, Tag) for ch in soup.contents)
    transformed_body = ''
    if not has_tags:
        # plain text -> handle lists, paragraphs, inline conversions
        lines = [ln.rstrip() for ln in body_orig.splitlines()]
        # try lists
        list_html = lines_to_list_html(lines)
        if list_html:
            transformed_body = list_html
        else:
            # wrap paragraphs
            paras = []
            cur_para_lines = []
            for ln in lines:
                if ln.strip() == '':
                    if cur_para_lines:
                        paras.append(' '.join(cur_para_lines))
                        cur_para_lines = []
                else:
                    cur_para_lines.append(ln.strip())
            if cur_para_lines:
                paras.append(' '.join(cur_para_lines))
            paras_html = [f'<p>{convert_inline_text_to_html(html.escape(p))}</p>' for p in paras]
            transformed_body = '\n'.join(paras_html)
    else:
        # Mixed HTML: traverse and replace NavigableString nodes by processed HTML fragments
        def recurse_replace(node):
            for child in list(node.contents):
                if isinstance(child, NavigableString):
                    text = str(child)
                    if not text.strip():
                        continue
                    # transform lists if multiline
                    if '\n' in text:
                        lines = [ln.rstrip() for ln in text.splitlines()]
                        list_html = lines_to_list_html(lines)
                        if list_html:
                            frag = BeautifulSoup(list_html, 'html.parser')
                            child.replace_with(frag)
                            continue
                    new_html = convert_inline_text_to_html(text)
                    frag = BeautifulSoup(new_html, 'html.parser')
                    child.replace_with(frag)
                elif isinstance(child, Tag):
                    recurse_replace(child)
        recurse_replace(soup)
        transformed_body = str(soup)

    # final: replace mails without mailto done earlier, keep images as <img> tags when present
    # we will not double-wrap existing <a> or <img>

    # Return transformed_body string (without enclosing title/headers)
    return transformed_body

def build_full_description(title_text: str, orig_desc: str, itunes_image_href: Optional[str], atom_link_href: Optional[str], om_sec_value: str, enclosure_prefixed_url: Optional[str], enclosure_plain_url: Optional[str]) -> str:
    """
    Build the 4 header lines + body + final enclosure link. Wrap result in CDATA.
    - title_text: plain text title (we will escape and insert)
    """
    # Unescape &lt; &gt; etc if present
    # If orig_desc contains escaped entities like &lt; then unescape them for processing (user asked)
    unescaped_orig = html.unescape(orig_desc or '')

    # Check whether orig already contains HR_HTML
    has_hr = contains_hr(unescaped_orig)

    parts = []
    # 1) title in first line (as plain text)
    parts.append(html.escape(title_text or ''))
    # 2-4 header lines only if origin doesn't already contain HR_HTML
    if not has_hr:
        # 2) image: prefer itunes image href
        if itunes_image_href:
            parts.append(f'<a href="{itunes_image_href}"><img src="{itunes_image_href}" /></a>')
        else:
            parts.append('')  # empty line if no image
        # 3) Si no ves...
        if atom_link_href:
            link = f'{atom_link_href}#{om_sec_value}'
            parts.append(f'Si no ves las imágenes entra en <a href="{link}">{link}</a>')
        else:
            parts.append('')
        # 4) HR
        parts.append(HR_HTML)
    # Body
    body_html = process_description_fragment(unescaped_orig, itunes_image_href, atom_link_href, om_sec_value)
    parts.append(body_html)
    # final enclosure link: href = enclosure_prefixed_url, text = enclosure_plain_url
    if enclosure_prefixed_url and enclosure_plain_url:
        parts.append(f'<a href="{enclosure_prefixed_url}">{html.escape(enclosure_plain_url)}</a>')
    # join with newlines
    full = '\n'.join([p for p in parts if p is not None])
    return full

# ----------------- om:des generation -----------------

def build_om_des_from_description(orig_desc: str) -> str:
    """
    From original description text, take the part AFTER HR_HTML (if present),
    parse as HTML fragment, then escape text nodes but keep tags.
    Return HTML string to be placed inside <om:des><div>...</div></om:des>
    """
    tail = orig_desc.split(HR_HTML, 1)[1] if HR_HTML in orig_desc else orig_desc or ''
    # parse tail as fragment
    frag = BeautifulSoup(tail, 'html.parser')
    # escape text nodes only
    def escape_text_nodes(node):
        for child in list(node.contents):
            if isinstance(child, NavigableString):
                # replace with escaped text (but keep as NavigableString)
                escaped = html.escape(str(child))
                child.replace_with(escaped)
            elif isinstance(child, Tag):
                escape_text_nodes(child)
    escape_text_nodes(frag)
    # get inner HTML
    inner = ''.join(str(c) for c in frag.contents)
    return inner

# ----------------- Core feed processing -----------------

def prefix_enclosure_if_op3(item_elem, op3_value: Optional[str]):
    if not op3_value:
        return None, None
    enc = item_elem.find('enclosure')
    if enc is None or 'url' not in enc.attrib:
        return None, None
    orig = enc.get('url')
    pref = f"{op3_value}{orig}"
    enc.set('url', pref)
    return pref, orig

def item_exists_in_channel(channel_elem, item_key: str) -> bool:
    # search by guid or link matching item_key
    for it in channel_elem.findall('.//item'):
        g = it.findtext('guid')
        l = it.findtext('link')
        if (g and g.strip() == item_key) or (l and l.strip() == item_key):
            return True
    return False

def extract_item_key_from_elem(item_elem) -> str:
    g = item_elem.findtext('guid')
    l = item_elem.findtext('link')
    if g and g.strip():
        return g.strip()
    if l and l.strip():
        return l.strip()
    # fallback: title+pubDate
    title = item_elem.findtext('title') or ''
    pub = item_elem.findtext('pubDate') or ''
    return (title + '||' + pub)[:200]

def insert_items_before_first(channel_elem, new_items: List[etree._Element]):
    # find first <item>
    items = channel_elem.findall('item')
    if items:
        first = items[0]
        parent = first.getparent()
        idx = parent.index(first)
        # insert in reversed order so first of new_items is top-most
        for ni in reversed(new_items):
            # ensure tail contains a blank line separation
            parent.insert(idx, ni)
            ni.tail = '\n'
    else:
        # no items -> append to channel before </channel>
        for ni in new_items:
            channel_elem.append(ni)
            ni.tail = '\n'

# ----------------- Compatibility functions (public API) -----------------

def find_attr(xml_or_text: str, tag: str, attr: str) -> Optional[str]:
    try:
        if isinstance(xml_or_text, (str, bytes)):
            root = parse_xml_text(xml_or_text) if isinstance(xml_or_text, str) else parse_xml_bytes(xml_or_text)
        else:
            root = xml_or_text
        elem = root.find(f'.//{tag}', namespaces=NSMAP)
        if elem is None:
            # try without namespaces
            elem = root.find(f'.//{tag}')
        if elem is not None:
            return elem.get(attr)
    except Exception:
        return None
    return None

def find_tag_text(xml_or_text: str, tag: str) -> Optional[str]:
    try:
        if isinstance(xml_or_text, (str, bytes)):
            root = parse_xml_text(xml_or_text) if isinstance(xml_or_text, str) else parse_xml_bytes(xml_or_text)
        else:
            root = xml_or_text
        elem = root.find(f'.//{tag}', namespaces=NSMAP)
        if elem is None:
            elem = root.find(f'.//{tag}')
        if elem is not None and elem.text:
            return elem.text
    except Exception:
        return None
    return None

def existing_keys_from_feed_text(feed_text: str) -> Set[str]:
    try:
        root = parse_xml_text(feed_text)
    except Exception:
        return set()
    keys = set()
    for it in root.findall('.//item'):
        key = extract_item_key_from_elem(it)
        keys.add(key)
    return keys

def fetch_source_items_list(url: str) -> List[str]:
    content = fetch_feed_content(url)
    if not content:
        return []
    try:
        root = parse_xml_bytes(content)
    except Exception:
        return []
    out = []
    for it in root.findall('.//item'):
        out.append(to_string(it))
    return out

def process_description_block_compat(title, link, image, desc, feed_image="", atom_link="", sec_id=""):
    # produce description CDATA text similar to build_full_description (but title passed separately)
    return build_full_description(title, desc or '', feed_image or image, atom_link or '', sec_id, None, None)

def replace_description_compat(item_xml: str, new_desc: str, sec_id="", atom_link="") -> str:
    # robust replacement: if original is malformed, create a minimal item wrapper
    try:
        root = parse_xml_text(item_xml)
    except Exception:
        safe = f"<item><description><![CDATA[{new_desc}]]></description></item>"
        return safe
    desc_elem = root.find('description')
    if desc_elem is None:
        desc_elem = etree.Element('description')
        root.append(desc_elem)
    desc_elem.text = etree.CDATA(new_desc)
    return to_string(root)

# ----------------- Main engine per feed -----------------

def process_feed_file(feed_path: Path, source_urls: List[str]):
    print(f"Processing feed: {feed_path}, sources: {source_urls}")
    try:
        feed_bytes = feed_path.read_bytes()
    except Exception as e:
        print(f"  ❌ cannot read {feed_path}: {e}")
        return

    root = parse_xml_bytes(feed_bytes)
    # find channel element
    channel = root.find('channel')
    if channel is None:
        print("  ❌ no <channel> found, skipping")
        return

    # detect op3 prefix in channel
    op3_elem = channel.find('op3')
    op3_val = op3_elem.text.strip() if (op3_elem is not None and op3_elem.text) else None

    # detect atom:link and itunes:image in channel (namespaced)
    atom_link_el = channel.find('atom:link', namespaces=NSMAP)
    atom_href = atom_link_el.get('href') if atom_link_el is not None else None
    itunes_img_el = channel.find('itunes:image', namespaces=NSMAP)
    itunes_href = itunes_img_el.get('href') if itunes_img_el is not None else None

    existing_omsecs = get_existing_omsecs(channel)
    existing_keys = set(extract_item_key_from_elem(it) for it in channel.findall('.//item'))

    print(f"  - existing items count: {len(existing_keys)}, existing om:sec count: {len(existing_omsecs)}")

    new_item_elems = []

    for src in source_urls:
        content = fetch_feed_content(src)
        if not content:
            print(f"  - could not fetch source {src}")
            continue
        src_root = parse_xml_bytes(content)
        src_channel = src_root.find('channel')
        if src_channel is None:
            print(f"  - source {src} has no channel")
            continue
        src_items = src_channel.findall('item')
        print(f"  - source {src} items: {len(src_items)}")
        for idx, src_item in enumerate(src_items, start=1):
            try:
                # key detection
                key = extract_item_key_from_elem(src_item)
                if key in existing_keys:
                    print(f"    [{src}] item {idx} -> exists (key match)")
                    continue
                # clone item into new element (deep copy)
                new_item = etree.fromstring(to_string(src_item).encode('utf-8'))
                # apply op3 to enclosure if any
                pref_url, orig_url = None, None
                if op3_val:
                    pref_url, orig_url = prefix_enclosure_if_op3(new_item, op3_val)
                # generate unique om:sec
                omsec = create_omsec_for_item(new_item, existing_omsecs)
                # append om:sec element with namespace
                om_sec_el = etree.Element(ensure_qname(NS_OM, 'sec'))
                om_sec_el.text = omsec
                new_item.append(om_sec_el)
                # description rework
                title_txt = new_item.findtext('title') or ''
                orig_desc_text = new_item.findtext('description') or ''
                # compute enclosure urls for final link
                enclosure_elem = new_item.find('enclosure')
                enc_url_plain = enclosure_elem.get('url') if (enclosure_elem is not None and enclosure_elem.get('url')) else None
                # if we prefixed earlier, enc_url_plain currently contains prefixed; we want both forms:
                if op3_val and enc_url_plain and enc_url_plain.startswith(op3_val):
                    enclosure_prefixed = enc_url_plain
                    # strip prefix to present plain
                    m = re.search(r'https?://', enc_url_plain)
                    if m:
                        enclosure_plain = enc_url_plain[m.start():]
                    else:
                        enclosure_plain = enc_url_plain
                else:
                    enclosure_prefixed = enc_url_plain
                    enclosure_plain = enc_url_plain
                # build description content
                description_cdata_text = build_full_description(title_txt, orig_desc_text, itunes_href, atom_href, omsec, enclosure_prefixed, enclosure_plain)
                # assign description as CDATA (robust)
                desc_elem = new_item.find('description')
                if desc_elem is None:
                    desc_elem = etree.Element('description')
                    new_item.append(desc_elem)
                desc_elem.text = etree.CDATA(description_cdata_text)
                # om:des
                omdes_html = build_om_des_from_description(orig_desc_text)
                # remove existing om:des if present in source
                existing_omdes = new_item.findall('{%s}des' % NS_OM)
                for eod in existing_omdes:
                    new_item.remove(eod)
                # add new om:des
                omdes_el = etree.Element(ensure_qname(NS_OM, 'des'))
                div = etree.Element('div')
                # div.text must contain escaped text where appropriate; omdes_html already has tags and escaped text nodes
                # Use fromstring on fragment to get correct nodes appended under div
                try:
                    frag = BeautifulSoup(omdes_html, 'html.parser')
                    # append children of frag into div as text (we'll set div.text to escaped version for safety as user requested)
                    div.text = None
                    # set inner as escaped for text nodes but keep tags: we already escaped text nodes in build_om_des_from_description
                    div.append(etree.fromstring(f"<div>{omdes_html}</div>").getchildren()[0] if omdes_html.strip() else etree.Element('span'))
                    # but to avoid fragile parsing, simpler: store escaped string inside div as text (as user asked)
                    div.clear()
                    div.text = omdes_html
                except Exception:
                    # fallback: escape everything
                    div.text = html.escape(omdes_html)
                omdes_el.append(div)
                new_item.append(omdes_el)
                # finished new_item, append to list
                new_item_elems.append(new_item)
                existing_keys.add(key)
                print(f"    [{src}] item {idx} '{(title_txt[:60] + '...') if len(title_txt)>60 else title_txt}' -> ADDED with om:sec={omsec}")
            except Exception as e:
                print(f"    [{src}] item {idx} processing error: {e}")
                continue

    if not new_item_elems:
        print("  - no new items to add")
        return

    # Insert new items before first item, preserving order: newest items first
    insert_items_before_first(channel, new_item_elems)

    # Write back (preserve xml declaration)
    try:
        out_bytes = etree.tostring(root, encoding='utf-8', pretty_print=True, xml_declaration=True)
        feed_path.write_bytes(out_bytes)
        print(f"  ✅ wrote {len(new_item_elems)} new items into {feed_path}")
    except Exception as e:
        print(f"  ❌ error writing feed file: {e}")

# ----------------- CLI / main -----------------

def main():
    # unbuffer stdout for realtime logs in Actions
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    base = Path("public")
    if not base.exists():
        print("No public/ directory found, exiting.")
        return

    # Determine targets: --all or specific path
    args = sys.argv[1:]
    target_paths: List[Path] = []
    if args and args[0] != '--all':
        # treat first arg as feed path
        p = Path(args[0])
        if p.exists():
            target_paths = [p]
        else:
            print(f"Given path {args[0]} does not exist.")
            return
    else:
        # walk folders and pick those with feed.xml
        for folder in sorted(base.iterdir()):
            if not folder.is_dir():
                continue
            feed_file = folder / "feed.xml"
            source_file = folder / "source.txt"
            print(f"Procesando carpeta: {folder}")
            print(f" - feed.xml existe: {feed_file.exists()}")
            print(f" - source.txt existe: {source_file.exists()}")
            if feed_file.exists() and source_file.exists():
                srcs = read_source_list_for_folder(folder)
                print(f" - URLs en source.txt: {srcs}")
                if srcs:
                    process_feed_file(feed_file, srcs)
                else:
                    print(" - source.txt vacío, se omite")
            else:
                print(" - Se omite carpeta (faltan archivos necesarios)")

if __name__ == "__main__":
    main()