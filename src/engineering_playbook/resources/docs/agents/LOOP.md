# LOOP.md — o ciclo de um chat unico

Um COORDINATOR — um unico chat — mede o estado real, planeja, delega, integra, valida e
reporta. Ele pode abrir subagentes para trabalho de fato independente; nao existe bastao entre
sessoes paralelas nem canal de handoff proprio para isso.

## 1. Quem trabalha

| Papel | Onde vive | Escreve na arvore? | Fala com o proprietario? |
|---|---|---|---|
| OWNER | fora do sistema | sim | e ele |
| COORDINATOR | o unico chat | sim | sim |
| IMPLEMENTER | subagente | sim, no escopo delegado | nao |
| REVIEWER | subagente | nao (read-only) | nao |
| TEST-ENGINEER | subagente | sim, somente testes | nao |
| SECURITY-REVIEWER | subagente | nao | nao |
| RESEARCHER | subagente | nao | nao |
| MEASURER | subagente | nao | nao |

Os seis papeis de subagente estao definidos em `.claude/agents/`. O COORDINATOR responde por
tudo que qualquer subagente produziu, inclusive pelo que nao leu.

## 2. O ciclo

Cada unidade de trabalho passa pelas etapas abaixo, na ordem, sem pular nenhuma:

1. **OBSERVAR** — `uv run python scripts/resume.py`, `git status --porcelain -uall`,
   `git log -1`, ler spec/plan/tasks e o escopo autorizado. Divergencia material entre Git,
   `.project/state.yml` e checkpoint **para aqui**.
2. **PLANEJAR** — objetivo unico, arquivos permitidos, invariantes, ultimo verde conhecido,
   proximo comando, condicao de parada. Decidir quantos subagentes: zero e resposta legitima e
   frequente.
3. **FOTOGRAFAR** — manifesto antes de mudar: status porcelain, arquivos que pretende alterar,
   hash de cada arquivo ja modificado, untracked, testes baseline. Havendo trabalho nao
   commitado, snapshot recuperavel **fora** do repositorio antes de tocar o arquivo.
4. **ALTERAR** — edicao cirurgica, uma unidade coerente, sem refactor oportunista. Reler o
   trecho alterado e conferir o diff imediatamente depois de cada alteracao.
5. **VERIFICAR** — testes em camadas: validacao sintatica, teste focal, modulo, pacote,
   upstream, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, guards, e a
   suite completa (`uv run pytest`) somente quando a unidade estiver estavel.
6. **REVISAR ISOLADAMENTE** — subagente REVIEWER, contexto separado, read-only na arvore
   compartilhada. Plantio adversarial somente em copia temporaria ou worktree fora da raiz.
7. **COMMITAR** — depois de PASS e com autorizacao explicita para operacao Git, commit pequeno
   via `uv run python scripts/delivery.py`, conforme `ENGINEERING.md`.

Estados possiveis de uma unidade: `WORKING`, `READY_FOR_REVIEW`, `CHANGES_REQUESTED`, `PASS`,
`OWNER_DECISION_REQUIRED`, `STOPPED`. Eles vivem em `.project/state.yml`, campo `unit_status`.

## 3. Quando abrir subagente

Abra quando o trabalho for **de fato independente** e o beneficio existir:

- pesquisa e medicao (read-only e sempre paralelizavel)
- pacotes ou modulos distintos, com arquivos que nao se sobrepoem
- suites de teste independentes
- revisao especializada (REVIEWER, SECURITY-REVIEWER)

Nao abra para tarefa trivial, para duas metades da mesma mudanca, para arquitetura ainda
indefinida, nem por paralelismo sem beneficio.

**Revisao independente e obrigatoria** no perfil `standard` e `strict`, e corre em subagente
REVIEWER.

