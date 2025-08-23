import feedparser
import os

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
                # construimos el bloque <item> a mano
                item = f"""
<item>
  <title>{entry.title}</title>
  <link>{entry.link}</link>
  <description>{entry.get("description","")}</description>
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