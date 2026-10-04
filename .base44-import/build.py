"""Embed the approved design with working photographs; never fabricate archival imagery."""
import base64, hashlib, io, json, lzma, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
ROOT=Path('.base44-import')
EXPECTED='fd8c1bba4bc9ebe3bf69d63f14fba1050e731c1d1bd1e31bd65bb32abb6d8696'
raw=lzma.decompress(base64.b64decode(''.join(p.read_text().strip() for p in sorted(ROOT.glob('source-*.b64')))))
assert hashlib.sha256(raw).hexdigest()==EXPECTED
html=raw.decode();data=json.loads(Path('eugm-adatok.json').read_text())
assert len(data['pages'])==15
photos={k:f'https://images.unsplash.com/{v}?auto=format&fit=crop&w=1400&q=82' for k,v in {
 'team':'photo-1522071820081-009f0129c71c','office':'photo-1497366754035-f200968a6e72',
 'architecture':'photo-1486406146926-c627a92ad1ab','desk':'photo-1499750310107-5fef28a66643'}.items()}
labels={'team':'Közös irodai munkavégzés — fotóillusztráció','office':'Modern irodai környezet — fotóillusztráció','architecture':'Építészet — fotóillusztráció','desk':'Szerkesztőségi munka — fotóillusztráció'}
aliases={u:u for u in photos.values()};info={};missing={};original_page_images=[]
# Only the user-provided public homepage is inspected; no accounts or credentials.
try:
 r=requests.get('https://www.ujeuropaigazdasagimagazin.com/',timeout=(5,12))
 print('Original homepage HTTP',r.status_code,flush=True)
 if r.ok:
  for im in BeautifulSoup(r.text,'html.parser').find_all('img'):
   src=im.get('src','');alt=im.get('alt','')
   if src.startswith(('https://','/')):
    original_page_images.append({'src':urljoin(r.url,src),'alt':alt})
except Exception as exc:
 print('Original homepage unavailable:',type(exc).__name__,flush=True)
for region in data['regions'].values():
 if not isinstance(region,str):continue
 for im in BeautifulSoup(region,'html.parser').find_all('img'):
  original=im.get('src','');alt=im.get('alt','')
  if not original or original.startswith('data:'):continue
  url=urljoin('https://grafcom.hu',original)
  # The preceding build verified that all 39 legacy grafcom asset paths return 404.
  if '/cikkek/' in url and 'ovari-laszlo' not in url:
   key='office'
   if any(x in url for x in ['digitalis-gazdasag','vallalkozoihid','partnerinfo','alphasonic']):key='team'
   elif any(x in url for x in ['hero-fooldal','europai-unio','europa-elmenykozpont','infoparlament','ep-irodak']):key='architecture'
   elif any(x in url for x in ['magazin','gmelet','fantasy-land','sikerre','hirek']):key='desk'
   for u in [original,url]:aliases[u]=photos[key];info[u]={'illustration':True,'label':labels[key]}
  elif 'eugm-logo' in url:
   aliases[original]=aliases[url]='https://eugm.hu/landing/images/eugm_logo.png'
  else:
   match=next((x for x in original_page_images if 'ovari-laszlo' in url and ('óvári' in x['alt'].lower() or 'ovari' in x['alt'].lower())),None)
   if match:
    aliases[original]=aliases[url]=match['src']
   else:
    text=(alt or 'Eredeti dokumentumkép')+' — az eredeti képfájl jelenleg nem elérhető.'
    missing[original]=missing[url]=text

def get_image(url):
 response=requests.get(url,timeout=(8,20));response.raise_for_status()
 assert len(response.content)<12_000_000
 with Image.open(io.BytesIO(response.content)) as image:
  image=ImageOps.exif_transpose(image);image.thumbnail((1400,1600),Image.Resampling.LANCZOS)
  image=image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
  out=io.BytesIO();image.save(out,format='WEBP',quality=84,method=6)
  content=out.getvalue();dimensions=list(image.size)
 return url,'data:image/webp;base64,'+base64.b64encode(content).decode(),{'url':url,'dimensions':dimensions,'bytes':len(content)}
assets={};manifest=[]
with ThreadPoolExecutor(max_workers=6) as pool:
 jobs={pool.submit(get_image,u):u for u in set(aliases.values())}
 for job in as_completed(jobs):
  url=jobs[job]
  try:
   u,uri,item=job.result();assets[u]=uri;manifest.append(item);print('PHOTO OK',u,flush=True)
  except Exception as exc:
   if 'images.unsplash.com' in url:raise
   print('Document image unavailable',url,type(exc).__name__,flush=True)
   for old,target in list(aliases.items()):
    if target==url:missing[old]='Eredeti arculati vagy dokumentumkép — a forráskép nem elérhető.';del aliases[old]
