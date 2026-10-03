# Antigravity Project Guidelines — Polymarket Quantitative Bot

## ⚡ Política de Economia de Tokens & Roteamento Inteligente (JEV SystemOne)

Para maximizar a duração dos limites de cota da API e economizar tokens do usuário:

1. **Roteamento de Subagentes por Complexidade**:
   - **Tarefas Simples & Pesquisa (Model: `flash` ou `flash_lite`)**:
     * Leitura e busca em arquivos de código, logs e journals.
     * Pesquisa na web, documentação e consultas de API.
     * Verificação de processos, status e portas.
     * Testes unitários rápidos e scripts de diagnóstico.
   - **Tarefas Críticas (Model: `pro`)**:
     * Auditorias formais de risco financeiro em código de execução real (Safe 1271, CLOB V2, Stop-Loss).
     * Refatorações arquiteturais profundas de múltiplos módulos.
     * Debates matemáticos e quantitativos de alta densidade.

2. **Integração com Jev (TypeSafe AI)**:
   - Para avaliar tarefas antes de executar, utilize a skill `typesafe` ou execute o script `router.py`.
   - O Jev responde em <300ms sem gerar texto livre, economizando tokens e classificando o nível de complexidade da tarefa.

3. **Comunicação Concisa (Modo Padrão)**:
   - Respostas do dia a dia enxutas e objetivas (2 a 6 linhas).
   - Respostas longas/exaustivas reservadas estritamente para pedidos explícitos de relatório ou auditoria.
