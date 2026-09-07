# Engineering Process

## Principios

- O repositorio e a fonte de verdade.
- Mudancas nao triviais exigem intencao, escopo e criterios verificaveis.
- Nenhuma tarefa termina sem evidencia real das verificacoes aplicaveis.
- Regras canonicas ficam em um unico lugar e adaptadores apenas referenciam.
- O processo e proporcional ao risco.
- Agentes nao ampliam escopo, publicam, apagam dados ou assumem permissoes.
- Produtos derivados nao dependem de LLM.
- Evidencia nunca e inventada.

## Sequencia Canonica

1. Classificar o perfil de workflow.
2. Criar ou atualizar specification.
3. Clarificar incertezas materiais.
4. Criar plano.
5. Quebrar em tarefas rastreaveis.
6. Implementar com TDD seletivo quando aplicavel.
7. Validar com comandos reais.
8. Revisar em modo somente leitura.
9. Convergir briefing, spec, plano, tarefas, codigo e evidencia.
10. Gerar checkpoint.

## Definition of Done

Uma entrega so e concluida quando requisitos e criterios foram satisfeitos, testes e verificacoes aplicaveis passaram, documentacao foi atualizada, limitacoes foram registradas, revisao e convergencia foram feitas, e `.project/state.yml` mais o checkpoint final estao validos.

## Git

Use trunk based development com branches curtas. Nao faca commit, push, merge, tag ou release sem autorizacao explicita. Commits e titulos de PR seguem Conventional Commits em ingles.