asset_urls=sorted(assets);indices={u:i for i,u in enumerate(asset_urls)}
map_indices={old:indices[target] for old,target in aliases.items()}

def safe(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
def patch(old,new):
 global html
 assert html.count(old)==1,'Patch mismatch: '+old[:90]
 html=html.replace(old,new,1)
asset_script='window.EUGM_ASSET_MAP=(()=>{const bytes='+safe([assets[u] for u in asset_urls])+', index='+safe(map_indices)+';return Object.fromEntries(Object.entries(index).map(([k,v])=>[k,bytes[v]]));})();window.EUGM_ASSET_INFO='+safe(info)+';window.EUGM_MISSING_ASSETS='+safe(missing)+';'
patch('<script id="embedded-source" type="application/json">null</script>', '<script id="embedded-source" type="application/json">'+safe(data)+'</script>\n<script>'+asset_script+'</script>')
patch('  const photo = id => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=1400&q=82`;', '  const photo = id => {const u=`https://images.unsplash.com/${id}?auto=format&fit=crop&w=1400&q=82`;return window.EUGM_ASSET_MAP[u]||u;};')
patch("  function pictureMarkup(src,alt,extra=''){", "  function pictureMarkup(src,alt,extra=''){\n    if(window.EUGM_MISSING_ASSETS[src])return `<div class=\"document-image-note\">${esc(window.EUGM_MISSING_ASSETS[src])}</div>`;const meta=window.EUGM_ASSET_INFO[src];if(meta)alt=meta.label;src=window.EUGM_ASSET_MAP[src]||src;")
patch("      const original=img.getAttribute('src')||'';", "      const original=img.getAttribute('src')||'';\n      if(window.EUGM_MISSING_ASSETS[original]){const label=document.createElement('span');label.className='document-image-note';label.textContent=window.EUGM_MISSING_ASSETS[original];img.replaceWith(label);return;}")
patch("      img.loading='lazy';img.decoding='async';", "      const mapped=window.EUGM_ASSET_MAP[original]||window.EUGM_ASSET_MAP[img.getAttribute('src')];if(mapped){img.src=mapped;img.removeAttribute('srcset');}const meta=window.EUGM_ASSET_INFO[original];if(meta){img.alt=meta.label;img.title=meta.label;img.closest('.im')?.classList.add('illustrative-photo');}\n      img.loading='lazy';img.decoding='async';")
patch('</style>', '.document-image-note{display:flex;align-items:center;justify-content:center;padding:20px;min-height:90px;background:#f5f6f0;color:#66745d;font:11px/1.6 Arial,sans-serif;text-align:center}.im>.document-image-note{position:absolute;inset:0}.source-content .illustrative-photo:after{content:"Fotóillusztráció";position:absolute;right:6px;top:6px;background:#fffdf5;padding:3px 6px;color:#52604c;font:8px Arial,sans-serif}.original-cover{max-width:100%}\n</style>')
patch('Az eredeti éles oldal és a Base44-változat nem módosult. A fotók külső szerverről töltődnek; internetkapcsolat szükséges.', 'Ez különálló, Base44-importhoz készített változat; az eredeti éles oldal nem módosult. A fényképek be vannak építve. A régi makett 404-es képeit fotóillusztrációk váltják; a hiányzó eredeti portrék, borítók és logók helyén jelzett szöveges tájékoztatás látható.')
patch('A szöveg beépítve; a fotók továbbra is internetkapcsolatot igényelnek.', 'A szöveg és a fotók beépítve.')
html=html.replace('Fotó: betöltéshez internetkapcsolat szükséges','A kép nem tölthető be').replace(' — betöltéshez internetkapcsolat szükséges',' — a kép nem tölthető be')
(ROOT/'export.html').write_text(html,encoding='utf-8')
report={'original_html_sha256':EXPECTED,'pages':15,'images':manifest,'bundle_bytes':len(html.encode()),'all_displayed_images_embedded':True,'unavailable_original_document_assets':missing,'original_homepage_images_found':original_page_images,'original_production_unchanged':True,'forms_connected':False}
(ROOT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('BUNDLE READY',report['bundle_bytes'],'bytes;',len(manifest),'embedded images;',len(missing),'missing original document image references disclosed',flush=True)
