import feedparser
import os
import re

def process_description(title, link, image_url, description):
    """Transforma la descripción según tus reglas"""
    html = ""

    # Título
    if title:
        html += f"<h3>{title}</h3>\n"

    # Imagen con enlace
    if image_url:
        html += f'<a href="{link}"><img src="{image_url}" /></a>\n'

    # Separador
    html += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

    # Emails → mailto:
    description = re.sub(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="mailto:\1">\1</a>', description)

    # Enlaces a imágenes → <img>
    description = re.sub(
        r'(https?://\S+\.(?:jpg|jpeg|png|gif))',
        r'<a href="\1"><img src="\1" /></a>', description)

    # Enlaces normales
    description = re.sub(
        r'(https?://[^\s<]+)',
        r'<a href="\1">\1</a>', description)

    # Listas no ordenadas con "-"
    if "-" in description:
        description = re.sub(r"(?:^|\n)- (.*)", r"<ul><li>\1</li></ul>", description)

    # Listas ordenadas con números "1."
    if re.search(r"(?:^|\n)\d+\.", description):
        description = re.sub(r"(?:^|\n)(\d+)\. (.*)", r"<ol><li>\2</li></ol>", description)

    # Párrafos
    paragraphs = [f"<p>{line.strip()}</p>" for line in description.split("\n") if line.strip()]
    description = "\n".join(paragraphs)

    html += description

    return f"<![CDATA[{html}]]>"

def update_feed(podcast_dir):
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "source.txt")
    dest_file = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️  Saltando {podcast_dir}: falta source.txt o feed.xml")
        return

    with open(source_file, encoding="utf-8") as f:
        sources = [line.strip() for line in f if line.strip()]

    if not sources:
        print(f"ℹ️  {podcast_dir}: source.txt vacío, nada que hacer")
        return

    with open(dest_file, encoding="utf-8") as f:
        existing_xml = f.read()

    insert_pos = existing_xml.find("<item>")
    if insert_pos == -1:
        print(f"⚠️  {podcast_dir}: feed.xml no tiene <item>, saltando")
        return

    new_items = ""
    for url in sources:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link and entry.link not in existing_xml:
                # Imagen: intenta usar itunes:image o enclosure
                image_url = None
                if "image" in entry and hasattr(entry.image, "href"):
                    image_url = entry.image.href
                elif "itunes_image" in entry:
                    image_url = entry.itunes_image
                elif "links" in entry:
                    for l in entry.links:
                        if l.get("rel") == "enclosure" and l.get("type", "").startswith("image"):
                            image_url = l.get("href")
                            break

                # Descripción procesada
                desc = entry.get("description", "")
                desc = process_description(entry.title, entry.link, image_url, desc)

                # Construcción del <item>
                item = f"""
<item>
  <title><![CDATA[{entry.title}]]></title>
  <link>{entry.link}</link>
  <description>{desc}</description>
</item>
"""
                new_items += item
                print(f"➕ Nuevo item en {podcast_dir}: {entry.title}")

    if new_items:
        updated = existing_xml[:insert_pos] + new_items + existing_xml[insert_pos:]
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"✅ {podcast_dir} actualizado con {new_items.count('<item>')} nuevos items")
    else:
        print(f"ℹ️  {podcast_dir}: sin nuevos items")

def main():
    podcasts_dir = "public"
    for podcast_dir in os.listdir(podcasts_dir):
        path = os.path.join(podcasts_dir, podcast_dir)
        if os.path.isdir(path):
            update_feed(podcast_dir)

if __name__ == "__main__":
    main()