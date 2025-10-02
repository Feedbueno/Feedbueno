import os
import re
import requests
from lxml import etree
from bs4 import BeautifulSoup
from html import escape

# Namespaces habituales
NSMAP = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
    "om": "https://omrey86.neocities.org/"
}


def parse_xml(text: str):
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(text.encode("utf-8"), parser=parser)


def sanitize_html_keep_tags(raw_html: str) -> str:
    """Escapa solo el texto plano dentro del HTML, conservando etiquetas."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for t in soup.find_all(text=True):
        if t.parent.name not in ["script", "style"]:
            t.replace_with(escape(t, quote=False))
    return str(soup)


def build_om_des(description: str) -> str:
    """Construye <om:des> escapando solo el texto plano, no las etiquetas."""
    if "<hr" in description:
        parts = description.split('<hr', 1)
        after_hr = "<hr" + parts[1]
        clean_html = sanitize_html_keep_tags(after_hr)
        return f"<om:des><div>{clean_html}</div></om:des>"
    return ""


def generate_sec_id(item, existing_ids):
    """Genera un ID único para om:sec."""
    season = item.findtext("itunes:season", namespaces=NSMAP)
    episode = item.findtext("itunes:episode", namespaces=NSMAP)
    if season and episode:
        candidate = f"s{season}e{episode}"
        if candidate not in existing_ids:
            return candidate
    text_fields = (item.findtext("title", ""), item.findtext("description", ""))
    for text in text_fields:
        m = re.search(r"\d+", text or "")
        if m:
            candidate = f"id{m.group(0)}"
            if candidate not in existing_ids:
                return candidate
    i = 1
    while True:
        candidate = f"auto{i}"
        if candidate not in existing_ids:
            return candidate
        i += 1


def format_text_with_rules(text: str) -> str:
    """Aplica reglas de formato al texto plano."""
    lines = text.splitlines()
    out = []
    list_buffer = []
    list_type = None
    num_start = None

    def flush_list():
        nonlocal out, list_buffer, list_type, num_start
        if list_buffer:
            if list_type == "ol":
                out.append(f'<ol start="{num_start}">')
                out.extend(f"<li>{x}</li>" for x in list_buffer)
                out.append("</ol>")
            elif list_type == "ul":
                out.append("<ul>")
                out.extend(f"<li>{x}</li>" for x in list_buffer)
                out.append("</ul>")
        list_buffer, list_type, num_start = [], None, None

    for line in lines:
        line = line.strip()
        if not line:
            flush_list()
            continue

        m = re.match(r"^(\d+)[\.\-\)]?\s*(.*)", line)
        if m:
            num = int(m.group(1))
            content = m.group(2)
            if list_type not in ("ol", None):
                flush_list()
            list_type = "ol"
            if num_start is None:
                num_start = num
            list_buffer.append(content)
            continue

        if re.match(r"^[-*]\s+(.*)", line):
            content = re.sub(r"^[-*]\s+", "", line)
            if list_type not in ("ul", None):
                flush_list()
            list_type = "ul"
            list_buffer.append(content)
            continue

        flush_list()
        # Convert emails
        line = re.sub(
            r"([\w\.-]+@[\w\.-]+\.\w+)",
            lambda m: f'<a href="mailto:{m.group(1)}">{m.group(1)}</a>',
            line,
        )
        # Convert links
        line = re.sub(
            r"(https?://[^\s]+)",
            lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
            line,
        )
        # Convert image links
        line = re.sub(
            r'<a href="(https?://[^\s]+?\.(jpg|jpeg|png|gif))">.*?</a>',
            lambda m: f'<a href="{m.group(1)}"><img src="{m.group(1)}" /></a>',
            line,
        )
        # Bold heuristic: words all uppercase longer than 3 chars
        line = re.sub(r"\b([A-Z]{4,})\b", r"<b>\1</b>", line)
        out.append(f"<p>{line}</p>")

    flush_list()
    return "\n".join(out)


def enhance_description(item, atom_link, sec_id, itunes_img_href, op3_prefix):
    """Genera una nueva description con las reglas pedidas."""
    title = item.findtext("title", "")
    desc = item.findtext("description", "")
    desc = desc or ""
    desc_plain = BeautifulSoup(desc, "html.parser").get_text("\n")

    new_lines = []
    if title:
        new_lines.append(f"<p><b>{title}</b></p>")

    if itunes_img_href:
        new_lines.append(
            f'<a href="{itunes_img_href}"><img src="{itunes_img_href}" /></a>'
        )

    if atom_link and sec_id:
        new_lines.append(
            f'Si no ves las imágenes entra en <a href="{atom_link}#{sec_id}">{atom_link}#{sec_id}</a>'
        )

    new_lines.append('<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />')

    body = format_text_with_rules(desc_plain)

    decorated_desc = "\n".join(new_lines) + "\n" + body

    # Añadir enlace al enclosure
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.get("url")
        prefixed_url = (op3_prefix or "") + url
        decorated_desc += f'\n<a href="{prefixed_url}">{url}</a>'

    return etree.CDATA(decorated_desc)


def process_feed(feed_path, source_urls):
    """Procesa un feed destino y añade ítems de los sources."""
    with open(feed_path, "r", encoding="utf-8") as f:
        original_text = f.read()

    root = parse_xml(original_text)
    channel = root.find("channel")

    atom_link = channel.find("atom:link", namespaces=NSMAP)
    atom_href = atom_link.get("href") if atom_link is not None else ""

    itunes_img = channel.find("itunes:image", namespaces=NSMAP)
    itunes_href = itunes_img.get("href") if itunes_img is not None else ""

    op3_elem = channel.find("op3")
    op3_prefix = op3_elem.text if op3_elem is not None else ""

    existing_ids = set(e.text for e in channel.findall("om:sec", namespaces=NSMAP))

    new_items_text = ""

    for url in source_urls:
        try:
            resp = requests.get(url, timeout=20)
            src_root = parse_xml(resp.text)
        except Exception as e:
            print(f"⚠️ Error leyendo {url}: {e}")
            continue

        for item in src_root.findall("channel/item"):
            sec_id = generate_sec_id(item, existing_ids)
            existing_ids.add(sec_id)

            # Añadir om:sec
            sec_elem = etree.Element("{https://omrey86.neocities.org/}sec")
            sec_elem.text = sec_id
            item.append(sec_elem)

            # Reemplazar description
            new_desc = enhance_description(item, atom_href, sec_id, itunes_href, op3_prefix)
            desc_elem = item.find("description")
            if desc_elem is None:
                desc_elem = etree.Element("description")
                item.append(desc_elem)
            desc_elem.text = new_desc

            # Añadir om:des
            om_des = build_om_des(desc_elem.text or "")
            if om_des:
                old = item.find("om:des", namespaces=NSMAP)
                if old is not None:
                    item.remove(old)
                item.append(etree.fromstring(om_des))

            item_xml = etree.tostring(item, encoding="unicode")
            new_items_text += "\n" + item_xml + "\n"

    if not new_items_text.strip():
        print(f"✅ {feed_path}: sin cambios")
        return

    updated_text = re.sub(
        r"(<item>)",
        new_items_text + r"\1",
        original_text,
        count=1,
        flags=re.DOTALL,
    )

    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(updated_text)

    print(f"✅ {feed_path}: añadidos nuevos items")


def main():
    base_dir = "public"
    for root, dirs, files in os.walk(base_dir):
        if "feed.xml" in files and "source.txt" in files:
            feed_path = os.path.join(root, "feed.xml")
            with open(os.path.join(root, "source.txt"), encoding="utf-8") as f:
                srcs = [l.strip() for l in f if l.strip()]
            print(f"Processing feed: {feed_path}, sources: {srcs}")
            process_feed(feed_path, srcs)


if __name__ == "__main__":
    main()