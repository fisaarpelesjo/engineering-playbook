# Specification: A issue e o contrato

## Contexto medido

Em 2026-09-20 o proprietario ordenou que tudo o que se abre neste repositorio abre tambem uma issue
no GitHub, e escolheu o GitHub Issues como quadro de trabalho. Nesse mesmo dia foram abertas doze
issues, `#7` a `#18`, e todas foram ligadas a mao.

Nada no repositorio verifica isso. A palavra `issue` aparece em quatro sitios e nenhum morde:
`.github/pull_request_template.md:7` dentro de um comentario HTML, `CONTRIBUTING.md:3` como prosa
sobre o nome da branch, `src/engineering_playbook/delivery.py:80` a validar que o numero E um numero
e nunca que a issue existe, e `profiles/workflows/lite.yml` como descricao de perfil. O job
`delivery-policy` valida nome de branch e titulo de PR; o ruleset exige uma revisao e os dois checks.
Ninguem pergunta se ha issue.

Uma regra que so uma pessoa aplica fica verde no dia em que essa pessoa esquece.

## Requirements

- FR-001: A fatia declara a sua issue no estado versionado, e o valor e o numero de uma issue que existe.
- FR-002: A esteira recusa publicar uma fatia sem cartao, com mensagem que diz o que fazer.
- FR-003: A CI recusa uma pull request que nao feche uma issue existente, no job `delivery-policy`.
- FR-004: A verificacao de existencia consulta o GitHub; um numero com a forma certa e uma issue fechada ou inexistente nao satisfazem o contrato.
- FR-005: O contrato chega ao projecto derivado: a copia em `src/engineering_playbook/resources/` e o `distribution.yml` carregam-no, senao ele vale so neste repositorio.
- FR-006: O modelo de pull request pede a issue em campo visivel, nao em comentario HTML.
- FR-007: O verificador cobre `specs/*` e nao apenas `specs/001-engineering-playbook`.
- FR-008: O cartao tem dois niveis: a spec abre a issue mae, cada fatia entregavel abre sub-issue ligada a ela, e a pull request fecha a SUB-issue.

## Non-Functional Requirements

- NFR-001: A vigia diz sempre o que falta e como resolver; nunca falha em silencio nem com texto generico.
- NFR-002: Nenhuma chamada de rede corre dentro de teste; o alcance ao GitHub e substituido no teste.
- NFR-003: Uma vigia que nao consegue medir recusa em vez de passar. Ambiente indisponivel nao e verde.
- NFR-004: A fraqueza conhecida de cada vigia fica escrita no proprio ficheiro da vigia.

## Acceptance Criteria

- AC-001: Uma pull request sem issue ligada fica VERMELHA no `delivery-policy`, medida numa corrida real e nao numa suite.
- AC-002: Uma pull request que fecha uma issue aberta fica verde no mesmo job.
- AC-003: `publish` sem cartao declarado sai com codigo nao-zero e nao cria nem edita pull request.
- AC-004: Um numero de issue que nao existe, ou que ja esta fechada, e recusado pelos dois portoes.
- AC-005: O ficheiro instalado num projecto derivado contem a mesma vigia, byte a byte.
- AC-006: `verify` deteta um ID de tarefa duplicado dentro de `specs/002-the-issue-is-the-contract/tasks.md`, provando que deixou de olhar so para a `001`.

## Fora de escopo

Criar o GitHub Project, as suas colunas e mover o cartao sozinho ao abrir, publicar e fundir. Isso e a
segunda fatia da `#8`, sobre terreno ja firme. O token ja tem o alcance `project`, medido com
`gh project list` a sair 0, portanto nada disto fica bloqueado por credencial.

## Grao do cartao

Decidido pelo proprietario em 2026-09-20, e espelha o que ele ja pratica no repositorio do produto,
onde `SCRUM-1982` e a spec e `SCRUM-1983` a `SCRUM-1988` sao as fatias.

A spec abre a issue mae. Cada fatia que cabe numa pull request abre uma sub-issue ligada a ela. A
pull request fecha a SUB-issue, nunca a mae -- se fechasse a mae, a spec fecharia na primeira entrega
e as fatias seguintes ficariam orfas. A mae fecha quando a ultima filha fechar.

As tarefas de `tasks.md` que nao sao entregaveis por si nao levam cartao; elas descrevem o trabalho
dentro de uma fatia.

Medido no proprio dia em que isto foi decidido: `gh issue edit` nao tem opcao de sub-issue nesta
versao (`gh 2.92.0`), e a ligacao faz-se pela API REST, `POST /repos/{owner}/{repo}/issues/{n}/sub_issues`,
com o `id` INTERNO da filha e nao o numero dela. O campo tem de ir como inteiro -- `gh api -F`, porque
`-f` envia string e a API recusa com `422 ... is not of type integer`.