Diga com precisao o que essa independencia **e** e o que ela **nao e**. Ela e contexto novo: o
REVIEWER nao herda a conviccao de quem escreveu o codigo, e por isso mede em vez de confirmar.
Ela **nao** e barreira de escrita: o subagente roda com as permissoes desta sessao, o `Bash`
que ele usa para medir tambem escreve, e o transcript dele nao passa pelos olhos do proprietario
antes da integracao. O "somente leitura" dos papeis de revisao e disciplina escrita em
`docs/agents/AGENT_POLICY.md`, nao uma trava tecnica geral. Quem integra responde por isso.

## 4. Contrato de delegacao

Todo subagente recebe, por escrito, na mensagem que o cria, os campos listados em
`docs/agents/AGENT_POLICY.md`. Sem esses campos, nao delegue.

## 5. Isolamento

- No maximo **um writer por arquivo**. Na arvore compartilhada, escrita e sempre sequencial.
- Escrita paralela exige worktree propria por writer, **fora da raiz do repositorio**
  (worktree dentro da raiz e coletada pelo pytest e aparece aos guards como arquivo novo).
- Worktree exige ambiente proprio, com os pacotes reinstalados a partir daquela arvore. Um
  ambiente instalado em modo editavel apontando para a arvore principal mede o codigo errado
  quando usado a partir de uma worktree; verde nessa condicao nao prova nada.
- Validacao rodada dentro de arvore isolada **nao** e evidencia para nenhum portao que leia a
  working tree por `git status` ou `git diff`.
- Nao deixar worktree orfa depois da integracao.

## 6. Integracao

- Ler o **diff** de cada subagente antes de integrar. Relatorio de subagente nao substitui diff.
- Depois de integrar, rodar as validacoes completas no estado consolidado, na arvore principal.
- Relatorio de subagente nunca e evidencia final.

## 7. Parada em OWNER

Duas paradas devolvem o bastao ao proprietario: `PASS` e `OWNER_DECISION_REQUIRED`.

Escalonamento obrigatorio: tocar arquivo upstream nao autorizado; expor simbolo privado;
contradicao entre spec, contrato, ADR e codigo; alterar contrato ou evento de auditoria
aprovado; mudar ordem de gates; reduzir seguranca ou fail-closed; nova dependencia externa;
teste aprovado com premissa aparentemente expirada; qualquer acao reservada ao proprietario e
ainda nao autorizada — inclusive as listadas em `ENGINEERING.md` e em
`docs/agents/OWNER_STANDING_ORDERS.md` quando este arquivo existir no projeto derivado.

O pacote de decisao chega pronto, com: pergunta decisoria em uma frase; causa comprovada e
arquivos envolvidos; duas a quatro opcoes mutuamente exclusivas; impacto, risco e custo por
opcao; a opcao recomendada em primeiro lugar; justificativa tecnica. A apresentacao usa
`AskUserQuestion` como menu navegavel quando a ferramenta existir — nunca tabela, lista
Markdown ou letras A/B/C em texto comum nesse caso. Maximo tres perguntas por chamada.

Decisao e binaria: ou e necessaria, e entra em `OWNER_DECISION_REQUIRED` com menu; ou nao e
necessaria, e nao chega ao proprietario de forma alguma. "Decisao sua, opcional" nao existe.

Tudo que estiver dentro do escopo autorizado o COORDINATOR resolve sozinho e reporta depois.

## 8. Antes de parar

- Confirmar a ultima tarefa realmente concluida.
- Confirmar arquivos fora do escopo: zero, ou listar cada um.
- Confirmar readiness e registros externos abertos.
- Confirmar working tree e acoes Git executadas.
- Gravar checkpoint (`uv run python scripts/checkpoint.py`).
- Dizer explicitamente qual autorizacao e necessaria em seguida.

## 9. Limite de retrabalho

Segunda ocorrencia da mesma classe de erro: parar a correcao pontual, achar a causa sistemica e
criar regra ou teste que elimine a classe inteira. Terceira ocorrencia: a unidade nao continua
ate a prevencao automatizada existir. Ver a tabela de erros medidos em `ENGINEERING.md`.
