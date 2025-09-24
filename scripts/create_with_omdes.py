import os
import re
import requests

# --- Utilidades ---

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
    import hashlib
    return "hash::" + hashlib.md5(item_xml.encode("utf-8", errors="ignore")).hexdigest()

def first_item_pos(dest_xml):
    m = re.search(r"<item\b", dest_xml, re.IGNORECASE)
    if m:
        return m.start()
    m = re.search(r"</channel>", dest_xml, re.IGNORECASE)
    return m.start() if m else -1

# --- Escapado robusto (texto + atributos, evitando doble escape) ---

def escape_text_preserve_tags(text):
    def escape_basic(s):
        # Escapar &, excepto si ya es una entidad válida
        s = re.sub(
            r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)',
            "&amp;",
            s
        )
        s = s.replace("<", "&lt;").replace(">", "&gt;")
        return s

    def process_tag(tag):
        # Escapar valores de atributos dentro de etiquetas
        def repl_attr(m):
            quote = m.group(1)
            value = m.group(2)
            return f'{quote}{escape_basic(value)}{quote}'
        return re.sub(r'(["\'])(.*?)(\1)',
                      lambda m: repl_attr(m),
                      tag)

    def replacer(match):
        part = match.group(0)
        if part.startswith("<") and part.endswith(">"):
            return process_tag(part)
        return escape_basic(part)

    return re.sub(r"<[^>]+>|[^<]+", replacer, text)

# --- Transformación de description en om:des ---

HR_MARKER = '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'

def build_omdes(item_xml):
    desc = extract_tag_text(item_xml, "description")
    if not desc:
        return None

    # Solo dividir si está exactamente el marcador esperado
    parts = desc.split(HR_MARKER, 1)
    if len(parts) < 2:
        return None

    after_hr = parts[1].strip()
    if not after_hr:
        return None

    processed = escape_text_preserve_tags(after_hr)
    return f"<om:des><div>{processed}</div></om:des>"

def inject_omdes(item_xml):
    omdes = build_omdes(item_xml)
    if not omdes:
        return item_xml

    # Si ya existe <om:des>, reemplazarlo
    if re.search(r"<om:des\b.*?</om:des>", item_xml, flags=re.IGNORECASE | re.DOTALL):
        return re.sub(r"<om:des\b.*?</om:des>", omdes, item_xml, count=1, flags=re.IGNORECASE | re.DOTALL)

    # Si no existe, añadirlo antes de </item>
    return re.sub(r"</item>", omdes + "\n</item>", item_xml, count=1, flags=re.IGNORECASE)

# --- Lógica principal ---

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
                new_blocks.append(inject_omdes(it))
                existing_keys.add(k)
                new_keys += 1

    if not new_blocks:
        print(f"ℹ️  {podcast_dir}: sin ítems nuevos")
        return

    insertion_text = "\n" + "\n".join(new_blocks) + "\n"
    updated = dest_xml[:ins_pos] + insertion_text + dest_xml[ins_pos:]
    write_text(dest_file, updated)
    print(f"✅  {podcast_dir}: insertados {new_keys} ítems nuevos con <om:des>")

def main():
    root = "public"
    for entry in os.listdir(root):
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            update_one_feed(entry)

if __name__ == "__main__":
    main()