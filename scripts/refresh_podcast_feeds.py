#!/usr/bin/env python3
from pathlib import Path
from lxml import etree
import copy

BASE_DIR = Path(__file__).resolve().parent.parent / "public"

def _localname(elem):
    return etree.QName(elem).localname

def _find_channel(root):
    for child in root:
        if _localname(child) == "channel":
            return child
    return None

def refresh_feed(feed0_path: Path, feed_path: Path):
    parser = etree.XMLParser(remove_blank_text=True)

    feed0_tree = etree.parse(str(feed0_path), parser)
    feed_tree = etree.parse(str(feed_path), parser)

    feed0_root = feed0_tree.getroot()
    feed_root = feed_tree.getroot()

    # --- Reemplazar xml-stylesheet processing-instruction ---
    # eliminar PIs existentes en el feed destino
    for pi in feed_tree.xpath("//processing-instruction('xml-stylesheet')"):
        parent = pi.getparent()
        if parent is not None:
            parent.remove(pi)
    # añadir PI(s) de feed0 antes del root
    for pi in feed0_tree.xpath("//processing-instruction('xml-stylesheet')"):
        feed_root.addprevious(etree.ProcessingInstruction("xml-stylesheet", pi.text))

    # --- Reemplazar atributos de <rss> completamente ---
    feed_root.attrib.clear()
    for k, v in feed0_root.attrib.items():
        feed_root.set(k, v)

    # --- Reemplazar todo lo que esté en <channel> ANTES del primer <item> ---
    channel0 = _find_channel(feed0_root)
    channel = _find_channel(feed_root)

    if channel0 is not None and channel is not None:
        # obtener los nodos de channel0 hasta (pero sin incluir) el primer <item>
        pre_items_from_feed0 = []
        for child in channel0:
            if _localname(child) == "item":
                break
            pre_items_from_feed0.append(copy.deepcopy(child))

        # encontrar índice del primer <item> en el channel actual
        first_item_index = None
        for idx, child in enumerate(list(channel)):
            if _localname(child) == "item":
                first_item_index = idx
                break
        if first_item_index is None:
            # no hay items -> consideramos final del channel
            first_item_index = len(channel)

        # eliminar todo lo que esté antes del primer <item>
        for _ in range(first_item_index):
            channel.remove(channel[0])

        # insertar los nodos copiados de feed0 (en el mismo orden) antes de los items existentes
        for i, new_child in enumerate(pre_items_from_feed0):
            channel.insert(i, new_child)

    # Guardar respetando la declaración XML
    feed_tree.write(str(feed_path), encoding="utf-8", xml_declaration=True, pretty_print=True)

def main():
    for podcast_dir in BASE_DIR.iterdir():
        if not podcast_dir.is_dir():
            continue

        feed0 = podcast_dir / "feed0.xml"
        feed = podcast_dir / "feed.xml"

        if feed0.exists() and feed.exists():
            print(f"Refrescando {feed} con {feed0}")
            refresh_feed(feed0, feed)
        else:
            print(f"Omitido {podcast_dir}: no se encontró feed0.xml o feed.xml")

if __name__ == "__main__":
    main()