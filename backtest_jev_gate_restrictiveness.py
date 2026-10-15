"""
=============================================================================
BACKTEST: JEV MICROSTRUCTURE GATE — RESTRICTIVIDADE E CALIBRACAO
=============================================================================
Lê o log real de avaliações em jev_shadow_evaluations.jsonl e cruza com
o journal de trades de cada desk para responder:
1. Qual a taxa de VETO actual? (o gate é restritivo demais?)
2. Quando o JEV deu VETO, o mercado realmente perdeu? (precision do VETO)
3. Quando o JEV deu APPROVE, ganhámos? (recall de wins)
4. O que acontece se abaixarmos o limiar de 0.62 → 0.55 ou 0.50?
5. Distribuição de veto_p (would_veto score) — onde está o limiar óptimo?
=============================================================================
"""
import os, json, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHADOW_FILE = os.path.join(BASE_DIR, "jev_shadow_evaluations.jsonl")

# Journals para cruzar resultado real
JOURNALS = {
    "desk1":   os.path.join(BASE_DIR, "live_trading_journal.json"),
    "desk2":   os.path.join(BASE_DIR, "sol_trading_journal.json"),
    "desk3b":  os.path.join(BASE_DIR, "desk3b_btc15m_live_journal.json"),
    "kalshi":  os.path.join(BASE_DIR, "kalshi_trading_journal.json"),
    "gold":    os.path.join(BASE_DIR, "kalshi_gold_15m_journal.json"),
    "natgas":  os.path.join(BASE_DIR, "kalshi_natgas_15m_journal.json"),
}

# ── 1. Carrega avaliações ──────────────────────────────────────────────────
evals = []
with open(SHADOW_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # Só queremos avaliações de entrada (têm "would_veto" score numérico e "verdict")
            if "verdict" in obj and "would_veto" in obj and isinstance(obj["would_veto"], float):
                evals.append(obj)
        except Exception:
            pass

total_evals = len(evals)
if total_evals == 0:
    print("ERRO: Nenhuma avaliação encontrada no log.")
    sys.exit(1)

print(f"\n{'='*72}")
print(f"  BACKTEST JEV MICROSTRUCTURE GATE — {total_evals} avaliações de entrada")
print(f"{'='*72}")

# ── 2. Estatísticas base ──────────────────────────────────────────────────
veto_count   = sum(1 for e in evals if e.get("verdict") == "VETO")
approve_count = total_evals - veto_count
veto_rate = veto_count / total_evals * 100

print(f"\n[A] TAXA DE VETO ACTUAL (limiar=0.62):")
print(f"    Total avaliações : {total_evals}")
print(f"    APROVADs          : {approve_count}  ({100-veto_rate:.1f}%)")
print(f"    VETADs            : {veto_count}  ({veto_rate:.1f}%)")

# ── 3. Distribuição do score would_veto ───────────────────────────────────
scores = [e["would_veto"] for e in evals]
buckets = [(0.0,0.2),(0.2,0.35),(0.35,0.50),(0.50,0.62),(0.62,0.75),(0.75,1.01)]
print(f"\n[B] DISTRIBUIÇÃO DO SCORE 'would_veto':")
for lo, hi in buckets:
    cnt = sum(1 for s in scores if lo <= s < hi)
    bar = '#' * (cnt * 40 // max(total_evals,1))
    label = f"[{lo:.2f}-{hi:.2f})"
    print(f"    {label:14s} {cnt:5d}  {cnt/total_evals*100:5.1f}%  {bar}")

# ── 4. Regimes ────────────────────────────────────────────────────────────
from collections import Counter
regimes = Counter(e.get("candle_regime","unknown") for e in evals)
print(f"\n[C] REGIME CLASSIFICADO PELO JEV:")
for regime, cnt in regimes.most_common():
    pct = cnt / total_evals * 100
    print(f"    {regime:20s} {cnt:5d}  ({pct:.1f}%)")

# ── 5. Cruzamento com journals — precisão do VETO ─────────────────────────
# Estratégia: pegar timestamps de trades nos journals e ver se o JEV
# avaliou perto desse timestamp (janela ±60s). Verificar se o trade foi WIN ou LOSS.
all_trades = []
for desk_key, jpath in JOURNALS.items():
    if not os.path.exists(jpath):
        continue
    try:
        with open(jpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("trades", []):
            result_raw = str(t.get("result","")).upper()
            is_win = "VIT" in result_raw or "WIN" in result_raw or "VITORIA" in result_raw
            is_loss = "DER" in result_raw or "LOSS" in result_raw or "DERROTA" in result_raw
            ts_str = t.get("timestamp","")
            if not ts_str:
                continue
            # Parse timestamp para segundos UNIX simples
            try:
                import re
                m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", ts_str)
                if not m:
                    continue
                import calendar
                from datetime import datetime
                dt = datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),
                              int(m.group(4)),int(m.group(5)),int(m.group(6)))
                ts_unix = calendar.timegm(dt.timetuple())
            except Exception:
                continue
            all_trades.append({
                "desk": desk_key,
                "ts": ts_unix,
                "is_win": is_win,
                "is_loss": is_loss,
                "pnl": float(t.get("cycle_pnl", t.get("pnl", 0.0)))
            })
    except Exception:
        pass

# Parse timestamps das avaliações
import re as _re, calendar as _cal
from datetime import datetime as _dt
def parse_ts(ts_str):
    m = _re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})", ts_str or "")
    if not m:
        return None
    d = _dt(int(m.group(1)),int(m.group(2)),int(m.group(3)),
            int(m.group(4)),int(m.group(5)),int(m.group(6)))
    return _cal.timegm(d.timetuple())

