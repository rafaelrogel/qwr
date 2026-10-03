"""
===============================================================================
  ANTIGRAVITY x JEV (TypeSafe AI) — MODEL ROUTER & TOKEN OPTIMIZER
===============================================================================
Specialized classification engine (<50ms) to route tasks between Gemini Flash
and Gemini Pro, preserving API tokens and extending daily quotas.
===============================================================================
"""
import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Configura UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Carrega API Key
load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")

if not JEV_API_KEY:
    print("[ERRO] JEV_API_KEY / TYPESAFE_API_KEY nao encontrada no .env!")
    sys.exit(1)

os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

client = TypeSafeClient()


def evaluate_route(task: str) -> dict:
    """
    Avalia a tarefa com o JEV em ~50-300ms e determina o melhor modelo.
    """
    questions = {
        "tier": Choice(
            instructions="Determine which AI model tier is required to solve this task efficiently with minimum token cost.",
            criteria={
                "flash": "Use Gemini Flash / Flash-Lite: simple lookups, status checks, shell commands, reading single files, grep, logs, or simple questions.",
                "pro": "Use Gemini Pro: complex architectural decisions, mathematical proofs, deep multi-file refactors, debugging subtle algorithmic bugs, or high-stakes quantitative analysis."
            }
        ),
        "complexity": Score(
            instructions="Rate task complexity from 1 to 5.",
            criteria=[
                "1 - Trivial status check or file view",
                "2 - Simple shell command or single function edit",
                "3 - Medium multi-step workflow or script update",
                "4 - Complex debugging or multi-module refactor",
                "5 - Critical system architecture or advanced quantitative math"
            ]
        ),
        "safety_risk": Noul(
            instructions="Estimate probability (0.0 to 1.0) that this task involves destructive actions (e.g. deleting files, force pushing git, killing critical processes)."
        )
    }

    t0 = time.time()
    resp = client.system_one(state=f"TASK TO EXECUTE:\n{task}", questions=questions)
    latency_ms = (time.time() - t0) * 1000

    tier = resp.answers["tier"].choice
    complexity = resp.answers["complexity"].score
    risk = getattr(resp.answers["safety_risk"], "noul", 0.0)

    # Cálculo estimado de economia de tokens vs Pro
    token_savings_pct = 85.0 if tier == "flash" else 0.0

    return {
        "task": task,
        "recommended_model": "Gemini Flash" if tier == "flash" else "Gemini Pro",
        "subagent_model_param": "flash" if tier == "flash" else "pro",
        "tier": tier,
        "complexity_score": round(float(complexity), 2),
        "destructive_risk_pct": round(float(risk) * 100, 1),
        "latency_ms": round(latency_ms, 1),
        "token_savings_pct": token_savings_pct
    }


def print_route_card(res: dict):
    print("\n" + "=" * 70)
    print(f"  ⚡ JEV MODEL ROUTER — DECISAO EM {res['latency_ms']} ms")
    print("=" * 70)
    print(f"  Tarefa:       {res['task'][:80]}{'...' if len(res['task']) > 80 else ''}")
    
    color_tag = "🟢 [ECONOMICO]" if res['tier'] == 'flash' else "🟣 [ALTA CAPACIDADE]"
    print(f"  Modelo:       {res['recommended_model']} {color_tag}")
    print(f"  Subagent:     Model: '{res['subagent_model_param']}'")
    print(f"  Complexidade: {res['complexity_score']} / 5.0")
    print(f"  Risco Seguro: {res['destructive_risk_pct']}% probabilidade de acao destrutiva")
    
    if res['tier'] == 'flash':
        print(f"  Economia:     ~85% de tokens/cota economizados em relacao ao Pro!")
    else:
        print(f"  Economia:     0% (Exige raciocinio avancado do Pro)")
    print("=" * 70 + "\n")


def run_benchmark():
    test_cases = [
        "Verificar se a porta 8080 esta aberta e listar os processos python",
        "Ler o arquivo README.md e resumir em 3 topicos",
        "Reescrever o motor de execucao CLOB V2 com validacao de assinatura EIP-712 em Rust e calcular matriz hessiana de risco",
        "Checar o saldo de USDC na carteira da Polygon",
        "Auditar 2.300 linhas de codigo quantitativo buscando condicoes de corrida, deadlock e falhas de borda no Stop-Loss",
        "Adicionar um print de log no inicio do loop de monitoramento"
    ]

    print("\n" + "=" * 80)
    print("  INICIANDO BENCHMARK DO JEV MODEL ROUTER (Typesafe AI)")
    print("=" * 80)

    total_time = 0.0
    flash_count = 0
    pro_count = 0

    for i, tc in enumerate(test_cases, 1):
        res = evaluate_route(tc)
        total_time += res['latency_ms']
        if res['tier'] == 'flash':
            flash_count += 1
        else:
            pro_count += 1
        
        badge = "⚡ FLASH (Economico)" if res['tier'] == 'flash' else "🧠 PRO (Raciocinio)"
        print(f"[{i}/{len(test_cases)}] {res['latency_ms']:>5.1f}ms | {badge:<22} | Score: {res['complexity_score']:.1f}/5.0 | {tc[:50]}...")

    avg_time = total_time / len(test_cases)
    print("=" * 80)
    print(f"  Latencia Media: {avg_time:.1f}ms por decisao")
    print(f"  Distribuicao:  {flash_count} tarefas Flash (~85% economia) | {pro_count} tarefas Pro")
    savings = (flash_count / len(test_cases)) * 85.0
    print(f"  Economia Global de Tokens Projetada: ~{savings:.1f}%")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jev Model Router for Antigravity")
    parser.add_argument("task", nargs="?", default="", help="Descricao da tarefa a avaliar")
    parser.add_argument("--benchmark", action="store_true", help="Executa suite de testes de benchmark")
    args = parser.parse_args()

    if args.benchmark:
        run_benchmark()
    elif args.task:
        res = evaluate_route(args.task)
        print_route_card(res)
    else:
        print("\n=== JEV MODEL ROUTER INTERATIVO ===")
        print("Digite a tarefa (ou 'benchmark' para testar, 'sair' para encerrar):\n")
        while True:
            try:
                line = input("Tarefa > ").strip()
                if not line or line.lower() in ("sair", "exit", "quit"):
                    break
                if line.lower() == "benchmark":
                    run_benchmark()
                    continue
                res = evaluate_route(line)
                print_route_card(res)
            except (KeyboardInterrupt, EOFError):
                break
