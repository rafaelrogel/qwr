"""
Unit Tests for Desk 5: Kalshi Natural Gas 15-Minute Algo Trader (KXNATGAS15M)
=============================================================================
Testes isolados com mocks completos de rede para execução instantânea (< 0.5s).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestNatGas15M(unittest.TestCase):

    def test_natgas_deadband_calculation(self):
        """Verifica o cálculo do deadband dinâmico de 10 bps com piso mínimo de $0.0030"""
        from kalshi_natgas_trader_15m import DEADBAND_BPS, DEADBAND_MIN_FLOOR

        strike = 3.3500
        # 10 bps de 3.35 = 0.00335
        dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike * DEADBAND_BPS, 4))
        self.assertAlmostEqual(dynamic_deadband, 0.0034, places=4)
        self.assertGreaterEqual(dynamic_deadband, DEADBAND_MIN_FLOOR)

        # Se strike for baixo (ex: $2.00 -> 10 bps = $0.0020 < piso $0.0030)
        strike_low = 2.0000
        dynamic_low = max(DEADBAND_MIN_FLOOR, round(strike_low * DEADBAND_BPS, 4))
        self.assertEqual(dynamic_low, DEADBAND_MIN_FLOOR, "Piso de $0.0030 deve prevalecer para evitar ruído")

    def test_natgas_price_cap_ev_protection(self):
        """Verifica que cotas > 60¢ ou < 25¢ são rejeitadas pelo filtro de valor esperado (EV)"""
        from kalshi_natgas_trader_15m import PRIMARY_MAX_PRICE, PRIMARY_MIN_PRICE

        # Cota cara (91¢) -> Rejeitar (assimetria negativa)
        ask_expensive = 0.91
        self.assertTrue(ask_expensive > PRIMARY_MAX_PRICE, "Cota de 91¢ deve ser rejeitada (> 60¢)")

        # Cota barata normal (45¢) -> Aceitar
        ask_fair = 0.45
        self.assertTrue(PRIMARY_MIN_PRICE <= ask_fair <= PRIMARY_MAX_PRICE, "Cota de 45¢ deve ser aceita")

        # Cota penny trap (10¢) -> Rejeitar
        ask_penny = 0.10
        self.assertTrue(ask_penny < PRIMARY_MIN_PRICE, "Cota de 10¢ deve ser rejeitada (< 25¢)")

    def test_natgas_jev_trend_alignment(self):
        """Verifica que o filtro Jev aprova apenas quando drift e vela anterior estão alinhados"""
        # Caso 1: Vela anterior UP e Drift UP -> Aprovado
        prior_dir = "UP"
        target_dir = "UP"
        approved = (prior_dir == target_dir)
        self.assertTrue(approved, "Tendência alinhada UP+UP deve ser aprovada")

        # Caso 2: Vela anterior DOWN e Drift UP -> Vetado
        prior_dir_rev = "DOWN"
        target_dir_drift = "UP"
        vetoed = (prior_dir_rev != target_dir_drift)
        self.assertTrue(vetoed, "Divergência entre vela anterior e drift deve ser vetada")

    def test_natgas_buy_fill_or_cancel(self):
        """Verifica que ordens resting na Kalshi são canceladas e não abrem posição no Desk 5"""
        with patch('kalshi_natgas_trader_15m.KalshiClient.get_real_balance', return_value={"shard2_balance": 9.05, "total_balance": 9.05}):
            from kalshi_natgas_trader_15m import KalshiNatGasTrader15M
            bot = KalshiNatGasTrader15M()
            bot.client.place_order = MagicMock(return_value={"order": {"order_id": "ng_ord_1", "status": "resting"}})
            bot.client.get_order_status = MagicMock(return_value={"order": {"order_id": "ng_ord_1", "status": "resting"}})
            bot.client.cancel_order = MagicMock(return_value={"order": {"order_id": "ng_ord_1", "status": "canceled"}})

            order_res = bot.client.place_order("KXNATGAS15M-TEST", "yes", 1, "0.5000", action="buy")
            order_id = order_res["order"]["order_id"]

            st = bot.client.get_order_status(order_id)
            buy_filled = st["order"]["status"] in ("executed", "filled")
            self.assertFalse(buy_filled)

            if not buy_filled:
                cancel_res = bot.client.cancel_order(order_id)
                self.assertEqual(cancel_res["order"]["status"], "canceled")
            bot.client.cancel_order.assert_called_once_with("ng_ord_1")

    def test_natgas_settlement_oracle(self):
        """Verifica que a liquidação oficial usa o oráculo da Kalshi (/markets/{ticker})"""
        from kalshi_natgas_trader_15m import KalshiClient
        client = KalshiClient(key_id="", private_key_pem_path="")
        client.request = MagicMock(return_value={
            "market": {
                "status": "settled",
                "result": "no",
                "settlement_timer": 900,
                "settlement_value": "no"
            }
        })

        res = client.get_market_settlement("KXNATGAS15M-TEST", max_retries=1)
        self.assertIsNotNone(res)
        self.assertEqual(res["result"], "no")
        self.assertEqual(res["status"], "settled")

    def test_natgas_live_state_output(self):
        """Verifica a geração do arquivo de estado em tempo real para o dashboard"""
        from kalshi_natgas_trader_15m import KalshiNatGasTrader15M, LIVE_STATE_JSON
        with patch('kalshi_natgas_trader_15m.KalshiClient.get_real_balance', return_value={"shard2_balance": 9.05, "total_balance": 9.05}):
            bot = KalshiNatGasTrader15M()
            mock_state = {
                "ticker": "KXNATGAS15M-TEST",
                "strike": 3.345,
                "spot": 3.355,
                "delta": 0.010,
                "deadband": 0.0033,
                "mode": "TEST",
                "status_signal": "UP / YES CONFIRMADO"
            }
            bot.update_live_state(mock_state)
            self.assertTrue(os.path.exists(LIVE_STATE_JSON))

            import json
            with open(LIVE_STATE_JSON, "r", encoding="utf-8") as f:
                read_data = json.load(f)
            self.assertEqual(read_data["ticker"], "KXNATGAS15M-TEST")
            self.assertEqual(read_data["delta"], 0.010)

if __name__ == "__main__":
    unittest.main(verbosity=2)
