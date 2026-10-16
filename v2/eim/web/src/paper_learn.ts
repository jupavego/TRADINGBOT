/** Pestaña «Aprendizaje»: qué estrategia funciona y cuál no (evaluación sombra + retroalimentación). */
import { CAUSE, esc, getPaper, nf, pct0, px, REASON, rr, side, STATUS, utc } from './paper_fmt'
import type { PaperSummary, ShadowIdea, StrategyRow } from './paper_types'

const ROW_H = 24
const MAX_BARS = 40               // con 3 marcos hay ~90 estrategias: el gráfico muestra extremos
const LABEL_W = 190
const VAL_W = 120

const fmtP = (p: number | null): string => (p === null ? '—' : p < 0.001 ? '<0,001' : nf(p, 3))

/** Barras horizontales: expectativa contraída por estrategia con ±1 error estándar y el control. */
function bars(rows: StrategyRow[], width: number): string {
  const xs = rows.flatMap((r) => [r.judgement.m - (r.judgement.se ?? 0), r.judgement.m + (r.judgement.se ?? 0)])
  const ctrl = rows.find((r) => r.family === 'control')
  const lo = Math.min(-0.5, ...xs), hi = Math.max(0.5, ...xs)
  const w = Math.max(200, width - LABEL_W - VAL_W)
  const x = (v: number): number => LABEL_W + ((v - lo) / (hi - lo)) * w
  const h = rows.length * ROW_H + 26
  let g = ''
  rows.forEach((r, i) => {
    const y = 6 + i * ROW_H, m = r.judgement.m, se = r.judgement.se ?? 0
    const x0 = x(0), x1 = x(m)
    const left = Math.min(x0, x1), bw = Math.max(2, Math.abs(x1 - x0))
    g += `<g class="pp-bar" data-i="${i}"><rect class="pp-hit" x="0" y="${y - 3}" width="${LABEL_W + w + VAL_W}" height="${ROW_H}"/>` +
      `<text x="${LABEL_W - 8}" y="${y + 12}" text-anchor="end" class="pp-lbl">${esc(r.name)}</text>` +
      `<rect x="${left}" y="${y + 3}" width="${bw}" height="12" rx="3" data-sign="${m >= 0 ? 1 : -1}" data-fam="${r.family}"/>` +
      (se ? `<line x1="${x(m - se)}" x2="${x(m + se)}" y1="${y + 9}" y2="${y + 9}" class="pp-whisk"/>` : '') +
      `<text x="${LABEL_W + w + 8}" y="${y + 12}" class="pp-val">${rr(m)} <tspan class="pp-n">n=${r.n}</tspan></text></g>`
  })
  const ticks = [lo, lo / 2, 0, hi / 2, hi].map((v) => `<text x="${x(v)}" y="${h - 4}" text-anchor="middle" class="pp-tick">${nf(v, 1)}</text>`).join('')
  const zero = `<line x1="${x(0)}" x2="${x(0)}" y1="2" y2="${h - 18}" class="pp-zero"/>`
  const cl = ctrl && ctrl.n ? `<line x1="${x(ctrl.judgement.m)}" x2="${x(ctrl.judgement.m)}" y1="2" y2="${h - 18}" class="pp-ctrl"/>` : ''
  return `<svg class="pp-bars" viewBox="0 0 ${LABEL_W + w + VAL_W} ${h}" width="100%" role="img" aria-label="Expectativa por estrategia">${zero}${cl}${g}${ticks}</svg>`
}

function stateChip(r: StrategyRow, v: PaperSummary, profile: string): string {
  const j = v.profiles.find((p) => p.id === profile)?.weights[r.id]
  if (!j) return '—'
  return `<span class="pp-state" data-s="${j.state}">${j.state_label}</span> <small class="num">×${nf(j.weight)}</small>`
}

export class PaperLearn {
  private open: string | null = null
  private fam = ''
  private shown: StrategyRow[] = []
  private tf = ''
  private view: PaperSummary | null = null
  private profile = 'moderado'

  constructor(private el: HTMLElement) {
    el.addEventListener('click', (e) => {
      const tr = (e.target as HTMLElement).closest<HTMLElement>('tr[data-sid]')
      if (!tr) return
      this.open = this.open === tr.dataset.sid ? null : tr.dataset.sid!
      this.paint()
    })
    el.addEventListener('change', (e) => {
      const s = e.target as HTMLSelectElement
      if (s.dataset.lf === 'fam') this.fam = s.value
      else if (s.dataset.lf === 'tf') this.tf = s.value
      else return
      this.paint()
    })
    el.addEventListener('mousemove', (e) => this.tip(e))
    el.addEventListener('mouseleave', () => { const t = el.querySelector<HTMLElement>('.pp-tip'); if (t) t.hidden = true })
  }

  show(v: PaperSummary, profile: string): void { this.view = v; this.profile = profile; this.paint() }

