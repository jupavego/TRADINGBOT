# Objetos vectoriales del mapa isométrico

`v2/eim/web/src/obs_iso_art.ts` se genera con estos scripts a partir de tres ilustraciones isométricas
(SVG de Illustrator) que aportó el usuario: oficina con cubículos (`a_office.svg`), sala de capacitación
(`b_training.svg`) planta de oficinas grande (`c_big.svg`), sala de reuniones con sofás (`d_new.svg`) y oficina abierta
(`e_new.svg`); `c2_parts.json` son objetos extra de `c_big.svg`. Los SVG originales no se versionan (pesan ~7 MB).

1. `python3 sheet.py <svg> hoja.html` → hoja de contacto con los objetos numerados (abrir en Chrome).
2. `python3 extract.py <svg> "39,117,..." 0.22 > x_parts.json` → extrae esos objetos (requiere `google-chrome`).
3. `python3 build_assets.py ../../v2/eim/web/src/obs_iso_art.ts` → simplifica (redondeo, sin grupos vacíos,
   sin piezas diminutas) y escribe los `<symbol>`; la lista `PICK` dice qué objeto es cada nombre.
