"""
=============================================================================
BACKTEST: JEV GREEN LIGHT OVERRIDE
=============================================================================
Responde às perguntas:
1. Qual a distribuição de worth_entering_now nos logs?
2. Quando JEV diz worth_entering_now >= X + regime=breakout,
   o trade real ganhou ou perdeu?
3. Quantos trades foram BLOQUEADOS pelos outros filtros mas o JEV
   teria aprovado com alta convicção? (oportunidades perdidas)
4. Qual o limiar óptimo de worth_entering_now para o Override?
=============================================================================
"""
import os, json, re, calendar
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHADOW_FILE = os.path.join(BASE_DIR, "jev_shadow_evaluations.jsonl")

JOURNALS = {
    "desk1":  os.path.join(BASE_DIR, "live_trading_journal.json"),
    "desk2":  os.path.join(BASE_DIR, "sol_trading_journal.json"),
    "desk3b": os.path.join(BASE_DIR, "desk3b_btc15m_live_journal.json"),
    "kalshi": os.path.join(BASE_DIR, "kalshi_trading_journal.json"),
    "gold":   os.path.join(BASE_DIR, "kalshi_gold_15m_journal.json"),
    "natgas": os.path.join(BASE_DIR, "kalshi_natgas_15m_journal.json"),
}

# ── Carregar shadow log ───────────────────────────────────────────────────
evals = []
with open(SHADOW_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "worth_entering_now" in obj and "candle_regime" in obj:
                evals.append(obj)
        except Exception:
            pass

total = len(evals)
print(f"\n{'='*72}")
print(f"  BACKTEST JEV GREEN LIGHT — {total} avaliações analisadas")
print(f"{'='*72}")

# ── Parse timestamps ──────────────────────────────────────────────────────
def parse_ts(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})", s or "")
    if not m:
        return None
    d = datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),
                 int(m.group(4)),int(m.group(5)),int(m.group(6)))
    return calendar.timegm(d.timetuple())

for e in evals:
    e["_ts"] = parse_ts(e.get("timestamp_utc",""))

# ── Carregar trades reais ─────────────────────────────────────────────────
all_trades = []
for desk_key, jpath in JOURNALS.items():
    if not os.path.exists(jpath):
        continue
    try:
        with open(jpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("trades", []):
            result_raw = str(t.get("result","")).upper()
            is_win  = any(w in result_raw for w in ["VIT","WIN","VITORIA"])
            is_loss = any(w in result_raw for w in ["DER","LOSS","DERROTA"])
            ts_str = t.get("timestamp","")
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", ts_str)
            if not m:
                continue
            d = datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),
                         int(m.group(4)),int(m.group(5)),int(m.group(6)))
            all_trades.append({
                "desk": desk_key,
                "ts": calendar.timegm(d.timetuple()),
                "is_win": is_win,
                "is_loss": is_loss,
                "pnl": float(t.get("cycle_pnl", t.get("pnl", 0.0)))
            })
    except Exception:
        pass

print(f"\n  Trades reais carregados: {len(all_trades)}")

