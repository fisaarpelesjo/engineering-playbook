# Delivery Pipeline

`scripts/delivery.py` automatiza uma esteira segura de entrega Git em etapas separadas:

`start -> prepare -> commit -> publish -> merge --auto -> status`.

Operacoes remotas exigem comando explicito e `--yes-remote`. O script nunca usa force push, nunca publica em `main`, nunca faz amend implicitamente, nunca cria tag ou release e nunca executa merge dentro de `publish`.

## Comandos

```bash
uv run python scripts/delivery.py start --type feat --number 019 --slug safe-delivery
uv run python scripts/delivery.py prepare --title "feat(delivery): add safe git delivery pipeline"
git add <files>
uv run python scripts/delivery.py commit
uv run python scripts/delivery.py publish --yes-remote --remote origin --base main
uv run python scripts/delivery.py status
uv run python scripts/delivery.py merge --auto --yes-remote
```

## Gates

- `start` valida nome da branch, recusa arvore suja sem `--allow-dirty`, e recusa partir de um HEAD que a base ainda nao contem -- depois de um squash merge o HEAD local carrega commits que `main` absorveu sob outra identidade, e uma branch criada ai nasce em conflito. Repita com `--from-base` para partir de `origin/main` mantendo as alteracoes por commitar, ou com `--allow-unmerged-head` apenas para empilhar deliberadamente sobre fatia ainda por integrar (issue #36).
- `prepare` exige branch diferente de `main`, executa verificacoes locais, revisao somente leitura, checkpoint e gera `.project/delivery/prepare.yml` mais `.project/delivery/pr.md`.
- `commit` exige prepare aprovado e atual, staged files, Conventional Commit, scan basico de secrets e ownership.
- `publish` exige commit local valido, branch diferente de `main`, checkpoint antes de remoto, push sem force e PR via GitHub CLI.
- `merge --auto` exige PR e CI configurada, exige veredicto assinado cobrindo o conteudo a integrar, habilita squash auto-merge e respeita branch protection.
- `status` e somente leitura e nao consulta remoto.

## Veredicto de conformidade

O veredicto nao e campo de `.project/state.yml`. Um registo escrito dentro da arvore altera a arvore
que ele descreve -- foi assim que `last_verified_commit` e depois `last_verified_tree` falharam
(issue #24, execucao 35535830710 e oito execucoes de push em `main`, 35525340039 a 35553187426).

O veredicto e uma attestation emitida por `.github/workflows/quality.yml` ao fim da bateria, assinada
pela identidade OIDC da propria execucao, com o digest do conteudo como sujeito. Nenhuma etapa da
entrega alcanca o material de assinatura. `merge` recusa conteudo sem veredicto, e qualquer terceiro
verifica o mesmo facto sem ler o ficheiro de estado:

```bash
uv run python scripts/attest.py verify
uv run python scripts/attest.py subject --out "$TMPDIR/content-verdict.txt"
```

`last_verified_commit` e `last_verified_tree` permanecem como cache de leitura: reportados quando
desactualizados, sem constituir portao.

**Ordem de operacao, mudada por esta fatia.** O veredicto e emitido no fim da execucao de push que
`publish` provoca. Portanto `merge --auto` ja nao pode ser encadeado imediatamente a seguir a
`publish`: enquanto essa execucao nao terminar, nao existe veredicto e o `merge` recusa, com o head
intacto e nada integrado. Repita o `merge` quando a execucao concluir. A recusa e o comportamento
pretendido, nao falha transitoria -- enfileirar auto-merge sobre conteudo que nenhuma execucao
assinou seria integrar por confianca no operador, que e o que esta fatia existe para eliminar.

Limites declarados: a attestation exige repositorio publico ou plano que a inclua, e o veredicto e
emitido apenas nessa condicao -- num repositorio privado o portao nao se aplica e e anunciado, nunca
silenciado; projecto derivado com `ci: none` nao possui identidade de execucao e mantem o mecanismo
anterior de commit e ancestralidade. A assinatura prova que uma execucao do workflow naquele caminho
assinou aquele conteudo, nao que passos esse workflow continha, e a verificacao corre no cliente. Os
vectores correspondentes estao enumerados em `specs/003-no-stage-without-a-mechanism/spec.md`.

## Recuperacao

Depois de falha de rede ou interrupcao, execute:

```bash
uv run python scripts/delivery.py status
uv run python scripts/resume.py
uv run python scripts/reconcile.py
```

Reexecute `publish` depois que a rede voltar. A etapa e idempotente: se o PR da branch ja existir, ele e atualizado em vez de recriado.

