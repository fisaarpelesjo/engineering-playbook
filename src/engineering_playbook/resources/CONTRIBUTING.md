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

Isto e um hook de git bruto (`scripts/git-hooks/pre-commit`), diferente do framework `pre-commit`
configurado em `.pre-commit-config.yaml` (que roda ruff). Instale-o uma vez por clone:

```bash
git config core.hooksPath scripts/git-hooks
chmod +x scripts/git-hooks/pre-commit
```

`chmod +x` e necessario a parte porque o instalador do playbook (`engineering-playbook init` /
`update`) copia o conteudo do ficheiro mas nao define bit de execucao; sem ele, em Linux e
macOS o git ignora o hook silenciosamente. O hook recusa um commit cujo `HEAD` seja `main` ou
`master`; nao impede push direto (isso e `scripts/delivery.py publish` e o ruleset em
`.github/rulesets/main.yml`) nem merge para `main`. `git commit --no-verify` e trocar
`core.hooksPath` continuam a saltar por cima dele -- essas fraquezas estao documentadas no
proprio ficheiro do hook.
