# Genera una hoja de contacto HTML con los objetos (grupos) de un SVG de Illustrator.
import sys, re, pathlib
src, out, maxfrac = sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.22
svg = pathlib.Path(src).read_text(encoding='utf-8')
svg = re.sub(r'<\?xml[^>]*\?>', '', svg)
svg = svg.replace('<svg ', '<svg id="SRC" style="position:absolute;left:-99999px;width:600px" ', 1)
html = f"""<!doctype html><meta charset=utf-8><body style="margin:0;background:#fff;font:10px monospace">
{svg}
<div id=grid style="display:flex;flex-wrap:wrap;gap:2px;width:1800px"></div>
<pre id=out></pre>
<script>
const root=document.getElementById('SRC'), vb=root.viewBox.baseVal, W=vb.width, MAX={maxfrac};
const cands=[]; let n=0;
function walk(e){{
  for(const k of e.children){{
    if(k.tagName!=='g') continue;
    let b; try{{b=k.getBBox()}}catch(_){{continue}}
    if(b.width<=0) continue;
    if(b.width>W*MAX||b.height>vb.height*MAX) {{ walk(k); continue }}
    if(b.width<W*0.012 && b.height<vb.height*0.012) continue;
    k.id=k.id||('o'+(n++)); cands.push([k.id,b.x,b.y,b.width,b.height]);
  }}
}}
walk(root);
const g=document.getElementById('grid');
cands.forEach(([id,x,y,w,h],i)=>{{
  const d=document.createElement('div'); d.style.cssText='border:1px solid #ccc;width:118px;height:132px;position:relative';
  d.innerHTML=`<svg width=118 height=118 viewBox="${{x-2}} ${{y-2}} ${{w+4}} ${{h+4}}"><use href="#${{id}}"/></svg><div style="position:absolute;bottom:1px;left:2px">${{i}}:${{id}} ${{w.toFixed(0)}}x${{h.toFixed(0)}}</div>`;
  g.appendChild(d);
}});
document.getElementById('out').textContent='CANDS='+JSON.stringify(cands);
</script>"""
pathlib.Path(out).write_text(html, encoding='utf-8')
