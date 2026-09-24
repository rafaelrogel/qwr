import os
import sys
import json
import pandas as pd
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("=" * 90)
print("  🚀 EXECUTANDO SIMULADOR QUANTITATIVO KALSHI: NATURAL GAS & EIA STORAGE (2010 - 2026)")
print("=" * 90)

csv_path = os.path.join("natural_gas_dataset", "eia_henryhub_unified_weekly_2010_2026.csv")
df = pd.read_csv(csv_path)
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date').reset_index(drop=True)

# 1. Feature Engineering
df['week_of_year'] = df['Date'].dt.isocalendar().week
df['month'] = df['Date'].dt.month
df['year'] = df['Date'].dt.year

# Sazonalidade média histórica de injeção/retirada para cada semana do ano
# (Usando janelas walk-forward para evitar look-ahead bias: só usa anos passados)
df['expected_net_change'] = np.nan
df['model_predicted_change'] = np.nan

# Walk-forward loop a partir de 2013 (usando 2010-2012 como dados iniciais de treino)
train_start_year = 2013
test_df = df[df['year'] >= train_start_year].copy().reset_index(drop=True)

initial_bankroll = 1000.0  # $1,000 USD
bankroll = initial_bankroll
stake_per_trade = 25.0     # $25 por contrato semanal (2.5% da banca inicial)
trades = []

# Kalshi Orderbook Simulation Parameters
spread_cost = 0.02         # 2 centavos de spread no livro da Kalshi
max_buy_price = 0.60       # Teto máximo de compra (similar ao nosso robô do BTC)

print(f"[*] Período de Simulação: {test_df['Date'].min().strftime('%Y-%m-%d')} a {test_df['Date'].max().strftime('%Y-%m-%d')}")
print(f"[*] Total de Semanas (Quintas-feiras): {len(test_df)} semanas ({len(test_df)/52:.1f} anos)")
print(f"[*] Banca Inicial: ${initial_bankroll:.2f} USD | Stake: ${stake_per_trade:.2f}\n")

for i in range(len(test_df)):
    current_date = test_df.loc[i, 'Date']
    actual_change = test_df.loc[i, 'net_change_bcf']
    current_price = test_df.loc[i, 'henry_hub_spot_price']
    surplus_pct = test_df.loc[i, 'storage_surplus_deficit_pct']
    week = test_df.loc[i, 'week_of_year']
    
    # Histórico disponível até o momento (sem lookahead)
    past_data = df[df['Date'] < current_date]
    same_week_past = past_data[past_data['week_of_year'] == week]
    
    if len(same_week_past) < 2:
        continue
    
    # 1. Consenso do Mercado (Média histórica ingênua de 5 anos que o varejo usa)
    market_consensus = same_week_past['net_change_bcf'].tail(5).mean()
    
    # 2. Nosso Modelo Preditivo (Ajuste por Momentum Térmico e Preço)
    # Se o preço do gás está alto, os produtores injetam mais ou retiram menos
    # Se a semana anterior teve desvio forte, há persistência térmica de 2 semanas
    prev_week = past_data.iloc[-1]
    prev_dev = prev_week['net_change_bcf'] - past_data[past_data['week_of_year'] == prev_week['week_of_year']]['net_change_bcf'].mean()
    
    # Modelo com inércia térmica (coeficiente de persistência de temperatura = 0.45)
    model_pred = market_consensus + 0.45 * prev_dev
    
    # Contrato Kalshi Semanal: "Will the weekly change be MORE BULLISH than market consensus?"
    # No inverno: mais retirada (número mais negativo) = BULLISH
    # No verão: menos injeção (número menor) = BULLISH
    is_winter = week in list(range(1, 14)) + list(range(45, 54))
    
    # Tighter storage (smaller/more negative net change) = BULLISH for gas price
    # Looser storage (larger/more positive net change) = BEARISH for gas price
    # Therefore, if model_pred < market_consensus, model predicts tighter supply (Bullish!)
    diff = market_consensus - model_pred
    std_err = 14.0
    z_score = diff / std_err
    prob_bullish = 1.0 / (1.0 + np.exp(-1.7 * z_score))
    
    # O mercado na Kalshi cota o consenso em 50¢
    edge_detected = False
    direction = None
    contract_price = 0.50
    
    if prob_bullish >= 0.60:
        # Modelo prevê que o dado será mais TIGHT/BULLISH que o consenso do mercado
        direction = "BULLISH"
        contract_price = 0.50 + spread_cost
        edge_detected = True
    elif prob_bullish <= 0.40:
        # Modelo prevê que o dado será mais LOOSE/BEARISH que o consenso
        direction = "BEARISH"
        contract_price = 0.50 + spread_cost
        edge_detected = True
        
    if edge_detected and contract_price <= max_buy_price:
        # Na realidade, o dado oficial da EIA foi mais tight (bullish) que o consenso?
        actual_is_bullish = actual_change < market_consensus
            
        win = (direction == "BULLISH" and actual_is_bullish) or (direction == "BEARISH" and not actual_is_bullish)
        
        shares = stake_per_trade / contract_price
        if win:
            payout = shares * 1.00
            pnl = payout - stake_per_trade
        else:
            pnl = -stake_per_trade
            
        bankroll += pnl
        
        trades.append({
            "date": current_date.strftime('%Y-%m-%d'),
            "direction": direction,
            "contract_price": contract_price,
            "market_consensus_bcf": round(market_consensus, 1),
            "model_pred_bcf": round(model_pred, 1),
            "actual_change_bcf": round(actual_change, 1),
            "win": win,
            "pnl": round(pnl, 2),
            "bankroll": round(bankroll, 2)
        })

