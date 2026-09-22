# Specification: Nenhuma etapa sem mecanismo

## Problema

O pipeline de entrega deste repositorio define etapas obrigatorias entre a redaccao do PRD e a
integracao na branch por omissao, mas a obrigatoriedade e declarativa: reside em documentacao de
processo e nao em pontos de enforcement executaveis. Etapa cuja execucao depende da disciplina do
operador nao constitui etapa obrigatoria; constitui convencao.

Medicao de 2026-09-20, por instrumento:

| Observacao | Comando | Resultado |
| --- | --- | --- |
| Hooks de cliente nao instalados | `git config --get core.hooksPath` | exit 1, valor ausente; `.git/hooks` contem apenas `*.sample` |
| Ausencia de enforcement no servidor | `gh api repos/:owner/:repo/rulesets` | lista vazia |
| Branch por omissao desprotegida | `gh api repos/:owner/:repo/branches/main/protection` | `404 Branch not protected` |
| Integracao sem revisao | `gh pr view 17 19 --json reviews` | `reviews: 0`, `reviewDecision` vazio |
| Ordem de etapas nao imposta | inspeccao de `src/engineering_playbook/delivery.py` | apenas a transicao `prepare -> commit` valida antecessor |
| Veredicto mutavel pelo executor | inspeccao de `.project/state.yml` | `last_verified_commit` e campo YAML sem assinatura nem verificacao de integridade |

