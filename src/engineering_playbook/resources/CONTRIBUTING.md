# Contributing

Use branches curtas no formato `<type>/<spec-or-issue>-<short-kebab-description>`. Titulos de commit e PR seguem Conventional Commits em ingles, por exemplo `feat(playbook): add checkpoint command`.

Descricoes de PR devem conter resumo, problema, requisitos, mudancas, evidencia de validacao, benchmarks quando aplicavel, riscos e checklist de review. Liste apenas comandos realmente executados.

Mudancas que afetem requisitos de produto devem referenciar IDs do PRD. Requisitos aceitos nao devem ser renumerados nem alterados silenciosamente para coincidir com a implementacao. Registre impacto sobre specs, planos, tarefas, testes, benchmarks, ADRs, documentacao, releases, compatibilidade e migracao.

Fluxo recomendado de entrega:

```bash
uv run python scripts/delivery.py start --type feat --number 019 --slug safe-delivery
uv run python scripts/delivery.py prepare --title "feat(delivery): add safe git delivery pipeline"
git add <files>
uv run python scripts/delivery.py commit
uv run python scripts/delivery.py publish --yes-remote --remote origin --base main
uv run python scripts/delivery.py status
uv run python scripts/delivery.py merge --auto --yes-remote
```

Nao use push direto para `main`, force push, amend implicito ou merge sem passar pelos gates.

## Guarda local: nenhum commit nasce na `main`

Isto e um hook de git bruto (`scripts/git-hooks/pre-commit` e `scripts/git-hooks/pre-push`).
Nao existe mais um segundo mecanismo de hook: o framework `pre-commit` e o seu
`.pre-commit-config.yaml` foram removidos por decisao registada em `docs/decisions/`, porque o
framework recusa instalar-se enquanto `core.hooksPath` estiver definido
(https://github.com/pre-commit/pre-commit/issues/3630) -- os dois nao coexistem por desenho, e
o hook bruto ja cobre formatacao e lint via `scripts/local_ci.py` no `pre-push`.

`engineering-playbook init` e `update` configuram `core.hooksPath` automaticamente (T203). Para
activar manualmente num clone existente:

```bash
git config core.hooksPath scripts/git-hooks
```

`doctor` e `verify` falham quando `core.hooksPath` nao aponta para `scripts/git-hooks`, e
tambem falham se `.pre-commit-config.yaml` for reintroduzido enquanto os hooks brutos estiverem
activos (os dois mecanismos nao podem estar activos ao mesmo tempo). O hook de commit recusa um
commit cujo `HEAD` seja `main` ou `master`; nao impede push direto (isso e
`scripts/delivery.py publish` e o ruleset em `.github/rulesets/main.yml`) nem merge para `main`.
`git commit --no-verify` e trocar `core.hooksPath` continuam a saltar por cima dele -- essas
fraquezas estao documentadas no proprio ficheiro do hook.
