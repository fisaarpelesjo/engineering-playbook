# Plan: Nenhuma etapa sem mecanismo

## Profile

Strict. A implementacao introduz pontos de enforcement que rejeitam alteracoes, altera a raiz de
confianca do veredicto de conformidade e propaga-se a todos os projectos derivados do template.

## Principio ordenador

Instrucao textual nao constitui controle sobre agente automatizado; apenas mecanismo executavel o
constitui. Documento de processo que prescreve a utilizacao do pipeline e prescricao, e um agente que
invoque `git commit` directamente executa a operacao. Medicao de 2026-09-20: a operacao ocorreu tres
vezes, sem deteccao por qualquer controle.

Em consequencia, cada requisito nomeia o mecanismo que o sustenta. Quatro classes existem, com
propriedades distintas de resistencia a bypass:

1. **Documentacao de processo** (`AGENTS.md`, `CLAUDE.md`): nao constitui controle. Funcao exclusiva de
   comunicacao de intencao.
2. **Hook de cliente** via `core.hooksPath`: constitui controle. Vetores de bypass conhecidos:
   `--no-verify` e reconfiguracao de `core.hooksPath`. Ambos documentados no proprio hook.
3. **Hook de harness** do tipo `PreToolUse`: constitui controle sobre agente automatizado, dado que a
   avaliacao ocorre no harness, anteriormente a execucao da ferramenta, e nao depende de decisao do
   modelo. Alcance limitado a estacao de trabalho que possua a configuracao.
4. **Ruleset no servidor**: constitui controle sobre todos os clientes, independentemente de
   configuracao local. Aplicado em 2026-09-20 sobre a branch por omissao.

Requisito sem mecanismo associado e intencao, e e rejeitado na revisao desta especificacao conforme
FR-010.

## Approach

1. **Reconciliacao entre configuracao declarada e aplicada.** O ruleset foi aplicado em 2026-09-20 com
   `required_approving_review_count: 0`, por decisao registada do proprietario, enquanto
   `.github/rulesets/main.yml` mantem `1` e a anotacao de proposta nao aplicada. O ficheiro passa a
   representar a configuracao efectiva, e um controle compara ficheiro e API.
2. **Activacao dos hooks de cliente.** O bootstrap configura `core.hooksPath`; `doctor` e `verify`
   retornam falha quando o valor nao referencia os hooks do repositorio. Inclui a arbitragem do
   `.pre-commit-config.yaml`, cuja coexistencia e incompativel por desenho: o framework recusa
   instalacao quando `core.hooksPath` esta definido
   (https://github.com/pre-commit/pre-commit/issues/3630).
3. **Sujeicao do agente automatizado.** Controle de harness que rejeita invocacao de escrita em git
   fora do pipeline, anteriormente a execucao da ferramenta.
4. **Imposicao da ordem das etapas.** Cada etapa emite recibo contendo identificador de commit e
   instante; a etapa subsequente rejeita a execucao na ausencia do recibo do antecessor. A transicao
   `prepare` para `commit` ja implementa esta verificacao; `start`, `publish` e `merge` nao.
5. **Realocacao da raiz de confianca.** O workflow `quality.yml` emite attestation assinada pela
   identidade OIDC da execucao, com o digest do conteudo como sujeito. O repositorio e publico,
   verificado por `gh api repos/:owner/:repo --jq .visibility`, de modo que
   `actions/attest-build-provenance` nao impoe requisito de plano.
   `last_verified_commit` e reclassificado como cache de leitura.
6. **Classificacao de casos ignorados.** Caso de teste ignorado sem justificativa declarada deixa de
   ser computado como aprovacao, por asserçao sobre o relatorio de execucao.
7. **Rastreabilidade e precedencia da especificacao.** Verificacao da cadeia pull request, sub-issue,
   issue mae, `specs/NNN/`, requisito do PRD, e rejeicao de alteracao de codigo nao associada a
   especificacao activa.
8. **Cobertura adversarial.** Suite que exercita cada vetor de bypass enumerado na matriz de cobertura,
   com verificacao por teste de mutacao de controle.

## Sequenciamento

A ordem de implementacao e determinada por custo e por dependencia de enforcement, nao por afinidade
tematica:

1. Itens 1 e 2: custo nulo em dependencias e eliminam duas classificacoes `ausente` da matriz.
2. Item 3: precede os demais porque, ate a sua vigencia, o proprio agente que implementa esta
   especificacao permanece capaz de contornar os controles que ela introduz.
3. Item 4: estabelece a precondicao estrutural para os itens 5 e 7, que pressupoem etapas ordenadas.
4. Itens 5 a 8: alteracao de arquitectura e cobertura, sobre base ja controlada.

## Risks

- A introducao de attestation cria periodo de coexistencia entre duas fontes de veredicto. A FR-007
  determina explicitamente qual prevalece, de modo a impedir estado ambiguo.
- O ruleset aplicado nao define actores de bypass: `current_user_can_bypass` retorna `never`,
  verificado na resposta da API. Bloqueio da integracao continua implica edicao do ruleset como unico
  caminho de recuperacao. Condicao registada como consequencia aceite.
- O controle de harness reside na configuracao da estacao de trabalho, nao no repositorio remoto.
  Estacao sem a configuracao mantem apenas o hook de cliente e o enforcement do servidor. O alcance e
  declarado conforme FR-012, de modo a nao inferir garantia inexistente.
- A imposicao de ordem por recibo pode rejeitar fluxos legitimos hoje executados fora do pipeline. O
  tratamento previsto e a incorporacao da etapa ausente ao pipeline, nao a reducao do controle.