for e in evals:
    e["_ts"] = parse_ts(e.get("timestamp_utc",""))

matched_veto_wins  = 0
matched_veto_loss  = 0
matched_approve_wins = 0
matched_approve_loss = 0

for trade in all_trades:
    t_ts = trade["ts"]
    # Procura avaliação JEV mais próxima do timestamp do trade (±120s)
    best = None
    best_dist = 9999999
    for e in evals:
        if e["_ts"] is None:
            continue
        dist = abs(e["_ts"] - t_ts)
        if dist < best_dist and dist < 120:
            best_dist = dist
            best = e
    if best is None:
        continue
    verdict = best.get("verdict","")
    if verdict == "VETO":
        if trade["is_win"]:  matched_veto_wins += 1
        if trade["is_loss"]: matched_veto_loss += 1
    else:
        if trade["is_win"]:  matched_approve_wins += 1
        if trade["is_loss"]: matched_approve_loss += 1

matched_total = matched_veto_wins + matched_veto_loss + matched_approve_wins + matched_approve_loss
print(f"\n[D] PRECISÃO DO VETO (cruzamento com {len(all_trades)} trades reais, {matched_total} matches ±120s):")
if matched_veto_wins + matched_veto_loss > 0:
    veto_precision = matched_veto_loss / (matched_veto_wins + matched_veto_loss) * 100
    print(f"    VETO emitido e trade PERDEU  : {matched_veto_loss}  (VETO CORRECTO)")
    print(f"    VETO emitido e trade GANHOU  : {matched_veto_wins}  (VETO EXCESSIVO / Falso Positivo)")
    print(f"    => Precisao do VETO: {veto_precision:.1f}% dos VETOs impediam uma DERROTA")
else:
    print("    (sem matches suficientes para calcular precisao do VETO)")

if matched_approve_wins + matched_approve_loss > 0:
    approve_wr = matched_approve_wins / (matched_approve_wins + matched_approve_loss) * 100
    print(f"\n    APPROVE emitido e trade GANHOU: {matched_approve_wins}  (APPROVE CORRECTO)")
    print(f"    APPROVE emitido e trade PERDEU: {matched_approve_loss}  (APPROVE ERRADO)")
    print(f"    => Win Rate com APPROVE: {approve_wr:.1f}%")

# ── 6. Simulação de limiares alternativos ────────────────────────────────
print(f"\n[E] SIMULAÇÃO: E SE MUDAR O LIMIAR DE VETO?")
print(f"    {'Limiar':>8} | {'VETOs':>6} | {'Taxa Veto':>9} | {'APROVADs':>8} | Impacto")
print(f"    {'-'*60}")
for thresh in [0.45, 0.50, 0.55, 0.60, 0.62, 0.65, 0.70, 0.75]:
    # Replicar critérios C1, C2, C3 com novo limiar
    new_vetos = 0
    for e in evals:
        veto_p = e.get("would_veto", 0.5)
        toxic_p = e.get("is_toxic_flow", 0.0)
        worth_p = e.get("worth_entering_now", 0.5)
        regime = e.get("candle_regime", "breakout")
        c1 = veto_p >= thresh
        c2 = (toxic_p >= 0.35) and (regime in ["exhaustion","chop_lateral"])
        c3 = (worth_p <= 0.25) and (regime == "exhaustion")
        if c1 or c2 or c3:
            new_vetos += 1
    new_rate = new_vetos / total_evals * 100
    arrow = "<-- ACTUAL" if abs(thresh - 0.62) < 0.001 else ""
    print(f"    {thresh:>8.2f} | {new_vetos:>6} | {new_rate:>8.1f}% | {total_evals-new_vetos:>8} | {arrow}")

# ── 7. Veredicto ─────────────────────────────────────────────────────────
print(f"\n{'='*72}")
print(f"  VEREDICTO FINAL")
print(f"{'='*72}")
majority_regime = regimes.most_common(1)[0][0]
print(f"  - Taxa de VETO actual: {veto_rate:.1f}%")
print(f"  - Regime mais comum classificado: '{majority_regime}'")
if veto_rate > 40:
    print(f"  [!] GATE POTENCIALMENTE RESTRITIVO DEMAIS (> 40% de VETO).")
    print(f"      Considere aumentar o limiar para 0.65-0.70 ou")
    print(f"      desactivar a Condição C2 (toxic_flow) em regime chop.")
elif veto_rate > 25:
    print(f"  [~] Gate moderadamente restritivo (25-40%). Razoável.")
    print(f"      Monitorar se VETOs coincidiram com derrotas reais.")
else:
    print(f"  [OK] Gate bem calibrado (< 25% de VETO). Não é restritivo demais.")
print()
