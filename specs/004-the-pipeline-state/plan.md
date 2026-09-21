# Plan: O estado do pipeline

## Profile

Standard. A implementacao altera o momento de escrita de artefactos de contabilidade e a atribuicao
de identificadores. Nao altera a raiz de confianca do veredicto, nem introduz dependencia externa,
nem amplia escopo de credencial.

## Approach

1. **Identificadores por conteudo, nao por contagem local.** `next_checkpoint_id` conta ficheiros do
   diretorio; duas arvores no mesmo estado atribuem necessariamente o mesmo numero. A substituicao
   deriva o identificador de algo que difere entre as duas execucoes -- o commit em que assenta, o
   instante com precisao suficiente, ou um sufixo curto do digest do conteudo do proprio checkpoint.
   O criterio de escolha e a unicidade sem coordenacao entre arvores, e a legibilidade do resultado
   perde para a unicidade quando as duas colidirem.
2. **Controlo de duplicacao.** Identificador repetido com conteudo divergente passa a ser rejeitado
   por `verify`, e nao descoberto como conflito durante um rebase.
3. **Momento da escrita da contabilidade.** `command_commit` cria o commit e escreve o estado a
   seguir, o que deixa a arvore suja por construcao. Avaliar: escrever antes e corrigir apos, escrever
   uma unica vez apos o ciclo completo, ou declarar o estado final como esperado e verifica-lo. A
   opcao escolhida e registada com a razao; a FR-001 exige determinismo e documentacao, nao uma
   implementacao especifica.
4. **Auto-invalidacao explicita.** Quando a integracao do checkpoint de uma `prepare` invalida essa
   `prepare`, a condicao e sinalizada no momento em que ocorre, com a accao correctiva nomeada, em vez
   de aparecer como rejeicao na etapa seguinte.
5. **Declaracao por artefacto.** Cada artefacto de contabilidade passa a declarar, junto ao codigo que
   o escreve, o momento de escrita e a condicao de invalidacao.

## Sequenciamento

O item 1 precede o item 2: um controlo de duplicacao sobre uma regra que produz duplicados
deterministicamente rejeitaria trabalho legitimo. Os itens 3 e 4 sao independentes entre si e podem
ser entregues em qualquer ordem. O item 5 acompanha cada um dos anteriores, nao constitui fatia
propria.

## Risks

- A alteracao do formato de identificador afecta ficheiros ja existentes. A NFR-002 determina que
  identificadores atribuidos nao sao reescritos, pelo que o controlo de duplicacao tem de tolerar o
  formato anterior sem o considerar defeito.
- Alterar o momento de escrita do estado toca o caminho que produz toda entrega. Uma regressao aqui
  manifesta-se em cada fatia subsequente, pelo que os testes precedem a alteracao.
- A evidencia directa da colisao historica nao e reproduzivel a partir do estado actual do
  repositorio. O teste que demonstra a FR-003 constroi a condicao em vez de a observar, e isso fica
  registado no proprio teste para que ninguem o leia como observacao de campo.
