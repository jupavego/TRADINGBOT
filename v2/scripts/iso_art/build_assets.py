# Genera v2/eim/web/src/obs_iso_art.ts con los objetos vectoriales elegidos de los SVG del usuario.
import sys, json; sys.path.insert(0, '.')
import opt  # noqa: E402
src = {'d': json.load(open('d_parts.json')), 'e': json.load(open('e_parts.json')), 'k': json.load(open('c2_parts.json')), 'a': json.load(open('a_parts.json')), 'b': json.load(open('b_parts.json')), 'c': json.load(open('c_parts.json')), 'p': json.load(open('a_people.json'))}
PICK = {  # nombre: (archivo, índice)
  'mujer': ('p', '39'), 'hombre': ('p', '117'), 'monitor': ('p', '38'),
  'planta': ('a', '187'), 'arbol': ('c', '37'), 'cactus': ('c', '23'), 'planta_alta': ('b', '37'), 'base_planta': ('b', '36'),
  'mueble': ('c', '21'), 'cajonera': ('c', '19'), 'archivador': ('a', '67'), 'estante': ('c', '29'), 'repisa': ('a', '137'),
  'dispensador': ('a', '66'), 'sofa': ('c', '36'), 'libros': ('c', '67'), 'mesa': ('c', '28'),
  'corcho': ('c', '16'), 'pizarra': ('c', '26'), 'tablero_graf': ('c', '84'), 'aire': ('c', '4'), 'reloj': ('b', '38'),
  'pizarra_negra': ('a', '41'), 'corcho_reloj': ('a', '139'), 'grafico': ('b', '9'),
  # área común (salitas y zonas de estar)
  'sofa_morado': ('d', '14'), 'planta_mueble': ('d', '15'), 'repisa_reloj': ('d', '4'), 'dona': ('d', '8'), 'barras': ('d', '9'),
  'sofa_blanco': ('e', '58'), 'arbol_grande': ('e', '132'), 'planta_maceta': ('e', '104'), 'sillon': ('e', '7'),
  'cafe': ('e', '69'), 'pizza': ('e', '105'), 'cocineta': ('k', '80'), 'sofa_corto': ('k', '55'),
}
defs, meta, total = [], {}, 0
for i, (name, (f, k)) in enumerate(PICK.items()):
    v = src[f][k]
    body = opt.drop_tiny(opt.full(v['svg'], f'q{i}_'), 0.6)
    x, y, w, h = (round(v[q], 1) for q in ('x', 'y', 'w', 'h'))
    defs.append(f'<symbol id="iso-a-{name}" viewBox="{x} {y} {w} {h}" overflow="visible">{body}</symbol>')
    meta[name] = [w, h]; total += len(body)
ts = '''/** Objetos vectoriales (personas, monitores, plantas, muebles, tableros) tomados de las ilustraciones
 * isométricas que aportó el usuario (archivos de Illustrator), simplificados para el mapa: se definen una
 * vez como <symbol> y se colocan con <use>. Archivo generado; para regenerarlo ver `v2/scripts/iso_art/`. */

/** Ancho y alto de cada objeto en sus unidades originales. */
export const ART: Record<string, [number, number]> = ''' + json.dumps(meta, ensure_ascii=False) + '''

export type ArtName = keyof typeof ART

/** Definiciones (van dentro de <defs> del SVG del mapa). */
export const ART_DEFS = ''' + json.dumps(''.join(defs), ensure_ascii=False) + '''
'''
open(sys.argv[1], 'w', encoding='utf-8').write(ts)
print('bytes', total, len(ts))