A ultima linha caracteriza a causa raiz e subordina as demais: **o executor da entrega e tambem o
emissor do veredicto de conformidade**. A literatura de integridade de cadeia de suprimentos trata
esta condicao como violacao de separacao de funcoes; a especificacao SLSA exige que a plataforma de
build gere a proveniencia e que o material criptografico de assinatura seja inacessivel aos passos
definidos pelo utilizador (https://slsa.dev/spec/v1.0/levels). Enquanto o veredicto for campo escrito
pelo processo local, qualquer controle posicionado acima dele e ornamental.

## Definicoes

- **Ponto de enforcement**: componente executavel que avalia uma condicao e interrompe o fluxo quando
  a condicao nao e satisfeita, com codigo de saida diferente de zero.
- **Vetor de bypass**: caminho conhecido pelo qual um agente ou operador alcanca o efeito de uma etapa
  sem atravessar o ponto de enforcement correspondente.
- **Raiz de confianca**: entidade cuja identidade ou assinatura sustenta a validade de um veredicto.
- **Teste adversarial**: teste que executa a tentativa que o controle deve rejeitar e assere a
  rejeicao observada.
- **Teste de mutacao de controle**: remocao deliberada do controle seguida de execucao da suite.
  Controle nao coberto e aquele cuja remocao mantem a suite aprovada.

## Requirements

- FR-001: A branch por omissao e protegida por configuracao no servidor, verificada por leitura da API e nao por declaracao em ficheiro nao aplicado.
- FR-002: O ficheiro versionado de ruleset representa a configuracao efectivamente aplicada; divergencia entre declarado e aplicado constitui falha de gate.
- FR-003: O procedimento de bootstrap configura `core.hooksPath`, e `doctor` e `verify` retornam falha em repositorio cujos hooks de cliente nao estejam activos.
- FR-004: Coexistencia nao arbitrada de dois mecanismos de hook e eliminada: um e removido, ou o repositorio declara qual governa e a razao tecnica da escolha.
- FR-005: A ordem das etapas e imposta por verificacao de antecessor. Etapa cujo antecessor nao registou execucao valida retorna falha.
- FR-006: O veredicto de conformidade e emitido por execucao cuja identidade e distinta da identidade do executor da entrega, e o sujeito do veredicto e o digest do conteudo, nao o identificador de commit da branch.
- FR-007: `last_verified_commit` deixa de constituir fonte de verdade e passa a cache de leitura do veredicto assinado.
- FR-008: Caso de teste ignorado nao e computado como aprovacao sem justificativa declarada e legivel por instrumento.
- FR-009: Cada ponto de enforcement documenta, no proprio ficheiro, os vetores de bypass conhecidos.
- FR-010: Cada requisito desta especificacao nomeia o mecanismo que o torna verificavel. Requisito sem mecanismo nomeado e rejeitado em revisao.
- FR-011: O agente automatizado esta sujeito aos mesmos pontos de enforcement que o operador humano, por mecanismo e nao por instrucao: invocacao de ferramenta que efectue escrita em git fora do pipeline e rejeitada antes da execucao.
- FR-012: O alcance de cada mecanismo e declarado. O controle de harness vigora na estacao de trabalho que o tenha configurado; fora dela permanecem apenas o hook de cliente e o enforcement do servidor.
- FR-013: Toda pull request possui cadeia de rastreabilidade completa: pull request, sub-issue, issue mae, `specs/NNN/`, requisito do PRD. Cada elo e verificado, e elo ausente constitui falha de gate.
- FR-014: Alteracao de codigo nao associada a especificacao activa constitui falha de gate.
- FR-015: Sub-issue sem issue mae, ou issue mae sem especificacao correspondente, constitui falha de gate.
- FR-016: Nenhuma etapa do pipeline, entre a redaccao do PRD e a integracao, permanece sem mecanismo nomeado. A cobertura e auditavel pela matriz desta especificacao.
- FR-017: Cada mecanismo possui teste adversarial que falha contra a revisao de codigo anterior a introducao do mecanismo.
- FR-018: Existe suite adversarial do pipeline que exercita cada vetor de bypass enumerado e assere a rejeicao observada, nao inferida.
- FR-019: Vetor de bypass descoberto posteriormente e incorporado a suite adversarial previamente a correccao correspondente.
- FR-020: Projecto derivado sem integracao continua mantem o mecanismo anterior de verificacao. A resolucao do defeito estrutural do squash e declarada como restrita aos projectos que dispoem de integracao continua, em vez de afirmada universalmente.
- FR-021: O controlo de reconciliacao do ruleset executa no `pre-push`, sob a credencial do proprio operador. A execucao em integracao continua e inviavel: o endpoint exige permissao de administracao, inalcancavel pelo token de workflow.

## Non-Functional Requirements

- NFR-001: Nao se introduz ferramenta adicional para problema ja resolvido. O hook de cliente existente permanece; a deficiencia medida foi ausencia de configuracao de `core.hooksPath`, nao insuficiencia da implementacao.
- NFR-002: Controle incapaz de obter a medicao retorna falha. Indisponibilidade de ambiente nao equivale a conformidade.
- NFR-003: As solucoes adoptadas sao proporcionais a repositorio de mantenedor unico. Controles cuja premissa e a existencia de multiplos operadores distintos sao excluidos com justificativa registada.
- NFR-004: Teste que apenas confirma a presenca do controle nao satisfaz a FR-017. Satisfaz-na o teste cuja falha e induzida pela remocao do controle.
- NFR-005: Esta especificacao nao estabelece ausencia de vetores de bypass. Estabelece que os vetores enumerados na matriz de cobertura estao mitigados e permanecem mitigados sob regressao. A distincao e registada porque a afirmacao mais forte constituiria precisamente a classe de asserçao nao verificada que esta especificacao existe para impedir.

## Acceptance Criteria

- AC-001: Tentativa de push directo para a branch por omissao e rejeitada pelo servidor, observada em execucao real.
- AC-002: Repositorio com `core.hooksPath` nao configurado produz falha em `doctor`.
- AC-003: Commit cujo antecessor `prepare` nao registou execucao valida e rejeitado.
- AC-004: O veredicto de conformidade de um commit e verificavel por terceiro sem confianca no ficheiro de estado, mediante `gh attestation verify` ou equivalente.
- AC-005: Caso de teste ignorado sem justificativa declarada produz falha de gate.
- AC-006: Ficheiro de ruleset e configuracao aplicada sao equivalentes; alteracao unilateral de um deles produz falha de gate.
- AC-007: Invocacao de escrita em git fora do pipeline por agente automatizado e rejeitada, observada em tentativa real.
- AC-008: Para cada requisito desta especificacao existe mecanismo nomeado no texto.
- AC-009: Pull request cuja sub-issue nao possua issue mae, ou cuja issue mae nao possua especificacao, produz falha de gate.
- AC-010: Pull request que altere codigo nao associado a especificacao activa produz falha de gate.
- AC-011: A matriz de cobertura nao contem etapa classificada como ausente de mecanismo.
- AC-012: A remocao individual de cada mecanismo produz falha da suite adversarial.
- AC-013: A suite adversarial e executada na integracao continua, nao apenas na estacao de trabalho do executor.

## Matriz de cobertura

Classificacao dos pontos de enforcement medidos em 2026-09-20. `servidor`: enforcement remoto, nao
contornavel pelo cliente. `CI`: enforcement em integracao continua, alcancado obrigatoriamente porque
a pull request e requisito do ruleset. `parcial`: mecanismo presente com vetor de bypass conhecido.
`ausente`: nenhum ponto de enforcement.

Esta matriz e lida por instrumento, nao por leitor: `tests/unit/test_coverage_matrix_is_measured.py` (T214) rejeita classificacao fora do vocabulario definido, `parcial` que nao declare o seu alcance, citacao de requisito ou tarefa inexistente, e qualquer alteracao ao conjunto de etapas `ausente` que nao venha acompanhada da actualizacao do inventario fixado. A AC-011 fica satisfeita automaticamente quando esse inventario esvaziar. Limite declarado conforme a NFR-005: o instrumento mede coordenacao e existencia -- que matriz e inventario mudam na mesma edicao, e que o artefacto citado existe -- e nao adequacao. Uma linha pode citar um ficheiro real que cobre outra coisa; isso e a T222. Fundamento medido: duas linhas desta tabela estavam desactualizadas em 2026-09-21, em sentidos opostos, e ambas foram descobertas por acaso.

| # | Etapa | Classificacao | Requisito que a cobre |
| --- | --- | --- | --- |
| 1 | Validacao do PRD por instrumento | CI | coberta, `core.validate_prd_document` em `src/engineering_playbook/core.py`, `tests/unit/test_core.py` |
| 2 | Existencia de especificacao, plano e tarefas referenciados pelo estado | CI | coberta, `core.verify_root` (State reference missing), `tests/unit/test_core.py` |
| 3 | Unicidade de identificadores de tarefa em `specs/*` | CI | coberta, spec 002, `core.verify_root`, `tests/unit/test_core.py` |
| 4 | Precedencia da especificacao sobre o codigo | CI | coberta, T213, `src/engineering_playbook/delivery.py` (`spec_precedence_refusal`), `.github/workflows/quality.yml`, `tests/unit/test_code_names_its_spec.py`: pull request que altera codigo toca o directorio da especificacao activa, ou declara `no_spec_reason` no estado. Associacao medida no diff e nao no campo de estado, que esteve desactualizado nos 8 commits de primeiro progenitor ate `48639d30`. Limites declarados: tocar o directorio nao e descrever a mudanca, e a lista de caminhos vem paginada com verificacao de truncagem. Refs: FR-014, AC-010 |
| 5 | Issue aberta previamente a entrega | CI | coberta, spec 002, `delivery.issue_is_open`, `tests/unit/test_issue_gate.py` |
| 6 | Vinculo sub-issue para issue mae e issue mae para especificacao | CI | coberta, T212, `src/engineering_playbook/delivery.py` (`traceability_refusal`), `tests/unit/test_the_chain_is_verified.py`: a issue que a pull request fecha resolve por `parent_issue_url` ate uma issue mae que nomeia `specs/NNN/` existente, ou nomeia-a ela propria, ou declara `no_spec_reason`. Elo em falta e nomeado. Refs: FR-015, AC-009 |
| 7 | Conformidade do nome de branch | CI | coberta, `delivery.validate_branch_name`, `tests/unit/test_core.py` |
| 8 | Proibicao de commit originado na branch por omissao | servidor | coberta, `.github/rulesets/main.yml`, `scripts/git-hooks/pre-commit`, `tests/unit/test_git_hooks.py` |
| 9 | Ordem `start`, `prepare`, `commit`, `publish`, `merge` | parcial, `publish` e `merge` nao verificam recibo do antecessor | FR-005, AC-003. T218 acrescentou a precondicao de `start`: recusa partir de HEAD que a base nao contem, com `--from-base` como saida. T219 fechou o segundo referente: `resolve_base` devolve `refs/remotes/<remote>/<base>`, ou `refs/heads/<base>` declarado quando nao existe ref remoto, e `publish` e `status` consomem-no, com teste ponta a ponta por comando e duas entradas de mutacao sobre os sitios de chamada (#61). Permanece parcial pela razao restante: `publish` e `merge` ainda nao verificam recibo do antecessor |
| 10 | Formatacao, analise estatica, tipos e testes | servidor | coberta, `.github/workflows/quality.yml`, `.github/rulesets/main.yml`, `tests/unit/test_local_ci.py` |
| 11 | Schemas, distribuicao e fixacao de Actions por SHA | CI | coberta, `core.verify_root` (GitHub Actions must be pinned by full SHA), `tests/unit/test_schema_validation.py`, `tests/unit/test_resource_mirror_parity.py`. A evidencia estava sobredeclarada ate #49: a paridade do espelho citada aqui excluia `.project/schemas/*` e `.github/workflows/quality.yml`, isto e, as duas familias com maior probabilidade de derivar, e o workflow foi editado a mao varias vezes numa sessao enquanto a exclusao vigorava -- sem numero exacto, porque o `git log` ve commits e nao sessoes e nenhum instrumento aqui o reproduz. Medido em 2026-09-22: os sete schemas ja eram identicos, portanto a exclusao nao protegia nada e apenas escondia a proxima edicao; o workflow difere em dois pontos legitimos, o job `adversarial` que um projecto derivado nao consegue correr e o `needs:` do `attest`, e passou a ser comparado de duas maneiras redundantes: estruturalmente, com o YAML das duas copias comparado depois de remover esse job, o que e imune a formatacao; e textualmente, entre ancoras literais asseridas como unicas, o que apanha comentarios e espacos em branco que o YAML nao ve. A primeira versao desta comparacao removia o bloco por varrimento de indentacao e a revisao mediu-a a falhar aberta nos dois sentidos com uma unica edicao. ALCANCE DECLARADO, NFR-005: nao sao comparadas as linhas em branco da costura -- no ficheiro da raiz sao as que precedem `  adversarial:`, isto e, o fim do job anterior, e na copia distribuida as que precedem `  attest:`. Pertencem ao bloco removido e no espelho nao tem onde viver; sem esta cegueira, espelhar correctamente essa linha dava vermelho. Uma linha com espacos nao conta como em branco, portanto continua a ser comparada; e a comparacao e sobre este par de ficheiros, nao sobre a adequacao do workflow. 85 pares espelhados, e tres entradas no inventario de mutacao -- uma por cada metade da redundancia mais a paridade dos schemas, porque a revisao mediu que a comparacao textual, citada aqui como metade do mecanismo, nao tinha entrada nenhuma a prova-la |
| 12 | Pull request obrigatoria, estrategia squash, proibicao de force push | servidor | coberta, `.github/rulesets/main.yml`, `tests/unit/test_ruleset_reconciliation.py` |
| 13 | Checks obrigatorios para integracao | servidor | coberta, `.github/rulesets/main.yml`, `tests/unit/test_ruleset_reconciliation.py` |
| 14 | Execucao da bateria previamente ao push | parcial, alcance limitado a estacao com `core.hooksPath` configurado, e nao vigora em integracao continua | coberta em parte, T203: `core.verify_root` rejeita `core.hooksPath` nao configurado, com testes adversariais em `tests/unit/test_hooks_path_activation.py`. Vectores declarados no proprio controlo: `--no-verify`, reconfiguracao posterior de `core.hooksPath`, clone onde ninguem executa estes comandos, e execucao em integracao continua, onde e deliberadamente saltado. Refs: FR-003, AC-002 |
| 15 | Emissao do veredicto de conformidade | CI | coberta, T208/T209, `.github/workflows/quality.yml`, `src/engineering_playbook/attestation.py`, `tests/unit/test_signed_verdict_leaves_the_tree.py`: attestation assinada pela identidade OIDC da execucao, emitida em job proprio que depende das duas baterias; `last_verified_commit` e `last_verified_tree` reclassificados como cache de leitura |
| 16 | Caso ignorado nao computado como aprovacao | CI | coberta, T210, `tests/conftest.py`, `tests/skip_policy.py`, `tests/unit/test_a_skip_is_declared.py`: asserçao sobre o relatorio de execucao, com inventario versionado. Alcance medido: skip em `setup`, `call` e `teardown`, skip ao nivel do modulo (`allow_module_level`, `importorskip`) que chega como relatorio de recolha, e `xfail`, cuja razao vem de `report.wasxfail`. Isento por desenho: corrida estreitada por `-k`, `-m`, `--deselect` ou caminho explicito, e corrida que nao executa (`--collect-only` e afins), porque e assim que a MEASURER conta testes |
| 17 | Verificacao do veredicto antes da integracao | parcial, controlo no cliente e nao required status check | FR-006, T208, `src/engineering_playbook/delivery.py`, `delivery.py merge` mede a tree do head remoto da pull request e recusa sem veredicto assinado, mas e passo de comando local: integracao pela interface do GitHub nao o atravessa. Ver vectores de bypass abaixo |
| 18 | Sujeicao do agente automatizado ao pipeline | parcial, alcance limitado a estacao configurada | coberta em parte, T205: `.claude/hooks/enforce_delivery_pipeline.py` rejeita `commit|push|merge|rebase|reset` anteriormente a execucao da ferramenta, com teste em `tests/unit/test_delivery_pipeline_hook.py`. T221 alargou-o a criacao e escrita de branch. Medido em 2026-09-21, depois de #61 e da revisao independente que o remediu, sobre 151 formas: recusa `switch -c`, `checkout -b`, `switch --create`, `checkout --orphan`, `branch <nome>`, `branch -d/-D/-m/-M/-c/-C/-f/--force`, `worktree add -b/-B`, `update-ref` e `symbolic-ref` sobre `refs/heads/`, e `fetch` com refspec que escreve ref local; com qualquer opcao global antes do verbo (a lista de quatro que aqui estava foi medida insuficiente: `-p`, `--work-tree=`, `--exec-path=` e `--git-dir=` passavam), com abreviatura de opcao longa no prefixo minimo que o git aceita, com verbo entre aspas, e atraves de `;` e `&&`. Permite as 70 formas de leitura testadas, incluindo comando multi-linha, cujo `-c` da linha seguinte era lido como flag do `switch` anterior. Os numeros desta celula sao verdadeiros da arvore em que foram medidos e de mais nenhuma -- sete rondas de revisao mostraram que qualquer edicao de texto os mexe, incluindo a edicao que os escreve. Limite medido e declarado no cabecalho do ficheiro: a decisao le a string inteira, portanto recusa tambem texto que cite estes comandos -- 221 linhas em 32 dos 374 ficheiros versionados, 121 delas pela guarda de branch, 92 das quais sob `tests/`, isto e, os proprios casos que enumeram o que e recusado. FR-012: fora da estacao configurada, nada disto vigora |
| 19 | Neutralizacao de injeccao de shell via titulo de pull request | CI | coberta, spec 002, `.github/workflows/quality.yml` (PR_TITLE via env), `tests/unit/test_core.py` |
| 20 | Cadeia de rastreabilidade entre pull request e PRD | parcial, o elo ate ao requisito do PRD nao existe para ser verificado | coberta em parte, T212, `src/engineering_playbook/delivery.py`, `tests/unit/test_the_chain_is_verified.py`: a cadeia pull request -> issue -> issue mae -> `specs/NNN/` e verificada. O ultimo elo fica aberto por dois factos medidos em 2026-09-21: o PRD e um template com 80 `TODO` e nenhum requisito preenchido (#46), e `FR-001` designa quatro coisas diferentes nas quatro specs, pelo que uma referencia de spec para PRD seria ambigua (#45). Refs: FR-013 |

## Vectores de bypass do veredicto assinado

Enumerados conforme a FR-009 e a FR-018, medidos ou derivados por leitura de instrumento em
2026-09-21, durante a revisao da fatia T208/T209. A NFR-005 aplica-se: esta lista afirma que estes
vectores estao enumerados, nao que sejam os unicos.

| Vector | Estado | Fundamento |
| --- | --- | --- |
| `quality.yml` alterado na propria branch que esta a ser assinada | aberto | `gh attestation verify --signer-workflow` impoe repositorio e caminho do workflow, nao a sua ref nem o seu conteudo (`gh attestation verify --help`, v2.92.0). Quem faz push de branch pode reduzir a bateria e obter assinatura da mesma identidade. Fecha com trusted builder: passo de assinatura em reusable workflow sobre ref protegida, verificado por `--signer-repo`/`--signer-digest`. Decisao de topologia, pendente do proprietario |
| Integracao pela interface do GitHub, ou `gh pr merge` a mao | aberto | A verificacao vive em `delivery.command_merge`, no cliente. Fecha tornando-a required status check no servidor, o que exige reordenar o fluxo: a attestation da branch e cunhada pela execucao de push que precede o merge |
| `merge --auto` integra mais tarde, contra um head que se moveu depois da medicao | aberto | O portao mede o head que `gh pr view --json headRefOid` reporta no instante da chamada. Os checks obrigatorios do servidor correm contra o head novo; o veredicto assinado nao e relido |
| Mecanismo removido sem que nenhum teste o note | parcial, alcance declarado | T215/T216: `src/engineering_playbook/mutation.py` remove cada mecanismo do inventario numa copia, exige que os alvos estivessem verdes antes, e so conta como apanhado um node id que passou a falhar. Medido em 2026-09-22, apos #49: 25 de 25 apanhados, e o inventario alcanca 8 das 20 etapas desta matriz -- 4, 9, 11, 15, 16, 17, 18, 20. As restantes nao tem entrada, portanto o vector permanece aberto para elas. Corre como job proprio em integracao continua (AC-013), e o job de assinatura depende dele |
| Assinatura emitida antes da bateria, por reordenacao de passos | fechado | O job de assinatura declara `needs` sobre todos os outros jobs, e `core.attestation_workflow_errors` rejeita workflow em que isso deixe de ser verdade. Teste de mutacao em `tests/unit/test_signed_verdict_leaves_the_tree.py` |
| Identidade de assinatura alcancavel por codigo do repositorio ou de dependencia | fechado | `id-token: write` alcanca todos os passos do job que a declara. A assinatura corre em job separado, cujos unicos passos sao checkout, `git rev-parse` e a Action; nenhum outro job pode declarar essas permissoes sem falhar `verify` |
| Attestation emitida em runner self-hosted | fechado | `--deny-self-hosted-runners` na verificacao |
| Attestation de outro repositorio ou de outro caminho de workflow | fechado | `--repo` e `--signer-workflow` na verificacao. Limite: num clone cujo `origin` aponte para um fork, o slug medido e o do fork |
| Repositorio privado, que nao pode emitir veredicto | nao aplicavel, declarado | `attestation.repository_identity` mede a visibilidade e o portao nao se aplica; o projecto mantem o mecanismo de commit e ancestralidade. Sem esta medicao o portao seria impossivel de satisfazer, e portao impossivel e portao removido |
| Criacao de branch fora da esteira (`git switch -c`, `git checkout -b`, `git branch`, `worktree add -b`, `update-ref`, refspec de `fetch`) | parcial, na estacao configurada | Medido contra `.claude/hooks/enforce_delivery_pipeline.py` em 2026-09-21, depois de T221 e de #61 e das seis rondas de revisao independente: 81 formas de escrita recusadas e 70 de leitura permitidas, enumeradas na etapa 18 e em `tests/unit/test_one_base_one_meaning.py`, mais um conjunto GERADO a partir do proprio git em `tests/unit/test_the_guard_agrees_with_git.py`: as opcoes que o git declarar em `git branch --git-completion-helper` e em `git branch -h`, cada uma corrida em varias formas contra um repositorio real, com `for-each-ref` a decidir se houve escrita e o guarda obrigado a concordar. Sem numero aqui de proposito: o numero depende da versao do git instalada, o proprio teste recusa-se a fixa-lo, e uma celula que o fixasse ficaria errada noutra maquina sem nada ficar vermelho -- que e a classe de afirmacao que esta spec existe para eliminar. O teste exige um piso e a presenca das opcoes que decidem escrita, e as opcoes que o git recusa em todas as formas estao fixadas como inventario, para que 'concordou' e 'nao mediu' deixem de ser indistinguiveis numa corrida verde. `parcial` e nao `fechado` por tres factos medidos: a guarda vive na estacao com `.claude/settings.json` activo e nao vale para quem nao a tem (FR-012); `bash -c`, caminho absoluto para o binario e substituicao de shell continuam declarados abertos no cabecalho do ficheiro; e uma enumeracao de formas e uma lista, nao uma prova de exaustao |

## Exclusoes de escopo

- **Merge queue**: mitiga contencao entre pull requests concorrentes pela mesma branch de destino. O
  repositorio opera com mantenedor unico e o gatilho `on: push` ja executa a bateria sobre a branch de
  destino apos a integracao. Reavaliar mediante evidencia de concorrencia real.
- **Implementacao directa de in-toto Layout e Link**: pressupoe distribuicao de material de assinatura
  por funcao operacional distinta, premissa nao satisfeita por operador unico. O formato in-toto ja e
  utilizado pelo mecanismo nativo de attestation.
- **Kyverno**: motor de politica de admissao para Kubernetes, ausente da topologia deste pipeline.
- **Instancia publica de Sigstore como dependencia autonoma**: desnecessaria, dado que o repositorio e
  publico e o mecanismo nativo de attestation cobre o caso sem dependencia adicional.
- **Substituicao do hook de cliente por framework de terceiros**: ver NFR-001.

## Decisoes registadas

Tomadas pelo proprietario em 2026-09-20, apos medicao, e vinculantes para as fatias subsequentes.

**Sequenciamento do veredicto.** A substituicao de `last_verified_commit` por `last_verified_tree`
precedeu a attestation. Fundamento medido: a tree hash e funcao exclusiva do conteudo e sobrevive ao
squash, dado que `strict_required_status_checks_policy` esta activo e obriga a branch a estar
actualizada perante a base. A medida fechou a mecanica do squash e **nao satisfez a FR-006**, por
manter o campo escrito e lido pelo executor da entrega.

**Realocacao concluida da raiz de confianca** (autorizada pelo proprietario em 2026-09-21, apos a
medicao abaixo). A tree tambem nao sobreviveu: o commit que regista o veredicto altera a arvore
sobre a qual o veredicto e emitido, medido na execucao 35535830710, e oito execucoes consecutivas de
push em `main` falharam por essa razao (35525340039 a 35553187426). A condicao e geral -- um registo
produzido dentro da transaccao que descreve falsifica aquilo que afirma -- e nao admite correccao
dentro da arvore, dado que a escrita e ela propria conteudo. Em consequencia, `quality.yml` emite
attestation assinada pela identidade OIDC da execucao, com o digest do conteudo como sujeito
(`actions/attest-build-provenance`, fixado por SHA, sob `id-token: write` e `attestations: write`);
`delivery.py merge` recusa conteudo sem veredicto assinado; e ambos os campos de estado passam a
cache de leitura, reportados quando desactualizados e sem constituir portao.

Limites declarados da realocacao, medidos e nao presumidos: a attestation exige repositorio publico
ou plano que a inclua, de modo que o veredicto e emitido apenas quando o repositorio e publico, e
`attestation.repository_identity` pergunta-o ao GitHub antes de qualquer portao o exigir; projecto
derivado com `ci: none` nao possui identidade de execucao e mantem o mecanismo anterior, conforme a
FR-020.

**O que a assinatura prova, e o que nao prova.** Prova que uma execucao de um workflow naquele
caminho, neste repositorio, em runner do GitHub, assinou aqueles bytes, e que o executor da entrega
nao a consegue forjar -- que e a separacao que a FR-006 exige e que o campo de estado nunca deu. Nao
prova que passos esse workflow continha, porque o ficheiro do workflow viaja na branch verificada. A
verificacao, por sua vez, permanece no cliente. Ambos os vectores estao enumerados na seccao
correspondente, e o seu fecho -- trusted builder e required status check -- e decisao de topologia
pendente do proprietario, registada em aberto em vez de afirmada como coberta.

**Localizacao do controlo de ruleset.** Executa no `pre-push`, sob a credencial do operador. Limite
declarado: protege exclusivamente operacoes originadas em estacao com o hook instalado e `gh`
autenticado; operacoes originadas noutro ambiente nao sao medidas, e o servidor nao impoe este
controlo.

**Projectos derivados sem integracao continua.** Mantem o mecanismo anterior. A alternativa avaliada
-- proibir squash nesses projectos, forcando merge commit real, sob o qual o identificador da branch
sobrevive como segundo progenitor -- foi rejeitada por impor politica de historico a projectos que
nao a escolheram.
