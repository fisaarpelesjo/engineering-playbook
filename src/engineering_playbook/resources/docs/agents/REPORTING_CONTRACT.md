# REPORTING_CONTRACT.md — como um relatorio ao proprietario e escrito

Vale para todo relatorio de um agente ou subagente ao proprietario, sobre uma feature, uma tarefa
ou um ciclo de trabalho.

## Abertura

`Feature {feature_id}: ~{percentual_ponderado}% concluida.`

Lidere pelo resultado. Depois venham evidencia, risco e arquivos.

## Secoes obrigatorias

1. Escopo autorizado
2. Tarefas, uma por uma
3. Arquivos criados e modificados
4. Interfaces publicas alteradas
5. Decisoes e divergencias
6. Testes e verificacoes, com totais reais
7. Preservacao de IDs estaveis (PRD, ADR, spec, tarefa)
8. Rastreabilidade com os requisitos do PRD, quando existirem
9. Dependencias entre tarefas, quando houver mais de uma em curso
10. Readiness e dependencias externas
11. Working tree e Git
12. Percentual
13. Proximo passo e autorizacao necessaria

Secao sem conteudo medido diz `NAO MEDIDO` e por que. Ela nao desaparece do relatorio.

## Os tres percentuais, que nao sao o mesmo numero

| Percentual | Como se deriva |
|---|---|
| `ledger` | tarefas executaveis concluidas / tarefas executaveis totais |
| `ponderado` | estimativa pelo peso arquitetural das fases; **identificada como estimativa** |
| `ponta a ponta` | capacidade real de receber uma entrada, executar o fluxo e entregar a saida com as dependencias que existem hoje |

Nunca apresente um deles como se fosse outro. O ponderado nunca substitui o do ledger.

## Guardas de palavra

- Nunca dizer "production ready" enquanto a readiness agregada nao for `READY`.
- Nunca chamar fixture de integracao real.
- Nunca chamar componente isolado de fluxo ponta a ponta.
- Nunca omitir que registros externos continuam abertos.
- Nunca dizer "tudo verde" havendo falha, skip, xfail, deselection ou portao nao executado.
- Nunca tratar volume grande de teste como prova de correcao sem dizer o que foi medido.

## Forma

pt-BR, direto, tecnico, sem bajulacao. Tabela so quando facilita comparacao objetiva.
Comando completo para colar quando o proprietario pedir o proximo passo. Nao repetir relatorio
inteiro sem necessidade. Nao esconder falha, skip, divergencia, limitacao ou decisao tomada.
