# -*- coding: utf-8 -*-
"""
CONSULTA INSTITUCIONAL AO JEV (TypeSafe SystemOne):
Auditoria do Repositório 'jarrodwatts/jev-trader' e Debate Intelectual sobre
o Funcionamento Prático, Arquitetura de 300ms na Monad/Kuru e Viabilidade Quantitativa.
"""

import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from typesafe_sdk import TypeSafeClient, Choice

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
====================================================================================================
DOSSIÊ TÉCNICO E FORENSE: AUDITORIA DO REPOSITÓRIO 'jarrodwatts/jev-trader'
Data: 2026-09-28 | Objeto: https://github.com/jarrodwatts/jev-trader
Autor: Jarrod Watts (@jarrodwatts)
Contexto: Implementação de um AI Market Maker autônomo na Monad Testnet operando na DEX Kuru (MON-USDC)
com decisões a cada bloco de 300 milissegundos utilizando o modelo Jev da TypeSafe AI.
====================================================================================================

1. ARQUITETURA TÉCNICA DO CÓDIGO (src/):
- Runtime: Bun (TypeScript nativo de alta performance).
- Orçamento de Latência (The 300ms Budget):
  * Read RPC Path: Consulta do livro L2 via 'eth_call' direto com seletor hand-crafted (0x46fdfbb1 getL2Book)
    bypasseando o SDK da Kuru para reduzir a leitura a ~18ms.
  * Write RPC Path: Transmissão da ordem via 'eth_sendRawTransaction' assíncrono (fire-and-forget), sem esperar confirmação.
  * Decision Engine: Modelo Jev via '@ai-sdk/typesafe-ai' e 'experimental_evaluate', operando com amostragem paralela
    (não-autoregressiva), retornando probabilidades determinísticas em 70ms a 150ms.
  * Hot Loop: Leitura (18ms) + Inferência Jev (80-120ms) + Assinatura/Envio (15ms) = ~120-180ms total (cabe confortavelmente no bloco de 300ms da Monad).
- Estrutura da Ordem:
  * Ordem post-only limite colocada a 1 tick dentro do spread ('quoteInsideTicks: 1'), substituindo a anterior via 'batchUpdate'
    (cancela ordem velha e coloca nova em uma única chamada atômica).
  * Lucro previsto: Captura do spread quando um taker bate na ordem passiva.
- Telemetria:
  * Servidor HTTP leve em Bun com Server-Sent Events (SSE) transmitindo métricas para frontend Next.js a 3.3Hz.

2. AS DECLARAÇÕES EXPLÍCITAS DO SPEC.MD E DO AUTOR:
- SPEC.md Linha 59: "One-line disclaimer: experimental demo, tiny bankroll, not financial advice, the model is not trying to be profitable."
- SPEC.md Linha 100: "Success criterion: A viewer with no context, watching a 20-second clip on a phone with the sound off, understands within three seconds that an AI is trading on a blockchain every fraction of a second, and can see what it costs. Then they share it."
- A proposta central é um SHOWCASE TECNOLÓGICO de velocidade: demonstrar que modelos System One (Jev) viabilizam trading on-chain sub-segundo, onde LLMs tradicionais (GPT/Claude) falham miseravelmente devido à latência de 2 a 3 segundos de geração sequencial de tokens.

