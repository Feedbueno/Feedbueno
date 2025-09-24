import os
import re
import requests
import hashlib
import string
import itertools

ITEM_RE = re.compile(r"<item\b[^>]*>.*?</item>", re.IGNORECASE | re.DOTALL)

def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def fetch_xml(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Feedbueno-Updater/1.0"})
    return r.text

def extract_items(xml_text):
    return ITEM_RE.findall(xml_text)

def extract_tag_text(item_xml, tag):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", item_xml, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    if val.startswith("<![CDATA[") and val.endswith("]]>"):
        val = val[len("<![CDATA["):-len("]]>")].strip()
    return val

def extract_enclosure_url(item_xml):
    m = re.search(r'<enclosure\b[^>]*\burl="([^"]+)"', item_xml, re.IGNORECASE)
    return m.group(1) if m else None

def item_key(item_xml):
    guid = extract_tag_text(item_xml, "guid")
    if guid: return f"guid::{guid}"
    link = extract_tag_text(item_xml, "link")
    if link: return f"link::{link}"
    encl = extract_enclosure_url(item_xml)
    if encl: return f"encl::{encl}"
    return "hash::" + hashlib.md5(item_xml.encode("utf-8", errors="ignore")).hexdigest()

def first_item_pos(dest_xml):
    m = re.search(r"<item\b", dest_xml, re.IGNORECASE)
    if m: return m.start()
    m = re.search(r"</channel>", dest_xml, re.IGNORECASE)
    return m.start() if m else -1

def extract_channel_image(xml_text):
    m = re.search(r'<itunes:image\b[^>]*\bhref="([^"]+)"', xml_text, re.IGNORECASE)
    return m.group(1) if m else None

def extract_channel_link(xml_text):
    """Extrae el <atom:link href="..."/> del canal"""
    m = re.search(r'<atom:link\b[^>]*\bhref="([^"]+)"', xml_text, re.IGNORECASE)
    return m.group(1) if m else None

# ---------------- OM:SEC -----------------

def suffix_generator():
    """Genera A, B, ..., Z, AA, AB, ..., infinitamente."""
    alphabet = string.ascii_uppercase
    n = 1
    while True:
        for comb in itertools.product(alphabet, repeat=n):
            yield "".join(comb)
        n += 1

def generate_sec_number(title, desc, used_numbers):
    text_candidates = [desc or "", title or ""]
    num = None
    for txt in text_candidates:
        m = re.search(r"\d+", txt)
        if m:
            num = m.group(0)
            break

    if not num:
        # inventar uno nuevo, empezando en 1 hasta encontrar libre
        candidate = 1
        while str(candidate) in used_numbers:
            candidate += 1
        num = str(candidate)

    # Si ya está usado, añadir sufijos A, B, C...
    base = num
    suffix_iter = suffix_generator()
    while num in used_numbers:
        num = base + next(suffix_iter)

    used_numbers.add(num)
    return num

def insert_om_sec(item_xml, sec_num):
    return re.sub(
        r"(</title>)",
        rf"\1\n<om:sec>{sec_num}</om:sec>",
        item_xml,
        count=1,
        flags=re.IGNORECASE
    )

# ---------------- Imagen -----------------

def replace_item_image(item_xml, channel_image_url):
    """Reemplaza o inserta <itunes:image> en un ítem con la URL general"""
    if not channel_image_url:
        return item_xml, None

    original = None
    m = re.search(r'<itunes:image\b[^>]*\bhref="([^"]+)"', item_xml, re.IGNORECASE)
    if m:
        original = m.group(1)
        new_item = re.sub(
            r'(<itunes:image\b[^>]*\bhref=")([^"]+)(")',
            rf'\1{channel_image_url}\3',
            item_xml,
            flags=re.IGNORECASE
        )
        return new_item, original

    new_item = re.sub(
        r"(</title>)",
        rf"\1\n<itunes:image href=\"{channel_image_url}\"/>",
        item_xml,
        count=1,
        flags=re.IGNORECASE
    )
    return new_item, original

# ---------------- Descripción -----------------

def rewrite_description(item_xml, sec_num, atom_link, original_image):
    title = extract_tag_text(item_xml, "title") or ""
    desc = extract_tag_text(item_xml, "description") or ""

    # Construir nuevas líneas
    sec_url = f"{atom_link}#{sec_num}" if atom_link else f"#{sec_num}"
    link_html = f'<a href="{sec_url}">{sec_url}</a>'

    new_desc_parts = [
        f"<p>{title}</p>",
        f"<p>Si no ves la imagen entra en {link_html}</p>",
        '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
        f'<img src="{original_image}"/>' if original_image else "",
        desc
    ]
    new_desc = "\n".join([p for p in new_desc_parts if p])

    # Reemplazar el bloque <description>
    return re.sub(
        r"<description\b[^>]*>.*?</description>",
        f"<description><![CDATA[{new_desc}]]></description>",
        item_xml,
        flags=re.IGNORECASE | re.DOTALL
    )

# ---------------- OM:DES -----------------

def insert_om_des(item_xml):
    """Crea o reemplaza <om:des> con contenido a partir del <hr> específico o todo si no existe.
    Siempre envuelto en <div>...</div>.
    """
    desc_match = re.search(r"<description\b[^>]*>(.*?)</description>", item_xml, re.IGNORECASE | re.DOTALL)
    if not desc_match:
        return item_xml

    desc_content = desc_match.group(1).strip()
    # Quitar CDATA si existe
    if desc_content.startswith("<![CDATA[") and desc_content.endswith("]]>"):
        desc_content = desc_content[len("<![CDATA["):-len("]]>")].strip()

    # Buscar el <hr> específico
    hr_marker = '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'
    if hr_marker in desc_content:
        desc_content = desc_content.split(hr_marker, 1)[1].strip()

    # Envolver en <div>
    omdes_tag = f"<om:des><div>{desc_content}</div></om:des>"

    if "<om:des>" in item_xml:
        # Reemplazar existente
        item_xml = re.sub(r"<om:des>.*?</om:des>", omdes_tag, item_xml, flags=re.DOTALL)
    else:
        # Insertar justo antes de </item>
        item_xml = item_xml.replace("</item>", f"{omdes_tag}</item>")

    return item_xml

# ---------------- MAIN -----------------

def update_one_feed(podcast_dir):
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "alotroladodelmicrofono.txt")
    dest_file   = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️  {podcast_dir}: falta alotroladodelmicrofono.txt o feed.xml — se omite")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        sources = [ln.strip() for ln in f if ln.strip()]

    if not sources:
        print(f"ℹ️  {podcast_dir}: alotroladodelmicrofono.txt vacío — se omite")
        return

    dest_xml = read_text(dest_file)
    channel_image = extract_channel_image(dest_xml)
    atom_link = extract_channel_link(dest_xml)

    existing_items = extract_items(dest_xml)
    existing_keys = set(item_key(ix) for ix in existing_items)

    # Inicializar set de OM:SEC ya usados
    used_numbers = set()
    for it in existing_items:
        sec = extract_tag_text(it, "om:sec")
        if sec:
            used_numbers.add(sec)

    ins_pos = first_item_pos(dest_xml)
    if ins_pos == -1:
        print(f"⚠️  {podcast_dir}: no se encontró <item> ni </channel> en feed.xml — se omite")
        return

    new_blocks = []
    new_keys = 0

    for url in sources:
        try:
            src_xml = fetch_xml(url)
        except Exception as e:
            print(f"❌  {podcast_dir}: error al descargar {url} — {e}")
            continue

        items = extract_items(src_xml)
        if not items:
            print(f"ℹ️  {podcast_dir}: {url} no parece RSS 2.0 (<item> no encontrado) — se omite")
            continue

        for it in items:
            k = item_key(it)
            if k not in existing_keys:
                title = extract_tag_text(it, "title")
                desc = extract_tag_text(it, "description")

                # Generar número OM:SEC
                sec_num = generate_sec_number(title, desc, used_numbers)
                it = insert_om_sec(it, sec_num)

                # Reemplazar imagen
                it, original_image = replace_item_image(it, channel_image)

                # Reescribir descripción
                it = rewrite_description(it, sec_num, atom_link, original_image)

                # Añadir/actualizar om:des
                it = insert_om_des(it)

                new_blocks.append(it)
                existing_keys.add(k)
                new_keys += 1

    if not new_blocks:
        print(f"ℹ️  {podcast_dir}: sin ítems nuevos")
        return

    insertion_text = "\n" + "\n".join(new_blocks) + "\n"
    updated = dest_xml[:ins_pos] + insertion_text + dest_xml[ins_pos:]
    write_text(dest_file, updated)
    print(f"✅  {podcast_dir}: insertados {new_keys} ítems nuevos al principio")

def main():
    root = "public"
    for entry in os.listdir(root):
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            update_one_feed(entry)

if __name__ == "__main__":
    main()