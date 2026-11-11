# Relatório de auditoria de segurança — MVP (Encontrei), run-1

> **Execução PARCIAL e INCOMPLETA.** O perfil `quick` faz uma única onda de caça. Além disso, `run_status` é `incomplete` (`validators_unavailable_on_host`): neste host Windows os validadores `validate-findings.cjs` e `validate-coverage-ledger.cjs` recusam ler qualquer arquivo, porque falta `O_NOFOLLOW`. O portão da Fase 4 não pôde ser cumprido. No lugar dele rodei checagens estruturais próprias, que não substituem os validadores.

## 1. Escopo e condições

| Item | Valor |
|---|---|
| Alvo | `D:\MVP` — `app.py`, `index.html`, `test_app.py`, `executar.bat`, `.gitignore`, `docs/api` |
| Revisão | commit `ef131bb`. A worktree estava suja apenas em arquivos que não são do alvo (`.gitignore`, `.claude/`, `docs/seguranca/`) |
| Perfil | `quick`: 1 onda de caça e 1 crítico final; um verificador novo por candidato (Fases 3 e 5 unidas) |
| Orçamento | 20 invocações de agente, proposto por mim e não fixado pelo usuário; subiu de 18 para 20 durante a execução, com registro. Gasto: 4 de reconhecimento, 6 caçadores (um refeito por resultado malformado), 1 crítico e 9 verificadores = **20** |
| Execução | Somente leitura de código-fonte e verificação local, sem sandbox. O host não tem sandbox imposto pelo SO (sem WSL, Docker ou bwrap), nem promoção segura de artefatos. **Nenhum código do alvo foi executado** |
| Execuções anteriores | Nenhum ledger anterior existe. O relatório manual em `docs/seguranca/` não foi usado como evidência |
| Cobertura adiada | 2 unidades propostas pelo crítico ficaram `deferred` (`quick_profile_final_critic`). Ver seção 7 |

## 2. Postura de segurança

A base técnica é boa: SQL sempre parametrizado, escape consistente no frontend, PBKDF2 com `compare_digest` e uploads confinados ao diretório. Os riscos estão nas **regras de confiança do fluxo**:
- a ativação de conta não prova posse do e-mail;
- a resposta de verificação não tem limite de tentativas;
- as transições de estado de item, denúncia e suspensão não conferem o estado anterior nem o papel de quem é afetado;
- as contas seed têm senhas públicas e são reativadas a cada inicialização.

Nenhuma dessas pistas pôde ser **confirmada** nesta execução, porque `confirmed` exige um resultado local observado em sandbox.

## 3. Achados confirmados

**Nenhum.** Os 9 candidatos foram validados de forma independente e permanecem `needs_validation`. Nenhum foi refutado (`rejected`) pela leitura do código.

## 4. Achados confirmados em detalhe

Não se aplica.

## 5. NEEDS VALIDATION (sem severidade)

O detalhe completo de cada pista está em `NEEDS-VALIDATION.md`. O bloqueio comum a todas é a falta de sandbox no host para observar o resultado local. A tabela traz os bloqueios adicionais.

| # | Pista | Trace (início → efeito) | Bloqueio além do sandbox | Próximo passo local | Verificação pelo responsável |
|---|---|---|---|---|---|
| NV01 | Link de verificação devolvido na resposta permite ativar conta de e-mail alheio | `app.py:904` → `:926/:938` → `:696` | Alcance de rede de cada implantação | Teste com SMTP stub: a resposta ainda traz `verification_url`; ativar e fazer login | Porta 8000 exposta além do loopback? SMTP configurado? |
| NV02 | Tentativas ilimitadas na resposta de verificação | `app.py:792` → `:983` → `:986` | — | 20 respostas erradas e depois a certa: nenhum 429, final 201 | — |
| NV03 | Moderador suspende Administrador pelo caminho das denúncias | `app.py:1059` → `:1099/:1111` → `:1112` | Intenção do produto (RN18 vale para staff?) | 3 denúncias "Procedente" e o admin passa a receber 403 | Confirmar a política de suspensão de staff |
| NV04 | `/returned` torna público (`Resolvido`) um item ocultado pela moderação | `app.py:1030` → `:1040` → `:751` | — | Ocultar, aprovar, `/returned`, e então o GET anônimo responde 200 | — |
| NV05 | Dispensa de denúncias reabre item resolvido, expirado ou guardado como `Aberto` | `app.py:1044` → `:1054` → `:1085` | — | Resolver, 3 denúncias, "Manter anúncio", e o item volta a `Aberto` | — |
| NV06 | Contas seed com senha pública são reativadas a cada início | `app.py:1394` → `:336` → `:343` | — | Suspender, rodar `init_db()` de novo, e o login responde 200 | — |
| NV07 | Ausência de validação de `Host` (DNS rebinding) com credenciais admin públicas | `app.py:1396` → `:899/:951` → `:889` | Proteções do navegador (PNA / anti-rebinding) | Login e `/api/admin/users` com `Host` estranho respondem 200 | Testar o rebinding nos navegadores da demo |
| NV08 | Chaves de tamanho livre retidas para sempre em `LOGIN_ATTEMPTS` | `app.py:899` → `:940-941` → `:944` | Alcance (loopback / PNA) | 3 e-mails de 64 KiB continuam retidos após 120 s simulados | Exposição além do loopback |
| NV09 | `PATCH` de fotos grava antes de validar e deixa arquivos órfãos | `app.py:1236` → `:1270/:1272` → `:85` | Exige uma conta verificada | `PATCH` com local inválido deixa 3 arquivos novos sem referência | Volume compartilhado com o SQLite? Há quota? |

