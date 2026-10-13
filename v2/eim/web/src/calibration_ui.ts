import { fetchCalibration, runBackfill, type CalibrationReport } from './api'
import { esc } from './panels'

const pct = (x: number | null | undefined, d = 1): string => (x == null ? '—' : `${(x * 100).toFixed(d)} %`)

/** Pestaña "Calibración": ¿son fiables las probabilidades y bandas de los escenarios? */
export class CalibrationPanel {
  private rep: CalibrationReport | null = null
  private busy = false
  private err = ''
  private h = 25

  constructor(private readonly el: HTMLElement, private readonly ctx: () => { symbol: string; tf: string }) {
    el.onclick = (e) => {
      if ((e.target as HTMLElement).closest('#cal-backfill')) void this.backfill()
    }
  }

  async reload(): Promise<void> {
    const { symbol, tf } = this.ctx()
    try { this.rep = await fetchCalibration(symbol, tf, this.h); this.err = '' }
    catch (e) { this.rep = null; this.err = (e as Error).message }
    this.render()
  }

  private async backfill(): Promise<void> {
    const { symbol, tf } = this.ctx()
    this.busy = true; this.render()
    try { this.rep = await runBackfill(symbol, tf, this.h); this.err = '' }
    catch (e) { this.err = `Backfill fallido: ${(e as Error).message}` }
    this.busy = false; this.render()
  }

  private curve(c: NonNullable<CalibrationReport['curve']>): string {
    const s = 120, pt = (p: number): number => 6 + p * (s - 12)
    const dots = c.map((d) => `<circle cx="${pt(d.p_pred)}" cy="${s - pt(d.p_obs)}" r="${2 + Math.min(4, Math.sqrt(d.n) / 8)}" fill="var(--accent)"><title>predicha ${pct(d.p_pred, 0)} · observada ${pct(d.p_obs, 0)} · n=${d.n}</title></circle>`).join('')
    return `<svg width="${s}" height="${s}" role="img" aria-label="Curva de calibración"><rect x="6" y="6" width="${s - 12}" height="${s - 12}" fill="none" stroke="var(--line)"/><line x1="6" y1="${s - 6}" x2="${s - 6}" y2="6" stroke="var(--muted)" stroke-dasharray="3 3"/>${dots}</svg>`
  }

  render(): void {
    const r = this.rep
    const { symbol, tf } = this.ctx()
    const head = `<div class="scen-bar"><b>Calibración · ${esc(symbol)} ${esc(tf)} · h=${this.h}</b> <span class="muted">Modo: Análisis (sin dinero)</span> <button id="cal-backfill" ${this.busy ? 'disabled' : ''}>${this.busy ? 'Evaluando…' : 'Ejecutar backfill walk-forward'}</button></div>`
    const err = this.err ? `<p class="scen-warn">${esc(this.err)}</p>` : ''
    if (!r) { this.el.innerHTML = head + err + '<p class="muted">Sin datos de calibración.</p>'; return }
    const cov = Object.entries(r.coverage ?? {}).map(([k, c]) =>
      `<tr><td>Banda ${k} %</td><td>${pct(c.nominal, 0)}</td><td>${pct(c.terminal)}</td><td>${pct(c.pooled)}</td></tr>`).join('')
    const verdict = r.verdict.map((v) => `<li>${esc(v)}</li>`).join('')
    this.el.innerHTML = head + err + `
      <p class="muted">${r.n_evaluated} pronósticos evaluados (${r.n_backfill ?? 0} por backfill) · muestra efectiva ≈ ${r.n_effective} · ${r.n_pending} pendientes</p>
      <div class="cal-grid">
        <div><table class="cal-t"><tr><th></th><th>Nominal</th><th>Terminal</th><th>Todas las velas</th></tr>${cov}</table>
        <p>Brier <b>${r.brier?.toFixed(3) ?? '—'}</b> vs caminata aleatoria ${r.brier_rw?.toFixed(3) ?? '—'} (skill ${pct(r.brier_skill)}) · pinball skill ${pct(r.pinball_skill)} · acierto direccional ${pct(r.directional?.accuracy)} (n=${r.directional?.n ?? 0}) · error de calibración ${pct(r.ece)}</p></div>
        <div>${r.curve ? this.curve(r.curve) : ''}<div class="muted">Predicha (→) vs observada (↑); diagonal = perfecta</div></div>
      </div>
      <h4>Veredicto</h4><ul class="cal-v">${verdict}</ul>
      <p class="muted">Caminata aleatoria: sin deriva, misma volatilidad que el propio pronóstico. Backfill sin plan ni derivados históricos.</p>`
  }
}
