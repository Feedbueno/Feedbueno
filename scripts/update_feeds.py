#!/usr/bin/env python3
# update_feeds.py
# -*- coding: utf-8 -*-
"""
Actualizador de feeds (update_feeds.py)

Funciones públicas (usadas por update_iniciativas.py en tu ejemplo):
 - fetch_source_items(url)
 - existing_keys_from_feed(dest_xml)
 - find_tag_text(xml, tag)
 - find_attr(xml, tag, attr)
 - strip_cdata(text)
 - item_key_from_xml(item_xml)
 - process_description_block(*args)
 - replace_description(*args)

Comportamiento:
 - Inserta nuevos <item> antes del primer <item> en feed destino.
 - No modifica el resto del feed.
 - Cumple las reglas solicitadas para om:sec, om:des, op3-enclosure prefix,
   y la transformación completa de description.
"""
import os
import re
import requests
import hashlib
import html
from html import escape
from typing import List, Set, Tuple, Optional

# Regex util
ITEM_RE = re.compile(r"<item\b[^>]*>.*?</item>", re.IGNORECASE | re.DOTALL)

# --- I/O básico (compatibilidad con tu script original) ---
def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_text(path: str, text: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def fetch_xml(url: str, timeout: int = 20) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Feedbueno-Updater/1.0"})
    r.raise_for_status()
    return r.text

# --- Extracción / utilidades XML simples ---
def extract_items(xml_text: str) -> List[str]:
    """Devuelve lista de bloques <item>...</item>"""
    return ITEM_RE.findall(xml_text)

def find_tag_text(xml: str, tag: str) -> Optional[str]:
    """
    Extrae contenido entre <tag...>...</tag>, sin CDATA si existe.
    Soporta tags con namespace (p.ej. itunes:season) pasados como 'itunes:season'.
    """
    # Buscamos la primera coincidencia del tag (ignorando atributos)
    m = re.search(rf"<{re.escape(tag)}\b[^>]*>(.*?)</{re.escape(tag)}>",
                  xml, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    # Quitar CDATA si existe
    if val.startswith("<![CDATA[") and val.endswith("]]>"):
        val = val[len("<![CDATA["):-len("]]>")]
    return val

def find_attr(xml: str, tag: str, attr: str) -> Optional[str]:
    """
    Busca <tag ... attr="..."> y devuelve el valor del atributo (primera ocurrencia).
    Soporta namespaced tags.
    """
    # Permitir <tag ... attr='...' ...> o "..."
    m = re.search(rf"<{re.escape(tag)}\b[^>]*\b{re.escape(attr)}=['\"]([^'\"]+)['\"]",
                  xml, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return m.group(1)

def extract_enclosure_url(item_xml: str) -> Optional[str]:
    m = re.search(r'<enclosure\b[^>]*\burl=["\']([^"\']+)["\']', item_xml, re.IGNORECASE)
    return m.group(1) if m else None

def strip_cdata(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text
    if t.startswith("<![CDATA["):
        t = t[len("<![CDATA["):]
    if t.endswith("]]>"):
        t = t[:-len("]]>")]
    return t

def item_key_from_xml(item_xml: str) -> str:
    """
    Clave de deduplicación:
     1) guid
     2) link
     3) enclosure url
     4) hash MD5 del bloque
    """
    guid = find_tag_text(item_xml, "guid")
    if guid:
        return "guid::" + strip_cdata(guid)
    link = find_tag_text(item_xml, "link")
    if link:
        return "link::" + strip_cdata(link)
    enc = extract_enclosure_url(item_xml)
    if enc:
        return "encl::" + enc
    return "hash::" + hashlib.md5(item_xml.encode("utf-8", errors="ignore")).hexdigest()

def existing_keys_from_feed(dest_xml: str) -> Set[str]:
    items = extract_items(dest_xml)
    return set(item_key_from_xml(it) for it in items)

def first_item_pos(dest_xml: str) -> int:
    m = re.search(r"<item\b", dest_xml, re.IGNORECASE)
    if m:
        return m.start()
    m = re.search(r"</channel>", dest_xml, re.IGNORECASE)
    return m.start() if m else -1

# --- Utilidades para om:sec únicas ---
def collect_existing_om_secs(dest_xml: str) -> Set[str]:
    """Recolecta todos los om:sec (sin namespace checks complejos)."""
    secs = set()
    for m in re.finditer(r"<om:sec\b[^>]*>(.*?)</om:sec>", dest_xml, re.IGNORECASE | re.DOTALL):
        val = m.group(1).strip()
        if val.startswith("<![CDATA[") and val.endswith("]]>"):
            val = val[len("<![CDATA["):-len("]]>")]
        secs.add(val)
    return secs

def make_candidate_from_itunes(item_xml: str) -> Optional[str]:
    season = find_tag_text(item_xml, "itunes:season")
    episode = find_tag_text(item_xml, "itunes:episode")
    if season and episode:
        s = re.sub(r"\D+", "", season) or "0"
        e = re.sub(r"\D+", "", episode) or "0"
        return f"s{s}e{e}"
    return None

def search_number_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Buscamos patrones T2E3, s1e1, "Temporada 2 Episodio 3", o digits
    m = re.search(r"[sS](\d+)[eE](\d+)", text)
    if m:
        return f"s{m.group(1)}e{m.group(2)}"
    m = re.search(r"[Tt](\d+)[^\d]{0,3}[Ee](\d+)", text)
    if m:
        return f"s{m.group(1)}e{m.group(2)}"
    # Buscar 'temporada 2 episodio 3' estilo
    m = re.search(r"temporad[ae]\s*(\d+)[^\d]{0,6}episod", text, re.IGNORECASE)
    if m:
        season = m.group(1)
        m2 = re.search(r"episod(?:io)?\D*(\d+)", text, re.IGNORECASE)
        if m2:
            return f"s{season}e{m2.group(1)}"
    # fallback a primer número encontrado
    m = re.search(r"(\d+)", text)
    if m:
        return f"n{m.group(1)}"
    return None

def generate_unique_om_sec(item_xml: str, dest_xml: str, fallback_counter_start: int = 1) -> str:
    existing = collect_existing_om_secs(dest_xml)
    # 1) intentar itunes season/episode
    cand = make_candidate_from_itunes(item_xml)
    if cand and cand not in existing:
        return cand
    # 2) buscar en title o description
    title = find_tag_text(item_xml, "title") or ""
    desc = find_tag_text(item_xml, "description") or ""
    t = strip_cdata(title) + "\n" + strip_cdata(desc)
    cand2 = search_number_in_text(t)
    if cand2 and cand2 not in existing:
        return cand2
    # 3) generar sec incremental autoNNN
    i = fallback_counter_start
    while True:
        candidate = f"auto{i}"
        if candidate not in existing:
            return candidate
        i += 1

# --- Transformación de description según requisitos ---
URL_RE = re.compile(
    r'(?P<url>https?://[^\s"<>()]+)', re.IGNORECASE
)
IMG_EXT_RE = re.compile(r".*\.(?:jpg|jpeg|png|gif|webp|svg)(?:\?.*)?$", re.IGNORECASE)
EMAIL_RE = re.compile(r'(?P<email>\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)')

BLOCK_TAGS = {"p", "br", "hr", "ol", "ul", "li"}

def remove_unwanted_tags_keep_text(html_text: str) -> str:
    """
    Quita tags no permitidos pero conserva su contenido y mantiene
    <p>, <br>, <hr>, <ol>, <ul>, <li>.
    Además simplifica atributos (elimina la mayoría).
    NOTA: no es un parser HTML perfecto, pero robusta para RSS typical content.
    """
    text = html_text

    # Eliminar scripts y estilos completos
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    # Convertir comentarios a vacío
    text = re.sub(r"(?s)<!--.*?-->", "", text)

    # Normalizar tags de cierre <hr /> <br /> -> <hr> <br>
    text = re.sub(r"<(br|hr)\b[^>]*?/?>", lambda m: f"<{m.group(1)} />", text, flags=re.IGNORECASE)

    # Extraer <img src="..."> y reemplazar por la URL (temporal), para luego procesar
    def img_to_url(m):
        attrs = m.group(0)
        src = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs)
        if src:
            return src.group(1)
        return ""
    text = re.sub(r"(?i)<img\b[^>]*>", img_to_url, text)

    # Convertir enlaces <a href="...">Texto</a> -> 'URL' (porque pediste convertirlo a enlace directo)
    def a_to_url(m):
        href = m.group(1)
        inner = m.group(2)
        # Si inner looks like an image or same as href, keep href as text
        return href
    text = re.sub(r'(?is)<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', a_to_url, text)

    # Eliminar cualquier etiqueta no permitida pero conservar contenido.
    # Permitir p, br, hr, ol, ul, li
    def strip_tag_keep_content(m):
        tag = m.group(1).lower()
        inner = m.group(2)
        if tag in BLOCK_TAGS:
            # Reconstruir simple sin atributos (excepto <ol start=> lo manejamos después)
            if tag == "br":
                return "<br />"
            if tag == "hr":
                return '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'
            if tag == "p":
                return f"<p>{inner}</p>"
            if tag in ("ol", "ul", "li"):
                return f"<{tag}>{inner}</{tag}>"
        # Si la etiqueta no está en permitidas, devolver solo contenido
        return inner
    # Procesar tags con contenido
    text = re.sub(r"(?is)<([^/\s>]+)[^>]*>(.*?)</\1>", strip_tag_keep_content, text)
    # Finalmente quitar tags aisladas
    text = re.sub(r"(?is)<[^>]+>", "", text)

    return text

def convert_plain_urls_and_emails_to_links(text: str) -> str:
    # Primero mails
    def mailer(m):
        mail = m.group("email")
        return f'<a href="mailto:{mail}">{mail}</a>'
    text = EMAIL_RE.sub(mailer, text)

    # Después URLs: si URL es imagen, convertir a <a><img/></a>
    def linker(m):
        url = m.group("url")
        if IMG_EXT_RE.match(url):
            return f'<a href="{url}"><img src="{url}" /></a>'
        else:
            return f'<a href="{url}">{url}</a>'
    text = URL_RE.sub(linker, text)
    return text

def detect_and_convert_plain_lists(text: str) -> str:
    """
    Detecta listas presentadas como líneas en texto y las convierte en ol/ul.
    Ejemplos:
      "0. Promo\n1. Episodio 1\n2. Episodio 2" -> <ol start=0>...
      "- item\n- item" -> <ul>...
    Detecta numeración flexible: "1.", "1-", "1.-", "1", etc.
    """
    lines = text.splitlines()
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect ordered list line
        mnum = re.match(r"^\s*(\d+)\s*[\.\-\)]?\s*(.*)$", line)
        mbul = re.match(r"^\s*([\-\*\u2022])\s+(.*)$", line)
        if mnum:
            # Build ordered list
            start = int(mnum.group(1))
            items = [mnum.group(2).strip()]
            i += 1
            while i < len(lines):
                m2 = re.match(r"^\s*(\d+)\s*[\.\-\)]?\s*(.*)$", lines[i])
                if m2:
                    items.append(m2.group(2).strip())
                    i += 1
                else:
                    break
            # produce <ol start=...>
            ol = [f'<ol start={start}>']
            for it in items:
                ol.append(f"<li>{it}</li>")
            ol.append("</ol>")
            out_lines.append("\n".join(ol))
            continue
        elif mbul:
            items = [mbul.group(2).strip()]
            i += 1
            while i < len(lines):
                m2 = re.match(r"^\s*([\-\*\u2022])\s+(.*)$", lines[i])
                if m2:
                    items.append(m2.group(2).strip())
                    i += 1
                else:
                    break
            ul = ["<ul>"]
            for it in items:
                ul.append(f"<li>{it}</li>")
            ul.append("</ul>")
            out_lines.append("\n".join(ul))
            continue
        else:
            out_lines.append(line)
            i += 1
    return "\n".join(out_lines)

def ensure_paragraphs(text: str) -> str:
    """
    Asegura que los párrafos estén envueltos en <p>...</p> cuando no están ya en elementos de bloque.
    Conserva <ol>, <ul>, <hr />, <br />.
    """
    blocks = []
    parts = re.split(r"(\n\s*\n+)", text)  # dividir por párrafos (doble salto)
    for part in parts:
        if not part.strip():
            blocks.append("")
            continue
        # Si la parte ya contiene tags de bloque al inicio, dejarla
        if re.match(r"^\s*<(p|ol|ul|hr|div|h\d|blockquote)\b", part.strip(), re.IGNORECASE):
            blocks.append(part.strip())
        else:
            # Envolver cada línea en <p>, pero si hay <br /> dentro, mantener
            # Si ya tiene <a> o <img> o <li>, no envolver por lineas con li
            if "<li>" in part:
                blocks.append(part.strip())
            else:
                # dividir por line breaks y envolver líneas no vacías
                lines = [ln.strip() for ln in part.splitlines() if ln.strip()]
                if not lines:
                    continue
                if len(lines) == 1:
                    blocks.append(f"<p>{lines[0]}</p>")
                else:
                    # múltiples líneas -> cada una como <p>
                    blocks.extend([f"<p>{ln}</p>" for ln in lines])
    # Limpiar vacíos dobles
    return "\n".join([b for b in blocks if b != ""])

def bold_relevant_text(text: str) -> str:
    """
    Coloca <b> alrededor de frases relevantes:
    heurística simple: lineas que contienen 'episod', 'temporad', 'capítulo'
    o que empiecen con 'Promo', 'Avance', etc.
    """
    lines = text.splitlines()
    out = []
    for ln in lines:
        if re.search(r"\b(episod|temporad|promo|avance|capítulo|capitulo)\b", ln, re.IGNORECASE):
            out.append(f"<p><b>{ln}</b></p>")
        else:
            out.append(ln)
    return "\n".join(out)

def has_dashed_hr(text: str) -> bool:
    return 'border-top:1px dashed' in text

def build_initial_header(title: str, itunes_image_href: str, atom_link: str, sec_id: str, dest_has_hr: bool) -> str:
    """
    Construye las 4 líneas iniciales que pides (title, image, 'Si no ves las imágenes entra en LINK', hr),
    sólo si el description no contiene ya la hr dashed.
    """
    if dest_has_hr:
        return ""
    lines = []
    # 1: título del episodio en la primera línea
    title_line = strip_cdata(title).strip()
    if title_line:
        lines.append(f"<p>{escape(title_line)}</p>")
    # 2: imagen de itunes:image como <a><img/></a>
    if itunes_image_href:
        img_escaped = escape(itunes_image_href, quote=True)
        lines.append(f'<p><a href="{img_escaped}"><img src="{img_escaped}" /></a></p>')
    # 3: "Si no ves las imágenes entra en LINK" -> LINK = atom_link + '#' + om:sec
    if atom_link and sec_id:
        link_full = atom_link.rstrip("/") + "#" + sec_id
        link_escaped = escape(link_full, quote=True)
        lines.append(f'<p>Si no ves las imágenes entra en <a href="{link_escaped}">{link_escaped}</a></p>')
    # 4: hr dashed
    lines.append('<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />')
    return "\n".join(lines)

# --- Funciones públicas que usan otros scripts --- #

def fetch_source_items(url: str) -> List[str]:
    """
    Descarga el XML de la URL y devuelve lista de <item>... bloques.
    """
    xml = fetch_xml(url)
    return extract_items(xml)

def process_description_block(*args) -> str:
    """
    Función robusta con múltiples firmas (para compatibilidad con update_iniciativas.py).
    Intenta interpretar los argumentos en orden:
      (title, link, img, desc_inner, feed_image, atom_link, sec_id)
    o versiones más cortas.
    Devuelve el HTML final de description (sin CDATA), listo para envolverse en CDATA si se desea.
    """
    # desempacar argumentos con tolerancia
    title = ""
    link = ""
    img = ""
    desc_inner = ""
    feed_image = ""
    atom_link = ""
    sec_id = ""

    if len(args) >= 1:
        title = args[0] or ""
    if len(args) >= 2:
        link = args[1] or ""
    if len(args) >= 3:
        img = args[2] or ""
    if len(args) >= 4:
        desc_inner = args[3] or ""
    if len(args) >= 5:
        feed_image = args[4] or ""
    if len(args) >= 6:
        atom_link = args[5] or ""
    if len(args) >= 7:
        sec_id = args[6] or ""

    # Normalizar desc
    desc = strip_cdata(desc_inner)

    # 1) Procesar HTML: quitar scripts, transformar <img> y <a> a URLs,
    #    quitar tags no permitidos, mantener p, br, hr, ol, ul, li.
    cleaned = remove_unwanted_tags_keep_text(desc)

    # 2) Detectar listas no declaradas y convertir
    lists_converted = detect_and_convert_plain_lists(cleaned)

    # 3) Convertir urls y mails a enlaces (imagenes -> <a><img/></a>)
    links_converted = convert_plain_urls_and_emails_to_links(lists_converted)

    # 4) Añadir título en primera línea
    # Nota: title puede contener HTML/CDATA, lo escapamos para evitar roturas
    title_html = strip_cdata(title) or ""
    if title_html:
        # evitar que el título termine dentro de <p> duplicado más adelante
        title_block = f"<p>{escape(title_html)}</p>"
    else:
        title_block = ""

    # 5) Imagen de itunes: si existe img (parámetro), usarlo; si no, usar feed_image
    itunes_img = img or feed_image or ""
    # image block
    img_block = ""
    if itunes_img:
        img_esc = escape(itunes_img, quote=True)
        img_block = f'<p><a href="{img_esc}"><img src="{img_esc}" /></a></p>'

    # 6) Cabecera "Si no ves las imágenes entra en LINK..."
    hr_present = has_dashed_hr(links_converted) or has_dashed_hr(cleaned) or has_dashed_hr(desc)
    header_block = ""
    if atom_link and sec_id and not hr_present:
        link_full = atom_link.rstrip("/") + "#" + sec_id
        header_block = f'<p>Si no ves las imágenes entra en <a href="{escape(link_full, quote=True)}">{escape(link_full)}</a></p>\n<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />'

    # 7) Asegurar párrafos
    main_body = ensure_paragraphs(links_converted)

    # 8) Poner negritas heurísticas
    main_body = bold_relevant_text(main_body)

    # Componer: si no había hr, añadimos las 4 líneas (title, image, aviso link, hr)
    initial_header = ""
    if not hr_present:
        # Construir con título, imagen, aviso y HR (si existe alguno)
        initial_header = "\n".join([block for block in (title_block, img_block, header_block) if block])
    else:
        # si hr ya presente, no duplicar; sin embargo debemos asegurarnos que el título e imagen estén en primera línea según pedido:
        # Poner el título y la imagen antes del contenido si no están ya.
        initial_header = "\n".join([b for b in (title_block, img_block) if b])

    # unir todo (evitar duplicar hr)
    components = []
    if initial_header:
        components.append(initial_header)
    if main_body:
        components.append(main_body)

    full_html = "\n".join(components).strip()

    # Si description final no contiene la HR dashed y header_block no incluído, aseguramos la linea final
    # (pero ya la añadimos más arriba si no había)
    return full_html

def replace_description(*args) -> str:
    """
    Reemplaza / añade la descripción en un item XML y añade <om:sec> y <om:des>.
    Variantes de llamadas posibles (compat con tu script):
      replace_description(raw_item, new_desc, sec_id, atom_link)
      replace_description(raw_item, new_desc, new_desc, sec_id)
      replace_description(raw_item, new_desc)
    Devuelve el item XML actualizado (string).
    """
    # Interpretar args
    if len(args) == 0:
        raise TypeError("replace_description requiere al menos raw_item y new_desc")
    raw_item = args[0]
    new_desc = args[1] if len(args) >= 2 else ""
    sec_id = None
    atom_link = None
    # buscar sec_id en los argumentos si aparece
    for a in args[2:]:
        if isinstance(a, str) and re.match(r"^[sSnNtTaAuo0-9]", a):
            # heurística: si parece sec (s1e1, autoNN, n123) lo tomamos
            sec_id = a
            continue
        if isinstance(a, str) and a.startswith("http"):
            atom_link = a
            continue
    # fallback
    sec_id = sec_id or (find_tag_text(raw_item, "om:sec") or "")

    # 1) Reemplazar / insertar <description>
    # new_desc debe quedar envuelto en <![CDATA[ ... ]]> para preservar HTML
    desc_block = f"<![CDATA[{new_desc}]]>"
    if re.search(r"<description\b[^>]*>.*?</description>", raw_item, flags=re.IGNORECASE | re.DOTALL):
        # reemplazar contenido
        new_item = re.sub(r"(<description\b[^>]*>).*?(</description>)",
                          rf"\1{desc_block}\2", raw_item, flags=re.IGNORECASE | re.DOTALL)
    else:
        # insertar antes de </item>
        new_item = re.sub(r"</item>", f"<description>{desc_block}</description>\n</item>", raw_item, flags=re.IGNORECASE)

    # 2) asegurar om:sec único: si se pasó sec_id usarlo, sino generarlo (necesitamos el feed destino para verificar unicidad
    #    pero en esta función no lo pasamos: esperamos que el llamador (update_one_feed) pase un sec correcto cuando sea requerido).
    #    Aquí: si ya existe om:sec en el item, lo actualizamos; si no existe y se pasa sec_id, lo insertamos; si no, no tocamos.
    if sec_id:
        if re.search(r"<om:sec\b[^>]*>.*?</om:sec>", new_item, flags=re.IGNORECASE | re.DOTALL):
            new_item = re.sub(r"(<om:sec\b[^>]*>).*?(</om:sec>)",
                              rf"\1{escape(sec_id)}\2", new_item, flags=re.IGNORECASE | re.DOTALL)
        else:
            # Insertar antes de </item>
            new_item = re.sub(r"</item>", f"<om:sec>{escape(sec_id)}</om:sec>\n</item>", new_item, flags=re.IGNORECASE)

    # 3) Construir om:des (a partir del contenido de description posterior a la HR dashed)
    # extraer description y buscar la HR dashed
    desc_inner = find_tag_text(new_item, "description") or ""
    desc_text = strip_cdata(desc_inner)
    # Dividir por la HR dashed indicada exactamente (o por la primera <hr ...dashed...>)
    hr_match = re.search(r'(<hr\b[^>]*border-top:1px dashed[^>]*>)', desc_text, re.IGNORECASE)
    omdes_content = ""
    if hr_match:
        # parte posterior a hr
        pieces = re.split(r'(<hr\b[^>]*border-top:1px dashed[^>]*>)', desc_text, flags=re.IGNORECASE)
        # encontrar el índice de la primera hr repetida
        # construir la substring después de la primera hr occurrence
        joined = "".join(pieces)
        # split once by pattern
        split_then = re.split(r'(?i)<hr\b[^>]*border-top:1px dashed[^>]*>', desc_text, maxsplit=1)
        if len(split_then) == 2:
            after_hr = split_then[1].strip()
            # Necesitamos 'escapar' el texto que no corresponde a etiquetas.
            # Simplificación segura: analizamos y escapamos texto entre '<' '>' sólo cuando no formen tags válidos.
            # Implementaremos una forma conservadora: mantendremos las etiquetas existentes y escaparemos el resto
            # usando una técnica simple: reemplazar '<' por '&lt;' y '>' por '&gt;' únicamente en fragmentos que no parecen tags.
            # Para mayor corrección, asumimos que after_hr contiene HTML parcial con tags ya limpios.
            # Por instrucción: "solo escape el texto que NO pertenezca a etiquetas".
            # Implementación práctica: reconstruir con regex que detecta tags y escapa texto entre ellos.
            parts = re.split(r"(<[^>]+?>)", after_hr)
            rebuilt = []
            for p in parts:
                if p.startswith("<") and p.endswith(">"):
                    # tag -> dejar tal cual
                    rebuilt.append(p)
                else:
                    # texto -> escapar caracteres especiales
                    rebuilt.append(escape(p))
            omdes_content = "<div>" + "".join(rebuilt).strip() + "</div>"
    else:
        # si no hay HR dashed, construir om:des con todo el description escapado (con un div)
        parts = re.split(r"(<[^>]+?>)", desc_text)
        rebuilt = []
        for p in parts:
            if p.startswith("<") and p.endswith(">"):
                rebuilt.append(p)
            else:
                rebuilt.append(escape(p))
        omdes_content = "<div>" + "".join(rebuilt).strip() + "</div>"

    # Insertar o reemplazar om:des
    if omdes_content:
        omdes_tag = f"<om:des>{omdes_content}</om:des>"
        if re.search(r"<om:des\b[^>]*>.*?</om:des>", new_item, flags=re.IGNORECASE | re.DOTALL):
            new_item = re.sub(r"(<om:des\b[^>]*>).*?(</om:des>)",
                              rf"\1{omdes_content}\2", new_item, flags=re.IGNORECASE | re.DOTALL)
        else:
            new_item = re.sub(r"</item>", f"{omdes_tag}\n</item>", new_item, flags=re.IGNORECASE)

    return new_item

# --- Lógica para procesar directorio de un podcast (modo standalone) --- #
def update_one_feed(podcast_dir: str):
    """
    Modo completo: lee source.txt (lista de URLs), descarga los items,
    aplica procesado de description, genera om:sec único (usando el feed destino),
    aplica prefijo op3 si existe en feed destino (tanto en <enclosure> como en el enlace final dentro de description),
    e inserta los items nuevos antes del primer <item> en feed.xml dentro de public/<podcast_dir>/ .
    """
    base = os.path.join("public", podcast_dir)
    source_file = os.path.join(base, "source.txt")
    dest_file = os.path.join(base, "feed.xml")

    if not os.path.exists(source_file) or not os.path.exists(dest_file):
        print(f"⚠️  {podcast_dir}: falta source.txt o feed.xml — se omite")
        return

    with open(source_file, "r", encoding="utf-8") as f:
        sources = [ln.strip() for ln in f if ln.strip()]

    if not sources:
        print(f"ℹ️  {podcast_dir}: source.txt vacío — se omite")
        return

    dest_xml = read_text(dest_file)

    existing_keys = existing_keys_from_feed(dest_xml)
    existing_secs = collect_existing_om_secs(dest_xml)

    ins_pos = first_item_pos(dest_xml)
    if ins_pos == -1:
        print(f"⚠️  {podcast_dir}: no se encontró <item> ni </channel> en feed.xml — se omite")
        return

    # Extraer datos del feed destino relevantes
    op3_prefix = find_tag_text(dest_xml, "op3") or ""
    atom_link = find_attr(dest_xml, "atom:link", "href") or ""
    feed_itunes_img = find_attr(dest_xml, "itunes:image", "href") or ""

    new_blocks = []
    new_keys = 0
    # contador fallback para generar om:sec si es necesario
    fallback_counter = 1

    for src in sources:
        try:
            src_xml = fetch_xml(src)
        except Exception as e:
            print(f"❌  {podcast_dir}: error al descargar {src} — {e}")
            continue

        items = extract_items(src_xml)
        if not items:
            print(f"ℹ️  {podcast_dir}: {src} no parece RSS 2.0 (<item> no encontrado) — se omite")
            continue

        for it in items:
            k = item_key_from_xml(it)
            if k in existing_keys:
                continue

            # Preparar datos
            title_inner = find_tag_text(it, "title") or ""
            link_inner = find_tag_text(it, "link") or ""
            img = find_attr(it, "itunes:image", "href") or find_attr(it, "media:thumbnail", "url") or ""
            desc_inner = find_tag_text(it, "description") or ""
            enclosure_url = extract_enclosure_url(it) or ""

            # Generar om:sec único para este item
            # intentamos a partir del propio item + el dest_xml (para no chocar)
            # construimos provisional item_with_tags para la generación (podría usar it)
            sec_candidate = None
            # 1) intentar itunes season/episode
            sec_candidate = make_candidate_from_itunes(it)
            if not sec_candidate:
                # 2) intentar buscar en title/desc
                sec_candidate = search_number_in_text(strip_cdata(title_inner) + "\n" + strip_cdata(desc_inner))
            # 3) fallback generado
            if not sec_candidate or sec_candidate in existing_secs:
                # buscar sec no repetido
                sec_candidate = generate_unique_om_sec(it, dest_xml, fallback_counter_start=fallback_counter)
                # avanzar fallback_counter para próximas iteraciones
                # si candidate es autoNN, extraer número y avanzar
                m = re.match(r"auto(\d+)", sec_candidate)
                if m:
                    fallback_counter = int(m.group(1)) + 1
                else:
                    fallback_counter += 1
            # marcar como usado
            existing_secs.add(sec_candidate)

            # Construir nueva descripción usando process_description_block
            new_desc = process_description_block(title_inner, link_inner, img, desc_inner, feed_itunes_img, atom_link, sec_candidate)

            # Insertar description en el item (y generar om:des)
            # replace_description admite varias firmas; pasamos raw_item, new_desc, sec_candidate, atom_link
            new_item = replace_description(it, new_desc, sec_candidate, atom_link)

            # Prefijar enclosure url si op3 existe (en el feed destino)
            if op3_prefix:
                # prefijamos en el tag enclosure
                if enclosure_url:
                    # aplicar prefijo en el tag enclosure
                    new_url = op3_prefix.strip() + enclosure_url
                    new_item = re.sub(r'(<enclosure\b[^>]*\burl=["\'])[^"\']+(["\'])',
                                      rf"\1{new_url}\2", new_item, flags=re.IGNORECASE)
                    # además, reemplazar el enlace final dentro de description que apunte al enclosure (si existe)
                    # buscamos la URL original en description CDATA y la sustituimos por prefijada en la parte de description
                    # Nota: description está envuelta en CDATA, pero en new_item lo está; hacemos replace dentro CDATA
                    def replace_in_cdata(match):
                        inner = match.group(1)
                        replaced = inner.replace(enclosure_url, new_url)
                        return f"<![CDATA[{replaced}]]>"
                    new_item = re.sub(r"<!\[CDATA\[(.*?)\]\]>", replace_in_cdata, new_item, flags=re.DOTALL)

            # Finalmente agregamos al conjunto
            new_blocks.append(new_item)
            existing_keys.add(k)
            new_keys += 1

    if not new_blocks:
        print(f"ℹ️  {podcast_dir}: sin ítems nuevos")
        return

    insertion_text = "\n" + "\n".join(new_blocks) + "\n"
    updated = dest_xml[:ins_pos] + insertion_text + dest_xml[ins_pos:]
    write_text(dest_file, updated)
    print(f"✅  {podcast_dir}: insertados {new_keys} ítems nuevos al principio (archivo: {dest_file})")

def main():
    root = "public"
    if not os.path.isdir(root):
        print("❌ No existe la carpeta 'public' en el directorio actual.")
        return
    for entry in os.listdir(root):
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            try:
                update_one_feed(entry)
            except Exception as e:
                print(f"⚠️  Error procesando {entry}: {e}")

if __name__ == "__main__":
    main()