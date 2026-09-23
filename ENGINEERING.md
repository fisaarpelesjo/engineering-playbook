# Engineering Process

## Principios

- O repositorio e a fonte de verdade.
- Mudancas nao triviais exigem intencao, escopo e criterios verificaveis.
- Nenhuma tarefa termina sem evidencia real das verificacoes aplicaveis.
- Regras canonicas ficam em um unico lugar e adaptadores apenas referenciam.
- O processo e proporcional ao risco.
- Agentes nao ampliam escopo, publicam, apagam dados ou assumem permissoes.
- Produtos derivados nao dependem de LLM.
- Evidencia nunca e inventada.

## Sequencia Canonica

1. Classificar o perfil de workflow.
2. Ler ou criar o Project Requirements Document — PRD quando houver requisitos de produto.
3. Confirmar que lacunas, contradicoes e requisitos nao verificaveis estao marcados.
4. Criar ou atualizar specification do Spec Kit apenas para recortes aprovados.
5. Clarificar incertezas materiais.
6. Criar plano.
7. Quebrar em tarefas rastreaveis.
8. Implementar com TDD seletivo quando aplicavel.
9. Validar com comandos reais.
10. Revisar em modo somente leitura.
11. Convergir PRD, specs, plano, tarefas, codigo e evidencia.
12. Gerar checkpoint.

## Project Requirements Document — PRD

O PRD em `docs/requirements/project-requirements.md` e a fonte mestre de requisitos do produto. Ele deve ser preenchido pelo proprietario antes do Spec Kit quando a mudanca envolver produto, comportamento, usuarios, dominio, contratos, dados, operacao ou criterios de sucesso.

Agentes devem ler o PRD antes de executar `specify`, `plan`, `tasks` ou `implement`, preservar IDs estaveis, nao inventar informacoes ausentes e pedir decisao humana apenas para ambiguidades materiais. Specs do Spec Kit referenciam IDs do PRD e nao substituem a fonte mestre.

## Definition of Done

Uma entrega so e concluida quando requisitos e criterios foram satisfeitos, testes e verificacoes aplicaveis passaram, documentacao foi atualizada, limitacoes foram registradas, revisao e convergencia foram feitas, rastreabilidade com PRD foi preservada quando aplicavel, e `.project/state.yml` mais o checkpoint final estao validos.

## Test policy

A skipped test is not a passing test. Zero tolerance here means zero *undeclared* skips, not `skipped 0`: every `skipped` or `xfailed` case in a full run is one somebody accepted in a versioned inventory, with its reason, and not one the author waved through with `pytest.skip("...")`. A skip for an unavailable platform or an expired credential is honest behaviour of the test; it is green only once it is declared. A declaration expected to skip on this platform that stopped skipping is refused, and so is a skip whose reason no longer starts with the declared one, so the inventory cannot outlive what it excuses. `--deselect`, `-k`, `-m` and explicit paths narrow a run; a narrowed run is not the full run and is never the evidence for Definition of Done.

In the playbook's own repository this is a mechanism, not a sentence: the test suite reads the execution report (not the exit code, which is zero for a run full of skips), compares it with the declared inventory, and fails the session on any difference. That mechanism is not installed into derived projects; a derived project that ships its own suite should apply the same rule to it.

## Git

Use trunk based development com branches curtas. Nao faca commit, push, merge, tag ou release sem autorizacao explicita. Commits e titulos de PR seguem Conventional Commits em ingles.

Entregas Git devem passar por `scripts/delivery.py`: start, prepare, commit, publish, merge --auto e status. `prepare` executa validacoes locais, revisao somente leitura, convergence e checkpoint, mas nao faz commit nem operacao remota. `publish` e `merge --auto` exigem comando explicito e autorizacao remota.

## Erros que ja custaram uma volta

Cada linha desta tabela e medida: um agente cometeu o erro, o portao apanhou, e o conserto
custou uma volta inteira do ciclo. Nao e um repositorio de conselhos; e o ledger dos erros que
este repositorio especifico ja pagou. Comeca vazio -- este repo nao herda o ledger do derivado.

| # | erro medido | regra que ficou | data |
|---|---|---|---|
| 1 | Edicao aplicada por `str.replace` ou por `if <literal> in texto:` que nao casou. Tres vezes na mesma sessao: um alvo de mutacao que nao foi trocado e a mutacao escapou; uma correccao declarada como feita que nunca entrou no ficheiro; e uma sonda de verificacao que imprimiu `ESCAPED` por nao ter inserido nada. As tres vezes o sintoma foi silencio, nao erro. | Toda a edicao automatizada assere a propria edicao antes de medir o efeito: `assert <literal> in texto` antes do `replace`, e nunca `if ... in texto:` a proteger uma substituicao. E o que o `apply_mutation` ja faz com `occurrences == 0 -> inert`. | 2026-09-22 |
| 2 | Numero de validacao citado de memoria em vez de remedido depois da ultima alteracao. `pyright` foi reportado a 0 erros estando a 3, todos no ficheiro que a fatia tinha acabado de reescrever, e o `prepare` corre `pyright` e devolve o exit code -- a fatia nao era entregavel e o relatorio dizia que era. | Numero que entra em relatorio, spec, tarefa ou corpo de pull request e medido DEPOIS da ultima edicao dessa fatia, e o comando que o mediu e citado ao lado. Um numero so e verdadeiro da arvore de onde foi tirado. | 2026-09-22 |

| 3 | Arvore editada enquanto uma revisao independente estava aberta. O revisor tira um manifesto SHA-256 antes e depois de medir; nas voltas 1 a 4 deu `380/380 unchanged`, na volta 5 deu quatro ficheiros alterados a meio da medicao. O relatorio dizia `arvore congelada`, e as conclusoes do revisor passaram a descrever uma arvore que ja nao existia: os numeros entregues estavam errados por nove ficheiros e 280 linhas antes de serem lidos. | Uma unidade entregue a revisao nao e editada ate a revisao fechar. O relatorio cita o commit ou o manifesto que descreve, e trabalho paralelo vai para `git stash` ou para uma segunda worktree, nunca para a arvore partilhada. Corolario da linha 2: um numero so e verdadeiro da arvore de onde foi tirado, e a revisao tambem. | 2026-09-22 |

<!-- | 4 | erro medido, curto e factual | a regra operacional que ficou dele | AAAA-MM-DD | -->

### A regra da terceira ocorrencia

A mesma classe de erro que volta tres vezes muda de tratamento:

1. Primeira ocorrencia: conserta-se.
2. Segunda ocorrencia da mesma classe: conserta-se e registra-se a classe nesta tabela.
3. Terceira ocorrencia: a unidade nao continua ate existir prevencao automatizada -- um portao
   que apanhe a classe inteira, nao so o caso que a revelou.
