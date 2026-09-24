"""
Test Jev Screener for The 98¢ Trade candidates
"""
import os
import sys
import json
import time
from dotenv import load_dotenv

load_dotenv()

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

def audit_market_with_jev(candidate: dict) -> dict:
    market_text = f"""
QUESTION: {candidate['question']}
OUTCOME TARGET: {candidate['outcome']} (Priced at ${candidate['price']:.3f} | Market Probability: {candidate['price']*100:.1f}%)
CURRENT PLATFORM: {candidate['platform']}
ORACLE / RESOLUTION SOURCE: {candidate.get('resolution_source', 'UMA / Official')}
EXPIRATION: {candidate.get('end_date')} ({candidate.get('days_remaining')} days remaining)

OFFICIAL MARKET RULES & DESCRIPTION:
{candidate.get('description', '')}
"""
    questions = {
        "rule_clarity_and_ambiguity": Choice(
            instructions="Audit the official market rules and resolution criteria. Determine whether the contract terms are crystal-clear and unambiguous, or whether there is risk of disputes, subjective interpretation, or oracle edge-case failures.",
            criteria={
                "crystal_clear": "Crystal-Clear & Deterministic: The rules specify an exact, unambiguous metric, authoritative source (e.g. Binance 1m candle at specific time), and leave zero room for interpretive dispute or oracle contention.",
                "ambiguous_or_disputable": "Ambiguous or Disputable: The rules contain vague terms, conflicting timezones, unclear fallback sources, or historically contested resolution patterns on UMA.",
                "high_tail_risk": "High Tail-Risk: The event outcome has non-negligible tail risk of an unexpected black swan or sudden reversal before the expiration deadline."
            }
        ),
        "uma_dispute_likelihood": Noul(
            instructions="Estimate the calibrated probability (0.0 to 1.0) that this market will experience an oracle dispute, payout delay, or contested resolution."
        ),
        "safety_audit_score": Score(
            instructions="Provide an overall institutional safety score from 1.0 to 5.0 for buying this contract at 98 cents. A score of 4.2+ means the contract is institutional-grade with virtually zero rule risk.",
            criteria=[
                "1.0 - Unacceptable risk / Obvious dispute trap / Subjective criteria",
                "2.0 - Elevated ambiguity or fragile oracle source",
                "3.0 - Moderate risk, standard market but slight edge-case uncertainty",
                "4.0 - Strong, well-defined market with reliable deterministic source",
                "5.0 - Pristine, incontrovertible resolution criteria with zero room for dispute"
            ]
        )
    }

    t0 = time.time()
    resp = client.system_one(state=market_text, questions=questions)
    elapsed = time.time() - t0

    q1 = resp.answers["rule_clarity_and_ambiguity"]
    q2 = resp.answers["uma_dispute_likelihood"]
    q3 = resp.answers["safety_audit_score"]

    return {
        "candidate": candidate["question"],
        "outcome": candidate["outcome"],
        "price": candidate["price"],
        "elapsed_sec": round(elapsed, 2),
        "rule_clarity": q1.choice,
        "rule_clarity_confidence": round(q1.confidence, 3),
        "dispute_likelihood": round(q2.noul, 3),
        "safety_score": round(q3.score, 2),
        "safety_score_confidence": round(q3.confidence, 3),
        "is_approved": (q1.choice == "crystal_clear" and q2.noul <= 0.15 and q3.score >= 4.20)
    }

if __name__ == "__main__":
    test_cand = {
        "platform": "Polymarket",
        "question": "Will the price of Bitcoin be above $80,000 on September 25?",
        "outcome": "Yes",
        "price": 0.985,
        "end_date": "2026-09-25T16:00:00Z",
        "days_remaining": 0.1,
        "resolution_source": "Binance BTC/USDT 1m candle 12:00 ET",
        "description": "This market will resolve to 'Yes' if the Binance 1 minute candle for BTC/USDT 12:00 in the ET timezone (noon) on September 25, 2026 has a 'Final' price strictly greater than 80,000. Otherwise, this market will resolve to 'No'. The resolution source is Binance via TradingView or Binance API."
    }

    print(f"Auditing market with Jev SystemOne: {test_cand['question']}...")
    result = audit_market_with_jev(test_cand)
    print(json.dumps(result, indent=2))
