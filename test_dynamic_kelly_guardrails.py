from execution_math import compute_kalshi_dynamic_contracts, compute_fractional_kelly_stake
from risk_gate import compute_dynamic_stake

def run_tests():
    print("--- Teste 1: Kalshi Bankroll Guardrails ---")
    # Bankroll baixo ($11.36) -> Max 2 contratos
    c1, s1 = compute_kalshi_dynamic_contracts(bankroll=11.36, win_probability=0.80, entry_price_cents=50, available_qty=10, delta_ratio=2.0)
    print(f"Bankroll $11.36 (High edge): Contratos={c1}, Status={s1}")
    assert c1 <= 2, "Falha: Ultrapassou limite de 2 contratos para banca < $20"

    # Bankroll intermediario ($30.00) -> Max 3 contratos
    c2, s2 = compute_kalshi_dynamic_contracts(bankroll=30.00, win_probability=0.85, entry_price_cents=50, available_qty=10, delta_ratio=2.0)
    print(f"Bankroll $30.00 (High edge): Contratos={c2}, Status={s2}")
    assert c2 <= 3, "Falha: Ultrapassou limite de 3 contratos para banca $20-$40"

    # Bankroll robusto ($60.00) -> Ate 5 contratos
    c3, s3 = compute_kalshi_dynamic_contracts(bankroll=60.00, win_probability=0.85, entry_price_cents=50, available_qty=10, delta_ratio=2.0)
    print(f"Bankroll $60.00 (High edge): Contratos={c3}, Status={s3}")
    assert c3 <= 5, "Falha: Ultrapassou teto de 5 contratos"

    # Teste 2: Guardrail de Profundidade L2 (Book Depth)
    # Se o book so tem 1 contrato disponivel, nao pode pedir mais
    c4, s4 = compute_kalshi_dynamic_contracts(bankroll=60.00, win_probability=0.85, entry_price_cents=50, available_qty=1, delta_ratio=2.0)
    print(f"Book Depth Cap (Only 1 in book): Contratos={c4}, Status={s4}")
    assert c4 == 1, "Falha: Nao respeitou profundidade L2"

    # Teste 3: Guardrail de Super-Edge
    # Se o delta_ratio for fraco (1.1), mantem 1 contrato
    c5, s5 = compute_kalshi_dynamic_contracts(bankroll=60.00, win_probability=0.60, entry_price_cents=50, available_qty=10, delta_ratio=1.1)
    print(f"Super-Edge Filter (Low conviction): Contratos={c5}, Status={s5}")
    assert c5 == 1, "Falha: Nao filtrou edge fraco"

    print("\n--- Teste 4: Desk 10 Dynamic Kelly ($1.00 a $3.00) ---")
    st1, status1 = compute_dynamic_stake(bankroll=20.0, win_probability=0.64, entry_price=0.45, fallback_stake=1.0, kelly_fraction=0.25, min_stake=1.0, max_stake=3.0)
    print(f"Desk 10 Base Edge (64%): Stake=${st1:.2f} ({status1})")
    assert 1.0 <= st1 <= 3.0

    st2, status2 = compute_dynamic_stake(bankroll=20.0, win_probability=0.74, entry_price=0.45, fallback_stake=1.0, kelly_fraction=0.25, min_stake=1.0, max_stake=3.0)
    print(f"Desk 10 Super Spike (74%): Stake=${st2:.2f} ({status2})")
    assert 1.0 <= st2 <= 3.0
    assert st2 > st1, "Super spike deveria alocar mais que base edge"

    print("\n>>> TODOS OS TESTES PASSARAM COM SUCESSO ABSOLUTO! <<<")

if __name__ == "__main__":
    run_tests()
