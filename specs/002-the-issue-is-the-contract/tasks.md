# Tasks: A issue e o contrato

- T101: Declarar o campo `issue` no estado e no workstream, e nos dois schemas. Refs: FR-001.
- T102: Escrever a funcao unica que responde se uma issue existe e esta aberta, com o alcance ao GitHub isolado para o teste o substituir. Refs: FR-004, NFR-002.
- T103: `publish` recusa publicar sem cartao declarado, com mensagem acionavel. Refs: FR-002, NFR-001, AC-003.
- T104: `validate-ci` recusa pull request que nao feche issue existente e aberta. Refs: FR-003, FR-004, AC-001, AC-002, AC-004.
- T105: Campo visivel para a issue no modelo de pull request, e a copia em `resources/` igual byte a byte. Refs: FR-006, FR-005, AC-005.
- T106: `distribution.yml` e o installer levam a vigia ao projecto derivado. Refs: FR-005, AC-005.
- T107: `core.py` passa a iterar `specs/*` em vez de fixar `specs/001-engineering-playbook/tasks.md`. Refs: FR-007, AC-006.
- T108: Escrever no proprio ficheiro da vigia as maneiras conhecidas de a contornar. Refs: NFR-004.
- T109: Correr a bateria, abrir uma pull request sem issue e LER o vermelho na corrida real. Refs: AC-001, AC-002.
