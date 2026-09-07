# Specification: Engineering Playbook

## Requirements

- FR-001: O playbook deve registrar contexto canonico, processo e limitacoes.
- FR-002: O playbook deve fixar uma versao estavel do GitHub Spec Kit como nucleo SDD.
- FR-003: O playbook deve fornecer perfis lite, standard e strict com gates distintos.
- FR-004: O playbook deve fornecer adaptadores concisos para agentes suportados.
- FR-005: O playbook deve validar YAMLs operacionais por JSON Schema.
- FR-006: O playbook deve oferecer comandos verify, doctor, checkpoint, resume, reconcile, bootstrap e migrate.
- FR-007: Resume, doctor e reconcile padrao devem ser somente leitura.
- FR-008: Checkpoint deve gravar estado e arquivo de checkpoint de forma atomica.
- FR-009: O playbook deve detectar IDs duplicados e referencias quebradas.
- FR-010: O playbook deve detectar ownership concorrente sobre paths de workstreams.
- FR-011: O playbook deve fornecer perfis de stack para Python, C++, CUDA, Rust, Go, TypeScript, Java, C#, Kotlin, Swift, R, Julia e SQL.
- FR-012: O playbook deve adotar MADR, Conventional Commits, SemVer e Keep a Changelog.
- FR-013: Produtos derivados devem proibir LLM como dependencia de produto.
- FR-014: O playbook deve oferecer CI reproduzindo comandos documentados.
- FR-015: Migrações e bootstrap nao devem sobrescrever personalizacoes silenciosamente.
- FR-016: O playbook deve fornecer um Project Requirements Document — PRD como fonte mestre de requisitos antes do Spec Kit.
- FR-017: O bootstrap deve criar copia editavel do PRD em `docs/requirements/project-requirements.md` sem sobrescrever arquivo existente.
- FR-018: O verificador deve validar regras objetivas do PRD, incluindo secoes, metadados, IDs, criterios de aceitacao, placeholders em aprovados e aprovacao humana.
- FR-019: O playbook deve oferecer uma esteira segura de entrega Git com start, prepare, commit, publish, merge --auto e status.
- FR-020: Operacoes remotas da esteira devem exigir autorizacao explicita, nunca usar force push e nunca publicar diretamente em main.
- FR-021: A CI deve validar branch name, PR title, formatacao, lint, analise estatica, testes, schemas, policies, convergence, referencias e rastreabilidade.
- FR-022: O playbook deve documentar um GitHub Ruleset proposto para proteger main sem aplica-lo remotamente.

## Non-Functional Requirements

- NFR-001: Scripts devem falhar com mensagens acionaveis.
- NFR-002: Verificacoes somente leitura nao devem modificar fixtures.
- NFR-003: Dependencias Python devem ser separadas entre runtime e desenvolvimento.

## Acceptance Criteria

- AC-001: `uv sync --locked` instala dependencias em clone limpo.
- AC-002: `uv run pytest` passa.
- AC-003: `uv run python scripts/verify.py` valida estrutura, schemas, referencias e politicas.
- AC-004: `uv run python scripts/doctor.py` diagnostica sem modificar arquivos.
- AC-005: `uv run python scripts/checkpoint.py` persiste estado atomicamente.
- AC-006: `uv run python scripts/resume.py` reconstrói contexto sem escrita.
- AC-007: `uv run python scripts/reconcile.py` altera apenas com `--apply`.
- AC-008: Um novo agente retoma somente pelo repositorio.
- AC-009: Perfis lite, standard e strict possuem gates distintos.
- AC-010: Spec Kit e nucleo SDD sem duplicacao de comandos.
- AC-011: MADR, Conventional Commits, SemVer e Changelog sao adotados.
- AC-012: Writers concorrentes exigem branch, worktree e ownership exclusivos.
- AC-013: Reviewer tem modo, prioridades, findings e vereditos.
- AC-014: Titulos de PR seguem Conventional Commits.
- AC-015: Nenhum produto derivado depende de LLM.
- AC-016: Migracoes nao sobrescrevem personalizacoes silenciosamente.
- AC-017: O template de PRD contem as secoes obrigatorias, front matter, ficha atomica de requisito, EARS, NFRs e rastreabilidade.
- AC-018: `uv run python scripts/bootstrap.py` cria o PRD editavel quando ausente e nao altera quando presente.
- AC-019: Fixtures de PRD validas passam e fixtures invalidas falham pelos motivos esperados.
- AC-020: `scripts/delivery.py status` e read-only e nao consulta remoto.
- AC-021: `scripts/delivery.py prepare` exige branch diferente de main e gera artefatos de entrega sem commit ou remoto.
- AC-022: `scripts/delivery.py commit` exige prepare atual, arquivos staged, ownership, scan de secrets e Conventional Commit.
- AC-023: `scripts/delivery.py publish` recusa main, exige commit local e atualiza PR de forma idempotente.
- AC-024: `scripts/delivery.py merge --auto` exige PR, CI e autorizacao explicita para auto-merge squash.
