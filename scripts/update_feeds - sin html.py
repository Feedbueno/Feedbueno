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
    # Preferimos el .text de requests (maneja encoding automáticamente).
    return r.text

def extract_items(xml_text):
    """Devuelve una lista con cada bloque <item>...</item> tal cual (texto crudo)."""
    return ITEM_RE.findall(xml_text)

def extract_tag_text(item_xml, tag):
    """Extrae el contenido de <tag>...</tag> (sin CDATA envolvente); si no existe, None."""
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", item_xml, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    # Quitar envoltorio CDATA si existe
    if val.startswith("<![CDATA[") and val.endswith("]]>"):
        val = val[len("<![CDATA["):-len("]]>")].strip()
    return val

def extract_enclosure_url(item_xml):
    """Intenta extraer url del <enclosure ... url="..."> si existe."""
    m = re.search(r'<enclosure\b[^>]*\burl="([^"]+)"', item_xml, re.IGNORECASE)
    return m.group(1) if m else None

def item_key(item_xml):
    """
    Clave de deduplicación:
    1) <guid> si existe
    2) <link> si existe
    3) url del <enclosure>
    4) hash simple del propio bloque (último recurso)
    """
    guid = extract_tag_text(item_xml, "guid")
    if guid: return f"guid::{guid}"
    link = extract_tag_text(item_xml, "link")
    if link: return f"link::{link}"
    encl = extract_enclosure_url(item_xml)
    if encl: return f"encl::{encl}"
    # Fallback: hash simple
    import hashlib
    return "hash::" + hashlib.md5(item_xml.encode("utf-8", errors="ignore")).hexdigest()

def first_item_pos(dest_xml):
    """Posición (índice) del primer <item>. Si no hay, intenta antes de </channel>; si tampoco, -1."""
    m = re.search(r"<item\b", dest_xml, re.IGNORECASE)
    if m:
        return m.start()
    m = re.search(r"</channel>", dest_xml, re.IGNORECASE)
    return m.start() if m else -1

# --- Lógica principal por carpeta ---

def update_one_feed(podcast_dir):
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "source.txt")
    dest_file   = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️  {podcast_dir}: falta source.txt o feed.xml — se omite")
        return

    # Leer URLs (una por línea)
    with open(source_file, "r", encoding="utf-8") as f:
        sources = [ln.strip() for ln in f if ln.strip()]

    if not sources:
        print(f"ℹ️  {podcast_dir}: source.txt vacío — se omite")
        return

    dest_xml = read_text(dest_file)

    # Construir set de claves existentes a partir del feed destino (para no duplicar)
    existing_items = extract_items(dest_xml)
    existing_keys = set(item_key(ix) for ix in existing_items)

    # Dónde insertar (justo antes del primer <item>)
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

        # Recorremos en orden de aparición en el feed origen.
        for it in items:
            k = item_key(it)
            if k not in existing_keys:
                # Guardamos el bloque tal cual, preservando CDATA, itunes:*, enclosure, estilos, etc.
                new_blocks.append(it)
                existing_keys.add(k)
                new_keys += 1

    if not new_blocks:
        print(f"ℹ️  {podcast_dir}: sin ítems nuevos")
        return

    # Construir bloque de inserción: añadimos un salto antes para mantener estética
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