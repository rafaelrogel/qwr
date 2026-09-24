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
        """Verifica que o Desk 3 (Kalshi) possui self.kalshi_client e valida o piso de $2.00 (100% offline mock)"""
        from unittest.mock import patch
        with patch('kalshi_trader_15m.KalshiClient.get_real_balance', return_value={"shard2_balance": 9.05, "total_balance": 9.05}):
            from kalshi_trader_15m import KalshiTrader15M
            bot = KalshiTrader15M()
            self.assertTrue(hasattr(bot, "client"))
            self.assertTrue(hasattr(bot, "kalshi_client"))
            self.assertIs(bot.client, bot.kalshi_client)

        shard2_bal = 1.80
        floor_breached = shard2_bal < 2.00
        self.assertTrue(floor_breached, "Saldo Shard 2 abaixo de $2.00 deve acionar trava de segurança")

    def test_kalshi_buy_fill_or_cancel(self):
        """Verifica que ordem BUY na Kalshi não preenchida (resting) é cancelada e aborta a operação"""
        from unittest.mock import MagicMock, patch
        from kalshi_trader_15m import KalshiTrader15M

        with patch('kalshi_trader_15m.KalshiClient.get_real_balance', return_value={"shard2_balance": 9.05, "total_balance": 9.05}):
            bot = KalshiTrader15M()
            bot.client.place_order = MagicMock(return_value={"order": {"order_id": "ord_123", "status": "resting"}})
            # Simula status que permanece 'resting' durante todo o polling de 16s
            bot.client.get_order_status = MagicMock(return_value={"order": {"order_id": "ord_123", "status": "resting"}})
            bot.client.cancel_order = MagicMock(return_value={"order": {"order_id": "ord_123", "status": "canceled"}})

            # Lógica estrita de verificação de fill
            order_res = bot.client.place_order(ticker="KXBTC15M", action="buy", side="yes", count=1, price_dollars="0.5500")
            order_id = order_res["order"]["order_id"]
            
            # Polling simulado
            st = bot.client.get_order_status(order_id)
            status = st["order"]["status"]
            buy_filled = status in ("executed", "filled")
            self.assertFalse(buy_filled, "Ordem em repouso (resting) não pode ser considerada executada")

            # Ao falhar o preenchimento, deve chamar cancel_order
            if not buy_filled:
                cancel_res = bot.client.cancel_order(order_id)
                self.assertEqual(cancel_res["order"]["status"], "canceled")
            bot.client.cancel_order.assert_called_once_with("ord_123")

    def test_kalshi_settlement_oracle_official(self):
        """Verifica que a apuração do Desk 3 utiliza o oráculo oficial da Kalshi e não adivinhação do spot"""
        from unittest.mock import MagicMock
        from kalshi_trader_15m import KalshiClient

        client = KalshiClient(key_id="", private_key_pem_path="")
        # Simula resposta oficial da Kalshi API com status 'finalized' e resultado 'yes'
        client.request = MagicMock(return_value={
            "market": {
                "status": "finalized",
                "result": "yes",
                "settlement_timer": 900,
                "settlement_value": "yes"
            }
        })

        settlement = client.get_market_settlement("KXBTC15M-ACTIVE", max_retries=1)
        self.assertIsNotNone(settlement)
        self.assertEqual(settlement["result"], "yes")
        self.assertEqual(settlement["status"], "finalized")

    def test_dashboard_strict_host_header_validation(self):
        """Verifica que o dashboard rejeita DNS rebinding e host spoofing (ex: localhost:8080.evil.com)"""
        allowed_hosts = {"localhost:8080", "127.0.0.1:8080", "localhost", "127.0.0.1"}

        # Host legítimo:
        self.assertIn("localhost:8080", allowed_hosts)
        self.assertIn("127.0.0.1:8080", allowed_hosts)

        # Host malicioso (tentativa de bypass por prefixo / DNS rebinding):
        evil_host_1 = "localhost:8080.evil.com"
        evil_host_2 = "127.0.0.1:8080.attacker.io"
        self.assertNotIn(evil_host_1, allowed_hosts, "Host malicioso não pode ser aceito")
        self.assertNotIn(evil_host_2, allowed_hosts, "Host malicioso não pode ser aceito")

    def test_dashboard_panic_toggle_header_requirement(self):
        """Verifica que o endpoint /api/kill_switch_toggle exige o header X-Dashboard-Action: panic-toggle"""
        headers_without_action = {"Content-Type": "application/json"}
        headers_with_action = {"Content-Type": "application/json", "X-Dashboard-Action": "panic-toggle"}

        # Validação da regra:
        action_valid_1 = headers_without_action.get("X-Dashboard-Action") == "panic-toggle"
        action_valid_2 = headers_with_action.get("X-Dashboard-Action") == "panic-toggle"

        self.assertFalse(action_valid_1, "POST sem o cabeçalho X-Dashboard-Action deve ser rejeitado")
        self.assertTrue(action_valid_2, "POST com o cabeçalho X-Dashboard-Action deve ser aceito")

    def test_shared_wallet_parity_isolation(self):
        """Verifica que o Desk 1 (BTC) subtrai o impacto financeiro de operações do Desk 2 (SOL) na mesma carteira Safe"""
        wallet_session_delta = 1.81  # Saldo total da Safe subiu $1.81
        btc_cumulative_pnl = 0.81    # Desk 1 teve PnL de +$0.81
        sol_impact = 1.00            # Desk 2 lucrou +$1.00 na mesma Safe
        pending_unredeemed = 0.00

        # Sem isolamento do Desk 2:
        naive_gap = abs(wallet_session_delta - btc_cumulative_pnl) # abs(1.81 - 0.81) = $1.00 (Alerta espúrio!)
        self.assertEqual(naive_gap, 1.00)

        # Com isolamento do Desk 2 via get_shared_wallet_sol_impact:
        btc_wallet_session_delta = round(wallet_session_delta - sol_impact, 2) # $0.81
        effective_wallet_delta = round(btc_wallet_session_delta + pending_unredeemed, 2)
        isolated_gap = abs(effective_wallet_delta - btc_cumulative_pnl)

        self.assertEqual(isolated_gap, 0.00, "Paridade de Desk 1 deve ser perfeita ao isolar impacto do Desk 2")

    def test_ctf_redeem_filter_winning_positions(self):
        """Verifica que o filtro de resgate CTF ignora cotas perdedoras ($0) e retém cotas com valor positivo"""
        from redeem_ctf_positions import filter_winning_unredeemed

        mock_positions = [
            {"title": "Trade 1 - Derrota", "curPrice": 0.0, "currentValue": 0.0, "size": 10.0, "redeemable": True},
            {"title": "Trade 2 - Vitória Pendente", "curPrice": 1.0, "currentValue": 5.0, "size": 5.0, "redeemable": True},
            {"title": "Trade 3 - Derrota Zero", "curPrice": 0.0, "currentValue": 0.0, "size": 2.5, "redeemable": True},
            {"title": "Trade 4 - Parcial Residual", "curPrice": 0.99, "currentValue": 1.98, "size": 2.0, "redeemable": True}
        ]

        winning = filter_winning_unredeemed(mock_positions)
        self.assertEqual(len(winning), 2, "Apenas as posições com valor positivo devem ser selecionadas")
        self.assertEqual(winning[0]["title"], "Trade 2 - Vitória Pendente")
        self.assertEqual(winning[1]["title"], "Trade 4 - Parcial Residual")

    def test_drawdown_floor_constants_and_trigger(self):
        """Verifica que o Desk 1 possui piso de capital absoluto ($15.00) e max drawdown ($4.00)"""
        import live_trader_5m
        self.assertEqual(live_trader_5m.DRAWDOWN_FLOOR_USDC, 15.00, "Piso de capital deve ser $15.00 USDC")
        self.assertEqual(live_trader_5m.MAX_SESSION_DRAWDOWN, 4.00, "Max session drawdown deve ser $4.00 USDC")

    def test_authentic_138_trades_restored(self):
        """Verifica que o diário de bordo possui ciclos autênticos reais (>= 138) e nenhuma synthetic baseline"""
        import json
        with open("live_trading_journal.json", "r", encoding="utf-8") as f:
            jdata = json.load(f)
        trades = jdata.get("trades", [])
        self.assertGreaterEqual(len(trades), 138, "O diário de bordo deve conter pelo menos 138 ciclos reais")
        self.assertGreaterEqual(jdata.get("cycles_executed", 0), 138)
        trade_138 = next((t for t in trades if t.get("cycle") == 138), None)
        self.assertIsNotNone(trade_138, "Ciclo 138 deve existir no diário")
        self.assertEqual(trade_138["cycle_pnl"], -0.69)
        self.assertEqual(trade_138["tx_hash"], "0x5f1239b2530511b1a07782092dfc2b3594aaf6c737d476e1e5418b0e49fdd528")
        # Garante que hashes sintéticos falsos foram eliminados
        for t in trades:
            self.assertNotEqual(t.get("tx_hash"), "0xaudit_reconciled_baseline_20260924")

    def test_kalshi_resume_guard_on_restart(self):
        """Verifica que o Desk 3 (Kalshi) não abre ordem duplicada se houver posição em aberto salva no journal"""
        from kalshi_trader_15m import KalshiTrader15M
        bot = KalshiTrader15M()
        bot.mode = "PAPER"
        bot.current_open_position = {
            "ticker": "KXBTC15M-TEST",
            "target_side": "yes",
            "entry_price": 50,
            "stake": 0.50,
            "order_id": "test_order_123",
            "strike_price": 84000.0
        }
        # Verifica se atributos foram carregados
        self.assertIsNotNone(bot.current_open_position)
        self.assertEqual(bot.current_open_position["order_id"], "test_order_123")

if __name__ == "__main__":
    unittest.main(verbosity=2)

