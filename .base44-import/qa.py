"""Offline browser QA: original layout, all routes, photographs and core controls."""
import json, threading
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path('.base44-import')
data=json.loads(Path('eugm-adatok.json').read_text())
server=ThreadingHTTPServer(('127.0.0.1',8765),partial(SimpleHTTPRequestHandler,directory=str(Path.cwd())))
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:8765/.base44-import/export.html'
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch()
 context=browser.new_context(viewport={'width':1440,'height':1050},device_scale_factor=1)
 # Every photograph must work without contacting its original host.
 context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(('http://127.0.0.1:8765/','data:','blob:')) else route.abort())
 page=context.new_page()
 errors=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(url+'#/index',wait_until='domcontentloaded')
 page.wait_for_function('window.EUGM_EDITORIAL?.getStatus().sourceLoaded === true')
 assert page.evaluate('window.EUGM_EDITORIAL.getStatus().pageCount')==15
 for width in [1440,390]:
  page.set_viewport_size({'width':width,'height':1050 if width>500 else 844})
  for route in [x['id'] for x in data['pages']]:
   page.evaluate('(route)=>location.hash="/"+route',route)
   page.wait_for_function('(route)=>window.EUGM_EDITORIAL.getStatus().route===route',arg=route)
   page.evaluate('document.querySelectorAll("img").forEach(i=>i.loading="eager")')
   page.evaluate('async()=>{await Promise.all(Array.from(document.images).map(i=>i.decode().catch(()=>null)));}')
   detail=page.evaluate('''()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,text:document.querySelector('#content').innerText.length,images:Array.from(document.images).filter(i=>i.getAttribute('src')).map(i=>({alt:i.alt,ok:i.complete&&i.naturalWidth>0,embedded:i.src.startsWith('data:')}))})''')
   detail.update(route=route)
   results.append(detail)
   assert detail['text']>30, 'Empty page: '+route
   assert detail['scrollWidth']<=width+1, 'Horizontal overflow: '+str(detail)
   assert all(i['ok'] and i['embedded'] for i in detail['images']), 'Image not embedded or broken: '+str(detail)
   print('PASS',width,route,len(detail['images']),'images',flush=True)
  page.evaluate('location.hash="/index"')
  page.wait_for_function('window.EUGM_EDITORIAL.getStatus().route==="index"')
  page.evaluate('document.querySelectorAll("img").forEach(i=>i.loading="eager")')
  page.evaluate('async()=>{await Promise.all(Array.from(document.images).map(i=>i.decode().catch(()=>null)));window.scrollTo(0,0)}')
  page.screenshot(path=str(root/('desktop.png' if width>500 else 'mobile.png')),full_page=True)
  if width==390:
   page.locator('[data-action="menu"]').click()
   assert page.locator('dialog[open]').count()==1
   page.keyboard.press('Escape')
 # Search actually produces results and saving toggles state.
 page.set_viewport_size({'width':1440,'height':1050})
 page.locator('[data-action="search"]').first.click()
 page.locator('#search-input').fill('gazdaság')
 page.wait_for_function('document.querySelector("#search-results").innerText.length>10')
 page.keyboard.press('Escape')
 saved=page.locator('[data-save]').first
 saved.click()
 assert saved.get_attribute('aria-pressed')=='true'
 saved.click()
 assert not errors, str(errors)
 # Base44 receives the complete rendered homepage, not a blank JS shell.
 page.evaluate('window.scrollTo(0,0)')
 page.evaluate('document.querySelectorAll("dialog").forEach(d=>d.close())')
 root.joinpath('export.html').write_text(page.content(),encoding='utf-8')
 root.joinpath('qa.json').write_text(json.dumps({'passed':True,'routes_tested':len(results),'javascript_errors':errors,'external_images_required':False,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
 print('QA COMPLETE: 30 route/viewport checks; search, bookmark, mobile menu passed',flush=True)
 browser.close()
server.shutdown()