## 6. Notas de endurecimento (não são achados) e padrões positivos

**Endurecimento** (dos caçadores, sem violação de fronteira demonstrada):
- Enumeração de contas: o login não roda PBKDF2 para e-mails inexistentes (`app.py:946`), e `resend-verification` responde 404/400/200 (`:931-932`).
- PBKDF2 com 120.000 iterações (`app.py:72`), abaixo das 600.000 recomendadas.
- O limite de login é por IP + e-mail (`:941`), então tentar uma senha em muitas contas não é limitado. Sessões não têm teto nem rotação, e o logout revoga só o token apresentado.
- Um moderador pode decidir reivindicações e denúncias que ele mesmo abriu (`:1001-1002`, `:1073`, `:1099`).
- `/returned` pode ser repetido sem conferir `returned_at` (`:1039-1042`).
- Uma thread por conexão, sem timeout (`:1396`, `:634`). Tokens expirados não são varridos. `body_json` lê até 24 MiB antes da autenticação.
- O laço de fotos do `PATCH` não tem `isinstance(dict)` (`:1263`, gera 500). `len(photo_urls)>3` em `:1271` é código morto.
- `/uploads/*` serve fotos de itens ocultos sem autenticação. Os nomes são aleatórios de 128 bits.
- Não há CSP nem `frame-ancestors`. `log_message` imprime a linha crua da requisição, o que permite injetar sequências de escape no console (`:604-605`).
- POSTs não autenticados aceitam qualquer `Content-Type` (`:626-638`).
- Denúncia de item oculto responde 201, enquanto o GET responde 404: oráculo de existência mínimo (`:1044-1051`).
- A contagem de denúncias "procedentes" é por denúncia, não por incidente (`:1090`). Curingas de `LIKE` não são escapados (`:760-763`).

**Padrões positivos verificados:**
- Todo SQL com dados do usuário usa `?`; o SQL em f-string só usa nomes fixos.
- `esc()` é aplicado em todo texto vindo da API, e os `onclick` interpolam apenas ids inteiros.
- Tokens são aleatórios e opacos, expiram, o usuário é relido a cada requisição, e as sessões são revogadas na suspensão.
- `/uploads` está protegido contra path traversal, com nomes aleatórios e `nosniff`.
- `create_item` valida tudo antes de gravar no disco.
- Os índices únicos parciais impedem dupla aprovação e reivindicações ativas duplicadas.
- As rotas admin e de moderação conferem o papel no servidor.
- O chat é restrito aos participantes e só abre após a aprovação.
- Não há segredos versionados, `eval` ou execução de shell.

## 7. Cobertura (do ledger)

| Estado | Unidades |
|---|---|
| covered | 4: login/sessão (U02), decisão/devolução/chat (U04), SQL e sinks do servidor (U11), renderização do frontend/XSS/token (U10) |
| candidate | 9: cada uma ligada a um registro `needs_validation` |
| blocked | 0 |
| deferred | 2: revogação de estado do catálogo (domínio/ponto de guarda/categoria desativados versus contas e itens existentes); corrida em check-then-act sem lock (limitador de login, quotas de `create_item`, contagem de auto-ocultação) |

- **Exclusões:** os companions MEMORY-SAFETY, AI-AND-LLM, SUPPLY-CHAIN, CLOUD, PROTOCOLS-RPC, DATA-ISOLATION e DESKTOP-MOBILE não se aplicam. CSRF foi excluído porque não há credencial ambiente (só Bearer); CORS porque nenhum `Access-Control-Allow-Origin` é enviado.
- **Crítico final:** `stop=false`, com 2 unidades faltantes aceitas e adiadas pelo perfil `quick`, e nenhuma reatribuição.
- **Limites:** esta é a primeira execução, sem ledger anterior. Uma execução nunca esgota o alvo. Uma nova rodada `standard`, com sandbox (WSL/Linux), deve começar pelas 2 unidades adiadas e tentar confirmar as 9 pistas.
