import os
import re
import feedparser
import xml.etree.ElementTree as ET
from copy import deepcopy

# -------------------------
# Helpers
# -------------------------

def has_rich_html(description: str) -> bool:
    """Detecta si el texto ya contiene HTML enriquecido."""
    return re.search(r"<(a|img|ul|ol|li|h[1-6])\b", description, flags=re.IGNORECASE) is not None


def process_description(title, link, image_url, description):
    """Transforma la descripción solo si no tiene HTML enriquecido."""

    html = ""

    # Título
    if title:
        html += f"<h3>{title}</h3>\n"

    # Imagen con enlace
    if image_url:
        html += f'<a href="{link}"><img src="{image_url}" /></a>\n'

    # Separador
    html += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    # Si ya tiene HTML "fuerte", la dejamos tal cual
    if has_rich_html(description):
        html += description
        return f"<![CDATA[{html}]]>"

    # Emails → mailto:
    description = re.sub(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="mailto:\1">\1</a>', description)

    # Enlaces a imágenes
    description = re.sub(
        r'(https?://\S+\.(?:jpg|jpeg|png|gif))',
        r'<a href="\1"><img src="\1" /></a>', description)

    # Enlaces normales
    description = re.sub(
        r'(https?://[^\s<]+)',
        r'<a href="\1">\1</a>', description)

    # Listas con "-"
    if "-" in description:
        description = re.sub(r"(?:^|\n)- (.*)", r"<ul><li>\1</li></ul>", description)

    # Listas numeradas "1."
    if re.search(r"(?:^|\n)\d+\.", description):
        description = re.sub(r"(?:^|\n)(\d+)\. (.*)", r"<ol><li>\2</li></ol>", description)

    # Párrafos
    paragraphs = [f"<p>{line.strip()}</p>" for line in description.split("\n") if line.strip()]
    description = "\n".join(paragraphs)

    html += description
    return f"<![CDATA[{html}]]>"


def copy_item_with_new_description(entry_elem, title, link, image_url, description):
    """Copia el item completo y reemplaza solo <description>."""
    new_item = deepcopy(entry_elem)

    # Eliminar descripción antigua
    for child in new_item.findall("description"):
        new_item.remove(child)

    # Añadir la nueva descripción procesada
    desc_elem = ET.SubElement(new_item, "description")
    desc_elem.text = process_description(title, link, image_url, description)

    return new_item


# -------------------------
# Main updater
# -------------------------

def update_feed(feed_dir):
    """Actualiza feed.xml en un directorio según source.txt."""

    source_file = os.path.join(feed_dir, "source.txt")
    dest_file = os.path.join(feed_dir, "feed.xml")

    if not os.path.exists(source_file):
        print(f"⚠️ No hay source.txt en {feed_dir}, se omite.")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [line.strip() for line in f if line.strip()]

    if not source_urls:
        print(f"⚠️ source.txt vacío en {feed_dir}, se omite.")
        return

    # Parsear el feed destino
    if not os.path.exists(dest_file):
        print(f"⚠️ No hay feed.xml en {feed_dir}, se omite.")
        return

    tree = ET.parse(dest_file)
    root = tree.getroot()
    channel = root.find("channel")

    if channel is None:
        print(f"❌ feed.xml en {feed_dir} no tiene <channel>")
        return

    # Extraer GUIDs existentes para no duplicar
    existing_guids = {guid.text for guid in channel.findall("item/guid") if guid.text}

    for url in source_urls:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            guid = getattr(entry, "id", getattr(entry, "guid", entry.link))
            if guid in existing_guids:
                continue  # Ya está en el feed

            # Obtener valores seguros
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            description = getattr(entry, "description", "")
            image_url = ""

            if "image" in entry:
                image_url = entry.image.href
            elif "itunes_image" in entry:
                image_url = entry.itunes_image

            # Copiar ítem completo desde XML del feed de origen
            if hasattr(entry, "_element"):  # feedparser guarda el ElementTree original
                entry_elem = entry._element
                new_item = copy_item_with_new_description(entry_elem, title, link, image_url, description)
                # Insertar arriba de los items existentes
                channel.insert(0, new_item)

            existing_guids.add(guid)

    # Guardar feed actualizado
    tree.write(dest_file, encoding="utf-8", xml_declaration=True)


def main():
    base_dir = os.path.join(os.getcwd(), "public")

    for folder in os.listdir(base_dir):
        feed_dir = os.path.join(base_dir, folder)
        if os.path.isdir(feed_dir):
            update_feed(feed_dir)


if __name__ == "__main__":
    main()