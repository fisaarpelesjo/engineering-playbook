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
2. Ler ou criar o Project Requirements Document — PRD quando houver requisitos de produto.
3. Confirmar que lacunas, contradicoes e requisitos nao verificaveis estao marcados.
4. Criar ou atualizar specification do Spec Kit apenas para recortes aprovados.
5. Clarificar incertezas materiais.
6. Criar plano.
7. Quebrar em tarefas rastreaveis.
8. Implementar com TDD seletivo quando aplicavel.
9. Validar com comandos reais.
10. Revisar em modo somente leitura.
11. Convergir PRD, specs, plano, tarefas, codigo e evidencia.
12. Gerar checkpoint.

## Project Requirements Document — PRD

O PRD em `docs/requirements/project-requirements.md` e a fonte mestre de requisitos do produto. Ele deve ser preenchido pelo proprietario antes do Spec Kit quando a mudanca envolver produto, comportamento, usuarios, dominio, contratos, dados, operacao ou criterios de sucesso.

Agentes devem ler o PRD antes de executar `specify`, `plan`, `tasks` ou `implement`, preservar IDs estaveis, nao inventar informacoes ausentes e pedir decisao humana apenas para ambiguidades materiais. Specs do Spec Kit referenciam IDs do PRD e nao substituem a fonte mestre.

## Definition of Done

Uma entrega so e concluida quando requisitos e criterios foram satisfeitos, testes e verificacoes aplicaveis passaram, documentacao foi atualizada, limitacoes foram registradas, revisao e convergencia foram feitas, rastreabilidade com PRD foi preservada quando aplicavel, e `.project/state.yml` mais o checkpoint final estao validos.

## Git

Use trunk based development com branches curtas. Nao faca commit, push, merge, tag ou release sem autorizacao explicita. Commits e titulos de PR seguem Conventional Commits em ingles.

Entregas Git devem passar por `scripts/delivery.py`: start, prepare, commit, publish, merge --auto e status. `prepare` executa validacoes locais, revisao somente leitura, convergence e checkpoint, mas nao faz commit nem operacao remota. `publish` e `merge --auto` exigem comando explicito e autorizacao remota.

## Erros que ja custaram uma volta

Cada linha desta tabela e medida: um agente cometeu o erro, o portao apanhou, e o conserto
custou uma volta inteira do ciclo. Nao e um repositorio de conselhos; e o ledger dos erros que
este repositorio especifico ja pagou. Comeca vazio -- este repo nao herda o ledger do derivado.

| # | erro medido | regra que ficou | data |
|---|---|---|---|

<!-- | 1 | erro medido, curto e factual | a regra operacional que ficou dele | AAAA-MM-DD | -->

### A regra da terceira ocorrencia

A mesma classe de erro que volta tres vezes muda de tratamento:

1. Primeira ocorrencia: conserta-se.
2. Segunda ocorrencia da mesma classe: conserta-se e registra-se a classe nesta tabela.
3. Terceira ocorrencia: a unidade nao continua ate existir prevencao automatizada -- um portao
   que apanhe a classe inteira, nao so o caso que a revelou.
