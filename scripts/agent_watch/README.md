# agent-watch — ver os subagentes ao vivo, sem largar o chat

O chat coordenador abre subagentes e so devolve o relatorio no fim. Esta ferramenta mostra,
num segundo terminal, o que cada subagente esta a fazer **enquanto faz**: cada ferramenta que
chama, cada resultado que recebe, cada erro.

Somente leitura. Nao escreve nada, nao fala com o harness, nao altera a sessao principal.

## Rodar

```bash
scripts/agent_watch/agent-watch.sh --grid                 # uma caixa por agente
scripts/agent_watch/agent-watch.sh --grid --only-active   # so quem escreve agora
scripts/agent_watch/agent-watch.sh                        # um feed unico, todos misturados
```

No Windows sem bash: `tools\agent-watch\agent-watch.cmd --grid`.

A pasta corrente decide qual projeto e vigiado; `--project <pedaco-do-nome>` escolhe outro.
Com o Windows Terminal, `Alt+Shift+D` divide o painel e a vista fica ao lado do chat.

### Grade

```
┌─ ade1f789 Relatorio e alerta na gram… ──┐┌─ a9469115 Ligar o semanal a gramatica ──┐
│ implementer  ativo  8 tools  1 err      ││ implementer  ativo  42 tools            │
│ ← 1064 exact = pull.share * 100 1065 s… ││ → Bash cd "…/intelligence-agent" && .v… │
│ → Read …/packages/daily_reporting/…     ││ ← ...................................   │
└─────────────────────────────────────────┘└─────────────────────────────────────────┘
 <projeto> · ativos 3 · caixas 12 · tools 390 · err 7 · ultima escrita 0.0s
```

| Estado | Significado |
| --- | --- |
| `ativo` | escreveu no transcript ha menos de 90 s |
| `parado` | mais de 90 s sem escrever e sem handback: comando longo, a espera de permissao, ou morto calado |
| `fim` | devolveu o relatorio (`SubagentHandback`) |

Opcoes uteis: `--thinking` (mostra o raciocinio), `--all` (todas as sessoes do projeto),
`--keep <s>` (quanto tempo um agente terminado fica na tela, 300 por omissao),
`--from-start` (relê o transcript desde o inicio), `--once --size 120x40` (imprime um
quadro e sai, para pipe e verificacao).

## Requisitos

`rich` para a grade; o feed unico corre so com a biblioteca padrao. O `.venv` do projeto
costuma nao ter `rich` — o launcher procura um interpretador que tenha, por esta ordem:
`$WATCH_PYTHON`, `python3`, `python`, `py`. Nada e instalado no `.venv`.

## De onde vem o dado

```
~/.claude/projects/<slug-do-projeto>/<session-id>/subagents/agent-<id>.jsonl
~/.claude/projects/<slug-do-projeto>/<session-id>/subagents/agent-<id>.meta.json
```

O harness escreve nesses ficheiros enquanto o subagente trabalha; o `.meta.json` traz
`agentType` e `description`. O `tasks/<agentId>.output` que o resultado da ferramenta anuncia
fica com zero bytes — medido em 19/09/2026, Claude Code 2.1.278 — e nao serve de fonte.

O formato e interno e pode mudar num update do Claude Code. Uma linha que o parser nao
reconhece vira uma previa crua em vez de rebentar: se a vista ficar cheia de linhas `?`,
o formato mudou e `subagent_feed.py` precisa de um ajuste.

## Ficheiros

| Ficheiro | Papel |
| --- | --- |
| `subagent_feed.py` | descoberta e parsing — fonte unica das duas vistas |
| `watch_grid.py` | grade, uma caixa por agente (precisa de `rich`) |
| `watch_stream.py` | feed unico, todos os agentes misturados |
| `agent-watch.sh` / `agent-watch.cmd` | launchers que escolhem vista e interpretador |
