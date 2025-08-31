import os
import feedparser
import re

def has_rich_html(description):
    return re.search(r"<(a|img|ul|ol|li|h[1-6])\b", description, flags=re.IGNORECASE) is not None

def process_description(title, link, image_url, description):
    html = ""
    if title:
        html += f"<h3>{title}</h3>\n"
    if image_url:
        html += f'<a href="{link}"><img src="{image_url}" /></a>\n'
    html += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'
    if has_rich_html(description):
        html += description
        return f"<![CDATA[{html}]]>"

    # procesado simplificado
    description = description.replace("&", "&amp;")
    return f"<![CDATA[{html}{description}]]>"

def build_item(entry):
    title = getattr(entry, "title", "")
    link = getattr(entry, "link", "")
    description = getattr(entry, "description", "")
    image_url = getattr(entry, "itunes_image", "")

    item = f"<item>\n"
    if title:
        item += f"  <title><![CDATA[{title}]]></title>\n"
    if link:
        item += f"  <link>{link}</link>\n"
    item += f"  <description>{process_description(title, link, image_url, description)}</description>\n"
    if hasattr(entry, "enclosures"):
        for enc in entry.enclosures:
            if "href" in enc:
                item += f'  <enclosure url="{enc["href"]}" type="{enc.get("type","audio/mpeg")}" />\n'
    if image_url:
        item += f'  <itunes:image href="{image_url}" />\n'
    guid = getattr(entry, "id", link)
    item += f"  <guid>{guid}</guid>\n"
    item += "</item>\n"
    return item

def update_feed(feed_dir):
    source_file = os.path.join(feed_dir, "source.txt")
    dest_file = os.path.join(feed_dir, "feed.xml")
    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [line.strip() for line in f if line.strip()]

    with open(dest_file, "r", encoding="utf-8") as f:
        xml_content = f.read()

    # buscar GUIDs existentes
    existing_guids = re.findall(r"<guid>(.*?)</guid>", xml_content)

    new_items = ""
    for url in source_urls:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            guid = getattr(entry, "id", getattr(entry, "guid", entry.link))
            if guid in existing_guids:
                continue
            new_items += build_item(entry)
            existing_guids.append(guid)

    if new_items:
        # Insertar justo antes de </channel>
        xml_content = xml_content.replace("</channel>", new_items + "</channel>")
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(xml_content)
        print(f"✔️ {feed_dir} actualizado con nuevos items")
    else:
        print(f"= {feed_dir} sin cambios")

def main():
    base_dir = os.path.join(os.getcwd(), "public")
    for folder in os.listdir(base_dir):
        feed_dir = os.path.join(base_dir, folder)
        if os.path.isdir(feed_dir):
            update_feed(feed_dir)

if __name__ == "__main__":
    main()