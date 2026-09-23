---
document_id: PRD-001
title: "Project Requirements Document — PRD"
version: "0.2.0"
status: draft
owners: []
reviewers: []
approvers: []
created_at: ""
updated_at: "2026-09-22"
approval_date: ""
supersedes: null
related_specs: []
---

# Project Requirements Document — PRD

<!--
Modelo mestre de requisitos do produto antes do GitHub Spec Kit.
Use N/A - nao aplicavel, porque: <justificativa> quando uma secao nao se aplicar.
Nao remova secoes sem registrar por que elas nao se aplicam.
Nenhum agente pode marcar este documento como approved nem inventar aprovacao humana.
-->

## Instrucoes de uso

<!-- Explique como preencher, revisar e transformar recortes aprovados em specs do Spec Kit. -->

Este PRD e um modelo hibrido com elementos de Product Requirements Document, Software Requirements Specification, Engenharia de Requisitos e especificacao orientada a criterios verificaveis. Ele e a fonte mestre de requisitos do produto. O GitHub Spec Kit continua responsavel por transformar recortes aprovados em specification -> plan -> tasks -> implementation -> validation -> convergence.

Preencha o PRD antes de executar `specify`, `plan`, `tasks` ou `implement`. Use `TODO`, `ASSUMPTION` ou `QUESTION` para informacoes ausentes. Nao copie silenciosamente requisitos para specs; referencie os IDs canonicos deste documento.

Profundidade por perfil:

- Lite: problema, objetivo, escopo, nao objetivos, requisitos essenciais, criterios de aceitacao, riscos principais e questoes abertas.
- Standard: todas as secoes aplicaveis, requisitos atomicos, NFRs mensuraveis, rastreabilidade, riscos, estrategia de validacao e aprovacao humana antes da implementacao.
- Strict: Standard mais revisao formal, aprovadores registrados, seguranca, privacidade, matriz completa, evidencias, mudancas formais, requisitos legais e criterios de entrada e saida.

READ THIS BEFORE READING ANYTHING ELSE. This document is a PROPOSAL, filled in by an agent under issue #46, and it is `draft` on purpose. What is written here was derived from artifacts that already exist in this repository -- `ENGINEERING.md`, `AGENTS.md`, the four specs under `specs/`, the delivery pipeline in `src/engineering_playbook/`, the coverage matrix and the closed issues -- and every claim is traceable to one of them.

What is NOT written here is as deliberate. `docs/requirements/README.md` forbids an agent from inventing stakeholders, deadlines, metrics, rules, limits, legal requirements, architecture or approvals. Every one of those is left as `TODO` or `QUESTION` below, including several sections that are empty from top to bottom. An empty section here means "no human has decided this yet", never "this does not matter".

The owner accepts, corrects or discards. Only a human approval moves `status` to `approved` and fills `approvers` and `approval_date`.

A NOTE ON LANGUAGE. The section headings of this document are in Portuguese because `core.REQUIRED_PRD_SECTIONS` validates them literally, and changing them belongs to issue #65 together with the rest of the translation. The body is written in English, which is the decision recorded for this repository on 2026-09-22.

## Metadados e controle do documento

<!-- Mantenha o front matter atualizado. Estados permitidos: draft, in_review, approved, superseded. -->

Status atual: draft

`related_specs` is deliberately empty. Four specs exist and none of them references this document; linking them is not a formatting exercise, it is the traceability decision that issue #45 has to settle first -- see "Questoes abertas".

## Historico de alteracoes

<!-- Registre data, autor humano ou papel, mudanca, motivo e impacto. -->

| Data | Versao | Autor | Mudanca | Impacto |
|---|---|---|---|---|
| TODO | 0.1.0 | TODO | Criacao inicial | TODO |
| 2026-09-22 | 0.2.0 | Agent proposal, issue #46 | Derivable sections filled from existing repository artifacts; everything requiring a human decision left as TODO or QUESTION | None until a human reviews it. Status stays `draft`, no requirement is `accepted`, so nothing here yet constrains a spec |

## Aprovacoes

<!-- Aprovacoes exigem pessoa, papel, data e decisao. Agentes nao preenchem aprovacao inexistente. -->

| Pessoa | Papel | Data | Decisao | Observacoes |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | No approval exists. This row is a placeholder and an agent must not fill it |

## Resumo executivo

<!-- Resuma problema, publico, valor, escopo e criterios de sucesso em linguagem clara. -->

This repository is an engineering playbook: a canonical process (`ENGINEERING.md`), a set of agent adapters, and a delivery pipeline (`scripts/delivery.py`) that carries a unit of work from `start` to `merge` while refusing, at each stage, to proceed on evidence it has not measured.

The problem it addresses is that a process written down is not a process enforced. This repository's own history is the evidence: thirty-nine issues were normalised by hand on 2026-09-22 -- nineteen Portuguese bodies, two Portuguese titles, two issues with no label, two whose body claimed a parent the API did not report -- and every one of them had passed every gate that existed at the time.

The product's value proposition is therefore mechanism over discipline: for each stage of the process there is a control that fails closed, and for each control there is an entry in a mutation inventory proving that removing it turns a test red. At the time of writing that inventory holds 34 mechanisms across 9 of the 20 stages of the coverage matrix in `specs/003-no-stage-without-a-mechanism/spec.md`; the other 11 stages are declared uncovered rather than assumed covered.

Success criteria are deliberately NOT stated here. See "Metricas e criterios de sucesso" -- they require a decision this document must not invent.

## Problema ou oportunidade

<!-- Descreva o problema real, quem sofre, quando ocorre e por que importa agora. -->

A software process that exists only as prose degrades silently. The failure is not that people disagree with the rules; it is that nothing measures whether the rules were followed, so a deviation produces no signal at all until somebody happens to read the artifact.

The repository states this as a principle -- "Regras canonicas ficam em um unico lugar e adaptadores apenas referenciam", "Evidencia nunca e inventada" -- and then measures itself against it. Three failure shapes recur, all of them observed in this repository rather than hypothesised:

1. A rule that is followed by discipline and by nothing else. It holds until the day it does not, and the day it does not produces no red.
2. A control that reports success it did not measure. A gate that cannot reach the network and answers "pass" is worse than no gate.
3. A document that claims more than the artifact it describes sustains. Across the review rounds of the last two slices, every finding was of this shape, including twice in an agent's own delivery reports.

Who suffers: whoever operates a derived project and believes a green pipeline means what it says.

## Evidencias do problema

<!-- Traga fatos, dados, incidentes ou citacoes verificaveis. Nao invente evidencia. -->

All of the following were measured in this repository and are recorded in its issues, specs or ledger. None is illustrative.

