import os import re import requests

-------------- utilidades de texto --------------

CDATA_OPEN = "<![CDATA[" CDATA_CLOSE = "]] >"

def strip_cdata(s: str) -> str: if s is None: return "" s = s.strip() if s.startswith(CDATA_OPEN) and s.endswith(CDATA_CLOSE): return s[len(CDATA_OPEN):-len(CDATA_CLOSE)] return s

def enc_cdata(s: str) -> str: return f"{CDATA_OPEN}{s}{CDATA_CLOSE}"

def findall_items(xml: str): return re.findall(r"<item\b[^>]>.?</item>", xml, flags=re.IGNORECASE | re.DOTALL)

def find_tag_text(xml: str, tag: str): m = re.search(rf"<{tag}\b[^>]>(.?)</{tag}>", xml, flags=re.IGNORECASE | re.DOTALL) return m.group(1) if m else ""

def find_attr(xml: str, tag: str, attr: str): m = re.search(rf"<{tag}\b[^>]\b{attr}="([^"]+)"[^>]/?>", xml, flags=re.IGNORECASE | re.DOTALL) return m.group(1) if m else ""

def replace_description(item_xml: str, new_desc_html_cdata: str) -> str: if re.search(r"<description\b", item_xml, flags=re.IGNORECASE): return re.sub( r"<description\b[^>]>.?</description>", f"<description>{new_desc_html_cdata}</description>", item_xml, flags=re.IGNORECASE | re.DOTALL ) else: return re.sub( r"</item>\s*$", f"<description>{new_desc_html_cdata}</description>\n</item>", item_xml, flags=re.IGNORECASE | re.DOTALL )

-------------- detección de HTML "fuerte" --------------

def has_rich_html(text: str) -> bool: if not text: return False return re.search(r"<(a|img|ul|ol|li|h[1-6]|p|br)\b", text, flags=re.IGNORECASE) is not None

-------------- construcción de la descripción --------------

def process_description_block(title_txt: str, link_txt: str, image_url: str, description_inner: str) -> str: header = "" if title_txt: header += f"<h3>{title_txt}</h3>\n" if image_url and link_txt: header += f'<a href="{link_txt}"><img src="{image_url}" /></a>\n' header += '<hr style="border:0;border-top:1px dashed #ccc;margin:20px 0;" />\n'

body = strip_cdata(description_inner or "")

if has_rich_html(body):
    final_html = header + body
    return enc_cdata(final_html)

# Caso "texto plano": aplicar transformaciones
# 1) Emails → mailto:
body = re.sub(
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'<a href="mailto:\1">\1</a>', body)

# 2) Enlaces a imágenes → <img> clicable
def repl_image(m):
    url = m.group(1)
    return f'<a href="{url}"><img src="{url}" /></a>'
body = re.sub(
    r'(?<!href=")(https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif)(?:[^\s<>"]*)?)',
    repl_image, body)

# 3) Enlaces normales (ignora imágenes ya convertidas)
def repl_link(m):
    url = m.group(1)
    return f'<a href="{url}">{url}</a>'
body = re.sub(
    r'(?<!href=")(https?://[^\s<>"]+)(?<!jpg)(?<!jpeg)(?<!png)(?<!gif)',
    repl_link, body)

# 4) Párrafos básicos
lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
body = "\n".join(f"<p>{ln}</p>" for ln in lines)

final_html = header + body
return enc_cdata(final_html)

-------------- claves para deduplicar --------------

def normalize_inner(t: str) -> str: t = strip_cdata(t or "") return re.sub(r"\s+", " ", t).strip().lower()

def item_key_from_xml(item_xml: str) -> str: guid = normalize_inner(find_tag_text(item_xml, "guid")) if guid: return "guid:" + guid link = normalize_inner(find_tag_text(item_xml, "link")) if link: return "link:" + link title = normalize_inner(find_tag_text(item_xml, "title")) pub = normalize_inner(find_tag_text(item_xml, "pubDate")) return "tp:" + title + "|" + pub

def existing_keys_from_feed(xml: str) -> set: return {item_key_from_xml(it) for it in findall_items(xml)}

-------------- obtención de ítems del feed origen (crudos) --------------

def fetch_source_items(url: str) -> list: r = requests.get(url, timeout=20, headers={ "User-Agent": "FeedbuenoUpdater/1.0 (+https://feedbueno.es)" }) r.raise_for_status() return findall_items(r.text)

-------------- actualización por carpeta --------------

def update_feed_dir(feed_dir: str): source_file = os.path.join(feed_dir, "source.txt") dest_file = os.path.join(feed_dir, "feed.xml")

if not (os.path.exists(source_file) and os.path.exists(dest_file)):
    print(f"⏭️  Omitido {feed_dir}: falta source.txt o feed.xml")
    return

with open(source_file, "r", encoding="utf-8") as f:
    source_urls = [ln.strip() for ln in f if ln.strip()]

if not source_urls:
    print(f"ℹ️  {feed_dir}: source.txt vacío")
    return

with open

