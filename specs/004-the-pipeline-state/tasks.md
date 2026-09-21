# Tasks: O estado do pipeline

- T301: Substituir a regra de atribuicao de identificador de checkpoint por uma que nao dependa da contagem de ficheiros da arvore local. Mecanismo: funcao unica de atribuicao, exercitada por teste que constroi duas arvores no mesmo estado. Refs: FR-003, AC-003.
- T302: Implementar rejeicao de identificador duplicado com conteudo divergente, tolerando o formato anterior conforme NFR-002. Mecanismo: controlo em `verify`. Refs: FR-004, AC-004.
- T303: Determinar e implementar o momento de escrita da contabilidade de modo a que o estado final de uma fatia seja deterministico e documentado. Mecanismo: alteracao em `command_commit` e teste sobre o estado da arvore apos o ciclo. Refs: FR-001, AC-001.
- T304: Sinalizar explicitamente a auto-invalidacao de uma `prepare` no momento em que ocorre, com a accao correctiva nomeada. Mecanismo: verificacao em `prepare`/`commit` e teste adversarial. Refs: FR-002, AC-002.
- T305: Declarar, junto ao codigo que escreve cada artefacto de contabilidade, o momento de escrita e a condicao de invalidacao. Mecanismo: texto adjacente ao codigo, verificado por teste que o le. Refs: FR-005, AC-005.
- T306: Confirmar que cada requisito desta especificacao nomeia o mecanismo que o torna verificavel. Mecanismo: revisao manual, unico item sem mecanismo automatizado, registado como tal. Refs: NFR-001.
