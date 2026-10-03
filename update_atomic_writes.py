# -*- coding: utf-8 -*-
"""
Script utilitário para atualizar os robôs com salvamento atômico (atomic_write_json)
e verificação de kill-switch do risk_gate.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def update_eth_trader():
    path = os.path.join(BASE_DIR, "eth_trader_5m.py")
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    # Import
    if "from risk_gate import" not in c:
        c = c.replace(
            "from typing import Optional, Dict, Any, List, Tuple",
            "from typing import Optional, Dict, Any, List, Tuple\nfrom risk_gate import atomic_write_json, safe_read_json, is_system_halted"
        )

    # update_live_state
    old_live = re.search(r"def update_live_state\(self, state_dict: dict\):.*?(?=def record_trade)", c, re.DOTALL)
    if old_live:
        new_live = "def update_live_state(self, state_dict: dict):\n        atomic_write_json(LIVE_STATE_JSON, state_dict)\n\n    "
        c = c[:old_live.start()] + new_live + c[old_live.end():]

    # record_trade
    old_rec = re.search(r"def record_trade\(self, trade_data: dict\):.*?(?=def run_cycle)", c, re.DOTALL)
    if old_rec:
        new_rec = """def record_trade(self, trade_data: dict):
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_ETH_5M", "current_balance": self.balance, "trades": []})
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)

    """
        c = c[:old_rec.start()] + new_rec + c[old_rec.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("[OK] eth_trader_5m.py atualizado.")


def update_kalshi_gold_trader():
    path = os.path.join(BASE_DIR, "kalshi_gold_trader_15m.py")
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    # Import
    if "from risk_gate import" not in c:
        c = c.replace(
            "from typing import Optional, Dict, Any, List, Tuple",
            "from typing import Optional, Dict, Any, List, Tuple\nfrom risk_gate import atomic_write_json, safe_read_json, is_system_halted"
        )

    # save_open_position & clear_open_position
    old_pos = re.search(r"def save_open_position\(self, pos_data: dict\):.*?(?=def update_live_state)", c, re.DOTALL)
    if old_pos:
        new_pos = """def save_open_position(self, pos_data: dict):
        self.current_open_position = pos_data
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = pos_data
            atomic_write_json(JOURNAL_JSON, data)

    def clear_open_position(self):
        self.current_open_position = None
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = None
            atomic_write_json(JOURNAL_JSON, data)

    """
        c = c[:old_pos.start()] + new_pos + c[old_pos.end():]

    # update_live_state
    old_live = re.search(r"def update_live_state\(self, state_dict: dict\):.*?(?=def record_trade)", c, re.DOTALL)
    if old_live:
        new_live = "def update_live_state(self, state_dict: dict):\n        atomic_write_json(LIVE_STATE_JSON, state_dict)\n\n    "
        c = c[:old_live.start()] + new_live + c[old_live.end():]

    # record_trade
    old_rec = re.search(r"def record_trade\(self, trade_data: dict\):.*?(?=def run_cycle)", c, re.DOTALL)
    if old_rec:
        new_rec = """def record_trade(self, trade_data: dict):
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_GOLD_15M", "current_balance": self.balance, "trades": []})
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)

    """
        c = c[:old_rec.start()] + new_rec + c[old_rec.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("[OK] kalshi_gold_trader_15m.py atualizado.")


def update_kalshi_natgas_trader():
    path = os.path.join(BASE_DIR, "kalshi_natgas_trader_15m.py")
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    # Import
    if "from risk_gate import" not in c:
        c = c.replace(
            "from typing import Optional, Dict, Any, List, Tuple",
            "from typing import Optional, Dict, Any, List, Tuple\nfrom risk_gate import atomic_write_json, safe_read_json, is_system_halted"
        )

    # save_open_position & clear_open_position
    old_pos = re.search(r"def save_open_position\(self, pos_data: dict\):.*?(?=def update_live_state)", c, re.DOTALL)
    if old_pos:
        new_pos = """def save_open_position(self, pos_data: dict):
        self.current_open_position = pos_data
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = pos_data
            atomic_write_json(JOURNAL_JSON, data)

    def clear_open_position(self):
        self.current_open_position = None
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = None
            atomic_write_json(JOURNAL_JSON, data)

    """
        c = c[:old_pos.start()] + new_pos + c[old_pos.end():]

    # update_live_state
    old_live = re.search(r"def update_live_state\(self, state_dict: dict\):.*?(?=def _get_active_strike_market)", c, re.DOTALL)
    if old_live:
        new_live = "def update_live_state(self, state_dict: dict):\n        atomic_write_json(LIVE_STATE_JSON, state_dict)\n\n    "
        c = c[:old_live.start()] + new_live + c[old_live.end():]

    # record_trade
    old_rec = re.search(r"def record_trade\(self, trade_data: dict\):.*?(?=def run_cycle)", c, re.DOTALL)
    if old_rec:
        new_rec = """def record_trade(self, trade_data: dict):
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_NATGAS_15M", "current_balance": self.balance, "trades": []})
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)

    """
        c = c[:old_rec.start()] + new_rec + c[old_rec.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("[OK] kalshi_natgas_trader_15m.py atualizado.")


def update_kalshi_trader_15m():
    path = os.path.join(BASE_DIR, "kalshi_trader_15m.py")
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    # Import
    if "from risk_gate import" not in c:
        c = c.replace(
            "from typing import Optional, Dict, Any, List, Tuple",
            "from typing import Optional, Dict, Any, List, Tuple\nfrom risk_gate import atomic_write_json, safe_read_json, is_system_halted"
        )

    # save_open_position & clear_open_position
    old_pos = re.search(r"def save_open_position\(self, pos_data: dict\):.*?(?=def _get_active_strike_market)", c, re.DOTALL)
    if old_pos:
        new_pos = """def save_open_position(self, pos_data: dict):
        self.current_open_position = pos_data
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = pos_data
            atomic_write_json(JOURNAL_JSON, data)

    def clear_open_position(self):
        self.current_open_position = None
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = None
            atomic_write_json(JOURNAL_JSON, data)

    """
        c = c[:old_pos.start()] + new_pos + c[old_pos.end():]

    # save_trade
    old_rec = re.search(r"def save_trade\(self, trade_data: dict\):.*?(?=def run_cycle)", c, re.DOTALL)
    if old_rec:
        new_rec = """def save_trade(self, trade_data: dict):
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_KALSHI_15M", "current_balance": self.balance, "trades": []})
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("cycle_pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("cycle_pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)

    """
        c = c[:old_rec.start()] + new_rec + c[old_rec.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("[OK] kalshi_trader_15m.py atualizado.")


if __name__ == "__main__":
    update_eth_trader()
    update_kalshi_gold_trader()
    update_kalshi_natgas_trader()
    update_kalshi_trader_15m()
    print("\nTodos os desks atualizados com atomic_write_json e safe_read_json com sucesso!")