- Thirty-nine issues normalised by hand on 2026-09-22: 19 Portuguese bodies, 2 Portuguese titles, 2 without any label, 2 whose body claimed `Sub-issue of #26` while the GitHub API reported no such parent, plus a Portuguese repository description. Every one had passed every existing gate. (Issue #65.)
- `publish` and `merge` wrote their own records after pushing and left the working tree dirty; `start` then refused the next slice. The way out was a hand-written commit or discarding what the pipeline had just produced. Both happened twice while delivering one slice. (Issue #64, closed 2026-09-22.)
- Two copies of the same Portuguese-detection word list had already diverged, 83 words against 58, with a known collision handled on one side only. (Issue #65.)
- A coverage matrix row can be closed by editing prose alone unless something measures it; this is why `test_coverage_matrix_is_measured.py` exists and why the mutation inventory is pinned in both directions. (Spec 003, AC-011.)
- `ENGINEERING.md` carries a ledger, "Erros que ja custaram uma volta", with three rows, each one an error this repository actually paid for: silent string substitutions that matched nothing, validation numbers quoted from memory instead of re-measured, and a tree edited while an independent review was open.

QUESTION: is there evidence from OUTSIDE this repository -- a derived project, another operator -- that the same problems occur there? Nothing in the repository records any, and an agent must not assume it.

## Visao do produto

<!-- Declare o estado futuro desejado, nao a solucao tecnica. -->

A project can adopt this playbook and get, from day one, a delivery process whose guarantees are mechanical rather than cultural: every stage that claims a control has one, every control fails closed when it cannot measure, and every limit that remains is written down where the operator will read it.

QUESTION, and it is the central one for this document. Issue #46 states it precisely and says the choice belongs to the owner and must not be inferred by any agent:

- Read as a tool whose product IS the pipeline, this repository has no unwritten product requirements. The empty sections below are adequacy, and the correct action is to mark them non-applicable with a justification.
- Read as a product with users -- the derived projects and whoever operates them -- there are real product requirements not yet written, and this document is in debt.

Everything below is written for the second reading, because it is the only one under which filling this document is useful at all. If the owner chooses the first, most of what follows should be replaced by `N/A - nao aplicavel, porque: <justificativa>`.

## Proposta de valor

<!-- Explique por que este produto e melhor que alternativas e status quo. -->

Against the status quo of a process document plus code review: the guarantees are checked by something that runs, so they survive fatigue, handover and time pressure.

Against a generic CI template: the controls are inventoried and adversarially tested. `scripts/mutation.py` removes each mechanism from a sandbox copy one at a time and requires that a named test, which was green before, fails without it. A control that nothing holds is reported as `escaped`, and a control that cannot be measured is reported as `unusable` rather than as a pass.

Against a stricter process: coverage is declared rather than implied. The matrix names 20 stages and states, per stage, whether the control lives on the server, in CI, is partial with its reach spelled out, or is absent.

TODO: this comparison is derived from what the repository does, not from any evaluation of alternatives with an operator. Whether these are the properties a potential adopter actually values is unverified.

## Objetivos

<!-- Objetivos devem ser observaveis e alinhados a metricas declaradas. -->

Derived from `ENGINEERING.md` "Principios" and from the acceptance criteria of the four existing specs.

- G-1. Every non-trivial change carries intent, scope and verifiable criteria before implementation begins.
- G-2. No stage of the canonical sequence claims a control that no mechanism enforces; where a stage is uncovered, the gap is declared.
- G-3. A control that cannot take its measurement refuses, and never reports a pass it did not observe.
- G-4. Evidence is never invented: numbers that enter a report, spec, task or pull request body are measured after the last edit of the unit they describe.
- G-5. A derived project inherits the process without depending on any LLM at runtime.
- G-6. An automated agent is subject to the same pipeline as a human, with no privileged path.

QUESTION: G-1 to G-6 are the goals the artifacts already pursue. Whether they are the goals the OWNER holds, in this order of priority, is a decision. No priority order is asserted here.

## Metricas e criterios de sucesso

<!-- Cada metrica precisa de definicao, unidade, baseline, alvo, janela e fonte. -->

TODO. `docs/requirements/README.md` forbids an agent from inventing metrics, and a target without a baseline, a window and a source is exactly the vague claim that NFR writing rules in this template reject.

What CAN be stated, because it is measured today and can serve as a baseline if the owner chooses to adopt any of it:

| Candidate measure | Value on 2026-09-22 | Source |
|---|---|---|
| Mechanisms in the mutation inventory, all held | 34 | `uv run python scripts/mutation.py` |
| Matrix stages reached by at least one mechanism | 9 of 20 | `specs/003-no-stage-without-a-mechanism/spec.md` |
| Matrix stages declared `parcial` or `ausente` | 11 of 20 | same |
| Automated tests passing | 773, 3 skipped | `uv run python -m pytest -q` |
| Tracked text files still carrying Portuguese | 113 of 254 read | `tests/unit/test_the_repository_speaks_one_language.py` |
| Ledger rows, errors that already cost a cycle | 3 | `ENGINEERING.md` |

QUESTION: which of these, if any, is a SUCCESS metric rather than a status counter? A count of mechanisms rises by adding mechanisms, which is not the same as the process being better. No target is proposed here for that reason.

## Nao objetivos

<!-- Declare o que o produto nao pretende resolver, para evitar expectativa falsa. -->

Derived from statements the repository already makes about itself.

- Not a CI service, a hosting platform or a replacement for GitHub Actions; it configures and depends on them.
- Not a runtime dependency on any LLM. "Produtos derivados nao dependem de LLM" is a principle in `ENGINEERING.md`; the agent adapters are an authoring convenience, not part of what a derived project runs.
- Not a guarantee of correctness of the code a derived project writes. Every control here is about process and evidence, never about whether the product is right.
- Not a security product. Controls that touch secrets exist (`scan_for_secrets`, the ruleset, the signed verdict), and they are narrow; see "Seguranca".
- Not a general-purpose project generator today. `--stack` accepts any string while `init` always writes a Python `pyproject.toml` and CI hardwired to Python; that gap is issue #66 with sub-issues #67 to #70, and until it closes, multi-stack support is a non-goal in fact whatever the flag suggests.

## Itens fora de escopo

<!-- Liste itens fora de escopo com motivo. -->

| Item | Motivo |
|---|---|
| Non-Python stacks | `init` writes a Python `pyproject.toml` and the CI workflow is Python-specific; nothing reads `profiles/stacks/*.yml`. Tracked as #66 |
| Clean tree after `merge` | The post-merge record is not knowable before the merge and cannot reach `main`, which `protect-main` guards with a pull request requirement and no bypass actors. Declared partial in matrix stage 9 |
| Required-status-check enforcement of the signed verdict | Verification happens in the client, not as a required check on the server. Declared partial in matrix stage 17 |
| Pre-push battery on unconfigured workstations | Reach is limited to a station with `core.hooksPath` configured. Declared partial in matrix stage 14 |
| Legal or regulatory conformance | No verification has been done; see "Conformidade legal e regulatoria" |

## Stakeholders

<!-- Liste stakeholders, interesse, influencia, expectativa e canal de decisao. -->

TODO. No stakeholder is recorded anywhere in this repository, and `docs/requirements/README.md` forbids inventing them.

What is observable, and is not the same thing as a stakeholder analysis: the repository has a single git author, the pull requests are opened and merged by one account, and no CODEOWNERS file exists. Whether that person is the sole stakeholder, the owner acting for others, or one of several, is unknown.

QUESTION: who, besides the repository owner, has an interest in this product, what is their expectation, and through which channel is a decision taken?

## Usuarios e personas

<!-- Personas devem vir de evidencia, entrevista ou decisao humana. -->

TODO. No interview, survey or usage evidence exists in the repository.

Two user shapes are IMPLIED by artifacts that exist, and are recorded here as candidates to be confirmed or discarded, not as personas:

- ASSUMPTION: an operator of a derived project, who runs `bootstrap.py` and then the delivery pipeline. Implied by `templates/project/`, `src/engineering_playbook/resources/` and the installer tests.
- ASSUMPTION: an automated agent working inside the repository under the adapters in `.claude/` and `docs/agents/`. Implied by `AGENTS.md` and by the `PreToolUse` hook that refuses a raw `git` invocation and points at the pipeline.

Neither has a validated goal, context of use or frequency. QUESTION: are both real, and is either the primary user?

## Necessidades dos stakeholders

<!-- Rastreie necessidade -> requisito. Necessidades nao sao ainda solucoes tecnicas. -->

| ID | Stakeholder | Necessidade | Evidencia | Requisitos relacionados |
|---|---|---|---|---|
| NEED-001 | TODO, see "Stakeholders" | Know whether a green pipeline means the controls actually ran | Matrix stages declared `parcial` and `ausente`; the mutation inventory exists to answer exactly this | FR-002, NFR-001 |
| NEED-002 | TODO | Not have a process deviation discovered by a human reading an artifact weeks later | 39 issues normalised by hand, all of which had passed every gate | FR-001, FR-003 |
| NEED-003 | TODO | Adopt the process in a project without adopting an LLM dependency | `ENGINEERING.md` principle, `bootstrap.py`, the shipped `resources/` mirror | FR-004 |

QUESTION: these needs are inferred from artifacts, not elicited from a person. Each row's stakeholder is unknown, which is why the column is `TODO` rather than guessed.

## Responsabilidades e ownership

<!-- Declare responsaveis por requisito, decisao, operacao e aprovacao. -->

TODO. No RACI, no CODEOWNERS file and no recorded delegation exist.

What the pipeline already enforces, which is about authority rather than ownership: remote operations, commits, merges, tags and releases require explicit human authorisation; `merge` requires `--auto` and an explicit remote authorisation flag; no agent may move this document to `approved`.

QUESTION: who owns a requirement once accepted, who owns operation of a derived project, and who approves a change to this document?

## Contexto e situacao atual

<!-- Descreva o estado atual, limitacoes conhecidas e impacto no negocio. -->

The repository contains, today:

- A canonical process in `ENGINEERING.md` and an entry point in `AGENTS.md`, with thin adapters (`CLAUDE.md`, `.claude/agents/`, `docs/agents/`) that reference rather than restate.
- A delivery pipeline, `scripts/delivery.py`, with the stages `start`, `prepare`, `commit`, `publish`, `merge --auto` and `status`, plus a `PreToolUse` hook that refuses raw `git` invocations which would bypass it.
- A verification entry point, `scripts/verify.py`, and a doctor, `scripts/doctor.py`.
- An adversarial harness, `scripts/mutation.py`, holding 39 mechanisms, each with the test that fails without it.
- Four specifications under `specs/`, of which `003-no-stage-without-a-mechanism` carries the 20-stage coverage matrix.
- A bootstrap path that installs a mirrored copy of the process into a derived project, with a parity test that refuses drift between the root and `src/engineering_playbook/resources/`.

Known limitations, all declared rather than discovered: matrix stages 9, 14, 17, 18 and 20 are `parcial` with their reach spelled out; the PRD-to-spec link is ambiguous until #45 settles identifier namespaces; `--stack` is not honoured (#66); `merge` still leaves a dirty tree (#64, declared).

Impact on the business: TODO, no business context is recorded.

## Sistemas e processos relacionados

<!-- Mapeie sistemas, integracoes, donos e restricoes externas. -->

| System | Role | Owner | External constraint |
|---|---|---|---|
| GitHub (repository, issues, pull requests, sub-issues API) | Source of the contract a delivery must satisfy: an open issue, a label, a parent link | External | Rate limits and availability; a network failure makes the gate refuse, by NFR-002 |
| GitHub Actions | Runs `quality`, `delivery-policy`, `adversarial` and `attest` | External | Attestations require a public repository or a plan that includes them |
| GitHub rulesets (`protect-main`) | Requires a pull request, forbids non-fast-forward and deletion, requires status checks | External | `bypass_actors` is empty, so no direct push to `main` exists for anyone |
| `gh` CLI | The only client used to reach the GitHub API from the pipeline | External | Must be installed and authenticated; absence is a refusal, not a pass |
| `uv` | Environment and command runner for every documented command | External | Every documented invocation is `uv run ...` |
| GitHub Spec Kit | Transforms approved slices into specification, plan, tasks | External | This document is upstream of it |
| `ruff`, `pyright`, `pytest` | Format, lint, types, tests | External | Pinned through the project configuration |

## Escopo e fronteiras do produto

<!-- Delimite dentro e fora do escopo, com criterio objetivo. -->

Inside the boundary: the canonical process, the agent adapters, the delivery pipeline, the verification and mutation harnesses, the specifications, the bootstrap and the shipped mirror installed into a derived project.

Outside the boundary: the derived project's own product code, its tests beyond the process scaffolding, its infrastructure, and any judgement about whether its product is correct.

The objective criterion for the boundary: if removing a thing would stop this repository from being able to state and enforce how work is delivered, it is inside; if it concerns what is being built rather than how the building is governed, it is outside.

## Diagrama de contexto

<!-- Use um diagrama textual claro, com atores, fluxos e limites. -->

```
                 +-------------------+
   operator ---> |  engineering-     | ---> derived project tree
   or agent      |  playbook         |      (process installed by bootstrap)
                 |                   |
                 |  ENGINEERING.md   |
                 |  delivery.py      |
                 |  verify.py        |
                 |  mutation.py      |
                 +---------+---------+
                           |
              reads/writes |  gh CLI
                           v
                 +-------------------+
                 |  GitHub           |
                 |  issues, PRs,     |
                 |  Actions, ruleset,|
                 |  attestations     |
                 +-------------------+

boundary: everything inside the left box is this product.
GitHub is external and is the authority on the contract and on integration.
```

## Glossario e linguagem do dominio

<!-- Defina termos do dominio, sinonimos proibidos e ambiguidades resolvidas. -->

| Term | Definition | Notes |
|---|---|---|
| Fatia (slice) | One unit of delivered work, from `start` to `merge`, closing exactly one issue | The Portuguese word is used throughout the specs; pending translation under #65 |
| Mechanism | A control that fails closed and is held by a named test which fails when the control is removed | A rule with no mechanism is not a mechanism |
| Mutation inventory | The list in `src/engineering_playbook/mutation.py`, pinned in both directions, of every mechanism and the test that holds it | Both directions: an addition and a removal both fail |
| Verdict (`caught`, `escaped`, `inert`, `unusable`) | The four outcomes of removing one mechanism in a sandbox | `inert` means the removal did not change the file; `unusable` means the baseline was not green |
| Coverage matrix | The 20-stage table in `specs/003-.../spec.md` recording where each stage's control lives | Values: `servidor`, `CI`, `parcial`, `ausente` |
| Declared limit | A weakness stated in the artifact rather than left to be discovered | Required by NFR-005 |
| Fail closed | A control that refuses when it cannot take its measurement | Required by NFR-002 |
| Checkpoint | A record, under `.project/checkpoints/`, of what happened at a point in time | Never rewritten; records are not edited to suit a later state |
| Signed verdict | An attestation produced by the CI workflow identity covering a tree, checked before integration | No step in the pipeline can forge it |
| Bookkeeping | Records the pipeline writes about itself: state and checkpoints | Distinct from the work; committed separately |
| Regra da terceira ocorrencia | On the third occurrence of an error class, automated prevention for the whole class is required, not a fix for the instance | `ENGINEERING.md` |

Forbidden synonyms: "check" and "gate" are not synonyms for "mechanism" unless a test holds them; "verified" is not a synonym for "ran without error".

## Premissas

<!-- Premissas devem ser explicitas, com impacto se forem falsas. -->

| ID | Assumption | Impact if false |
|---|---|---|
| ASSUMPTION-1 | The repository is hosted on GitHub and will remain so | Most of the matrix moves from `servidor`/`CI` to `ausente`; the ruleset, attestation and sub-issue controls have no equivalent |
| ASSUMPTION-2 | Operators run the documented commands through `uv` | Version drift between environments reappears; the pinned tool versions stop being the ones that ran |
| ASSUMPTION-3 | A derived project wants the process enforced rather than advisory | The pre-push hook and the pipeline hook become friction to disable, and the controls go with them |
| ASSUMPTION-4 | The working station is Windows or POSIX with git available | Line-ending handling and hook installation are already known to differ; three tests skip on Windows for the execute bit |

QUESTION: none of these has been confirmed with an operator. They are the assumptions the artifacts already embody.

## Dependencias

<!-- Inclua dependencias tecnicas, organizacionais, contratuais e externas. -->

Runtime, measured from `pyproject.toml` on 2026-09-22:

- `PyYAML>=6.0.2`
- `jsonschema>=4.23.0`
- optional `watch`: `rich>=13.7.0`
- `requires-python = ">=3.11"`

Development and verification: `ruff`, `pyright`, `pytest`, `uv`.

External services: GitHub, `gh` CLI, GitHub Actions, GitHub attestations.

Organisational and contractual dependencies: TODO. None is recorded.

## Restricoes

<!-- CONSTRAINT indica limite obrigatorio. Restricoes tecnicas precisam justificativa. -->

```yaml
id: CON-001
title: "No direct push to the default branch"
type: CON
statement: "O sistema deve integrar mudancas em main exclusivamente por pull request."
rationale: "The ruleset protect-main requires a pull request, forbids non-fast-forward and deletion, and has an empty bypass_actors list, so no identity can push directly. Any design that needs to write to main after a merge is impossible rather than merely discouraged."
source: "gh api repos/:owner/:repo/rulesets/23734100, measured 2026-09-22"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-001
    statement: "Dado o ruleset ativo, quando um push direto para main e tentado, entao o servidor recusa."
    verification_method: inspection
verification_method: inspection
dependencies: []
conflicts: []
related_items: []
owner: "TODO"
risk: "A change of hosting removes this control entirely"
```

```yaml
id: CON-002
title: "Attestations require a public repository"
type: CON
statement: "O sistema deve tratar a ausencia de atestacao como limite declarado quando o repositorio for privado."
rationale: "Attestations are not minted for a private repository without a plan that includes them, so the signed-verdict gate cannot apply there. The limit is declared and those projects keep the commit and ancestry mechanism in core.verify_root instead."
source: "src/engineering_playbook/delivery.py, signed_verdict_refusal docstring; FR-020"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-002
    statement: "Dado um repositorio privado, quando merge corre, entao a excecao e anunciada e nao silenciosa."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items: []
owner: "TODO"
risk: "A silent exemption would make the gate look present where it cannot exist"
```

```yaml
id: CON-003
title: "A record that names a commit cannot live inside that commit"
type: CON
statement: "O sistema nao deve versionar artefato cujo conteudo identifique o proprio commit que o contem."
rationale: "The local CI receipt names the head it verified. Committing it means the next push regenerates it against the commit that carries it, so the tree can never be clean. Measured on the first real publish through the fixed code path, and closed by making the receipt ignored."
source: "Issue #64; src/engineering_playbook/delivery.py, BOOKKEEPING_PATHS"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-003
    statement: "Dado um artefato que nomeia a propria cabeca, quando publish corre, entao esse artefato nao esta entre os caminhos commitados."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items: []
owner: "TODO"
risk: "Reintroducing it blocks every subsequent start"
```

## Jornadas dos usuarios

<!-- Descreva jornadas ponta a ponta, nao apenas telas ou endpoints. -->

Journey A, adopting the process in a new project. The operator runs `uv run python scripts/bootstrap.py`, which installs the process files and a mirrored copy of the canonical documents. They then have the canonical sequence, the pipeline and the verification entry points without writing any of them.

Journey B, delivering one slice. An open issue exists and carries a label and, where applicable, a parent. The operator or agent runs `start`, does the work, runs `prepare` (which runs the local battery, a read-only review and a checkpoint but touches nothing remote), `commit`, `publish` (which pushes, opens or updates the pull request, then records what it did), waits for CI, and `merge --auto`. At each stage a control refuses rather than assumes.

Journey C, discovering that a control is missing. Somebody notices a stage of the matrix with no mechanism, or a mutation entry reports `escaped`. The gap becomes an issue, then a slice, and the matrix row changes only when a mechanism exists to change it -- editing the prose alone is refused by `test_coverage_matrix_is_measured.py`.

TODO: these journeys are reconstructed from the code and the issue history. No journey has been observed with a real operator, and none has a recorded frequency, duration or pain point.

## Casos de uso e cenarios

<!-- Inclua ator, objetivo, pre-condicoes, fluxo e resultado observavel. -->

UC-1. Deliver a change under the pipeline.
Actor: operator or automated agent. Goal: integrate a change into `main` with evidence.
Preconditions: an open issue that satisfies the contract; a clean working tree; the process installed.
Flow: `start` -> work -> `prepare` -> `commit` -> `publish` -> CI -> `merge --auto`.
Observable result: a squash commit on `main`, the issue closed, the state recording the verified commit and tree, and a checkpoint written.

UC-2. Refuse a delivery that does not satisfy the contract.
Actor: the pipeline. Goal: refuse rather than integrate unmeasured content.
Preconditions: any stage's precondition unmet -- no declared issue, issue closed, branch name invalid, prepare stale, no signed verdict covering the tree.
Observable result: a non-zero exit and a message naming the cause and the corrective action. Nothing remote happens.

UC-3. Prove that a control is real.
Actor: the mutation harness. Goal: show that each inventoried mechanism is held.
Flow: for each entry, copy the tree to a sandbox, require the named tests green, remove the mechanism, require at least one of them to fail.
Observable result: `caught`, or a verdict naming why not.

## Fluxos principais

<!-- Liste o caminho nominal com passos observaveis. -->

1. `start --type <t> --number <nnn> --slug <s>` creates the branch from the resolved base, refuses a dirty tree unless `--allow-dirty` is given, and records `issue: <nnn>` and the branch in `.project/state.yml` (issue #73), which leaves that file modified until `commit` folds it in.
2. Work happens. Specs, tasks and code change together.
3. `prepare` refuses a state whose `issue` is not the number the branch was started for, then runs format, lint, types, tests and `verify.py`, performs a read-only review and writes a checkpoint. It commits nothing and touches nothing remote.
4. `commit` refuses staged secrets and paths outside the active ownership, creates the content commit, records the verified commit and tree, and folds that record into a second commit so the tree is clean.
5. `publish` verifies the declared issue is open, pushes, opens or updates the pull request, records the delivery, commits that record and pushes it.
6. CI runs `quality`, `delivery-policy` and `adversarial`, then `attest` mints the signed verdict.
7. `merge --auto` refuses content no run has signed, squash-merges, and records the squash commit and tree.

## Fluxos alternativos

<!-- Cubra variacoes legitimas sem tratar erro como caminho principal. -->

- Stacked slice: `start --allow-unmerged-head` begins from a head the base does not contain, deliberately.
- Branch from base: `start --from-base` ignores the current head.
- Carrying bookkeeping forward: `start --allow-dirty` proceeds on a dirty tree, which is how the residue that `merge` still leaves is carried across.
- Re-publishing: `publish` on an existing pull request edits it rather than creating a second one.
- A derived project with no workflow, or `ci: none`: the signed-verdict gate does not apply and says so, keeping the commit and ancestry mechanism instead.

## Fluxos de erro e recuperacao

<!-- Declare falhas esperadas, resposta do sistema e recuperacao. -->

| Failure | System response | Recovery |
|---|---|---|
| `gh` cannot answer | Refuse, naming that nothing was measured (NFR-002) | Restore connectivity and re-run the same stage |
| Declared issue closed or missing | Refuse before any remote operation | Declare an existing, open issue |
| Prepare stale because HEAD moved | Refuse; when the only movement was the pipeline's own records, say so explicitly (FR-002) | Re-run `prepare`, or nothing at all when the message says it self-invalidated |
| No signed verdict covers the tree | Refuse to merge | Wait for the run that mints it; do not merge ahead of it |
| Staged secrets | Refuse to commit | Remove the secret; the scan also covers the pipeline's own records |
| Second push fails after the bookkeeping commit | Return the push failure with the prepare already following the new head | Re-run `publish`; this is why the prepare is updated before the push |
| Mutation baseline not green | Report `unusable` rather than a pass | Fix the baseline; a mutant that cannot run measures nothing |

## Regras de negocio

<!-- Regras de negocio devem vir de fonte humana, legal, operacional ou decisao aprovada. -->

```yaml
id: BR-001
title: "No stage without a mechanism"
type: BR
statement: "O sistema deve recusar declarar uma etapa coberta sem um mecanismo que falhe fechado e um teste que falhe sem ele."
rationale: "A rule held by discipline alone produces no signal the day it is not followed. This is the organising rule of spec 003 and the reason the mutation inventory exists."
source: "ENGINEERING.md; specs/003-no-stage-without-a-mechanism/spec.md"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-004
    statement: "Dado uma linha da matriz declarada coberta, quando o mecanismo dela e removido, entao um teste nomeado falha."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items: []
legal_or_policy_reference: "N/A - nao aplicavel, porque: regra interna de processo, sem base legal"
evidence: "uv run python scripts/mutation.py, 34 of 34 held on 2026-09-22"
```

```yaml
id: BR-002
title: "Evidence is never invented"
type: BR
statement: "O sistema deve exigir que numeros em relatorio, spec, tarefa ou corpo de pull request sejam medidos depois da ultima edicao da unidade que descrevem."
rationale: "Ledger row 2 records the cost: pyright reported at 0 while at 3, on the file the slice had just rewritten, so the delivery was not deliverable and the report said it was."
source: "ENGINEERING.md, ledger row 2"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-005
    statement: "Dado um numero publicado sobre a arvore, quando a arvore muda, entao o numero e remedido antes de ser reportado."
    verification_method: inspection
verification_method: inspection
dependencies: []
conflicts: []
related_items: []
legal_or_policy_reference: "N/A - nao aplicavel, porque: regra interna de processo, sem base legal"
evidence: "ENGINEERING.md ledger; test_the_numbers_in_this_file_are_the_numbers_it_measures"
```

```yaml
id: BR-003
title: "Third occurrence earns automated prevention"
type: BR
statement: "Quando uma classe de erro ocorrer pela terceira vez, o sistema deve exigir prevencao automatizada para a classe inteira e nao correcao do caso."
rationale: "Two occurrences can be accident; the third is a property of the process. Recorded in ENGINEERING.md and already applied at least once, when the anti-stale-number test was written."
source: "ENGINEERING.md, regra da terceira ocorrencia"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-006
    statement: "Dado a terceira ocorrencia de uma classe, quando a unidade e entregue, entao existe mecanismo que cobre a classe."
    verification_method: inspection
verification_method: inspection
dependencies: []
conflicts: []
related_items: []
legal_or_policy_reference: "N/A - nao aplicavel, porque: regra interna de processo, sem base legal"
evidence: "ENGINEERING.md ledger rows 1 to 3"
```

## Requisitos funcionais

<!-- Cada requisito contem uma obrigacao principal, clara, viavel, verificavel e rastreavel. -->

Padroes de redacao equivalentes ao EARS:

- O sistema deve <comportamento observavel>.
- Quando <evento>, o sistema deve <resposta>.
- Enquanto <estado>, o sistema deve <comportamento>.
- Se <condicao indesejada>, o sistema deve <resposta>.
- Onde <recurso estiver habilitado>, o sistema deve <comportamento>.

IDENTIFIER WARNING. `specs/003-no-stage-without-a-mechanism/` already uses `FR-001` and upward for ITS OWN requirements, with different meanings. The identifiers below are PRD identifiers and they collide by shape. Issue #45 owns that namespace decision, and until it lands no spec should cite a bare `FR-nnn` as if it were unambiguous. Every block here is `proposed` for that reason among others.

```yaml
id: FR-001
title: "A delivery satisfies the issue contract before anything remote happens"
type: FR
statement: "Quando publish e invocado, o sistema deve verificar que a issue declarada existe e esta aberta antes de qualquer operacao remota."
rationale: "39 issues reached a delivered state by hand with defects no gate looked at. The contract is what makes a pull request traceable to intent."
source: "Issue #65; src/engineering_playbook/delivery.py, command_publish"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-007
    statement: "Dado que a issue declarada esta fechada, quando publish corre, entao nada e empurrado e o comando recusa."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items:
  - NEED-002
owner: "TODO"
risk: "TODO"
target_release: "TODO"
stability: "draft"
```

```yaml
id: FR-002
title: "The pipeline leaves no tree behind it"
type: FR
statement: "Quando um estagio escreve os proprios registos, o sistema deve devolver a arvore de trabalho limpa ou declarar por que nao consegue."
rationale: "start refuses a dirty tree, correctly, so a stage that dirties it blocks the next slice. Measured three times in one delivery."
source: "Issue #64"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-008
    statement: "Dado uma arvore limpa, quando publish termina, entao git status --porcelain nao devolve nada."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items:
  - NEED-001
owner: "TODO"
risk: "merge remains declared partial"
target_release: "TODO"
stability: "draft"
```

```yaml
id: FR-003
title: "Coverage is declared, never implied"
type: FR
statement: "O sistema deve declarar, por etapa do processo, onde o controlo vive e qual o alcance dele."
rationale: "A matrix row can be closed by editing prose; only a mechanism can close it truthfully. 11 of 20 stages are declared partial or absent rather than presented as covered."
source: "specs/003-no-stage-without-a-mechanism/spec.md"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-009
    statement: "Dado uma etapa declarada parcial, quando a declaracao e editada sem mecanismo, entao um teste falha."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items:
  - NEED-001
owner: "TODO"
risk: "TODO"
target_release: "TODO"
stability: "draft"
```

```yaml
id: FR-004
title: "A derived project inherits the process without an LLM"
type: FR
statement: "O sistema deve instalar num projeto derivado o processo canonico e os controlos sem exigir qualquer dependencia de LLM em execucao."
rationale: "Principle in ENGINEERING.md. The agent adapters are an authoring convenience and must not become a runtime requirement."
source: "ENGINEERING.md; scripts/bootstrap.py; src/engineering_playbook/resources/"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-010
    statement: "Dado um projeto derivado recem-criado, quando a bateria corre, entao nenhuma etapa exige um LLM."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items:
  - NEED-003
owner: "TODO"
risk: "TODO"
target_release: "TODO"
stability: "draft"
```

TODO: this list is not complete and is not claimed to be. It records the obligations that existing artifacts already demonstrate. Deciding which product requirements are missing is the owner's, and is the substance of the QUESTION in "Visao do produto".

## Requisitos nao funcionais

<!-- Termos vagos exigem metrica, unidade, condicao, limiar, ambiente, metodo e evidencia. -->

Cubra quando aplicavel: desempenho e capacidade, disponibilidade, confiabilidade, resiliencia, seguranca, privacidade, usabilidade, acessibilidade, compatibilidade, interoperabilidade, manutenibilidade, testabilidade, modificabilidade, portabilidade, instalabilidade, observabilidade, operabilidade, escalabilidade, eficiencia de recursos, internacionalizacao e localizacao.

```yaml
id: NFR-001
title: "A control that cannot measure refuses"
type: NFR
statement: "Enquanto um controlo nao conseguir tomar a medicao dele, o sistema deve recusar em vez de reportar aprovacao."
rationale: "An unreachable network is not a conformance verdict. This is NFR-002 of spec 003, restated here as a product property because it governs every gate."
source: "specs/003-no-stage-without-a-mechanism/spec.md, NFR-002"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-011
    statement: "Dado que gh nao responde, quando merge corre, entao o comando recusa e diz que nada foi medido."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items:
  - NEED-001
measurement_unit: "boolean, per control"
threshold: "zero controls that report success without measuring"
evidence: "tests/unit/test_signed_verdict_leaves_the_tree.py::test_merge_refuses_when_gh_cannot_answer"
```

```yaml
id: NFR-002
title: "Every limit is declared where the operator reads it"
type: NFR
statement: "Enquanto existir uma fraqueza conhecida, o sistema deve declara-la no artefato em vez de a deixar por descobrir."
rationale: "NFR-005 of spec 003. A weakness left unsaid is the defect this repository keeps paying for; the matrix and the docstrings carry the declarations."
source: "specs/003-no-stage-without-a-mechanism/spec.md, NFR-005"
priority: must
status: proposed
acceptance_criteria:
  - id: AC-012
    statement: "Dado uma etapa com alcance limitado, quando a matriz e lida, entao o limite esta escrito e nomeia a condicao."
    verification_method: inspection
verification_method: inspection
dependencies: []
conflicts: []
related_items:
  - NEED-001
measurement_unit: "stages with an undeclared known limit"
threshold: "zero"
evidence: "specs/003-no-stage-without-a-mechanism/spec.md, 11 of 20 stages declared parcial or ausente"
```

```yaml
id: NFR-003
title: "Portability across the supported workstations"
type: NFR
statement: "Enquanto o projeto correr em Windows ou POSIX com git disponivel, o sistema deve comportar-se identicamente exceto onde o limite estiver declarado."
rationale: "Line endings and the execute bit already differ. CRLF handling caused a real regression in the mutation harness, and three installer tests skip on Windows for the execute bit."
source: "tests/unit/test_installer_modes.py; src/engineering_playbook/mutation.py, apply_mutation"
priority: should
status: proposed
acceptance_criteria:
  - id: AC-013
    statement: "Dado uma arvore CRLF, quando uma mutacao e aplicada, entao o estilo de terminador do ficheiro e preservado."
    verification_method: test
verification_method: test
dependencies: []
conflicts: []
related_items: []
measurement_unit: "tests skipped for platform reasons, each with a declared reason"
threshold: "3 on Windows, all declared"
evidence: "uv run python -m pytest -q, 773 passed 3 skipped on 2026-09-22"
```

TODO: performance, capacity, availability and scalability are not specified. Nothing in the repository measures them and no target exists. QUESTION: are they applicable to a process toolkit at all, or is `N/A` with a justification the right answer?

## Modelo e requisitos de dados

<!-- Inclua entidades, propriedades, origem, retencao, qualidade e classificacao. -->

| Entity | Where | Origin | Retention | Classification |
|---|---|---|---|---|
| Project state | `.project/state.yml` | Written by the pipeline | Versioned, current value only | Non-personal, operational |
| Delivery record | `.project/state.yml`, `delivery` block | Written by `publish` from the GitHub answer | Versioned | Non-personal |
| Prepare record | `.project/delivery/prepare.yml` | Written by `prepare` | Scratch, git-ignored | Non-personal |
| Checkpoint | `.project/checkpoints/*.yml` | Written by `checkpoint.py` | Appended, never rewritten | Non-personal, historical record |
| Local CI receipt | `.project/last-ci-run.yml` | Written by the pre-push hook | Git-ignored, local only | Non-personal; cannot be versioned, see CON-003 |
| Workstream ownership | `.project/workstreams/*.yml` | Human-authored | Versioned | Non-personal |

Quality rule already enforced: a record is never edited to agree with a later state. A checkpoint is a statement about a point in time, and rewriting one would make a record say something it did not say.

TODO: no retention period, no archival policy and no data classification scheme beyond the above.

## Interfaces e integracoes

<!-- Declare atores, sistemas, protocolos, formatos, frequencia, erros e ownership. -->

| Interface | Protocol/format | Direction | Errors | Owner |
|---|---|---|---|---|
| `scripts/delivery.py` CLI | Process invocation, exit codes, stdout | Operator/agent -> system | Non-zero exit with a message naming cause and corrective action | This product |
| `gh` CLI to the GitHub API | HTTPS, JSON | System -> GitHub | Absence or failure is a refusal, never a pass | GitHub |
| `PreToolUse` hook | JSON decision on stdin/stdout | Agent harness -> system | A deny decision with a message pointing at the pipeline | This product |
| Pre-push git hook | Exit code | git -> system | Non-zero blocks the push | This product |
| GitHub Actions workflows | YAML, job outcomes | System -> CI | A failing required check blocks integration | GitHub |

## APIs, eventos e contratos externos

<!-- Contratos externos devem ser versionados, rastreaveis e testaveis. -->

The product publishes no API of its own. It consumes:

- GitHub issues and pull requests, through `gh`.
- The GitHub sub-issues API, for the parent relationship the contract gate checks.
- GitHub attestations, for the signed verdict.
- GitHub rulesets, read to understand what the server will refuse.

Versioning of these contracts is GitHub's. TODO: nothing in the repository pins a GitHub API version or records what happens when one of these endpoints changes shape.

## Seguranca

<!-- Nao invente ameaças ou controles; registre QUESTION onde analise faltar. -->

No threat model exists. The following controls exist and are named here because they are observable, not because they constitute a security posture:

- `scan_for_secrets` refuses a commit whose staged files match credential-shaped patterns, and also covers the records the pipeline commits about itself.
- The ruleset forbids force-push and deletion of `main` and requires a pull request.
- Integration requires a verdict signed by an identity no step in the pipeline can reach.
- The pull request title is neutralised against shell injection in CI (matrix stage 19).
- A derived project's tree is written by the installer, which is a path where a value from this repository enters someone else's project.

QUESTION: no threat model, no asset inventory, no adversary definition and no analysis of the installer as a supply-chain path have been done. Declaring this product "secure" on the strength of the list above would be exactly the overclaim this repository refuses elsewhere.

## Privacidade

<!-- Declare dados pessoais, finalidade, minimizacao, retencao e base legal quando aplicavel. -->

`AGENTS.md` already forbids storing full transcripts, chain-of-thought, secrets, tokens or personal data in the repository's artifacts.

Personal data that does exist, incidentally: git author names and email addresses in commit metadata, and GitHub account identifiers in issues and pull requests. These are inherent to using git and GitHub rather than collected by this product.

TODO: purpose, minimisation, retention and legal basis are not stated. QUESTION: does any derived project use this in a context where those must be stated formally?

## Autorizacao e controle de acesso

<!-- Defina papeis, permissoes, negacoes, elevacao e auditoria esperada. -->

Enforced today:

- No direct push to `main` for any identity; `bypass_actors` is empty (CON-001).
- Remote operations, commits, merges, tags and releases require explicit human authorisation.
- No agent may set this document's `status` to `approved` or fill `approvers`.
- An automated agent is subject to the same pipeline as a human; the hook refuses the raw `git` path that would bypass it.

TODO: no role model, no permission matrix and no defined escalation path exist. QUESTION: are there several roles, or only "the owner"?

## Auditoria e rastreabilidade

<!-- Defina eventos auditaveis, retencao, integridade e acesso aos logs. -->

The audit trail is the repository itself: the commit history, the checkpoints, the pull requests, the CI runs and the attestations. Integrity of the last of these is the only part not resting on the repository's own honesty, because it is signed by the workflow identity.

The chain the pipeline enforces today runs pull request -> issue -> parent issue -> `specs/NNN/`. The link from a requirement in this document to the spec that implements it does NOT exist yet; matrix stage 20 declares it partial for that reason, and issue #45 has to settle identifiers first.

TODO: no retention period and no access control over the audit trail are stated.

## Conformidade legal e regulatoria

<!-- Nao alegue conformidade sem verificacao formal. Registre referencias especificas. -->

TODO. No legal or regulatory analysis has been performed and none is recorded. `docs/requirements/README.md` forbids an agent from inventing legal requirements, and claiming conformance without formal verification is explicitly out of bounds.

QUESTION: is this product used in any context with a regulatory obligation? If not, this section becomes `N/A - nao aplicavel, porque: <justificativa>`, and only a human can write that justification.

## Acessibilidade

<!-- Declare padroes, usuarios afetados, criterios e metodo de verificacao. -->

TODO. The product's surface is a command-line interface and Markdown documents. No accessibility standard has been chosen, no affected user has been identified and no verification method exists.

QUESTION: does a standard apply to a CLI and its documentation here, and if not, what is the justification that should replace this section?

## Observabilidade

<!-- Inclua logs, metricas, traces, alertas, dashboards e diagnostico. -->

What exists: every pipeline stage prints what it did or why it refused; `scripts/doctor.py` diagnoses the environment; `scripts/status` reports where a delivery stands; the mutation harness reports a verdict per mechanism; CI job outcomes are visible per run.

What does not: no metrics, no traces, no alerting, no dashboard, and no aggregation across runs or across derived projects.

TODO: whether any of those is wanted is a decision, not a gap an agent should fill in.

## Operacao e suporte

<!-- Descreva suporte, SLAs se existirem, procedimentos e limites operacionais. -->

Operating procedures are the canonical sequence in `ENGINEERING.md` and the pipeline stages. Diagnosis starts at `scripts/doctor.py` and `scripts/resume.py`.

TODO: no support channel, no SLA, no on-call and no escalation exist. QUESTION: is this product supported for anyone other than its owner?

## Backup, recuperacao e continuidade

<!-- Defina RPO, RTO, escopo de backup e teste de restauracao. -->

TODO. No RPO, no RTO, no backup scope and no restore test exist.

What is observable: all durable state lives in the git repository and on GitHub, so continuity is whatever git and GitHub provide, and the local scratch (`.project/delivery/`, the CI receipt) is reproducible by re-running the stage that writes it.

QUESTION: is the GitHub copy considered the backup, and is that acceptable?

## Migracao e compatibilidade

<!-- Inclua compatibilidade retroativa, migracao de dados e janela de transicao. -->

Compatibility mechanisms that exist: the parity test refuses drift between the canonical documents and the shipped mirror, so a derived project cannot silently receive a stale copy; `last_verified_tree` is recorded alongside `last_verified_commit` because only the tree survives a squash unchanged.

TODO: there is no versioning scheme for the process itself, no migration path for a derived project created under an older version of the playbook, and no compatibility window. QUESTION: how does a project that adopted this six months ago receive a later change to the process?

## Ambientes e implantacao

<!-- Declare ambientes, diferencas relevantes e criterios de promocao. -->

Environments: the operator's workstation (Windows or POSIX), and GitHub Actions runners. There is no staging or production environment, because the product is not deployed as a service; it is installed into a repository.

Relevant differences already measured: the execute bit is ignored on Windows (three tests skip, each with a declared reason), and line endings differ, which caused a real regression in the mutation harness.

Promotion criterion: integration into `main` through a pull request whose tree carries a signed verdict.

## Restricoes tecnologicas justificadas

<!-- Justifique escolhas obrigatorias de tecnologia com motivo tecnico ou contratual. -->

| Choice | Justification |
|---|---|
| Python `>=3.11` | Measured from `pyproject.toml`. Some code depends on newer behaviour, which is why line-ending handling avoids `Path.read_text(newline=)` (3.13+) and f-string backslashes (3.12+) |
| `uv` as the runner | Every documented command is `uv run ...`, so the environment that ran a check is the one that is pinned |
| `gh` CLI as the only GitHub client | One client, one place where an API failure is interpreted, and one place to make that failure a refusal rather than a pass |
| YAML for state and records | Human-readable by the operator who has to diagnose a refusal; already the format of the state the process describes |
| GitHub Actions | The controls that must not be bypassable live on the server, and the ruleset and attestations are GitHub features |

TODO: none of these was recorded as a decision with alternatives considered at the time. They are reconstructed justifications, which is weaker than an ADR.

## Criterios globais de aceitacao

<!-- Criterios globais devem ser objetivos, testaveis e independentes de implementacao. -->

- The full battery passes: format, lint, types, tests and `verify.py`.
- Every mechanism in the mutation inventory is held by a test that fails without it.
- Every matrix stage states where its control lives, and every partial or absent stage states why.
- No number in a delivered artifact was written before the last edit of the unit it describes.
- No requirement marked `accepted` contains an unresolved placeholder.
- The working tree is clean at the end of each stage that can leave it clean, and the exceptions are declared.

## Estrategia de verificacao e validacao

<!-- Diferencie verificacao e validacao, com metodo, evidencia e responsavel. -->

Verification, "did we build it right", is mechanised and runs on every delivery:

| Method | Instrument |
|---|---|
| Static analysis | `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` |
| Test | `uv run python -m pytest -q` |
| Structural inspection | `uv run python scripts/verify.py` |
| Adversarial | `uv run python scripts/mutation.py`, which removes each mechanism and requires a named test to fail |
| Independent review | A read-only reviewer over the diff and artifacts before PASS |

Validation, "did we build the right thing", is NOT mechanised and is honestly weak: there is no operator feedback, no adoption evidence and no measurement from any derived project. TODO, and it is the largest gap in this document.

## Riscos e mitigacoes

<!-- Inclua probabilidade, impacto, resposta, responsavel e gatilho. -->

| ID | Risk | Evidence it is real | Response |
|---|---|---|---|
| R-1 | A document claims more than the artifact sustains | Every review finding across the last two slices was of this shape, twice in an agent's own delivery reports | Independent review before PASS; the anti-stale-number test; ledger row 2 |
| R-2 | A control exists but nothing holds it | Measured: deleting a CI step left the whole suite green | The mutation inventory, pinned in both directions |
| R-3 | A test holds the fake instead of the mechanism | Measured: a one-token change to `git add -A` left five tests green | Adversarial review plus a mutation entry whose target is the exact line |
| R-4 | The process is adopted and then bypassed under pressure | A gate that goes red on correct work is a gate somebody switches off, which is why detector reach was traded for zero false positives | Keep false positives at zero on real data; measure before widening any gate |
| R-5 | Coverage is believed to be complete | 11 of 20 stages are not fully covered | Declare per stage; refuse prose-only closure |
| R-6 | No validation with a real user | Nothing in the repository records one | TODO, owner decision |

Probability, impact, owner and trigger columns are TODO: assigning them is a judgement this document must not invent.

## Alternativas consideradas

<!-- Registre alternativas, criterios e razao da escolha. -->

Recorded in the repository:

- ADR 0000 adopts MADR as the decision record format.
- ADR 0001 chooses a single client-side hook mechanism.
- Issue #64 recorded three routes for the dirty-tree defect -- fold the writes into a commit, make the records scratch, or make `start` accept known bookkeeping paths. The first was chosen; the third was rejected because an exception in a gate is not a fix for the cause; the second was rejected because it contradicts the decision in #52 to keep the pull request number in a versioned artifact.
- Issue #65 recorded the trade on detector reach: adding function words raised reach from 4 of 10 to 7 of 10 and refused ordinary English, so they were removed, keeping zero false positives across all 45 real issue titles.

TODO: most technology choices predate any recorded alternative analysis.

## Decisoes que exigem ADR

<!-- Liste decisoes arquiteturais que exigem registro formal. -->

- The identifier namespace between this document and the specs (issue #45). Until it is settled, a bare `FR-nnn` is ambiguous and the traceability matrix cannot close.
- Whether this repository is a tool whose product is the pipeline, or a product with external users. This decision determines whether most of this document is debt or is non-applicable, and it is the open QUESTION in "Visao do produto".
- Multi-stack support: what `--stack` means, and whether `init` and CI become stack-aware (issue #66 and its sub-issues #67 to #70).
- Whether the signed verdict becomes a required status check on the server rather than a client-side control (matrix stage 17).

## Releases e marcos

<!-- Relacione entregas a requisitos, criterios e datas quando existirem. -->

TODO. The project version is `0.1.0` and no release has been cut, no milestone exists and no date is recorded. Inventing a roadmap is explicitly forbidden.

## Matriz de rastreabilidade

<!-- Rastreie necessidade -> requisito -> criterio -> verificacao -> evidencia. -->

| Need | Requirement | Criterion | Verification | Evidence |
|---|---|---|---|---|
| NEED-001 | FR-003, NFR-001, NFR-002 | AC-009, AC-011, AC-012 | Test, inspection | Matrix in spec 003; `test_coverage_matrix_is_measured.py`; 34 of 34 mechanisms held |
| NEED-002 | FR-001 | AC-007 | Test | `tests/unit/test_issue_gate.py` |
| NEED-001 | FR-002 | AC-008 | Test | `tests/unit/test_publish_leaves_tree_clean.py` |
| NEED-003 | FR-004 | AC-010 | Test | Installer and mirror parity tests |

INCOMPLETE ON PURPOSE. The column that should link each requirement to the SPEC that implements it is missing, because the identifier namespace is ambiguous until issue #45 lands. Matrix stage 20 of spec 003 declares that same gap. Filling this column now would create exactly the false traceability that stage 20 exists to refuse.

## Questoes abertas

<!-- Liste perguntas nao resolvidas, dono, prazo e impacto. -->

| ID | Question | Impact if unanswered |
|---|---|---|
| Q-1 | Is this a tool whose product is the pipeline, or a product with external users? | Determines whether this whole document is debt or is largely non-applicable. Everything below the vision section is written for the second reading |
| Q-2 | Who are the stakeholders and users, and what is the evidence? | Stakeholders, personas, needs and ownership stay TODO; no requirement can be prioritised honestly |
| Q-3 | What are the success metrics, with baseline, target, window and source? | The product cannot tell whether it is succeeding; the counters listed are status, not success |
| Q-4 | How are PRD identifiers separated from spec identifiers (issue #45)? | Traceability cannot close; matrix stage 20 stays partial |
| Q-5 | Is there any legal, regulatory or accessibility obligation? | Those sections stay TODO and cannot become a justified N/A |
| Q-6 | Has anyone outside this repository used the process? | Validation, as opposed to verification, has no evidence at all |

Owner and deadline columns are deliberately absent: both require a human decision.

## Decisoes pendentes

<!-- Liste decisoes pendentes com opcoes, criterio de escolha e responsavel. -->

| Decision | Options | Criterion |
|---|---|---|
| Accept, correct or discard this proposal | Accept as `in_review`; correct and then review; discard and mark the document non-applicable | Whichever reading of Q-1 the owner holds |
| Identifier namespace | Prefix PRD identifiers; prefix spec identifiers; keep both and define a resolution order | Issue #45 |
| Multi-stack support | Make `--stack` real; remove the flag; document it as Python-only | Issue #66 |
| `merge` dirty tree | Accept as a declared limit; move the record to scratch; make `start` carry it | Whether a declared limit is acceptable for an operator-facing stage |

## Waiting room ou requisitos futuros

<!-- Guarde ideias nao priorizadas sem poluir o escopo atual. -->

Open issues not yet scheduled, recorded here so they are not mistaken for scope: #8, #26, #28, #34, #45, #50, #54, #56, #63, #66 with #67 to #70, #73.

Ideas implied by the artifacts but not decided: aggregating mutation results across runs to see coverage move over time; a version for the process itself so a derived project can tell which one it has; making the signed verdict a required server-side check.

## Referencias e anexos

<!-- Liste fontes, documentos, decisoes e evidencias relacionadas. -->

- `ENGINEERING.md` — canonical process, principles, the Definition of Done and the ledger of errors already paid for.
- `AGENTS.md` — entry point for agents and the limits on what they may do.
- `docs/requirements/README.md` — the rules this document was filled under, including what an agent may not invent.
- `specs/001` to `specs/004` — the four existing specifications; `003-no-stage-without-a-mechanism` carries the 20-stage coverage matrix.
- `docs/decisions/0000-use-madr.md`, `docs/decisions/0001-single-client-hook-mechanism.md` — the two ADRs.
- `src/engineering_playbook/mutation.py` — the mechanism inventory.
- Issues #45, #46, #64, #65, #66, #73 — the decisions and defects this document cites.
