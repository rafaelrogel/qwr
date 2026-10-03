import os, json, time
from dotenv import load_dotenv
load_dotenv()
from typesafe_sdk import TypeSafeClient, Choice, Score

key = os.getenv('JEV_API_KEY') or os.getenv('TYPESAFE_API_KEY')
client = TypeSafeClient(api_key=key)

# Load the 2h report
report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'brain', 'c125241d-a48c-4ba7-aab4-bba800620ab2', '2h_performance_report.md'))
with open(report_path, 'r', encoding='utf-8') as f:
    report_text = f.read()

questions = {
    "report_analysis": Choice(
        instructions="Analise o relatório de performance de 2 horas e forneça insights, recomendações e possíveis alterações no código ou estratégia.",
        criteria={
            "no_action_needed": "Nenhuma ação necessária, tudo dentro dos parâmetros esperados.",
            "adjust_spread_gate": "Sugira refinamento no gate de spread ou parâmetros de retardo.",
            "new_desk_suggestion": "Sugira criação de novo desk ou ajuste de estratégia.",
        }
    )
}

print('='*80)
print('CONSULTANDO JEV SOBRE RELATÓRIO DE 2H')
print('='*80)

t0 = time.time()
res = client.system_one(state=report_text, questions=questions)
elapsed = time.time() - t0
print(f"[OK] JEV response in {elapsed:.2f}s")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "analysis": {
        "choice": res.answers['report_analysis'].choice,
        "confidence": res.answers['report_analysis'].confidence,
        "probs": res.answers['report_analysis'].probabilities,
    }
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jev_2h_report_verdict.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
