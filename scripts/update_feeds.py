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
    """Parse XML robustamente."""
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(text.encode("utf-8"), parser=parser)


def sanitize_html_keep_tags(raw_html: str) -> str:
    """
    Escapa solo el texto plano dentro del HTML, conservando las etiquetas.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    for t in soup.find_all(text=True):
        if t.parent.name not in ["script", "style"]:
            t.replace_with(escape(t, quote=False))
    return str(soup)


def build_om_des(description: str) -> str:
    """
    Construye <om:des> escapando solo el texto plano,
    no las etiquetas HTML.
    """
    if "<hr" in description:
        parts = description.split('<hr', 1)
        after_hr = "<hr" + parts[1]
        clean_html = sanitize_html_keep_tags(after_hr)
        return f"<om:des><div>{clean_html}</div></om:des>"
    return ""


def generate_sec_id(item, existing_ids):
    """
    Genera un ID único para om:sec.
    """
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


def enhance_description(item, atom_link, sec_id, itunes_img_href, op3_prefix):
    """
    Genera una nueva description con las reglas pedidas.
    """
    title = item.findtext("title", "")
    desc = item.findtext("description", "")
    desc = desc or ""
    desc = BeautifulSoup(desc, "html.parser").get_text("\n")

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

    if new_lines[-1] not in desc:
        decorated_desc = "\n".join(new_lines) + "\n" + desc
    else:
        decorated_desc = desc

    # Añadir enlace al enclosure
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.get("url")
        prefixed_url = (op3_prefix or "") + url
        decorated_desc += (
            f'\n<a href="{prefixed_url}">{url}</a>'
        )

    return etree.CDATA(decorated_desc)


def process_feed(feed_path, source_urls):
    """
    Procesa un feed destino y añade ítems de los sources.
    """
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

    # Guardamos items nuevos en texto para insertar manualmente
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

            # Serializamos el item
            item_xml = etree.tostring(item, encoding="unicode")
            new_items_text += "\n" + item_xml + "\n"

    if not new_items_text.strip():
        print(f"✅ {feed_path}: sin cambios")
        return

    # Insertamos los nuevos items justo antes del primer <item>
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