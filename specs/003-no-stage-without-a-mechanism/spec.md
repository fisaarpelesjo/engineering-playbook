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

| # | Etapa | Classificacao | Requisito que a cobre |
| --- | --- | --- | --- |
| 1 | Validacao do PRD por instrumento | CI | coberta |
| 2 | Existencia de especificacao, plano e tarefas referenciados pelo estado | CI | coberta |
| 3 | Unicidade de identificadores de tarefa em `specs/*` | CI | coberta, spec 002 |
| 4 | Precedencia da especificacao sobre o codigo | ausente | FR-014, AC-010 |
| 5 | Issue aberta previamente a entrega | CI | coberta, spec 002 |
| 6 | Vinculo sub-issue para issue mae e issue mae para especificacao | ausente | FR-015, AC-009 |
| 7 | Conformidade do nome de branch | CI | coberta |
| 8 | Proibicao de commit originado na branch por omissao | servidor | coberta |
| 9 | Ordem `start`, `prepare`, `commit`, `publish`, `merge` | parcial | FR-005, AC-003 |
| 10 | Formatacao, analise estatica, tipos e testes | servidor | coberta |
| 11 | Schemas, distribuicao e fixacao de Actions por SHA | CI | coberta |
| 12 | Pull request obrigatoria, estrategia squash, proibicao de force push | servidor | coberta |
| 13 | Checks obrigatorios para integracao | servidor | coberta |
| 14 | Execucao da bateria previamente ao push | ausente, hook nao instalado | FR-003, AC-002 |
| 15 | Integridade de `last_verified_commit` | ausente | FR-006, FR-007, AC-004 |
| 16 | Caso ignorado nao computado como aprovacao | ausente | FR-008, AC-005 |
| 17 | Medicao do commit efectivamente integrado | parcial, verificacao posterior a integracao | FR-006 |
| 18 | Sujeicao do agente automatizado ao pipeline | ausente | FR-011, AC-007 |
| 19 | Neutralizacao de injeccao de shell via titulo de pull request | CI | coberta, spec 002 |
| 20 | Cadeia de rastreabilidade entre pull request e PRD | ausente | FR-013 |

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
precede a attestation. Fundamento medido: a tree hash e funcao exclusiva do conteudo e sobrevive ao
squash, dado que `strict_required_status_checks_policy` esta activo e obriga a branch a estar
actualizada perante a base. A medida fecha a mecanica do defeito sem dependencia externa nem
ampliacao de escopo de token. **Nao satisfaz a FR-006**: o campo permanece escrito e lido pelo
executor da entrega, sem separacao de funcoes e sem prova verificavel por terceiro. A attestation
assinada permanece como fatia subsequente, condicionada a autorizacao explicita da dependencia
`actions/attest` e da ampliacao de `permissions`.

**Localizacao do controlo de ruleset.** Executa no `pre-push`, sob a credencial do operador. Limite
declarado: protege exclusivamente operacoes originadas em estacao com o hook instalado e `gh`
autenticado; operacoes originadas noutro ambiente nao sao medidas, e o servidor nao impoe este
controlo.

**Projectos derivados sem integracao continua.** Mantem o mecanismo anterior. A alternativa avaliada
-- proibir squash nesses projectos, forcando merge commit real, sob o qual o identificador da branch
sobrevive como segundo progenitor -- foi rejeitada por impor politica de historico a projectos que
nao a escolheram.
