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
7. Criar o Project Requirements Document — PRD como fonte mestre anterior ao Spec Kit.
8. Integrar o PRD ao bootstrap sem sobrescrita silenciosa.
9. Validar regras objetivas do PRD sem transformar Markdown em linguagem rigida.
10. Implementar esteira segura de entrega Git em `scripts/delivery.py`.
11. Criar CI de policy de entrega e ruleset declarativo para main.
12. Executar format, lint, typecheck, testes, verify, doctor, resume, reconcile e checkpoint.
13. Fazer revisao somente leitura e convergencia final.

## Risks

- Repositorio inicial sem `HEAD`; scripts devem tratar como `unborn`.
- CI usa acoes de terceiros com politica documentada em vez de SHA fixo.
- Spec Kit nao e instalado automaticamente; a versao e fixada para uso externo.
- Validacao semantica de requisitos continua sendo revisao humana; automacao cobre apenas regras objetivas.
- Operacoes remotas da esteira nao podem ser validadas localmente sem autorizacao; testes cobrem guardas e comandos construidos.
