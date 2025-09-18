import os
import glob
import re

# Ruta a los feeds (subimos un nivel desde /scripts/)
BASE_PATH = os.path.join(os.path.dirname(__file__), "../public/*/feed.xml")

def process_feed(feed_path):
    print(f"Procesando {feed_path}")
    with open(feed_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex para encontrar cada <item>...</item>
    def repl_item(match):
        item = match.group(0)

        # Buscar <description>...</description>
        desc_match = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
        if not desc_match:
            return item

        desc_content = desc_match.group(1)
        # Eliminar CDATA si existe
        desc_clean = re.sub(r"^<!\[CDATA\[|\]\]>$", "", desc_content.strip())

        # Construir etiqueta om:des
        omdes_tag = f"<om:des>{desc_clean}</om:des>"

        if "<om:des>" in item:
            # Reemplazar si ya existe
            item = re.sub(r"<om:des>.*?</om:des>", omdes_tag, item, flags=re.DOTALL)
        else:
            # Insertar justo antes de </item>
            item = item.replace("</item>", f"{omdes_tag}</item>")

        return item

    # Reemplazar todos los items
    new_content = re.sub(r"<item\b.*?</item>", repl_item, content, flags=re.DOTALL)

    # Solo sobrescribir si hay cambios
    if new_content != content:
        with open(feed_path, "w", encoding="utf-8") as f:
            f.write(new_content)

def main():
    feeds = glob.glob(BASE_PATH)
    if not feeds:
        print("No se encontraron feeds.")
        return
    for feed in feeds:
        process_feed(feed)

if __name__ == "__main__":
    main()