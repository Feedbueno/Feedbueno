import os
import re
import shutil
import update_feeds


def update_feed_dir_with_image(feed_dir: str):
    imagen_file = os.path.join(feed_dir, "imagen.txt")
    source_file = os.path.join(feed_dir, "source.txt")
    dest_file   = os.path.join(feed_dir, "feed.xml")

    # Si no existe imagen.txt, no hacemos nada
    if not os.path.exists(imagen_file):
        print(f"⏭️  Omitido {feed_dir}: no hay imagen.txt")
        return

    # Copiamos imagen.txt -> source.txt para que update_feeds lo use
    shutil.copyfile(imagen_file, source_file)

    # Ejecutamos update_feeds normal
    update_feeds.update_feed_dir(feed_dir)

    # Después de update_feeds, hacemos los cambios adicionales en feed.xml
    if not os.path.exists(dest_file):
        return

    with open(dest_file, "r", encoding="utf-8") as f:
        xml = f.read()

    # Obtenemos la imagen del feed (de <channel>)
    feed_img = update_feeds.find_attr(xml, "itunes:image", "href") or ""

    # 1. Insertar itunes:image del episodio en la descripción antes del <hr>
    def add_image_to_description(m):
        block = m.group(1)
        img = re.search(r'<itunes:image[^>]*href="([^"]+)"', block, flags=re.IGNORECASE)
        if not img:
            return m.group(0)
        img_url = img.group(1)
        return block.replace(
            '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
            f'<img src="{img_url}" />\n'
            '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />',
            1
        )

    xml = re.sub(r"(<description><!\[CDATA\[.*?\]\]></description>)", add_image_to_description, xml, flags=re.DOTALL)

    # 2. Sustituir <itunes:image .../> del episodio por la del feed
    if feed_img:
        items = re.findall(r"<item\b[^>]*>.*?</item>", xml, flags=re.IGNORECASE | re.DOTALL)
        for item in items:
            new_item = re.sub(
                r"<itunes:image\b[^>]*/>",
                f'<itunes:image href="{feed_img}" />',
                item,
                flags=re.IGNORECASE
            )
            if new_item != item:
                xml = xml.replace(item, new_item)

    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"✨ {feed_dir}: postprocesado con imagen en descripción y reemplazo a imagen del feed")


def main():
    base = os.path.join(os.getcwd(), "public")
    if not os.path.isdir(base):
        print("❌ No existe la carpeta 'public'")
        return

    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            update_feed_dir_with_image(path)


if __name__ == "__main__":
    main()