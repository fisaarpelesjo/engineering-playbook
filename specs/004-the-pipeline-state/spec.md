# Specification: O estado do pipeline

## Problema

O pipeline de entrega escreve a propria contabilidade durante a execucao, e essa contabilidade passa
entao a contradizer a execucao que descreve. A causa e unica; as manifestacoes sao tres e foram
medidas em 2026-09-20 ao longo de sete fatias entregues.

| Observacao | Origem medida |
| --- | --- |
| Toda fatia termina com arvore suja | `delivery.py:459-494`: `git commit` executa, e so depois `record_verified_commit` escreve `.project/state.yml` |
| Uma `prepare` pode ser invalidada por artefacto proprio | `delivery.py:294-312`: `prepare_is_fresh` rejeita quando o HEAD registado difere do actual; o checkpoint que a `prepare` gera provoca isso se for integrado num commit separado |
| Identificadores de checkpoint colidem entre branches | `core.py:579-583`: `next_checkpoint_id` conta ficheiros do diretorio local, sem estado partilhado |

O padrao comum: **o artefacto de registo e produzido dentro da transacao que ele descreve**, e a sua
producao altera aquilo que ele afirma. O mesmo padrao, um nivel acima, produziu o defeito da spec 003:
o commit que regista o veredicto altera a arvore sobre a qual o veredicto e emitido.

## Definicoes

- **Contabilidade**: artefactos que registam a execucao do pipeline -- `.project/state.yml`,
  `.project/checkpoints/`, `.project/delivery/` -- em oposicao ao conteudo entregue.
- **Auto-invalidacao**: condicao em que a producao de um registo torna falso o proprio registo.

## Requirements

- FR-001: A escrita de contabilidade nao deixa a arvore de trabalho em estado que o operador tenha de interpretar. O estado final de uma fatia e determinado e documentado.
- FR-002: Uma etapa nao e invalidada por artefacto que ela propria produziu. Se a invalidacao for inevitavel, e sinalizada explicitamente em vez de detectada por comparacao subsequente.
- FR-003: Identificadores de checkpoint sao unicos por repositorio, nao por arvore de trabalho. Duas branches partindo do mesmo estado nao produzem o mesmo identificador.
- FR-004: A colisao de identificadores, caso ocorra, e detectada por controlo executavel e nao por conflito durante integracao.
- FR-005: Cada artefacto de contabilidade declara, no proprio ficheiro ou no codigo que o escreve, em que momento do fluxo e escrito e o que invalida.

## Non-Functional Requirements

- NFR-001: Nenhum requisito desta especificacao e satisfeito por convencao de operacao. Cada um nomeia o mecanismo que o torna verificavel, conforme FR-010 da especificacao 003.
- NFR-002: As alteracoes preservam a compatibilidade com repositorios existentes: contabilidade ja escrita permanece legivel, e identificadores ja atribuidos nao sao reescritos.
- NFR-003: Teste que apenas confirma a presenca do controlo nao satisfaz esta especificacao. Satisfaz-na o teste cuja falha e induzida pela remocao do controlo.

## Acceptance Criteria

- AC-001: Concluida uma fatia pelo pipeline, a arvore de trabalho encontra-se em estado declarado e verificavel, sem exigir julgamento sobre o que descartar.
- AC-002: Uma `prepare` seguida da integracao do proprio checkpoint nao produz rejeicao silenciosa na etapa seguinte.
- AC-003: Duas arvores de trabalho partindo do mesmo estado produzem identificadores de checkpoint distintos.
- AC-004: Um identificador duplicado com conteudo divergente e rejeitado por controlo antes de alcancar integracao.
- AC-005: Para cada artefacto de contabilidade existe registo escrito do momento de escrita e da condicao de invalidacao.

## Evidencia historica

A colisao descrita na FR-003 foi observada, nao inferida: durante um rebase, `CP-20260919-001.yml`
apresentou conflito `add/add` entre duas branches criadas no mesmo dia, cada uma com conteudo
proprio. A branch que continha a versao divergente foi posteriormente removida, pelo que a evidencia
directa deixou de ser alcancavel por `git log --all`; a medicao subsequente localizou seis
identificadores atribuidos por mais de um commit, todos com conteudo identico. O mecanismo esta
demonstrado; a instancia divergente especifica nao e reproduzivel a partir do estado actual do
repositorio.

## Exclusoes de escopo

- A integridade do veredicto de conformidade permanece na especificacao 003. Esta especificacao trata
  do momento e da unicidade dos registos, nao da sua autoria.
- A ausencia de cobertura de teste em `scripts/agent_watch/` nao pertence a esta especificacao: e
  lacuna de cobertura de uma ferramenta, sem relacao com contabilidade de pipeline.
