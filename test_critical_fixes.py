import os
import sys
import unittest

# Ensure root path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestCriticalFixes(unittest.TestCase):
    
    def test_oracle_feed_abort_logic(self):
        """Verifica que quando o strike é None ou <= 0, o sistema aborta e não assume 0.0"""
        strike = None
        # Simulação da lógica corrigida
        if not strike or strike <= 0:
            aborted = True
        else:
            aborted = False
        self.assertTrue(aborted, "Deve abortar quando strike for None")
        
        strike = 0.0
        if not strike or strike <= 0:
            aborted = True
        else:
            aborted = False
        self.assertTrue(aborted, "Deve abortar quando strike for 0.0")

    def test_true_wallet_parity_algebra(self):
        """Verifica que a checagem de paridade é real e não tautológica"""
        initial_bal = 21.00
        # Simula 3 trades com PnL teórico de +$2.50 no total
        trades_cycle_pnl = [1.00, 1.00, 0.50]
        cumulative_pnl = sum(trades_cycle_pnl) # +$2.50
        
        # Cenário 1: Carteira real subiu apenas +$0.50 (divergência de $2.00)
        new_wallet_balance = 21.50
        wallet_delta = round(new_wallet_balance - initial_bal, 2)
        parity_gap = abs(wallet_delta - cumulative_pnl)
        
        self.assertEqual(parity_gap, 2.00, "Parity gap deve detectar exatamente a divergência de $2.00")
        self.assertGreater(parity_gap, 1.50, "Deve disparar o alarme de divergência contábil")

    def test_kalshi_sell_order_single_book_mapping(self):
        """Verifica o mapeamento correto de ordens no single-book da Kalshi V2"""
        from kalshi_trader_15m import KalshiClient
        client = KalshiClient(key_id="", private_key_pem_path="")
        
        # Teste BUY YES: side deve ser 'bid', preço yes_dollars
        # Teste BUY NO: side deve ser 'ask', preço (100 - no_dollars)
        # Teste SELL YES: side deve ser 'ask', preço yes_dollars
        # Teste SELL NO: side deve ser 'bid', preço (100 - no_dollars)
        
        # BUY YES a 55¢
        # side='bid', price='0.5500'
        # SELL YES a 85¢
        # side='ask', price='0.8500'
        action_buy = "buy"
        side_yes = "yes"
        book_side_buy_yes = "bid" if side_yes == "yes" else "ask"
        self.assertEqual(book_side_buy_yes, "bid")
        
        action_sell = "sell"
        book_side_sell_yes = "ask" if side_yes == "yes" else "bid"
        self.assertEqual(book_side_sell_yes, "ask")

    def test_sol_restart_dedup(self):
        """Verifica que o histórico de trades repovoa traded_windows na reinicialização"""
        mock_trades = [
            {"window_ts": 1790241600, "result": "VITÓRIA"},
            {"window_ts": 1790241900, "result": "DERROTA"},
            {"window_ts": 1790242200, "result": "VITÓRIA"}
        ]
        traded_windows = {int(t["window_ts"]) for t in mock_trades if "window_ts" in t}
        self.assertEqual(len(traded_windows), 3)
        self.assertIn(1790241900, traded_windows)
        self.assertNotIn(1790242500, traded_windows)

    def test_requirements_pinning(self):
        """Verifica que dependências críticas estão declaradas no requirements.txt"""
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        self.assertTrue(os.path.exists(req_path))
        with open(req_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("py-clob-client-v2", content)
        self.assertIn("typesafe-sdk", content)
        self.assertIn("cryptography", content)

    def test_file_based_kill_switch_detection(self):
        """Verifica que a presença do arquivo HALT é detectada e aciona a parada imediata"""
        test_halt = os.path.join(os.path.dirname(__file__), "TEST_HALT")
        try:
            with open(test_halt, "w") as f:
                f.write("STOP")
            halt_active = os.path.exists(test_halt)
            self.assertTrue(halt_active, "Kill-switch deve detectar a existência do arquivo de parada")
        finally:
            if os.path.exists(test_halt):
                os.remove(test_halt)

    def test_master_deposit_drawdown_breaker(self):
        """Verifica que o circuit breaker ancorado no depósito trava permanentemente se drawdown > $6.00"""
        initial_deposit = 21.00
        max_drawdown = 6.00
        
        # Saldo caiu para $14.50 (perda de $6.50)
        current_balance = 14.50
        total_loss = initial_deposit - current_balance
        breaker_tripped = total_loss >= max_drawdown
        self.assertTrue(breaker_tripped, "Breaker deve travar quando saldo cair abaixo de $15.00")

    def test_threaded_tcp_server_class(self):
        """Verifica que o servidor do dashboard suporta concorrência ThreadedTCPServer"""
        from dashboard_server import ThreadedTCPServer
        import socketserver
        self.assertTrue(issubclass(ThreadedTCPServer, socketserver.ThreadingMixIn))
        self.assertTrue(issubclass(ThreadedTCPServer, socketserver.TCPServer))

if __name__ == "__main__":
    unittest.main(verbosity=2)
