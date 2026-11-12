# Extrae objetos elegidos (por índice de la hoja de contacto) como fragmentos SVG con su bbox.
import sys, re, pathlib, json, subprocess, html as H
src, picks, maxfrac = sys.argv[1], sys.argv[2], float(sys.argv[3])
svg = re.sub(r'<\?xml[^>]*\?>', '', pathlib.Path(src).read_text(encoding='utf-8'))
svg = svg.replace('<svg ', '<svg id="SRC" style="position:absolute;left:-99999px;width:600px" ', 1)
page = f"""<!doctype html><meta charset=utf-8><body>{svg}<pre id=out></pre><script>
const root=document.getElementById('SRC'), vb=root.viewBox.baseVal, W=vb.width, MAX={maxfrac};
const cands=[]; let n=0;
function walk(e){{ for(const k of e.children){{ if(k.tagName!=='g') continue; let b; try{{b=k.getBBox()}}catch(_){{continue}}
  if(b.width<=0) continue; if(b.width>W*MAX||b.height>vb.height*MAX){{walk(k);continue}}
  if(b.width<W*0.012&&b.height<vb.height*0.012) continue; cands.push([k,b]); }} }}
walk(root);
const res={{}};
for(const i of [{picks}]){{ const [k,b]=cands[i]; let s=k.outerHTML;
  const refs=new Set([...s.matchAll(/(?:url\\(#|href="#)([^)"]+)/g)].map(m=>m[1])); let extra='';
  for(const r of refs){{ const el=document.getElementById(r); if(el && !k.contains(el)) extra+=el.outerHTML }}
  res[i]={{x:b.x,y:b.y,w:b.width,h:b.height,svg:(extra?'<defs>'+extra+'</defs>':'')+s}} }}
document.getElementById('out').textContent=JSON.stringify(res);
</script>"""
p = pathlib.Path('/tmp/extract_page.html'); p.write_text(page, encoding='utf-8')
dom = subprocess.run(['google-chrome','--headless=new','--no-sandbox','--disable-gpu','--virtual-time-budget=4000','--dump-dom','file://'+str(p)],capture_output=True,text=True).stdout
m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
print(H.unescape(m.group(1)))