# ── [A] Distribuição de worth_entering_now ───────────────────────────────
worths = [e.get("worth_entering_now", 0) for e in evals]
print(f"\n[A] DISTRIBUIÇÃO DE 'worth_entering_now':")
buckets = [(0.0,0.2),(0.2,0.35),(0.35,0.50),(0.50,0.65),(0.65,0.80),(0.80,1.01)]
for lo, hi in buckets:
    cnt = sum(1 for w in worths if lo <= w < hi)
    bar = '#' * (cnt * 40 // max(total,1))
    print(f"    [{lo:.2f}-{hi:.2f})  {cnt:4d}  {cnt/total*100:5.1f}%  {bar}")

# ── [B] Distribuição por regime + worth ──────────────────────────────────
print(f"\n[B] WORTH_ENTERING_NOW por REGIME:")
regimes = ["breakout","chop_lateral","exhaustion"]
for regime in regimes:
    subset = [e.get("worth_entering_now",0) for e in evals if e.get("candle_regime")==regime]
    if not subset:
        continue
    avg = sum(subset)/len(subset)
    mx  = max(subset)
    high = sum(1 for w in subset if w >= 0.70)
    print(f"    {regime:20s}  n={len(subset):3d}  avg={avg:.3f}  max={mx:.3f}  (>=0.70: {high})")

# ── [C] Cruzamento worth_entering_now + regime=breakout vs trades reais ──
print(f"\n[C] CORRELAÇÃO: JEV 'worth_entering_now' vs RESULTADO REAL DO TRADE:")
print(f"    (janela de match ±90s entre avaliação JEV e timestamp do trade)")
print()

# Para cada trade real, encontra a avaliação JEV mais próxima
matched = []
for trade in all_trades:
    best, best_dist = None, 9999999
    for e in evals:
        if e["_ts"] is None:
            continue
        dist = abs(e["_ts"] - trade["ts"])
        if dist < best_dist and dist < 90:
            best_dist = dist
            best = e
    if best:
        matched.append({
            "worth": best.get("worth_entering_now", 0),
            "regime": best.get("candle_regime","?"),
            "veto_score": best.get("would_veto",0),
            "is_win": trade["is_win"],
            "is_loss": trade["is_loss"],
            "pnl": trade["pnl"],
            "desk": trade["desk"]
        })

print(f"    Matches encontrados: {len(matched)} de {len(all_trades)} trades")

# Tabela por limiar de worth
thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
print(f"\n    {'Limiar':>8} | {'Matches':>7} | {'Wins':>5} | {'Losses':>6} | {'WR%':>6} | {'P&L Total':>10} | Regime breakout only")
print(f"    {'-'*75}")

best_threshold = None
best_wr = 0

for thresh in thresholds:
    # Todos os regimes
    sub = [m for m in matched if m["worth"] >= thresh]
    wins = sum(1 for m in sub if m["is_win"])
    losses = sum(1 for m in sub if m["is_loss"])
    pnl = sum(m["pnl"] for m in sub)
    wr = wins/(wins+losses)*100 if (wins+losses) > 0 else 0

    # Só regime breakout
    sub_b = [m for m in matched if m["worth"] >= thresh and m["regime"]=="breakout"]
    wins_b = sum(1 for m in sub_b if m["is_win"])
    losses_b = sum(1 for m in sub_b if m["is_loss"])
    wr_b = wins_b/(wins_b+losses_b)*100 if (wins_b+losses_b) > 0 else 0

    marker = " <-- BREAKOUT WR PICO" if wr_b > best_wr and (wins_b+losses_b) >= 3 else ""
    if wr_b > best_wr and (wins_b+losses_b) >= 3:
        best_wr = wr_b
        best_threshold = thresh

    print(f"    {thresh:>8.2f} | {len(sub):>7} | {wins:>5} | {losses:>6} | {wr:>5.1f}% | {pnl:>+10.2f}$ | "
          f"breakout: {wins_b}W/{losses_b}L ({wr_b:.0f}%){marker}")

# ── [D] Oportunidades perdidas (JEV queria entrar mas filtros bloquearam) ─
print(f"\n[D] OPORTUNIDADES POTENCIALMENTE PERDIDAS:")
print(f"    (avaliações onde JEV tinha alta convicção mas NÃO coincide com nenhum trade real)")
print()

# Avaliações sem match (potencialmente bloqueadas pelos outros filtros)
matched_eval_ts = set()
for trade in all_trades:
    for e in evals:
        if e["_ts"] and abs(e["_ts"] - trade["ts"]) < 90:
            matched_eval_ts.add(e["_ts"])
            break

missed = [e for e in evals
          if e["_ts"] not in matched_eval_ts
          and e.get("worth_entering_now", 0) >= 0.70
          and e.get("candle_regime") == "breakout"]

print(f"    Avaliações JEV com worth>=0.70 + regime=breakout SEM trade correspondente: {len(missed)}")
if missed:
    avg_worth = sum(e.get("worth_entering_now",0) for e in missed) / len(missed)
    avg_score = sum(e.get("would_veto",0) for e in missed) / len(missed)
    print(f"    -> worth_entering_now médio: {avg_worth:.3f}")
    print(f"    -> would_veto score médio:   {avg_score:.3f}")
    print(f"    -> Exemplos (primeiros 5):")
    for e in missed[:5]:
        snap = e.get("state_snapshot", {})
        print(f"       [{e.get('timestamp_utc','')}] desk={e.get('desk_id','?')} | "
              f"worth={e.get('worth_entering_now',0):.2f} | "
              f"delta=${snap.get('delta_usd',0):+.1f} | "
              f"regime={e.get('candle_regime','?')} | "
              f"side={snap.get('side','?')}")

# ── Veredicto ────────────────────────────────────────────────────────────
print(f"\n{'='*72}")
print(f"  VEREDICTO FINAL")
print(f"{'='*72}")
if best_threshold:
    print(f"  Limiar óptimo para JEV Override: worth_entering_now >= {best_threshold:.2f}")
    print(f"  Win rate no regime breakout a esse limiar: {best_wr:.1f}%")
    print(f"  Oportunidades perdidas (JEV queria, filtros bloquearam): {len(missed)}")
    if best_wr >= 65:
        print(f"  [OK] Edge estatístico suficiente — IMPLEMENTAR JEV GREEN LIGHT OVERRIDE")
    elif best_wr >= 55:
        print(f"  [~]  Edge marginal — implementar com stake reduzido (50% do normal)")
    else:
        print(f"  [!]  Sem edge claro — NÃO implementar Override ainda")
else:
    print(f"  Dados insuficientes para calcular limiar óptimo.")
print()
