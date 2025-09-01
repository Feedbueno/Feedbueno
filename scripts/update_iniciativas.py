import os
import re
import argparse
from update_feeds import (
    strip_cdata,
    find_tag_text,
    find_attr,
    replace_description,
    process_description_block,
    item_key_from_xml,
    existing_keys_from_feed,
    fetch_source_items
)

def ensure_itunes_tags(item_xml: str, title_text: str) -> str:
    """
    Añade o modifica itunes:season=1 y itunes:episode=N (extraído del título).
    """
    # Forzar <itunes:season>1</itunes:season>
    if re.search(r"<itunes:season>", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(r"<itunes:season>.*?</itunes:season>",
                          "<itunes:season>1</itunes:season>",
                          item_xml, flags=re.IGNORECASE | re.DOTALL)
    else:
        item_xml = re.sub(r"</item>", "<itunes:season>1</itunes:season>\n</item>",
                          item_xml, flags=re.IGNORECASE)

    # Extraer número del título
    m = re.search(r"(\d+)", title_text)
    episode_num = m.group(1) if m else "1"

    if re.search(r"<itunes:episode>", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(r"<itunes:episode>.*?</itunes:episode>",
                          f"<itunes:episode>{episode_num}</itunes:episode>",
                          item_xml, flags=re.IGNORECASE | re.DOTALL)
    else:
        item_xml = re.sub(r"</item>", f"<itunes:episode>{episode_num}</itunes:episode>\n</item>",
                          item_xml, flags=re.IGNORECASE)

    return item_xml

def update_feed_dir_iniciativas(feed_dir: str, search_text: str, source_filename: str):
    source_file = os.path.join(feed_dir, source_filename)
    dest_file = os.path.join(feed_dir, "feed.xml")

    if not (os.path.exists(source_file) and os.path.exists(dest_file)):
        print(f"⏭️  Omitido {feed_dir}: falta {source_filename} o feed.xml")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [ln.strip() for ln in f if ln.strip()]

    if not source_urls:
        print(f"ℹ️  {feed_dir}: {source_filename} vacío")
        return

    with open(dest_file, "r", encoding="utf-8") as f:
        dest_xml = f.read()

    existing = existing_keys_from_feed(dest_xml)
    new_items = []

    # Datos del feed destino
    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    feed_image = find_attr(dest_xml, "itunes:image", "href") or ""
    op3_prefix = find_tag_text(dest_xml, "op3")

    om_counter = 1

    for url in source_urls:
        try:
            for raw_item in fetch_source_items(url):
                title_inner = find_tag_text(raw_item, "title")
                title_txt = strip_cdata(title_inner)

                # Filtro insensible a mayúsculas/minúsculas
                if search_text.lower() not in title_txt.lower():
                    continue

                key = item_key_from_xml(raw_item)
                if key in existing:
                    continue

                link_inner = find_tag_text(raw_item, "link")
                img = (
                    find_attr(raw_item, "itunes:image", "href")
                    or find_attr(raw_item, "media:thumbnail", "url")
                    or ""
                )
                desc_inner = find_tag_text(raw_item, "description")

                om_sec = str(om_counter)
                om_counter += 1

                new_desc = process_description_block(
                    strip_cdata(title_inner),
                    strip_cdata(link_inner),
                    img,
                    desc_inner,
                    atom_link,
                    om_sec,
                    feed_image
                )
                new_item = replace_description(raw_item, new_desc, new_desc, om_sec)

                # prefijo OP3 en enclosure
                if op3_prefix:
                    def repl_enclosure(m):
                        url = m.group(1)
                        length = m.group(2)
                        type_ = m.group(3)
                        new_url = op3_prefix + url
                        return f'<enclosure url="{new_url}" length="{length}" type="{type_}"/>'
                    new_item = re.sub(
                        r'<enclosure url="([^"]+)" length="([^"]+)" type="([^"]+)"/>',
                        repl_enclosure,
                        new_item,
                        flags=re.IGNORECASE
                    )

                new_item = ensure_itunes_tags(new_item, title_txt)
                new_items.append(new_item)
                existing.add(key)
        except Exception as e:
            print(f"⚠️  Error leyendo {url}: {e}")

    if not new_items:
        print(f"= {feed_dir}: sin nuevos episodios que contengan '{search_text}'")
        return

    # Insertar arriba (antes del primer <item>)
    insertion_block = "\n".join(new_items)
    first_item = re.search(r"<item\b", dest_xml, flags=re.IGNORECASE)
    if first_item:
        insert_pos = first_item.start()
        updated_xml = dest_xml[:insert_pos] + insertion_block + "\n" + dest_xml[first_item.start():]
    else:
        updated_xml = re.sub(r"</channel>\s*$", insertion_block + "\n</channel>",
                             dest_xml, flags=re.IGNORECASE | re.DOTALL)

    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(updated_xml)

    print(f"✅ {feed_dir}: añadidos {len(new_items)} episodios nuevos que contienen '{search_text}'")

def main():
    parser = argparse.ArgumentParser(description="Actualizar feeds filtrando por título.")
    parser.add_argument("--text", required=True, help="Texto a buscar en el título (insensible a mayúsculas).")
    parser.add_argument("--source", required=True, help="Archivo fuente (ej. imetal.txt, imario.txt).")
    args = parser.parse_args()

    base = os.path.join(os.getcwd(), "public")
    if not os.path.isdir(base):
        print("❌ No existe la carpeta 'public'")
        return

    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            update_feed_dir_iniciativas(path, args.text, args.source)

if __name__ == "__main__":
    main()