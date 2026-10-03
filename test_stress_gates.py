# -*- coding: utf-8 -*-
import execution_math
import risk_gate

print("1. Teste de Livro Vazio ou Iliquido:")
vwap, cost, shares, slip = execution_math.calculate_vwap_ask([], 20.0)
print(f"   Livro vazio -> VWAP: {vwap} (Esperado: None)")

print("\n2. Teste de Livro com USD 4.80 de profundidade para ordem de USD 20:")
shallow_book = [(0.48, 10.0)] # total $4.80
vwap, cost, shares, slip = execution_math.calculate_vwap_ask(shallow_book, 20.0)
print(f"   Livro raso -> VWAP: {vwap}, Custo parcial: USD {cost:.2f} (Esperado: None)")

print("\n3. Teste de Livro Profundo para ordem de USD 20:")
deep_book = [(0.48, 20.0), (0.49, 50.0), (0.50, 100.0)]
vwap, cost, shares, slip = execution_math.calculate_vwap_ask(deep_book, 20.0)
print(f"   Livro profundo -> VWAP: {vwap:.4f}, Custo: USD {cost:.2f}, Cotas: {shares:.2f}, Slippage: {slip:.1f} bps")

print("\n4. Teste de Pre-Trade Gate com Net Edge Negativo:")
ok, msg = risk_gate.check_pre_trade_gate("DESK1_BTC_5M", "UP", 20.0, 65000, 64950, fair_value=0.50, vwap_price=0.50)
print(f"   Zero edge -> Aprovado? {ok} | Msg: {msg}")

print("\n5. Teste de Pre-Trade Gate com Net Edge Positivo (+5.5%):")
ok, msg = risk_gate.check_pre_trade_gate("DESK1_BTC_5M", "UP", 20.0, 65000, 64950, fair_value=0.56, vwap_price=0.49)
print(f"   Positivo -> Aprovado? {ok} | Msg: {msg}")

print("\n6. Teste de Kelly Fracionario com Edge Negativo (odds desfavoraveis):")
stake, status = risk_gate.compute_dynamic_stake(bankroll=500.0, win_probability=0.40, entry_price=0.55)
print(f"   Edge negativo -> Stake: USD {stake:.2f} | Status: {status}")

print("\n7. Teste de Kelly Fracionario com Alta Conviccao (65% win, entry 0.45):")
stake, status = risk_gate.compute_dynamic_stake(bankroll=500.0, win_probability=0.65, entry_price=0.45)
print(f"   Alta conviccao -> Stake: USD {stake:.2f} | Status: {status}")

print("\n8. Teste de Gate Diurno (Dukascopy/HistData Autocorrelation Switching):")
deadband_mom, reg_mom = risk_gate.get_dynamic_deadband_gate(strike=85000.0, current_utc_hour=13) # London/NY open momentum
deadband_chop, reg_chop = risk_gate.get_dynamic_deadband_gate(strike=85000.0, current_utc_hour=20) # Asia/Evening chop
print(f"   13h UTC (Momentum): Deadband ${deadband_mom:.2f} ({reg_mom['regime']} mult {reg_mom['deadband_multiplier']}x)")
print(f"   20h UTC (Chop/MeanRevert): Deadband ${deadband_chop:.2f} ({reg_chop['regime']} mult {reg_chop['deadband_multiplier']}x)")
assert deadband_chop > deadband_mom, "Erro: Deadband de chop deve ser maior que momentum"
print("   -> ASSERCAO PASSOU: Deadband de chop expandido com sucesso.")

print("\n9. Teste de Gate de Cauda Gorda (Dukascopy/HistData Fat Tail Hazard):")
# Caso A: Contrato a 95¢ com distancia de apenas 0.3% (< 0.75% 3 sigmas) e 12h restantes
safe_a, msg_a = risk_gate.check_fat_tail_safety_gate(entry_price=0.95, strike_distance_pct=0.003, hours_remaining=12.0)
print(f"   Caso A (95¢, 0.3% dist, 12h): Seguro? {safe_a} | Veto: {msg_a}")
assert not safe_a, "Erro: Contrato com cauda gorda deveria ter sido vetado"

# Caso B: Contrato a 95¢ com distancia confortavel de 1.8% (> 0.75%)
safe_b, msg_b = risk_gate.check_fat_tail_safety_gate(entry_price=0.95, strike_distance_pct=0.018, hours_remaining=12.0)
print(f"   Caso B (95¢, 1.8% dist, 12h): Seguro? {safe_b} | Status: {msg_b}")
assert safe_b, "Erro: Contrato seguro deveria ter sido aprovado"
print("   -> ASSERCAO PASSOU: Salvaguarda de Cauda Gorda atuando com precisao estrita.")

print("\n10. Teste de Gate de Order Flow Imbalance / Microestrutura (Binance 50 GB Tick Alpha):")
# Caso A: Divergencia Toxica (Preco UP, mas CVD DOWN) -> Veto
ofi_ok_a, ofi_msg_a = risk_gate.check_order_flow_imbalance_gate(target_side="UP", dominant_signal="DOWN", net_cvd_usd=-350_000, cvd_ratio=0.35)
print(f"   Caso A (Preco UP, CVD DOWN): Aprovado? {ofi_ok_a} | Veto: {ofi_msg_a}")
assert not ofi_ok_a, "Erro: Divergencia toxica de venda deveria ter sido vetada"

# Caso B: Convergencia Plena (Preco UP e CVD UP) -> Aprovado
ofi_ok_b, ofi_msg_b = risk_gate.check_order_flow_imbalance_gate(target_side="UP", dominant_signal="UP", net_cvd_usd=420_000, cvd_ratio=0.68)
print(f"   Caso B (Preco UP, CVD UP): Aprovado? {ofi_ok_b} | Status: {ofi_msg_b}")
assert ofi_ok_b, "Erro: Convergencia plena de compra deveria ter sido aprovada"
print("   -> ASSERCAO PASSOU: Gate de Order Flow Imbalance operando com 100% de precisao.")
