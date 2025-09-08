#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresca feeds: copia TODO desde el inicio de feed0.xml hasta ANTES del primer <item>
y lo pega delante de los <item> existentes en feed.xml (sin eliminar los items de feed.xml).
Crea una copia de seguridad de feed.xml antes de sobrescribir.
"""
from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

# Ajusta si tu estructura es diferente
BASE_DIR = Path(__file__).resolve().parent.parent / "public"

# Busca la primera etiqueta <item (ignora mayúsc/minúsc)
ITEM_RE = re.compile(r"<\s*item\b", re.IGNORECASE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _backup(path: Path) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(f"{path.name}.bak.{ts}")
    shutil.copy2(path, bak)
    return bak


def refresh_feed(feed0_path: Path, feed_path: Path, dry_run: bool = False) -> None:
    feed0_txt = _read_text(feed0_path)
    feed_txt = _read_text(feed_path)

    # Extraer encabezado EXACTO de feed0 (todo hasta justo antes del primer <item)
    m0 = ITEM_RE.search(feed0_txt)
    header_end = m0.start() if m0 else len(feed0_txt)
    header_from_feed0 = feed0_txt[:header_end]

    # Extraer la parte de items / resto de feed (desde el primer <item> de feed)
    m1 = ITEM_RE.search(feed_txt)
    if m1:
        items_and_trailer = feed_txt[m1.start():]
    else:
        # Si feed.xml no tiene items, intentamos usar el cierre existente en feed.xml
        close_pos = feed_txt.find("</channel>")
        if close_pos != -1:
            items_and_trailer = feed_txt[close_pos:]
        else:
            # Fallback: añadimos cierres estándar para que el XML quede bien formado
            items_and_trailer = "\n</channel>\n</rss>\n"

    new_content = header_from_feed0 + items_and_trailer

    print(f"-> Preparando actualizar: {feed_path}")
    if dry_run:
        print("DRY RUN activado: no se sobrescribe nada.")
        return

    bak = _backup(feed_path)
    print(f"   Copia de seguridad creada: {bak}")

    _write_text(feed_path, new_content)
    print(f"   Feed actualizado correctamente: {feed_path}")


def main():
    if not BASE_DIR.exists():
        print(f"ERROR: BASE_DIR no existe: {BASE_DIR}", file=sys.stderr)
        return

    for podcast_dir in sorted(BASE_DIR.iterdir()):
        if not podcast_dir.is_dir():
            continue
        feed0 = podcast_dir / "feed0.xml"
        feed = podcast_dir / "feed.xml"
        if feed0.exists() and feed.exists():
            try:
                refresh_feed(feed0, feed, dry_run=False)
            except Exception as exc:
                print(f"ERROR procesando {podcast_dir}: {exc}", file=sys.stderr)
        else:
            print(f"Omitido {podcast_dir}: falta feed0.xml o feed.xml")


if __name__ == "__main__":
    main()