# Segurança — MVP Encontrei

Esta pasta reúne o trabalho de segurança feito sobre o MVP: uma revisão manual, uma auditoria feita com a skill de agente [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) e as **correções aplicadas** a partir das duas. A lista de correções, o teste de regressão de cada uma e o que ficou pendente estão em [correcoes.md](correcoes.md).

## Conteúdo

| Arquivo | O que é |
|---|---|
| [correcoes.md](correcoes.md) | Correções aplicadas para V01–V15 e NV01–NV09, com o teste de cada uma e as pendências |
| [relatorio-vulnerabilidades.md](relatorio-vulnerabilidades.md) | Revisão manual do código. Achados V01–V15, cada um com severidade e correção sugerida |
| [auditoria-skill-run-1/REPORT.md](auditoria-skill-run-1/REPORT.md) | Relatório principal da auditoria com a skill, em português |
| [auditoria-skill-run-1/NEEDS-VALIDATION.md](auditoria-skill-run-1/NEEDS-VALIDATION.md) | As 9 pistas (NV01–NV09) com trace no código e plano de teste, em inglês |
| [auditoria-skill-run-1/FINDINGS-DETAIL.md](auditoria-skill-run-1/FINDINGS-DETAIL.md) | Achados confirmados. Vazio nesta execução |
| [auditoria-skill-run-1/architecture.md](auditoria-skill-run-1/architecture.md) | Mapa de arquitetura e fronteiras de confiança montado no reconhecimento |
| [auditoria-skill-run-1/findings.json](auditoria-skill-run-1/findings.json) | Registros estruturados das pistas no schema da skill |
| [auditoria-skill-run-1/coverage-ledger.json](auditoria-skill-run-1/coverage-ledger.json) | Ledger de cobertura: as 15 unidades revisadas, as pendentes e as adiadas |
| [auditoria-skill-run-1/run-metadata.json](auditoria-skill-run-1/run-metadata.json) | Metadados da execução: commit, perfil, orçamento e limitações do host |

## 1. Revisão manual

A revisão foi feita lendo `app.py`, `index.html`, `test_app.py` e a documentação da API. O resultado está em `relatorio-vulnerabilidades.md`, com 15 achados de severidade variada e uma correção sugerida para cada um. Os principais temas são:
- ativação de conta sem prova de posse do e-mail;
- força bruta na pergunta de verificação;
- contas seed com senhas públicas;
- token guardado em `localStorage`;
- ausência de cabeçalhos de segurança;
- limites de recurso.

## 2. Auditoria com a skill `security-audit`

### Instalação

A skill foi instalada em `.claude/skills/security-audit/`, copiada do repositório da Cloudflare com o `LICENSE` incluído. O Claude Code a carrega automaticamente neste projeto.

### Como a execução foi feita

| Item | Valor |
|---|---|
| Data | 2026-11-11 |
| Commit auditado | `ef131bb` |
| Escopo | `app.py`, `index.html`, `test_app.py`, `executar.bat`, `.gitignore`, `docs/api` |
| Perfil | `quick`: uma onda de caça, um crítico final e um verificador independente por candidato |
| Agentes | 20 no total: 4 de reconhecimento, 6 caçadores (um refeito por resposta malformada), 1 crítico e 9 verificadores |
| Status | **`incomplete`** (`validators_unavailable_on_host`) |

A skill trabalha em fases:
1. **Reconhecimento**: mapa da arquitetura, fronteiras de confiança e ledger de cobertura.
2. **Caça**: agentes isolados, cada um responsável por uma unidade do ledger.
3. **Crítico**: procura lacunas de cobertura.
4. **Verificação**: um agente novo e independente revisa cada candidato.
5. **Relatórios**.

### Limitações deste host (Windows)

- **Sem sandbox imposto pelo SO.** Não há WSL, Docker nem bwrap. A skill só permite executar código do alvo dentro de um sandbox sem rede, com o alvo montado somente para leitura e com limites de recurso. Por isso **nenhum código do MVP foi executado**, e nenhum achado pôde ser classificado como `confirmed`, já que essa classificação exige um resultado observado.
- **Validadores indisponíveis.** `validate-findings.cjs` e `validate-coverage-ledger.cjs` dependem de `O_NOFOLLOW`, que o Node não oferece no Windows. Em lugar deles foram feitas checagens estruturais manuais, que não substituem os validadores.

### Resultado

Nenhum achado foi **confirmado** e nenhum foi **rejeitado**. As **9 pistas** ficaram em `needs_validation`, ou seja, o caminho existe no código, mas falta observar o efeito:

| # | Pista | Nova em relação à revisão manual? |
|---|---|---|
| NV01 | O link de verificação vem na resposta da API e permite ativar uma conta com e-mail alheio | não |
| NV02 | A pergunta de verificação aceita tentativas ilimitadas | não |
| NV03 | Um moderador consegue suspender um Administrador pelo caminho das denúncias | **sim** |
| NV04 | `/returned` torna público um item que a moderação tinha ocultado | **sim** |
| NV05 | Dispensar denúncias reabre como `Aberto` um item resolvido, expirado ou no ponto de guarda | **sim** |
| NV06 | Contas seed com senha pública são reativadas a cada inicialização | **sim** |
| NV07 | O servidor não valida o cabeçalho `Host` (risco de DNS rebinding com credenciais admin públicas) | **sim** |
| NV08 | `LOGIN_ATTEMPTS` guarda chaves de tamanho livre para sempre | não |
| NV09 | O `PATCH` de fotos grava antes de validar e deixa arquivos órfãos | não |

As revisões de SQL injection, XSS, path traversal, autorização das rotas admin e moderação e chat não encontraram problemas. Os padrões positivos verificados estão na seção 6 do `REPORT.md`.

**Cobertura:** das 15 unidades, 4 ficaram *covered* e 9 são *candidate* (cada uma ligada a uma pista). As outras 2 foram *deferred* pelo perfil `quick`:
- revogação de estado do catálogo: desativar um domínio, um ponto de guarda ou uma categoria não afeta as contas e os itens que já existem;
- condições de corrida em verificações check-then-act sem lock.

## 3. Próximos passos sugeridos

1. Instalar o WSL (`wsl --install`) ou rodar em Linux, para que a skill tenha sandbox e validadores funcionando.
2. Rodar a skill de novo no perfil `standard`. Começar pelas 2 unidades adiadas e tentar confirmar as 9 pistas usando o plano de teste de cada uma em `NEEDS-VALIDATION.md`.
3. ~~Corrigir os achados, com testes de regressão.~~ Feito em 2026-11-11 (ver [correcoes.md](correcoes.md)). Uma nova execução da skill deve partir desse código corrigido.

## Observações

- A saída original da skill foi gerada fora do repositório, como a skill exige, em `~/security-audit-skill/MVP/run-1/`. Esta pasta guarda uma cópia dos relatórios finais. Os prompts dos agentes (`agents/`) não foram copiados.
- Os arquivos `.json` seguem o schema `report-schema.json` da skill e podem ser comparados em execuções futuras: o ledger de cobertura é reaproveitado como "execução anterior".