  private rows(): StrategyRow[] {
    const v = this.view!
    return v.strategies.filter((r) => (!this.fam || r.family === this.fam) && (!this.tf || r.timeframe === this.tf))
      .sort((a, b) => (b.n ? b.judgement.m : -9) - (a.n ? a.judgement.m : -9))
  }

  private tip(e: MouseEvent): void {
    const g = (e.target as Element).closest<SVGGElement>('.pp-bar')
    const t = this.el.querySelector<HTMLElement>('.pp-tip')
    if (!t) return
    if (!g) { t.hidden = true; return }
    const r = this.shown[Number(g.dataset.i)]
    if (!r) return
    t.hidden = false
    t.innerHTML = `<b>${esc(r.name)}</b><br>Expectativa contraída ${rr(r.judgement.m)} ± ${rr(r.judgement.se, 2)}<br>` +
      `R medio bruto ${rr(r.mean_r)} · acierto ${pct0(r.win_rate)} · n=${r.n}<br>PF ${r.pf === null ? '—' : nf(r.pf)} · p (Holm) ${fmtP(r.p_holm)}`
    const box = this.el.getBoundingClientRect()
    t.style.left = `${Math.min(e.clientX - box.left + 14, box.width - 260)}px`
    t.style.top = `${e.clientY - box.top + 14}px`
  }

  private paint(): void {
    const v = this.view
    if (!v) return
    const ins = v.insights.map((i) => `<li data-tone="${i.tone}">${esc(i.text)}</li>`).join('')
    const fams = v.family_stats.map((f) => `<span class="pp-fam"><b>${esc(v.families[f.family] ?? f.family)}</b> ` +
      `<span class="num">${rr(f.mean_r)}</span> <small class="muted">n=${f.n}</small></span>`).join('')
    const all = this.rows()
    const tfSel = `<select data-lf="tf"><option value="">15m · 1h · 4h</option>` +
      (v.timeframes ?? []).map((t) => `<option${t === this.tf ? ' selected' : ''}>${t}</option>`).join('') + '</select>'
    const tfStats = (v.tf_stats ?? []).map((t) => `<span class="pp-fam"><b>${t.timeframe}</b> <span class="num">${rr(t.mean_r)}</span> ` +
      `<small class="muted">acierto ${pct0(t.win_rate)} · n=${t.n}</small></span>`).join('')
    const famSel = `<select data-lf="fam"><option value="">Todas las familias</option>` +
      Object.entries(v.families).map(([k, n]) => `<option value="${k}"${k === this.fam ? ' selected' : ''}>${esc(n)}</option>`).join('') + '</select>'
    const width = Math.max(560, this.el.clientWidth - 20)
    let withN = all.filter((r) => r.n)
    const cut = withN.length > MAX_BARS
    if (cut) withN = [...withN.slice(0, MAX_BARS / 2), ...withN.slice(-MAX_BARS / 2)]
    this.shown = withN
    const chart = (withN.length ? bars(withN, Math.min(width, 980)) : '<p class="muted">Aún no hay operaciones cerradas.</p>') +
      (cut ? `<p class="muted pp-note">Se muestran las ${MAX_BARS / 2} mejores y las ${MAX_BARS / 2} peores; filtra por marco o familia para ver el resto.</p>` : '')
    const prof = v.profiles.find((p) => p.id === this.profile)?.name ?? this.profile
    const rows = all.map((r) => {
      const side_ = Object.entries(r.by_side).map(([k, s]) => `${k} ${rr(s.mean_r, 2)} (${s.n})`).join(' · ')
      const tr = `<tr data-sid="${r.id}" aria-expanded="${this.open === r.id}" title="${esc(r.description)}">` +
        `<td><b>${esc(r.name)}</b><br><small class="muted">${esc(v.families[r.family] ?? r.family)}</small></td>` +
        `<td>${stateChip(r, v, this.profile)}</td><td class="num">${r.n}${r.open ? ` <small class="muted">+${r.open} ab.</small>` : ''}</td>` +
        `<td class="num">${pct0(r.win_rate)}</td><td class="num">${rr(r.mean_r)}</td>` +
        `<td class="num"><b>${rr(r.judgement.m)}</b><br><small class="muted">± ${r.judgement.se === null ? '—' : nf(r.judgement.se)}</small></td>` +
        `<td class="num">${r.pf === null ? '—' : nf(r.pf)}</td><td class="num">${rr(r.sum_r, 1)}</td>` +
        `<td class="num">${nf(r.max_dd_r, 1)}</td><td class="num">${rr(r.vs_control)}</td><td class="num">${fmtP(r.p_holm)}</td>` +
        `<td class="num">${pct0(r.fill_rate)}</td><td class="num">${r.mfe_r === null ? '—' : `${nf(r.mfe_r, 1)} / ${nf(r.mae_r ?? 0, 1)}`}</td>` +
        `<td class="num">${r.hold_h === null ? '—' : nf(r.hold_h, 1)}</td><td><small>${side_ || '—'}</small></td></tr>`
      return tr + (this.open === r.id ? `<tr class="pp-detail"><td colspan="15" data-detail="${r.id}"><p class="muted">Cargando…</p></td></tr>` : '')
    }).join('')
    this.el.innerHTML = `<ul class="pp-insights">${ins}</ul><div class="pp-fams">${tfStats}</div><div class="pp-fams">${fams}</div>` +
      `<div class="pp-filters"><h4 class="sh">Expectativa por estrategia (R por operación)</h4>${tfSel}${famSel}</div>` +
      `<div class="pp-chartbox">${chart}<div class="pp-tip" hidden></div></div>` +
      '<p class="muted pp-note">Barra = expectativa contraída hacia 0 (pocas operaciones pesan poco) · bigote = ±1 error estándar · línea discontinua = control aleatorio. ' +
      'El color solo marca el signo; el valor está a la derecha.</p>' +
      `<div class="pp-scroll"><table class="pp-t pp-learn"><thead><tr><th>Estrategia</th><th>Estado en ${esc(prof)}</th><th>n</th><th>Acierto</th>` +
      '<th>R medio</th><th>R contraído</th><th>PF</th><th>R total</th><th>DD (R)</th><th>vs control</th><th>p (Holm)</th>' +
      '<th>Llenado</th><th>MFE / MAE (R)</th><th>Horas</th><th>Por lado</th></tr></thead>' +
      `<tbody>${rows}</tbody></table></div>` +
      '<p class="muted pp-note">Evaluación sombra: cada estrategia con una operación viva a la vez, igual para todos los perfiles, con costos y funding. ' +
      'La retroalimentación solo usa operaciones ya cerradas en cada instante (sin mirar el futuro); una estrategia en pausa se sigue midiendo y vuelve sola si se recupera. Clic en una fila para ver sus operaciones.</p>'
    if (this.open) void this.detail(this.open)
  }

