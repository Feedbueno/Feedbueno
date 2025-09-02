#!/usr/bin/env python3
"""
scripts/update_iniciativas.py

Versión robusta que reutiliza todo desde update_feeds.py y detecta
automáticamente las firmas de process_description_block / replace_description
para mantener compatibilidad con cambios futuros.
Imprime información detallada para debug en los logs de Actions.
"""
import os
import re
import argparse
import inspect
import traceback
import update_feeds as uf  # importar el módulo completo y usar sus funciones

def ensure_itunes_tags(item_xml: str, title_text: str) -> str:
    """
    Añade o modifica itunes:season=1 y itunes:episode=N (extraído del título).
    """
    # Forzar <itunes:season>1</itunes:season>
    if re.search(r"<itunes:season>", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(r"<itunes:season>.*?</itunes:season>",
                          "<itunes:season>1</itunes:season>",
                          item_xml, flags=re.IGNORECASE | re.DOTALL)
    else:
        item_xml = re.sub(r"</item>", "<itunes:season>1</itunes:season>\n</item>",
                          item_xml, flags=re.IGNORECASE)

    # Extraer número del título
    m = re.search(r"(\d+)", title_text)
    episode_num = m.group(1) if m else "1"

    if re.search(r"<itunes:episode>", item_xml, flags=re.IGNORECASE):
        item_xml = re.sub(r"<itunes:episode>.*?</itunes:episode>",
                          f"<itunes:episode>{episode_num}</itunes:episode>",
                          item_xml, flags=re.IGNORECASE | re.DOTALL)
    else:
        item_xml = re.sub(r"</item>", f"<itunes:episode>{episode_num}</itunes:episode>\n</item>",
                          item_xml, flags=re.IGNORECASE)

    return item_xml

def try_call(func, arg_lists):
    """
    Intenta llamar func con cada tuple de args en arg_lists hasta que
    uno funcione (no TypeError). Devuelve (resultado, used_args_tuple) o
    (None, None) si todos fallan.
    """
    for args in arg_lists:
        try:
            return func(*args), args
        except TypeError:
            continue
        except Exception:
            # Si la función lanza otra excepción, la propagamos (no la ignoramos),
            # porque puede ser un error real al procesar contenido.
            raise
    return None, None

def update_feed_dir_iniciativas(feed_dir: str, search_text: str, source_filename: str):
    print(f"\n--- Procesando carpeta: {feed_dir} (buscar '{search_text}' usando {source_filename}) ---")
    source_file = os.path.join(feed_dir, source_filename)
    dest_file = os.path.join(feed_dir, "feed.xml")

    if not os.path.exists(source_file):
        print(f"⏭️  Omitido: no existe el archivo de fuentes: {source_file}")
        return
    if not os.path.exists(dest_file):
        print(f"⏭️  Omitido: no existe el feed destino: {dest_file}")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        source_urls = [ln.strip() for ln in f if ln.strip()]
    print(f"  - URLs en {source_filename}: {len(source_urls)}")
    if not source_urls:
        print("ℹ️  Archivo de fuentes vacío.")
        return

    with open(dest_file, "r", encoding="utf-8") as f:
        dest_xml = f.read()

    # Datos del feed destino (para avisos y op3)
    atom_link = uf.find_attr(dest_xml, "atom:link", "href") or ""
    feed_image = uf.find_attr(dest_xml, "itunes:image", "href") or ""
    op3_prefix = uf.find_tag_text(dest_xml, "op3") or ""
    print(f"  - atom:link (destino): '{atom_link}'")
    print(f"  - itunes:image (canal): '{feed_image}'")
    print(f"  - op3 prefix: '{op3_prefix}'")

    existing = uf.existing_keys_from_feed(dest_xml)
    print(f"  - items ya existentes en feed destino: {len(existing)} keys")

    new_items = []
    om_counter = 1

    for src in source_urls:
        print(f"\n  Leyendo fuente: {src}")
        try:
            raw_items = uf.fetch_source_items(src)
        except Exception as e:
            print(f"  ⚠️ Error al obtener items de {src}: {e}")
            traceback.print_exc()
            continue

        print(f"   - Ítems recuperados: {len(raw_items)}")
        for idx, raw_item in enumerate(raw_items, start=1):
            try:
                title_inner = uf.find_tag_text(raw_item, "title")
                title_txt = uf.strip_cdata(title_inner)
                matches = (search_text.lower() in title_txt.lower())
                print(f"    * Item {idx}: title='{title_txt[:70]}'... match={matches}")

                if not matches:
                    continue

                key = uf.item_key_from_xml(raw_item)
                if key in existing:
                    print("      - Ya existe en feed destino -> saltando")
                    continue

                link_inner = uf.find_tag_text(raw_item, "link")
                img = (uf.find_attr(raw_item, "itunes:image", "href")
                       or uf.find_attr(raw_item, "media:thumbnail", "url")
                       or "")
                desc_inner = uf.find_tag_text(raw_item, "description")

                sec_id = str(om_counter)

                # Llamar a process_description_block con distintas firmas posibles.
                # Probamos variantes (de mayor a menor aridad), para mantener compat.
                process_variants = [
                    (uf.strip_cdata(title_inner), uf.strip_cdata(link_inner), img, desc_inner, feed_image, atom_link, sec_id),
                    (uf.strip_cdata(title_inner), uf.strip_cdata(link_inner), img, desc_inner, atom_link, sec_id, feed_image),
                    (uf.strip_cdata(title_inner), uf.strip_cdata(link_inner), img, desc_inner, feed_image, sec_id),
                    (uf.strip_cdata(title_inner), uf.strip_cdata(link_inner), img, desc_inner, feed_image),
                    (uf.strip_cdata(title_inner), uf.strip_cdata(link_inner), img, desc_inner),
                ]
                new_desc, used = try_call(uf.process_description_block, process_variants)
                if new_desc is None:
                    raise RuntimeError("No se pudo llamar a process_description_block con ninguna firma conocida.")
                print(f"      - process_description_block llamada con {len(used)} args")

                # Llamar a replace_description con variantes posibles
                replace_variants = [
                    (raw_item, new_desc, sec_id, atom_link),
                    (raw_item, new_desc, new_desc, sec_id),
                    (raw_item, new_desc),
                ]
                replaced, used2 = try_call(uf.replace_description, replace_variants)
                if replaced is None:
                    raise RuntimeError("No se pudo llamar a replace_description con ninguna firma conocida.")
                new_item = replaced
                print(f"      - replace_description llamada con {len(used2)} args")

                # Prefijo OP3 en enclosure (si aplica)
                if op3_prefix:
                    m = re.search(r'<enclosure\b([^>]*)url="([^"]+)"([^>]*)/?>', new_item, flags=re.IGNORECASE)
                    if m:
                        orig_url = m.group(2)
                        new_url = op3_prefix.strip() + orig_url
                        new_item = re.sub(r'(<enclosure\b[^>]*url=")[^"]+(")', rf'\1{new_url}\2', new_item, flags=re.IGNORECASE)
                        print("      - Se aplicó op3 prefix a enclosure")

                # Forzar tags itunes
                new_item = ensure_itunes_tags(new_item, title_txt)

                new_items.append(new_item)
                existing.add(key)
                om_counter += 1

            except Exception as e:
                print(f"    ⚠️ Error procesando item {idx} de {src}: {e}")
                traceback.print_exc()
                continue

    if not new_items:
        print("\n= Resultado: no se añadieron episodios nuevos (filtro / duplicados / errores).")
        return

    # Insertar arriba (antes del primer <item>)
    insertion_block = "\n".join(new_items)
    first_item = re.search(r"<item\b", dest_xml, flags=re.IGNORECASE)
    if first_item:
        insert_pos = first_item.start()
        updated_xml = dest_xml[:insert_pos] + insertion_block + "\n" + dest_xml[insert_pos:]
    else:
        updated_xml = re.sub(r"</channel>\s*$", insertion_block + "\n</channel>", dest_xml,
                             flags=re.IGNORECASE | re.DOTALL)

    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(updated_xml)

    print(f"\n✅ {feed_dir}: añadidos {len(new_items)} episodios nuevos que contienen '{search_text}'")
    print(f"  - Feed destino actualizado en: {dest_file}")

def main():
    parser = argparse.ArgumentParser(description="Actualizar feeds filtrando por título.")
    parser.add_argument("--text", required=True, help="Texto a buscar en el título (insensible a mayúsculas).")
    parser.add_argument("--source", required=True, help="Archivo fuente (ej. imetal.txt, imario.txt).")
    args = parser.parse_args()

    base = os.path.join(os.getcwd(), "public")
    if not os.path.isdir(base):
        print("❌ No existe la carpeta 'public'")
        return

    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            update_feed_dir_iniciativas(path, args.text, args.source)

if __name__ == "__main__":
    main()