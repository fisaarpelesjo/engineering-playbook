# Recovery Protocol

## Depois de interrupcao, queda de maquina ou troca de sessao

1. `uv run python scripts/resume.py` — le o estado versionado e compara com o Git real.
2. `uv run python scripts/reconcile.py` — confere `.project/state.yml` contra o checkpoint.
3. Divergencia material entre Git, estado e checkpoint: **pare antes de implementar** e registre
   a decisao necessaria.

`.project/state.yml` malformado nao se reconstroi por suposicao: pare e peca decisao do
proprietario.

## Interrupcao durante entrega Git

Antes de repetir `prepare`, `commit`, `publish` ou `merge --auto`, execute
`uv run python scripts/delivery.py status`. Repetir uma etapa de entrega sem medir o estado
anterior duplica trabalho ou publica algo incompleto.

## Perda ou mudanca inesperada de arquivo

1. Parar imediatamente. Nao executar outro comando que mute arvore, indice ou historico.
2. Medir o estado real: `git status --porcelain -uall`, `git diff` e, quando houver duvida sobre
   conteudo, hash do arquivo afetado (`git hash-object <arquivo>`).
3. Comparar essa medicao com o snapshot ou manifesto registrado antes da mudanca — o que se
   sabia estar sujo, e por quem.
4. Restaurar somente os trechos comprovadamente perdidos, um a um. Nao reescrever o arquivo
   inteiro por suposicao do que "deveria" estar la.
5. Reexecutar validacao sintatica e o teste focal do trecho tocado.
6. Reportar exatamente o que foi afetado, o que foi restaurado e com base em que evidencia.

Proibido reconstruir a partir do que os testes parecem exigir antes de medir o snapshot
disponivel. Teste falho descreve um sintoma, nao prova qual era o conteudo anterior.

## Comandos proibidos enquanto houver trabalho nao commitado

Lista fechada — nenhum destes corre sem commit, stash nomeado ou autorizacao explicita cobrindo
exatamente esta perda:

- `git checkout --`
- `git restore`
- `git reset` (qualquer modo)
- `git clean`
- `git stash` (inclusive `pop`/`drop` sobre stash alheio)
- substituicao integral de um arquivo (reescrever o arquivo inteiro em vez de editar o trecho)
- script de replay ou formatacao aplicado sobre multiplos arquivos de uma vez
- busca-e-substituicao global na arvore
- regeneracao completa de uma arvore de diretorios

Mutacao adversarial ou indevida se desfaz **reaplicando o inverso da mudanca especifica**, nunca
com um comando desta lista.

## Subagente que morreu calado

Um subagente ou processo em segundo plano pode terminar sem aviso, sem erro visivel e sem
mensagem final. Ausencia de mensagem nao e prova de progresso nem de conclusao.

Confira a **fonte** que ele deveria ter mudado (arquivo, commit, saida de comando) perto do
horario em que o trabalho deveria ter terminado, antes de assumir que ele ainda esta rodando ou
que terminou com sucesso.
