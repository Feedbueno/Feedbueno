import os
import glob
import xml.etree.ElementTree as ET

BASE_PATH = "public/*/feed.xml"

def process_feed(feed_path):
    print(f"Procesando {feed_path}")
    tree = ET.parse(feed_path)
    root = tree.getroot()

    # Detectar namespace (RSS suele tenerlo)
    nsmap = {}
    for elem in root.iter():
        if elem.tag[0] == "{":
            uri, _, tag = elem.tag[1:].partition("}")
            nsmap[uri] = True

    # Buscar items
    for item in root.findall(".//item"):
        desc = item.find("description")
        if desc is None or desc.text is None:
            continue

        # Eliminar CDATA si existiera (ET lo maneja como texto)
        desc_text = desc.text.strip()

        # Buscar si ya existe om:des
        omdes = item.find("om:des")
        if omdes is None:
            omdes = ET.SubElement(item, "om:des")
        omdes.text = desc_text

    tree.write(feed_path, encoding="utf-8", xml_declaration=True)

def main():
    feeds = glob.glob(BASE_PATH)
    if not feeds:
        print("No se encontraron feeds.")
        return
    for feed in feeds:
        process_feed(feed)

if __name__ == "__main__":
    main()