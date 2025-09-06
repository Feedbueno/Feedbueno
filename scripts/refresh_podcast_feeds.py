#!/usr/bin/env python3
import os
from pathlib import Path
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent.parent / "public"

def refresh_feed(feed0_path: Path, feed_path: Path):
    parser = etree.XMLParser(remove_blank_text=True)

    feed0_tree = etree.parse(str(feed0_path), parser)
    feed_tree = etree.parse(str(feed_path), parser)

    feed0_root = feed0_tree.getroot()
    feed_root = feed_tree.getroot()

    # --- Copiar/actualizar xml-stylesheet ---
    for pi in feed_tree.xpath("//processing-instruction('xml-stylesheet')"):
        parent = pi.getparent()
        if parent is not None:
            parent.remove(pi)

    for pi in feed0_tree.xpath("//processing-instruction('xml-stylesheet')"):
        feed_root.addprevious(etree.ProcessingInstruction("xml-stylesheet", pi.text))

    # --- Actualizar atributos de <rss> ---
    for k, v in feed0_root.attrib.items():
        feed_root.set(k, v)

    # --- Actualizar etiquetas dentro de <channel> (excepto <item>) ---
    channel0 = feed0_root.find("channel")
    channel = feed_root.find("channel")

    if channel0 is not None and channel is not None:
        for child0 in channel0:
            if child0.tag == "item":
                continue
            existing = channel.find(child0.tag)
            if existing is not None:
                existing.text = child0.text
                existing.attrib.update(child0.attrib)
            else:
                channel.append(child0)

    # Guardar respetando la declaración XML
    feed_tree.write(str(feed_path), encoding="utf-8", xml_declaration=True, pretty_print=True)

def main():
    for podcast_dir in BASE_DIR.iterdir():
        feed0 = podcast_dir / "archivos" / "feed0.xml"
        feed = podcast_dir / "archivos" / "feed.xml"

        if feed0.exists() and feed.exists():
            print(f"Refrescando {feed} con {feed0}")
            refresh_feed(feed0, feed)
        else:
            print(f"Omitido {podcast_dir}: no se encontró feed0.xml o feed.xml")

if __name__ == "__main__":
    main()