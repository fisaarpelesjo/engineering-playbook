# Plan: A issue e o contrato

## Profile

Strict. A mudanca cria um portao novo que pode recusar trabalho de terceiros, toca a esteira de
entrega e desce para todos os projectos derivados.

## Approach

1. Campo `issue` no estado e no workstream. Os sete schemas nao declaram `additionalProperties: false`
   -- medido -- logo o campo entra sem migracao; ainda assim ele e declarado no schema, porque um
   campo que o schema nao nomeia e um campo que ninguem sabe que existe.
2. Uma funcao so responde "esta issue existe e esta aberta", e os dois portoes chamam-na. Duas
   implementacoes da mesma pergunta foi o defeito que a `015` mediu no outro repositorio.
3. `publish` recusa sem cartao. E o portao local, o que da a mensagem util enquanto a pessoa trabalha.
4. `validate-ci` recusa pull request que nao feche issue existente. E o portao que ninguem esquece,
   porque corre no servidor.
5. O modelo de pull request ganha campo visivel para a issue, e as copias em `resources/` acompanham.
6. `core.py` deixa de fixar `specs/001-engineering-playbook/tasks.md` e passa a iterar `specs/*`.
7. Testes que provam a mordida, nunca a ausencia dela inferida de suite verde: uma PR sem issue
   recusada, uma com issue aberta aceite, uma com issue inexistente recusada, uma com issue fechada
   recusada.

## Numeracao

Requisitos e criterios numeram-se dentro desta spec, a partir de `001`. As tarefas usam `T1NN` para
nao colidir com as `T0NN` da `001` enquanto `state.active_task` for um campo unico para todo o
repositorio.

## Risks

- Um portao que consulta a rede falha quando a rede falha. A NFR-003 obriga a recusar nesse caso, e
  isso ira parar trabalho legitimo quando o GitHub estiver em baixo. E a troca escolhida: preferir o
  trabalho parado ao contrato silenciosamente desligado.
- O portao local e contornavel com `--no-verify` e empurrando por fora da esteira. Por isso o portao
  que conta e o da CI, e a fraqueza fica escrita na vigia.
- Passar a iterar `specs/*` pode acender divergencias que hoje ninguem ve, em specs que nunca foram
  verificadas. Isso e o portao a funcionar, e o que aparecer regista-se como achado.
