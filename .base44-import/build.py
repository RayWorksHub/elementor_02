"""Prepare the approved editorial HTML for Base44's documented HTML import."""
from __future__ import annotations
import base64, hashlib, io, json, lzma, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

ROOT = Path('.base44-import')
EXPECTED = 'fd8c1bba4bc9ebe3bf69d63f14fba1050e731c1d1bd1e31bd65bb32abb6d8696'
parts = sorted(ROOT.glob('source-*.b64'))
assert len(parts) == 4, 'Missing original HTML transport part'
raw = lzma.decompress(base64.b64decode(''.join(p.read_text().strip() for p in parts)))
assert hashlib.sha256(raw).hexdigest() == EXPECTED, 'Original HTML checksum mismatch'
html = raw.decode('utf-8')
data = json.loads(Path('eugm-adatok.json').read_text())
assert len(data['pages']) == 15 and len(data['regions']) >= 15
photos = {
 'team': 'https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=1400&q=82',
 'office': 'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=82',
 'architecture': 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1400&q=82',
 'desk': 'https://images.unsplash.com/photo-1499750310107-5fef28a66643?auto=format&fit=crop&w=1400&q=82',
}
replacements = [('hero-fooldal', photos['architecture']), ('digitalis-gazdasag', photos['team']), ('promise-group', photos['office'])]
aliases = {u:u for u in photos.values()}
for text in [html, *data['regions'].values()]:
 if not isinstance(text, str):
  continue
 for image in BeautifulSoup(text, 'html.parser').find_all('img'):
  original = image.get('src', '')
  if not original or original.startswith('data:'):
   continue
  url = urljoin('https://grafcom.hu', original)
  target = next((v for pattern,v in replacements if pattern in url),url)
  aliases[original] = target
  aliases[url] = target
urls = sorted(set(aliases.values()))
print('Image sources:',len(urls),flush=True)
for u in urls:
 print('PHOTO',u,flush=True)
cache = ROOT/'image-cache'
cache.mkdir(exist_ok=True)

def fetch_image(url: str):
 parsed = urlparse(url)
 if parsed.scheme != 'https' or parsed.hostname not in {'grafcom.hu','www.grafcom.hu','images.unsplash.com'}:
  raise ValueError('Unexpected image host: '+url)
 path = cache/(hashlib.sha256(url.encode()).hexdigest()+'.webp')
 if path.exists():
  content = path.read_bytes()
 else:
  last_error = None
  for attempt in range(3):
   try:
    response = requests.get(url,timeout=(10,30),headers={'User-Agent':'EUGM-Editorial-Asset-Bundler/1.0'})
    response.raise_for_status()
    if len(response.content)>12_000_000:
     raise ValueError('Oversized source image')
    with Image.open(io.BytesIO(response.content)) as image:
     image = ImageOps.exif_transpose(image)
     image.thumbnail((1600,1800),Image.Resampling.LANCZOS)
     image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
     out = io.BytesIO()
     image.save(out,format='WEBP',quality=86,method=6)
     content = out.getvalue()
    path.write_bytes(content)
    break
   except Exception as exc:
    last_error=exc
    if attempt == 2:
     raise RuntimeError(f'Image unavailable: {url}: {last_error}') from exc
    time.sleep(attempt+1)
 with Image.open(io.BytesIO(content)) as check:
  dimensions=list(check.size)
 print('OK',url,len(content),dimensions,flush=True)
 return url,'data:image/webp;base64,'+base64.b64encode(content).decode(),{'url':url,'bytes':len(content),'dimensions':dimensions,'sha256':hashlib.sha256(content).hexdigest()}
assets,manifest = {},[]
failures=[]
with ThreadPoolExecutor(max_workers=8) as pool:
 jobs={pool.submit(fetch_image,u):u for u in urls}
 for job in as_completed(jobs):
  try:
   url,uri,item=job.result()
   assets[url]=uri
   manifest.append(item)
  except Exception as exc:
   failures.append(str(exc));print('FAILED',exc,flush=True)
if failures:
 (ROOT/'image-errors.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2))
 raise RuntimeError(f'{len(failures)} images could not be embedded. No broken-image bundle will be imported.')
asset_map={old:assets[target] for old,target in aliases.items()}

def patch(old: str,new: str):
 global html
 assert html.count(old)==1, 'Non-unique patch target: '+old[:100]
 html=html.replace(old,new,1)

encoded_data=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
patch('<script id="embedded-source" type="application/json">null</script>',
      '<script id="embedded-source" type="application/json">'+encoded_data+'</script>\n<script>window.EUGM_ASSET_MAP='+json.dumps(asset_map,separators=(',',':')).replace('<','\\u003c')+';</script>')
patch('  const photo = id => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=1400&q=82`;',
      '  const photo = id => {const u=`https://images.unsplash.com/${id}?auto=format&fit=crop&w=1400&q=82`;return window.EUGM_ASSET_MAP[u]||u;};')
patch("  function pictureMarkup(src,alt,extra=''){", "  function pictureMarkup(src,alt,extra=''){\n    src=window.EUGM_ASSET_MAP[src]||src;")
patch("      img.loading='lazy';img.decoding='async';", "      const mapped=window.EUGM_ASSET_MAP[img.getAttribute('src')];if(mapped){img.src=mapped;img.removeAttribute('srcset');}\n      img.loading='lazy';img.decoding='async';")
patch('Az eredeti éles oldal és a Base44-változat nem módosult. A fotók külső szerverről töltődnek; internetkapcsolat szükséges.',
      'Ez különálló, Base44-importhoz készített változat; az eredeti éles oldal nem módosult. A tartalom és az ellenőrzött fényképek a HTML-csomagba vannak építve.')
patch('A szöveg beépítve; a fotók továbbra is internetkapcsolatot igényelnek.',
      'A szöveg és a fotók beépítve.')
# Image errors remain explicit and never substitute unrelated people or venues.
html=html.replace('Fotó: betöltéshez internetkapcsolat szükséges','A kép nem tölthető be')
html=html.replace(' — betöltéshez internetkapcsolat szükséges',' — a kép nem tölthető be')
(ROOT/'export.html').write_text(html,encoding='utf-8')
report={'original_html_sha256':EXPECTED,'pages':len(data['pages']),'images':sorted(manifest,key=lambda x:x['url']),'bundle_bytes':len(html.encode()),'all_images_embedded':True,'original_production_unchanged':True,'forms_connected':False}
(ROOT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('BUNDLE READY',report['bundle_bytes'],'bytes;',report['pages'],'pages;',len(manifest),'photographs/assets',flush=True)
