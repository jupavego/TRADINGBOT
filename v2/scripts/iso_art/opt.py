import re, json, sys
def num(m, p): 
    v = float(m.group(0)); s = f"{v:.{p}f}".rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'
def optimize(svg, prefix, p=1):
    s = svg
    s = re.sub(r'\s*xmlns(:\w+)?="[^"]*"', '', s)
    s = s.replace('xlink:href', 'href')
    s = re.sub(r'style="enable-background:[^"]*"', '', s)
    s = re.sub(r'style="overflow:visible;?"', '', s)
    def st(m):
        out = []
        for decl in m.group(1).split(';'):
            if ':' not in decl: continue
            k, v = [x.strip() for x in decl.split(':', 1)]
            if k == 'enable-background': continue
            out.append(f'{k}="{v}"')
        return ' '.join(out)
    s = re.sub(r'style="([^"]*)"', st, s)
    # números en atributos geométricos
    def geo(m):
        val = re.sub(r'-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?', lambda n: ' ' + num(n, p) + ' ', m.group(2))
        val = re.sub(r'\s+', ' ', val).strip()
        val = re.sub(r' ?([,MLHVCSQTAZmlhvcsqtaz()]) ?', r'\1', val)
        val = re.sub(r' -', '-', val) if m.group(1) in ('d', 'points') else val
        return f'{m.group(1)}="{val}"'
    s = re.sub(r'\b(points|d|x|y|width|height|cx|cy|r|rx|ry|x1|y1|x2|y2|transform|stroke-width|stroke-miterlimit)="([^"]*)"', geo, s)
    s = re.sub(r' stroke-miterlimit="[^"]*"', '', s)
    # ids: renombrar a cortos con prefijo
    ids = re.findall(r'\bid="([^"]+)"', s); used = set(re.findall(r'(?:url\(#|href="#)([^)"]+)', s))
    mp = {}
    for i, old in enumerate(dict.fromkeys(ids)):
        if old in used: mp[old] = f'{prefix}{len(mp)}'
    s = re.sub(r'\s*\bid="([^"]+)"', lambda m: f' id="{mp[m.group(1)]}"' if m.group(1) in mp else '', s)
    s = re.sub(r'(url\(#|href="#)([^)"]+)', lambda m: m.group(1) + mp.get(m.group(2), m.group(2)), s)
    s = re.sub(r'>\s+<', '><', s); s = re.sub(r'\s{2,}', ' ', s); s = re.sub(r'\s+/>', '/>', s); s = re.sub(r' >', '>', s)
    return s
if __name__ == '__main__':
    d = json.load(open(sys.argv[1]))
    for k, v in d.items():
        o = optimize(v['svg'], 'x'); print(k, len(v['svg']), len(o))

def flatten(s):
    s = re.sub(r'></(polygon|path|rect|circle|ellipse|line|polyline|use)>', '/>', s)
    out, stack = [], []
    for tok in re.split(r'(<g\b[^>]*>|</g>)', s):
        if tok.startswith('<g'):
            plain = tok == '<g>'
            stack.append(plain)
            if not plain: out.append(tok)
        elif tok == '</g>':
            if not stack.pop(): out.append(tok)
        else: out.append(tok)
    return ''.join(out)

def full(svg, prefix, p=1):
    return flatten(optimize(svg, prefix, p))

def drop_tiny(s, minsz=1.2):
    def poly(m):
        nums = [float(x) for x in re.findall(r'-?\d*\.?\d+', m.group(1))]
        xs, ys = nums[0::2], nums[1::2]
        return '' if max(xs) - min(xs) < minsz and max(ys) - min(ys) < minsz else m.group(0)
    s = re.sub(r'<polygon [^>]*points="([^"]*)"[^>]*/>', poly, s)
    def path(m):
        d = m.group(1)
        if re.search(r'[A-Z]', d[1:].replace('Z', '')) or d.count('M') + d.count('m') > 1: return m.group(0)
        segs = re.findall(r'[a-z][^a-zA-Z]*', d[d.index(d.lstrip('M0123456789.,-')[0]) if False else 0:])
        # tamaño aproximado: suma de desplazamientos relativos absolutos
        nums = [abs(float(x)) for x in re.findall(r'-?\d*\.?\d+', d.split('M',1)[1].split(re.split(r'[a-z]', d.split('M',1)[1])[0],1)[1] if re.search('[a-z]', d) else '')]
        return '' if nums and sum(nums) < minsz * 2 else m.group(0)
    s = re.sub(r'<path [^>]*d="([^"]*)"[^>]*/>', path, s)
    s = re.sub(r'<g\b[^>]*></g>', '', s)
    return s
