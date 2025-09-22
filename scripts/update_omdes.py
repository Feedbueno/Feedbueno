import os
import re
import requests
import hashlib

# --- Configuración ---
HR_MARKER = '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'

# --- Utilidades ---

ITEM_RE = re.compile(r"<item\b[^>]*>.*?</item>", re.IGNORECASE | re.DOTALL)

def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def fetch_xml(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Feedbueno-OMDES/1.0"})
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

def clean_for_omdes(text: str) -> str:
    """Limpia el texto para om:des: elimina <br>, escapa &, conserva lo demás."""
    # Eliminar <br> y variantes
    text = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    # Reemplazar & que no sean parte de entidades (&amp; &lt; &gt; &quot; etc.)
    text = re.sub(r"&(?!(amp;|lt;|gt;|quot;|apos;))", "&amp;", text)
    return text.strip()

def replace_or_insert_omdes(item_xml):
    """Crea o actualiza <om:des> basado en <description>, buscando HR_MARKER."""
    desc = extract_tag_text(item_xml, "description")
    if not desc:
        return item_xml

    # Partir en líneas para buscar el marcador
    lines = desc.splitlines()
    new_text = None
    for i, line in enumerate(lines):
        if line.strip() == HR_MARKER:
            new_text = "\n".join(lines[i+1:]).strip()
            break

    # Si no se encontró el marcador, copiar todo
    if new_text is None:
        new_text = desc.strip()

    # Limpiar y escapar
    cleaned = clean_for_omdes(new_text)

    # Construir bloque
    omdes_block = f"<om:des><div>{cleaned}</div></om:des>"

    if re.search(r"<om:des\b[^>]*>.*?</om:des>", item_xml, re.IGNORECASE | re.DOTALL):
        return re.sub(
            r"<om:des\b[^>]*>.*?</om:des>",
            omdes_block,
            item_xml,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Insertar justo después de </description>
    return re.sub(r"(</description>)", r"\1\n" + omdes_block, item_xml, count=1, flags=re.IGNORECASE)

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
    if m:
        return m.start()
    m = re.search(r"</channel>", dest_xml, re.IGNORECASE)
    return m.start() if m else -1

# --- Lógica principal por carpeta ---

def update_one_feed(podcast_dir):
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "omdes.txt")
    dest_file   = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️  {podcast_dir}: falta omdes.txt o feed.xml — se omite")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        sources = [ln.strip() for ln in f if ln.strip()]

    if not sources:
        print(f"ℹ️  {podcast_dir}: omdes.txt vacío — se omite")
        return

    dest_xml = read_text(dest_file)

    existing_items = extract_items(dest_xml)
    existing_keys = set(item_key(ix) for ix in existing_items)

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
            print(f"ℹ️  {podcast_dir}: {url} no parece RSS 2.0 — se omite")
            continue

        for it in items:
            k = item_key(it)
            if k not in existing_keys:
                it = replace_or_insert_omdes(it)
                new_blocks.append(it)
                existing_keys.add(k)
                new_keys += 1

    if not new_blocks:
        print(f"ℹ️  {podcast_dir}: sin ítems nuevos")
        return

    insertion_text = "\n" + "\n".join(new_blocks) + "\n"
    updated = dest_xml[:ins_pos] + insertion_text + dest_xml[ins_pos:]
    write_text(dest_file, updated)
    print(f"✅  {podcast_dir}: insertados {new_keys} ítems nuevos con om:des")

def main():
    root = "public"
    for entry in os.listdir(root):
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            update_one_feed(entry)

if __name__ == "__main__":
    main()