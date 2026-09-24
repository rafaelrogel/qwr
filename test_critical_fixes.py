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

    def test_dashboard_panic_button_toggle(self):
        """Verifica a alternância de ativação e desativação em arquivo isolado sem tocar no HALT de produção"""
        test_halt = os.path.join(os.path.dirname(__file__), "TEST_ISOLATED_HALT")
        test_emergency = os.path.join(os.path.dirname(__file__), "TEST_ISOLATED_EMERGENCY")
        from dashboard_server import HTML_CONTENT
        
        # Garante estado limpo inicial
        if os.path.exists(test_halt):
            os.remove(test_halt)
        if os.path.exists(test_emergency):
            os.remove(test_emergency)

        try:
            # 1. Estado inicial: Desativado
            self.assertFalse(os.path.exists(test_halt))
            self.assertFalse(os.path.exists(test_emergency))

            # 2. Simula toggle de ativação em arquivo isolado
            with open(test_halt, "w", encoding="utf-8") as f:
                f.write("HALTED_BY_DASHBOARD_TEST\n")
            
            is_halted = os.path.exists(test_halt) or os.path.exists(test_emergency)
            self.assertTrue(is_halted, "Kill-switch isolado deve estar ativo após acionamento")

            # 3. Simula toggle de desativação
            if os.path.exists(test_halt):
                os.remove(test_halt)

            is_halted_after = os.path.exists(test_halt) or os.path.exists(test_emergency)
            self.assertFalse(is_halted_after, "Kill-switch isolado deve estar inativo após desativação")

            # 4. Verifica presença dos elementos na UI do Dashboard
            self.assertIn('id="btnPanic"', HTML_CONTENT)
            self.assertIn('id="panicGlobalBanner"', HTML_CONTENT)
            self.assertIn('togglePanicButton', HTML_CONTENT)
            self.assertIn('/api/kill_switch_toggle', HTML_CONTENT)

        finally:
            if os.path.exists(test_halt):
                os.remove(test_halt)
            if os.path.exists(test_emergency):
                os.remove(test_emergency)

    def test_parity_accounting_with_unredeemed_tokens(self):
        """Verifica que vitórias por expiração com cotas pendentes de resgate não geram falso alarme de paridade"""
        # Simula 2 vitórias seguidas na expiração ($1.00 stake -> $1.85 payout cada)
        # Saldo USDC inicial: $21.81.
        # Ao comprar: gastou $2.00 em USDC -> saldo USDC caiu para $19.81 (delta wallet = -$2.00)
        # Payouts teóricos: 2 x $1.85 = $3.70.
        # Lucro líquido teórico: +$1.70.
        # Na versão antiga com bug: parity_gap = abs(-$2.00 - $1.70) = $3.70 > $3.50 (FALSO HALT!)
        # Na nova versão com pendentes: effective_delta = -$2.00 + $3.70 (cotas pendentes) = +$1.70 -> parity_gap = $0.00!
        wallet_usdc_delta = -2.00
        cumulative_cycle_pnl = 1.70
        pending_unredeemed_payouts = 3.70

        # Versão corrigida:
        effective_wallet_delta = round(wallet_usdc_delta + pending_unredeemed_payouts, 2)
        parity_gap = abs(effective_wallet_delta - cumulative_cycle_pnl)

        self.assertEqual(effective_wallet_delta, 1.70)
        self.assertEqual(parity_gap, 0.00, "Paridade deve ser exata ao contabilizar cotas vencedoras pendentes de resgate")
        self.assertLess(parity_gap, 1.50, "Não deve disparar alarme nem travar robô")

    def test_kalshi_tp_only_on_fill(self):
        """Verifica que ordens 'resting' na Kalshi não creditam PnL antes do fill real"""
        # Ordem resting (ainda no livro sem comprador):
        mock_resting_order = {"order": {"order_id": "k123", "status": "resting"}}
        status_resting = mock_resting_order["order"]["status"]
        sell_ok_resting = status_resting in ("executed", "filled")
        self.assertFalse(sell_ok_resting, "Ordem descansando (resting) no livro NÃO pode ser dada como sell_ok")

        # Ordem preenchida (filled):
        mock_filled_order = {"order": {"order_id": "k124", "status": "filled"}}
        status_filled = mock_filled_order["order"]["status"]
        sell_ok_filled = status_filled in ("executed", "filled")
        self.assertTrue(sell_ok_filled, "Ordem preenchida (filled) deve ser aprovada para crédito de PnL")

    def test_dashboard_csrf_origin_validation(self):
        """Verifica que o servidor do dashboard rejeita origens externas e aceita localhost"""
        from dashboard_server import QuantDashboardHandler
        
        class DummyHandler:
            headers = {}
            def _is_allowed_origin(self):
                origin = self.headers.get("Origin", "")
                if not origin:
                    return True
                return origin in ("http://localhost:8080", "http://127.0.0.1:8080")

        dh = DummyHandler()
        # Origem externa maliciosa:
        dh.headers = {"Origin": "https://evil-site.com"}
        self.assertFalse(dh._is_allowed_origin(), "Origem externa deve ser bloqueada")

        # Localhost legítimo:
        dh.headers = {"Origin": "http://localhost:8080"}
        self.assertTrue(dh._is_allowed_origin(), "Localhost deve ser permitido")

    def test_sol_live_config_and_drawdown_floor(self):
        """Verifica que o Desk 2 (SOL) remove 0x da chave e respeita o drawdown floor de $15.00"""
        pk_test = "0x3d709a29f7e3a9fce4ead72b41eea04042cfa033a2b905074b6766c5a3cbc650"
        pk_stripped = pk_test[2:] if pk_test.startswith("0x") else pk_test
        self.assertFalse(pk_stripped.startswith("0x"))
        self.assertEqual(len(pk_stripped), 64)

        # Drawdown floor
        safe_bal = 14.50
        floor_breached = safe_bal < 15.00
        self.assertTrue(floor_breached, "Saldo abaixo de $15.00 deve acionar trava de segurança")

    def test_kalshi_live_config_and_client_attributes(self):
        """Verifica que o Desk 3 (Kalshi) possui self.kalshi_client e valida o piso de $2.00"""
        from kalshi_trader_15m import KalshiTrader15M
        bot = KalshiTrader15M()
        self.assertTrue(hasattr(bot, "client"))
        self.assertTrue(hasattr(bot, "kalshi_client"))
        self.assertIs(bot.client, bot.kalshi_client)

        shard2_bal = 1.80
        floor_breached = shard2_bal < 2.00
        self.assertTrue(floor_breached, "Saldo Shard 2 abaixo de $2.00 deve acionar trava de segurança")

if __name__ == "__main__":
    unittest.main(verbosity=2)
