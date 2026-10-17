"""Formato del informe de arbitraje (T43): números y tablas Markdown en español."""

from __future__ import annotations

from datetime import UTC, datetime

NAMES = {"funding_carry": "Carry de funding", "basis": "Base (cash-and-carry trimestral)",
         "related_perps": "Perpetuos relacionados USDT-M/USDC-M",
         "triangular": "Triangular spot"}


def day(t: int | None) -> str:
    return "—" if t is None else datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d")


def pct(x: float | None, d: int = 2) -> str:
    return "—" if x is None else f"{x * 100:+.{d}f} %".replace(".", ",")


def bps(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{x:+.{d}f} pb".replace(".", ",")


def num(x: float | None, d: int = 0) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{d}f}"
    return s.replace(",", " ").replace(".", ",")


def ci(v: list[float] | None) -> str:
    if not v or v[0] != v[0]:
        return "—"
    return f"[{v[0]:+.1f}; {v[1]:+.1f}] pb".replace(".", ",")


def table(head: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def stats_row(label: str, st: dict) -> list[str]:
    if not st.get("n"):
        return [label, "0", "—", "—", "—", "—", "—", "—", "—"]
    return [label, str(st["n"]), pct(st.get("apr_period")), pct(st.get("apr_invested")),
            bps(st.get("mean_bps")), ci(st.get("ci95_mean_bps")),
            f"{st.get('p_value', float('nan')):.3f}".replace(".", ","),
            bps(st.get("worst_bps")), pct(st.get("max_dd"), 1).lstrip("+")]


STATS_HEAD = ["Caso", "Operaciones", "Anual (período)", "Anual (invertido)", "Neto medio/op",
              "IC95 % media", "p (media ≤ 0)", "Peor op.", "Caída máx."]


def brief_row(label: str, row: dict, strategies: tuple[str, ...]) -> list[str]:
    cells = [label]
    for s in strategies:
        st = row.get(s) or {}
        if not st.get("n"):
            cells.append("0 op.")
            continue
        extra = f", {st['liquidations']} liq." if st.get("liquidations") else ""
        cells.append(f"{st['n']} op. · {pct(st.get('apr_period'))} · "
                     f"{bps(st.get('mean_bps'))}/op · 12 m {pct(st.get('last_year_apr'))}{extra}")
    return cells


def breakdown(costs: dict) -> str:
    keys = (("price_pnl", "precio/base"), ("funding", "funding"), ("fees", "−comisiones"),
            ("slippage", "−deslizamiento"), ("legging", "−pata incompleta (esperado)"),
            ("liq_loss", "−liquidación"))
    return " · ".join(f"{name} {num(costs.get(k), 2)} USD" for k, name in keys)
