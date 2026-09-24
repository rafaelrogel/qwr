"""
Testes Unitários para o Desk 6 (Yield Harvester 98¢ com Screener Jev)
"""

import os
import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import desk6_yield_harvester as d6

class TestDesk6YieldHarvester(unittest.TestCase):

    def setUp(self):
        # Cria arquivos temporários de teste
        self.test_journal = "test_desk6_journal.json"
        self.test_csv = "test_desk6_journal.csv"
        self.test_state = "test_desk6_state.json"
        
        d6.JOURNAL_JSON = self.test_journal
        d6.JOURNAL_CSV = self.test_csv
        d6.STATE_JSON = self.test_state

    def tearDown(self):
        for f in [self.test_journal, self.test_csv, self.test_state]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def test_01_journal_initialization(self):
        """Testa se o diário é inicializado com a estrutura correta."""
        j = d6.load_journal()
        self.assertIn("metadata", j)
        self.assertIn("stats", j)
        self.assertIn("positions", j)
        self.assertEqual(j["metadata"]["max_stake"], 1.0)
        self.assertEqual(j["metadata"]["max_positions"], 5)
        self.assertTrue(os.path.exists(self.test_journal))

    def test_02_state_file_update(self):
        """Testa atualização e persistência do arquivo de estado para o dashboard."""
        journal = {
            "positions": [
                {"status": "OPEN", "stake": 1.0, "pnl": 0.0},
                {"status": "OPEN", "stake": 1.0, "pnl": 0.0},
                {"status": "WON", "stake": 1.0, "pnl": 0.02}
            ]
        }
        d6.update_state_file(journal, "2026-09-24 22:00:00 UTC", 10, 2)
        self.assertTrue(os.path.exists(self.test_state))
        
        with open(self.test_state, "r", encoding="utf-8") as f:
            st = json.load(f)
        
        self.assertEqual(st["desk"], "Desk 6")
        self.assertEqual(st["active_positions_count"], 2)
        self.assertEqual(st["max_active_positions"], 5)
        self.assertEqual(st["current_exposure_usd"], 2.0)
        self.assertEqual(st["max_exposure_usd"], 5.0)
        self.assertEqual(st["total_pnl_usd"], 0.02)
        self.assertEqual(st["last_candidates_scanned"], 10)
        self.assertEqual(st["last_candidates_approved"], 2)

    def test_03_position_cap_limit(self):
        """Testa se o limite máximo de 5 posições impede novas compras."""
        journal = {
            "positions": [
                {"id": i, "status": "OPEN", "stake": 1.0, "market_id": f"m_{i}"}
                for i in range(5)
            ]
        }
        active = [p for p in journal["positions"] if p.get("status") == "OPEN"]
        slots = d6.MAX_ACTIVE_POSITIONS - len(active)
        self.assertEqual(slots, 0)

    def test_04_reconcile_open_positions_won(self):
        """Testa a reconciliação e cálculo de P&L quando uma posição vence."""
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        journal = {
            "stats": {"total_trades": 0, "winning_trades": 0, "losing_trades": 0, "total_pnl": 0.0, "win_rate": 0.0, "active_positions": 1},
            "positions": [{
                "id": 1,
                "status": "OPEN",
                "question": "Test Market",
                "price": 0.98,
                "stake": 1.0,
                "shares": 1.0204,
                "end_date": past_date
            }]
        }
        d6.save_journal(journal)
        d6.reconcile_open_positions(journal)
        
        updated_pos = journal["positions"][0]
        self.assertEqual(updated_pos["status"], "WON")
        self.assertEqual(updated_pos["payout"], 1.0204)
        self.assertEqual(updated_pos["pnl"], 0.0204)
        self.assertEqual(journal["stats"]["winning_trades"], 1)
        self.assertEqual(journal["stats"]["total_pnl"], 0.0204)

    def test_05_jev_veto_dispute_risk(self):
        """Testa se o auditor Jev veta mercados com risco de disputa elevado."""
        fake_candidate = {
            "question": "Contested Market",
            "outcome": "Yes",
            "price": 0.98,
            "platform": "Polymarket",
            "end_date": "2026-09-25T00:00:00Z",
            "days_remaining": 1.0,
            "resolution_source": "UMA",
            "description": "Vague rules"
        }
        
        # Simula resposta do Jev com escolha 'approved' mas disputa alta
        mock_client = MagicMock()
        mock_ans_verdict = MagicMock()
        mock_ans_verdict.choice = "approved"
        mock_ans_verdict.confidence = 0.60
        mock_ans_verdict.probabilities = {"approved": 0.6, "rejected": 0.4}

        mock_ans_dispute = MagicMock()
        mock_ans_dispute.noul = 0.35 # > 0.15 threshold!

        mock_resp = MagicMock()
        mock_resp.answers = {"verdict": mock_ans_verdict, "dispute_risk": mock_ans_dispute}
        mock_client.system_one.return_value = mock_resp

        with patch.object(d6, "jev_client", mock_client):
            audit = d6.audit_with_jev(fake_candidate)
            self.assertFalse(audit["approved"])
            self.assertEqual(audit["dispute_prob"], 0.35)

    def test_06_jev_approval_pristine(self):
        """Testa se o auditor Jev aprova mercado com regras pristinas."""
        fake_candidate = {
            "question": "Official Government Release",
            "outcome": "Yes",
            "price": 0.985,
            "platform": "Polymarket",
            "end_date": "2026-09-26T00:00:00Z",
            "days_remaining": 2.0,
            "resolution_source": "Federal Register",
            "description": "Deterministic official metric"
        }
        
        mock_client = MagicMock()
        mock_ans_verdict = MagicMock()
        mock_ans_verdict.choice = "approved"
        mock_ans_verdict.confidence = 0.85
        mock_ans_verdict.probabilities = {"approved": 0.85, "rejected": 0.15}

        mock_ans_dispute = MagicMock()
        mock_ans_dispute.noul = 0.05 # <= 0.15

        mock_resp = MagicMock()
        mock_resp.answers = {"verdict": mock_ans_verdict, "dispute_risk": mock_ans_dispute}
        mock_client.system_one.return_value = mock_resp

        with patch.object(d6, "jev_client", mock_client):
            audit = d6.audit_with_jev(fake_candidate)
            self.assertTrue(audit["approved"])
            self.assertEqual(audit["verdict"], "approved")
            self.assertLessEqual(audit["dispute_prob"], 0.15)


if __name__ == "__main__":
    unittest.main()