  private async detail(id: string): Promise<void> {
    const cell = this.el.querySelector<HTMLElement>(`[data-detail="${id}"]`)
    if (!cell || !this.view) return
    try {
      const r = await getPaper<{ total: number; ideas: ShadowIdea[] }>(`/ideas?symbol=${this.view.symbol}&strategy=${id}&limit=40`)
      const s = this.view.strategies.find((x) => x.id === id)!
      const reg = Object.entries(s.by_regime).map(([k, x]) => `${esc(k)}: ${rr(x.mean_r)} (${x.n})`).join(' · ')
      const reasons = Object.entries(s.by_reason).map(([k, n]) => `${REASON[k] ?? k} ${n}`).join(' · ')
      const causes = Object.entries(s.by_cause ?? {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${CAUSE[k] ?? k} ${n}`).join(' · ')
      const ctx = Object.entries(s.by_context ?? {}).sort((a, b) => a[1].mean_r - b[1].mean_r).map(([k, x]) =>
        `<span class="pp-ctx" data-s="${x.state}">${esc(k.replace('|', ' · '))}: ${rr(x.mean_r)} (${x.n})${x.state === 'pausa' ? ' · en pausa' : ''}</span>`).join(' ')
      cell.innerHTML = `<p>${esc(s.description)} <span class="pp-tfb">${esc(s.timeframe)}</span></p><p class="muted">Por régimen: ${reg || '—'} · Salidas: ${reasons || '—'} · ` +
        `últimas 10: ${rr(s.last10_r)} · decididas en vivo: ${s.origin_live}</p>` +
        `<p class="muted">Por qué perdió: ${causes || '—'}</p>` +
        (ctx ? `<p class="pp-ctxs"><b>Contextos (régimen · lado):</b> ${ctx}</p>` : '') +
        `<table class="pp-t pp-mini"><thead><tr><th>Señal (UTC)</th><th>Lado</th><th>Entrada / SL / TP</th><th>Estado</th><th>R</th><th>Por qué</th></tr></thead><tbody>` +
        r.ideas.map((o) => `<tr><td class="num">${utc(o.t)}</td><td>${side(o.side)} · ${o.kind === 'limit' ? 'límite' : 'mercado'}</td>` +
          `<td class="num">${px(o.fill ?? o.entry)} / ${px(o.sl)} / ${px(o.tp)}</td>` +
          `<td>${STATUS[o.status] ?? o.status}${o.reason ? ` · ${REASON[o.reason] ?? o.reason}` : ''}</td>` +
          `<td class="num">${rr(o.r)}</td><td><small>${esc(o.why.join(' · '))}</small></td></tr>`).join('') +
        `</tbody></table><p class="muted">${r.total} ideas evaluadas en total.</p>`
    } catch (e) {
      cell.innerHTML = `<p class="alert bad">${esc((e as Error).message)}</p>`
    }
  }
}