df_trades = pd.DataFrame(trades)
n_trades = len(df_trades)
wins = df_trades['win'].sum()
losses = n_trades - wins
win_rate = (wins / n_trades) * 100 if n_trades > 0 else 0
total_pnl = bankroll - initial_bankroll
total_roi = (total_pnl / initial_bankroll) * 100

# Drawdown
df_trades['peak'] = df_trades['bankroll'].cummax()
df_trades['drawdown'] = (df_trades['bankroll'] - df_trades['peak']) / df_trades['peak']
max_dd = df_trades['drawdown'].min() * 100

# Profit factor
gross_profit = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
gross_loss = abs(df_trades[df_trades['pnl'] < 0]['pnl'].sum())
profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.nan

# Sharpe ratio anualizado (52 semanas por ano)
weekly_returns = df_trades['pnl'] / initial_bankroll
sharpe = (weekly_returns.mean() / weekly_returns.std()) * np.sqrt(52) if weekly_returns.std() > 0 else 0

print("=" * 90)
print("  📊 RESULTADOS FINAIS DO SIMULADOR QUANTITATIVO KALSHI NATURAL GAS")
print("=" * 90)
print(f"  • Total de Operações Executadas: {n_trades} semanas")
print(f"  • Vitórias: {wins} | Derrotas: {losses}")
print(f"  • Taxa de Acerto (Win Rate): {win_rate:.2f}%")
print(f"  • Lucro Líquido: ${total_pnl:,.2f} USD")
print(f"  • Retorno Total sobre a Banca: +{total_roi:.2f}%")
print(f"  • Profit Factor: {profit_factor:.2f}")
print(f"  • Máximo Drawdown: {max_dd:.2f}%")
print(f"  • Sharpe Ratio Anualizado: {sharpe:.2f}")

# Salva arquivo de trades e resumo
summary = {
    "simulation_period": f"{test_df['Date'].min().strftime('%Y-%m-%d')} to {test_df['Date'].max().strftime('%Y-%m-%d')}",
    "total_trades": int(n_trades),
    "wins": int(wins),
    "losses": int(losses),
    "win_rate_pct": round(win_rate, 2),
    "initial_bankroll": initial_bankroll,
    "final_bankroll": round(bankroll, 2),
    "net_profit_usd": round(total_pnl, 2),
    "total_roi_pct": round(total_roi, 2),
    "profit_factor": round(profit_factor, 2),
    "max_drawdown_pct": round(max_dd, 2),
    "annualized_sharpe_ratio": round(sharpe, 2)
}

with open("kalshi_natgas_simulator_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

df_trades.to_csv("kalshi_natgas_simulation_trades.csv", index=False)
print("\n[*] Resultados salvos em kalshi_natgas_simulator_summary.json e kalshi_natgas_simulation_trades.csv")
