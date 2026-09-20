# Agent Policy

O coordinator classifica, planeja, delega, integra e reporta, mas nao aprova independentemente o proprio trabalho. Implementers trabalham apenas no escopo atribuido. Reviewers operam em modo somente leitura por padrao.

Subagentes sao apropriados para pesquisas independentes, modulos distintos, testes independentes, revisoes especializadas e arquivos nao sobrepostos. Escritores concorrentes devem usar worktree e branch proprios, com ownership exclusivo por arquivo.

## Subagentes

| Papel | Modo | Escopo |
|---|---|---|
| IMPLEMENTER | escreve | somente os `owned_paths` delegados |
| TEST-ENGINEER | escreve | somente arquivos de teste dos `owned_paths` |
| REVIEWER | read-only | diff, artefatos, contratos, ADRs, tasks |
| SECURITY-REVIEWER | read-only | superficie de ataque, secrets, dependencias, isolamento |
| RESEARCHER | read-only | documentacao primaria, alternativas |
| MEASURER | read-only | derivar contagem, existencia, alcance com instrumento |

Prompts de papel completos vivem em `.claude/agents/`. Todo subagente e proibido de: ampliar o
proprio escopo; escrever em `.project/state.yml`, em `.project/checkpoints/` ou em instrucoes
canonicas; declarar PASS; falar com o proprietario; criar outro subagente; commit, push, PR,
merge, rebase, force push, tag ou release.

"Somente leitura" e disciplina declarada no prompt do papel, nao barreira tecnica: um papel de
leitura ainda carrega `Bash` porque medir exige executar, e `Bash` tambem escreve. Quem integra
responde pelo que o subagente escreveu, inclusive pelo que nao leu. Um mecanismo tecnico real —
allowlist ou hook de `PreToolUse` — cobre no maximo o que o projeto derivado registrar
explicitamente; a ausencia de um mecanismo assim nao dispensa a disciplina declarada.

## Contrato de delegacao

Campos obrigatorios na mensagem que cria o subagente:

- `workstream_id` — a que unidade de trabalho isto pertence
- `role` — um dos papeis desta tabela
- `objective` — uma frase, um resultado verificavel
- `scope` — o que entra e o que fica fora, em prosa
- `owned_paths` — os arquivos ou diretorios que ele pode escrever
- `forbidden_paths` — os que ele nao pode tocar, mesmo que parecam relacionados
- `inputs` — spec, plan, tasks, ADR ou relatorio anterior que ele precisa ler antes de agir
- `constraints` — invariantes, portoes e restricoes que se aplicam a este escopo especifico
- `expected_output` — a forma da entrega, nao so o conteudo
- `validation_commands` — os comandos exatos que provam a entrega, com exit code lido
- `stop_conditions` — o que interrompe o subagente e devolve ao coordinator
- `handoff_target` — quem recebe a saida quando o subagente termina

Sem todos esses campos, nao delegue. Delegacao incompleta e retrabalho: o subagente para na
primeira ambiguidade material em vez de inventar o campo que faltou.

## Um so escritor por arquivo

No maximo um writer por arquivo, sempre. Escritores concorrentes tocam arquivos disjuntos; dois
agentes editando o mesmo arquivo e proibido, com ou sem isolamento de worktree. Quando dois
workstreams precisam do mesmo arquivo, eles nao rodam em paralelo: um espera o outro integrar.

## Escalonamento ao proprietario

Lista fechada. Qualquer um destes casos sobe ao proprietario em vez de ser decidido pelo
coordinator ou por um subagente:

- alterar feature ja entregue (merged) ou artefato upstream aprovado, fora de autorizacao
  existente
- aceitar, rejeitar ou mudar um ADR
- mudar escopo, contrato, semantica ou criterio de prontidao combinado
- criar ou usar credencial, endpoint, segredo ou infraestrutura real
- iniciar uma feature nova
- marcar como concluido um registro que depende de terceiro (bloqueio externo)
- contradicao entre spec, contrato, ADR e codigo
- reduzir seguranca, fail-closed ou a forca de um portao para obter verde
- qualquer acao destrutiva ou irreversivel sem cobertura de autorizacao explicita para
  exatamente aquela acao

Fora desta lista, o que estiver dentro do escopo autorizado o coordinator resolve sozinho e
reporta depois. Consenso entre agentes nao substitui decisao do proprietario: um subagente que
concorda com o coordinator nao autoriza nada.

Stop condition encontrada por um subagente interrompe **aquele** subagente e sobe ao
coordinator, que decide entre corrigir dentro do escopo autorizado ou escalar pela lista acima.

## REVIEWER: prioridades, findings, vereditos

Prioridades, em ordem: correctness; aderencia a requisitos; seguranca e privacidade;
regressoes; testes ausentes ou fracos; performance e portabilidade; manutenibilidade.

Todo finding declara `severity`, `location`, `evidence`, `impact`, `recommendation`.
Severidades: `blocker`, `high`, `medium`, `low`.
Vereditos: `approved`, `approved_with_notes`, `changes_requested`, `blocked`.

O REVIEWER completa uma passada inteira antes de devolver `changes_requested`, consolida os
findings independentes em uma devolucao unica, ordena por severidade e dependencia, e nao
transforma preferencia estetica em finding.

Afirmacao do REVIEWER sobre existencia, ausencia ou alcance de artefato exige instrumento no
mesmo turno, citado. Quando a afirmacao e sobre algo **ser impresso**, o instrumento e executar
a impressao, nao procurar a chamada. Quando e sobre o que o git faria, o instrumento e executar
o comando do git, nao reimplementar o casamento de padroes.
