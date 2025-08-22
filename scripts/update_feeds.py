import feedparser
import os
import xml.etree.ElementTree as ET

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

def update_feed(podcast_dir):
    source_file = os.path.join(BASE_DIR, podcast_dir, "source.txt")
    dest_file = os.path.join(BASE_DIR, podcast_dir, "feed.xml")

    if not os.path.exists(source_file):
        print(f"⚠️ {podcast_dir}: no tiene source.txt, se omite.")
        return

    # Leer todas las URLs de origen
    with open(source_file, "r", encoding="utf-8") as f:
        sources = [line.strip() for line in f if line.strip()]

    if not sources:
        print(f"⚠️ {podcast_dir}: source.txt vacío, se omite.")
        return

    # Crear estructura básica si no existe el feed destino
    if not os.path.exists(dest_file):
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = f"{podcast_dir} podcast combinado"
        ET.SubElement(channel, "description").text = f"Feed clonado de múltiples fuentes"
        ET.SubElement(channel, "link").text = f"https://feedbueno.es/{podcast_dir}/"
        tree = ET.ElementTree(root)
    else:
        tree = ET.parse(dest_file)

    channel = tree.getroot().find("channel")

    # Recoger todos los links existentes
    existing_links = {item.find("link").text for item in channel.findall("item") if item.find("link") is not None}

    # Encontrar la posición del primer item
    first_item = channel.find("item")

    new_count = 0
    for url in sources:
        parsed = feedparser.parse(url)

        for entry in parsed.entries:
            if entry.link not in existing_links:
                item = ET.Element("item")
                ET.SubElement(item, "title").text = entry.title
                ET.SubElement(item, "description").text = entry.get("description", "")
                ET.SubElement(item, "link").text = entry.link

                if first_item is not None:
                    channel.insert(list(channel).index(first_item), item)
                else:
                    channel.append(item)

                existing_links.add(entry.link)
                new_count += 1

    # Guardar feed actualizado
    tree.write(dest_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ {podcast_dir}: añadidos {new_count} ítems nuevos (de {len(sources)} feeds de origen)")

if __name__ == "__main__":
    for folder in os.listdir(BASE_DIR):
        full_path = os.path.join(BASE_DIR, folder)
        if os.path.isdir(full_path):
            update_feed(folder)