3. CONSIDERAÇÕES DE MICROESTRUTURA E RISCO REAL (THE QUANT PERSPECTIVE):
- A Monad gera 3.3 blocos por segundo (~288.000 blocos/dia).
- Gas limit fixo de 350.000 gas por tx -> ~0.0357 MON por bloco -> ~428 MON por hora em taxas de rede.
- Adverse Selection (Seleção Adversa): Colocar ordens limite a cada 300ms sem cancelamento preditivo de toxic flow expõe o bot a ser "atropelado" por takers informados sempre que o preço se mover bruscamente contra a cotação.
- O repositório funciona perfeitamente como engine de demonstração e benchmark de infraestrutura, mas NÃO é um gerador de alfa lucrativo para capital real de longo prazo sem proteções de fluxo tóxico e regime.
====================================================================================================
"""

questions = {
    "technical_functionality_verdict": Choice(
        instructions="JEV, avalie a pergunta do usuário: 'Does this work?'. O código do repositório 'jarrodwatts/jev-trader' funciona tecnicamente conforme anunciado?",
        criteria={
            "WORKS_EXACTLY_AS_ANNOUNCED": "SIM, FUNCIONA EXATAMENTE COMO ANUNCIADO: O código é perfeitamente funcional, elegante e cumpre 100% da sua proposta técnica. Ele conecta na Monad, lê o livro L2 da Kuru em sub-20ms, invoca a API do Jev via Vercel AI SDK em ~100ms e submete transações 'batchUpdate' dentro da janela de 300ms do bloco da Monad.",
            "BROKEN_NON_FUNCTIONAL_CODE": "NÃO FUNCIONA: O código possui erros graves de compilação, dependências inexistentes ou seletores ABI incorretos que impedem a execução.",
            "THEORETICAL_MOCK_ONLY": "APENAS TEÓRICO / MOCK: O repositório só funciona em modo mock e não possui integração real com a blockchain Monad ou com a API Jev."
        }
    ),
    "financial_profitability_reality_check": Choice(
        instructions="JEV, o usuário pode usar esse robô para ganhar dinheiro no mercado real de forma lucrativa, ou trata-se de um showcase/demo de infraestrutura?",
        criteria={
            "TECH_DEMO_NOT_PROFITABLE_STRATEGY": "É UM SHOWCASE TÉCNICO DE VELOCIDADE, NÃO UM ROBÔ LUCRATIVO: O próprio autor declara no SPEC.md que o robô 'is not trying to be profitable'. Em HFT de 300ms, cotar continuamente a 1 tick da ponta sem filtro de toxic flow gera sangramento severo por seleção adversa e consumo brutal de gás (~428 MON/hora). Sua finalidade é provar a viabilidade da inferência sub-100ms do Jev na Monad, e não gerar lucro financeiro.",
            "HIGHLY_PROFITABLE_PRODUCTION_STRATEGY": "É UMA ESTRATÉGIA ALTAMENTE LUCRATIVA: O robô captura o spread em todos os blocos e acumula retorno consistente superando com folga o custo de gás e a seleção adversa.",
            "SCAM_HONEYPOT": "É UM GOLPE: O código foi desenhado para drenar a carteira do usuário de forma maliciosa."
        }
    ),
    "architectural_value_for_our_ecosystem": Choice(
        instructions="JEV, o que há de mais valioso nesse repositório que nós (Antigravity & AGY) devemos assimilar na nossa arquitetura de trading?",
        criteria={
            "BIFURCATED_RPC_AND_RAW_L2_ENCODING": "BIFURCAÇÃO DE RPC E LEITURA L2 DE ZERO-OVERHEAD: O padrão de separar a rota de leitura rápida ('READ_RPC_URL') da rota de envio 'fire-and-forget', somado ao seletor de chamada única (0x46fdfbb1 getL2Book) sem instanciar classes pesadas de SDK, é uma aula de engenharia de baixa latência aplicável em qualquer chain EVM.",
            "CONTINUOUS_POST_ONLY_QUOTING": "A ESTRATÉGIA DE COTAR EM TODOS OS BLOCOS: Devemos adotar o market making contínuo em 300ms sem filtros direcionais.",
            "NOTHING_RELEVANT": "NADA RELEVANTE: O repositório não adiciona nada ao que já temos."
        }
    ),
    "system_one_vs_llm_debate": Choice(
        instructions="JEV, o vídeo destaca que LLMs levam 3 segundos decodificando tokens enquanto o Jev responde em 70-150ms via amostragem paralela determinística. Essa comparação é matematicamente precisa?",
        criteria={
            "ACCURATE_SYSTEM_ONE_VS_SYSTEM_TWO_DISTINCTION": "PRECISÃO ABSOLUTA: A física da inferência LLM tradicional exige decodificação token a token auto-regressiva, o que impõe um piso de latência física (>1.5s). O Jev opera como 'System One' cognitivo: avalia matrizes de tensores em paralelo e colapsa diretamente no espaço de probabilidade das ações sem geração de texto, sendo a única arquitetura de IA capaz de operar no tempo de bloco de blockchains modernas (Monad 300ms, Solana 400ms).",
            "MARKETING_EXAGGERATION": "EXAGERO DE MARKETING: LLMs tradicionais podem ser acelerados com speculative decoding para bater 100ms em hardware doméstico.",
            "NO_DIFFERENCE": "NÃO HÁ DIFERENÇA RELEVANTE: 3 segundos ou 100ms têm o mesmo impacto prático no mercado financeiro."
        }
    )
}

print("=" * 80)
print(" [JEV SYSTEMONE] CONSULTANDO JEV: AUDITORIA DO 'jarrodwatts/jev-trader'...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> PARECER DO JEV RECEBIDO EM {elapsed:.2f}s <<<\n")

results = {}
for qname, ans in resp.answers.items():
    print(f"[{qname.upper()}]")
    print(f"Decisão: {ans.choice}")
    print(f"Confiança: {ans.confidence * 100:.1f}%")
    print("Probabilidades:")
    for opt, p in ans.probabilities.items():
        print(f"  * {opt}: {p:.1%}")
    print("-" * 60)
    results[qname] = {
        "choice": ans.choice,
        "confidence": ans.confidence,
        "probabilities": ans.probabilities
    }

output_payload = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "answers": results
}

output_file = "jev_jarrod_watts_audit_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Veredito do JEV gravado em '{output_file}'.")
