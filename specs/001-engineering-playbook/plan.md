# Plan: Engineering Playbook

## Profile

Strict, porque o briefing define governanca, estado persistido, CI, seguranca operacional e contratos reutilizaveis.

## Approach

1. Criar documentos canonicos e adaptadores concisos.
2. Criar metadados versionados em `.project`.
3. Criar schemas JSON para YAML operacional.
4. Implementar scripts Python usando PyYAML e jsonschema.
5. Criar perfis de workflow e stack.
6. Criar fixtures e testes cobrindo validacao, estado, retomada, reconciliacao e checkpoint.
7. Executar format, lint, typecheck, testes, verify, doctor, resume, reconcile e checkpoint.
8. Fazer revisao somente leitura e convergencia final.

## Risks

- Repositorio inicial sem `HEAD`; scripts devem tratar como `unborn`.
- CI usa acoes de terceiros com politica documentada em vez de SHA fixo.
- Spec Kit nao e instalado automaticamente; a versao e fixada para uso externo.

