# Relatório de vulnerabilidades — Encontrei (MVP local)

**Data:** 06/11/2026  
**Escopo:** `app.py` (servidor HTTP, API, regras de negócio, persistência) e `index.html` (frontend), commit `ef131bb`.  
**Método:** revisão manual do código-fonte, seguida de provas de conceito executadas contra uma **cópia isolada** do sistema (banco temporário, sem tocar em `data/`). Todos os achados marcados como **confirmado** foram reproduzidos.

## 1. Resumo executivo

O MVP tem uma base defensiva melhor que a média para um projeto acadêmico. As consultas SQL são parametrizadas, as senhas usam PBKDF2 com sal, o frontend escapa dados antes de inserir no HTML e o upload valida a assinatura dos arquivos. As falhas mais sérias não são de injeção. Elas estão nas **regras de confiança do fluxo**: a verificação de e-mail pode ser contornada, a pergunta de verificação aceita tentativas ilimitadas e a moderação automática pode ser manipulada.

| Severidade | Qtde. |
|---|---|
| Alta | 2 |
| Média | 5 |
| Baixa | 6 |
| Informativa | 2 |

> **Contexto de risco.** O servidor escuta apenas em `127.0.0.1` e o README já declara que ele não é para produção. As severidades abaixo consideram o cenário para o qual o produto foi projetado (uso real por uma comunidade acadêmica). Em demonstração local, o risco prático é baixo.

### Tabela de achados

| ID | Severidade | Título | Status |
|---|---|---|---|
| V01 | Alta | Verificação de e-mail contornável (link devolvido na resposta da API) | Confirmado |
| V02 | Alta | Força bruta ilimitada da pergunta de verificação | Confirmado |
| V03 | Média | Ocultação automática de anúncios manipulável com contas fantoche | Confirmado |
| V04 | Média | Contas de demonstração com senhas públicas criadas automaticamente | Confirmado |
| V05 | Média | Sem HTTPS, sem cabeçalhos de segurança e token em `localStorage` | Confirmado |
| V06 | Média | Proteção fraca contra força bruta no login e hash abaixo do recomendado | Revisão de código |
| V07 | Média | Negação de serviço por consumo de recursos | Revisão de código |
| V08 | Baixa | Enumeração de contas (mensagens e tempo de resposta) | Confirmado |
| V09 | Baixa | Arquivos órfãos e erro 500 na edição de fotos | Confirmado |
| V10 | Baixa | Metadados EXIF (ex.: GPS) preservados nas fotos publicadas | Revisão de código |
| V11 | Baixa | Segredos armazenados em texto puro no banco | Revisão de código |
| V12 | Baixa | Reivindicação pode ser aprovada em item oculto ou expirado | Revisão de código |
| V13 | Baixa | Divulgação de versão e informações no cabeçalho `Server` e em `/api/health` | Confirmado |
| V14 | Informativa | Sem validação do cabeçalho `Host` (DNS rebinding) | Revisão de código |
| V15 | Informativa | SMTP pode enviar credenciais sem TLS se configurado assim | Revisão de código |

---

## 2. Achados detalhados

### V01 — Verificação de e-mail contornável · **Alta**

**Onde:** [app.py:923-926](../../app.py) (`/api/register`) e [app.py:935-938](../../app.py) (`/api/resend-verification`).

**Descrição.** As duas rotas sempre devolvem `verification_url` no JSON de resposta, **mesmo quando o e-mail foi enviado por SMTP**. Quem faz o cadastro recebe o link de ativação diretamente e não precisa ter acesso à caixa de e-mail.

**Evidência (prova de conceito).** Cadastro de `reitoria@campus.edu.br` (endereço que o atacante não controla): resposta `201` com `verification_url`; o próprio atacante abriu o link (`200`) e entrou no sistema como essa conta.

**Impacto.**
- Qualquer pessoa cria contas com e-mails institucionais de terceiros (professores, setores, colegas) e se passa por eles.
- A restrição por domínio institucional (RN do catálogo de domínios) perde o efeito.
- Isso viabiliza a criação em massa de contas, que alimenta V03.
- `/api/resend-verification` também ativa contas pendentes de outras pessoas.

**Recomendação.**
- Devolver o link **somente** em modo de desenvolvimento explícito (ex.: variável `ENCONTREI_DEV=1`) e nunca quando houver SMTP configurado.
- Em produção, responder com uma mensagem genérica ("se o e-mail for válido, enviaremos um link").
- Guardar apenas o hash do token de verificação (ver V11).

---

### V02 — Força bruta ilimitada da pergunta de verificação · **Alta**

**Onde:** [app.py:972-983](../../app.py) (`POST /api/items/{id}/claims`).

**Descrição.** A resposta enviada é comparada com a resposta cadastrada e, se errar, o servidor responde `400 "Resposta não confere"`. Não há limite de tentativas, atraso, registro de erros nem aviso ao publicador. As respostas costumam ter baixíssima entropia (cores, números, desenhos simples).

**Evidência.** No item "Caderno de capa preta" (*"Qual a cor do elástico?"*), um script testou uma lista de 11 cores. A resposta correta foi aceita na 11ª tentativa e a reivindicação foi criada, sem qualquer bloqueio.

**Impacto.** A pergunta de verificação é o principal controle contra a retirada de objetos por quem não é dono. Com tentativas ilimitadas, qualquer usuário consegue reivindicar itens alheios (incluindo cartões e documentos em pontos de guarda).

**Recomendação.**
- Limitar tentativas por usuário e por item (ex.: 3) e bloquear novas tentativas por um período.
- Registrar tentativas incorretas e mostrá-las ao publicador ou à moderação.
- Considerar a resposta como um *indício* para análise humana, não como critério automático de aceite.
- Orientar o publicador a criar perguntas com respostas específicas.

---

### V03 — Ocultação automática manipulável com contas fantoche · **Média**

**Onde:** [app.py:1052-1057](../../app.py).

**Descrição.** Três denúncias pendentes de usuários distintos ocultam o anúncio automaticamente. Combinado com V01 e com a falta de limite no cadastro, um único atacante cria três contas e tira do ar qualquer anúncio.

**Evidência.** Três contas `bot0..2@alunos.campus.edu.br` foram criadas e autoverificadas; após três denúncias, o item "Garrafa térmica verde" passou a responder `404` para o público.

**Impacto.** Censura de anúncios legítimos e sobrecarga da moderação. A mesma lógica de "3 denúncias procedentes" pode levar à suspensão de contas se a moderação confirmar denúncias em lote.

**Recomendação.** Corrigir V01 primeiro. Além disso, limitar cadastros por IP e por período, e dar peso às denúncias conforme a idade e o histórico da conta. Também vale exigir confirmação de um moderador antes de ocultar, ou pelo menos priorizar a fila.

---

### V04 — Contas de demonstração com senhas públicas · **Média**

**Onde:** [app.py:331-340](../../app.py); senhas listadas no `README.md` e em `COMECE-AQUI.txt`.

**Descrição.** Ao iniciar o banco, `init_db()` sempre cria quatro contas ativas, incluindo `admin@campus.edu.br` / `Admin@12345`, com senhas documentadas publicamente.

**Evidência.** Login como administrador com as credenciais do README: sucesso.

**Impacto.** Se o sistema for exposto em qualquer rede (laboratório, Wi-Fi do campus, ou mudando `HOST` para `0.0.0.0`), qualquer pessoa vira administradora.

**Recomendação.** Criar dados de demonstração apenas com uma opção explícita (ex.: `python app.py --demo`). Fora desse modo, gerar a senha do primeiro administrador aleatoriamente e exibi-la uma única vez no terminal, ou exigir a troca no primeiro acesso.

---

### V05 — Sem HTTPS, sem cabeçalhos de segurança e token em `localStorage` · **Média**

**Onde:** [app.py:699-707](../../app.py) (entrega do `index.html`), `send_json`/`send_html`; `index.html` (`localStorage.setItem('enc_token', ...)`).

**Descrição.**
- O tráfego é HTTP puro: senhas e tokens trafegam sem criptografia.
- Faltam `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors` e `Referrer-Policy` (confirmado: todos ausentes).
- O token de sessão fica no `localStorage`, acessível a qualquer script da página.

**Impacto.** Hoje não foi encontrada XSS (o frontend escapa os dados com `esc()`). Mesmo assim, qualquer falha futura de escape ou dependência maliciosa vira roubo de sessão imediato, porque não há CSP para conter o dano. A página também pode ser embutida num `iframe` de terceiros (clickjacking).

**Recomendação.**
- Servir via HTTPS (proxy reverso) em qualquer uso fora do `localhost`.
- Adicionar `Content-Security-Policy` restritiva. Isso exige mover os `onclick` inline para `addEventListener`, ou usar *nonces*.
- Adicionar `X-Frame-Options: DENY` e `Referrer-Policy: no-referrer`.
- Preferir cookie de sessão `HttpOnly; Secure; SameSite=Strict` (com proteção CSRF) em vez de `localStorage`.

---

### V06 — Proteção fraca contra força bruta no login e hash abaixo do recomendado · **Média**

**Onde:** [app.py:939-952](../../app.py), [app.py:70-73](../../app.py).

**Descrição.**
- O limite de 8 tentativas por minuto é contado por **IP + e-mail**. Um atacante que testa uma senha comum contra muitos e-mails (*password spraying*) nunca é bloqueado, e cada e-mail ainda aceita cerca de 11.500 tentativas por dia.
- A política de senha exige apenas 8 caracteres, sem checar senhas vazadas ou comuns.
- O PBKDF2-SHA256 usa 120.000 iterações; a OWASP recomenda 600.000 (ou Argon2id/scrypt).
- Os tokens de sessão valem 12 h, sem renovação nem expiração por inatividade.

**Recomendação.** Somar um limite global por IP e um bloqueio progressivo por conta. Aumentar as iterações (com migração do hash no próximo login), recusar senhas comuns e adicionar expiração por inatividade.

---

### V07 — Negação de serviço por consumo de recursos · **Média**

**Onde:** [app.py:32](../../app.py) (`MAX_BODY = 24 MB`), [app.py:626-638](../../app.py), [app.py:35-36](../../app.py), [app.py:1396](../../app.py).

**Descrição.**
- `ThreadingHTTPServer` cria uma thread por conexão, sem limite e sem *timeout* de leitura. Conexões lentas (*slowloris*) ou muitos corpos de 24 MB esgotam memória e threads.
- `LOGIN_ATTEMPTS` e `TOKENS` só crescem: cada combinação IP + e-mail nova cria uma entrada que nunca é removida, e tokens expirados só são apagados se forem reutilizados.
- `maintenance()` roda dentro de requisições e percorre tabelas inteiras.

**Recomendação.** Definir `timeout` no handler, reduzir `MAX_BODY` (3 fotos × 5 MB em base64 ≈ 20 MB, então vale enviar fotos por `multipart` ou uma de cada vez), limpar periodicamente os dicionários em memória e, em produção, usar servidor WSGI/ASGI atrás de proxy com limites.

---

### V08 — Enumeração de contas · **Baixa**

**Onde:** [app.py:927-932](../../app.py), [app.py:916](../../app.py), [app.py:945-948](../../app.py).

**Evidência.**
- `/api/resend-verification`: conta existente → `400 "Esta conta já está verificada"`; inexistente → `404 "Conta não encontrada"`.
- `/api/register` responde `409` para e-mail já cadastrado.
- Login: ~36 ms para e-mail existente (executa PBKDF2) contra ~8 ms para inexistente.

**Impacto.** Permite descobrir quais e-mails institucionais têm conta, o que facilita V06 e phishing.

**Recomendação.** Mensagens genéricas e idênticas. No login, calcular o hash mesmo quando o usuário não existe (hash fictício) para igualar o tempo.

---

### V09 — Arquivos órfãos e erro 500 na edição de fotos · **Baixa**

**Onde:** [app.py:1262-1271](../../app.py).

**Descrição.** Na edição, cada foto é **gravada em disco antes** de as demais serem validadas e antes do `UPDATE`. Se a 2ª foto for inválida, a 1ª fica órfã em `uploads/`. Além disso, um item da lista que não seja objeto (ex.: `"texto"`) gera `AttributeError` e resposta `500`. Na criação, essa checagem existe; na edição, não.

**Evidência.** PATCH com uma foto válida + uma inválida → `400` e 1 arquivo órfão criado; PATCH com `photos: ["texto"]` → `500`.

**Impacto.** Preenchimento gradual do disco (cada requisição pode deixar até ~10 MB) e ruído de erro no servidor.

**Recomendação.** Reutilizar a mesma função de validação da criação. Validar todas as fotos antes, gravar somente após o `commit` e apagar os arquivos se a transação falhar.

---

### V10 — Metadados EXIF preservados nas fotos · **Baixa**

**Onde:** [app.py:1189-1199](../../app.py), [app.py:1220-1224](../../app.py).

**Descrição.** As fotos são gravadas byte a byte, sem recodificação. Fotos de celular frequentemente carregam GPS, data, modelo do aparelho e às vezes o nome do dono do aparelho.

**Impacto.** Vazamento da localização de quem publicou (por exemplo, foto tirada em casa) para qualquer visitante, inclusive sem login.

**Recomendação.** Remover metadados ao receber a imagem (recodificar com uma biblioteca de imagem, ou retirar os segmentos APP1/EXIF de JPEG e `eXIf` de PNG/WEBP).

---

### V11 — Segredos armazenados em texto puro · **Baixa**

**Onde:** colunas `users.verification_token`, `items.verification_answer` e `claims.answer` ([app.py:920](../../app.py), [app.py:1228](../../app.py), [app.py:986](../../app.py)).

**Descrição.** Tokens de ativação e respostas de verificação ficam legíveis no `data/encontrei.sqlite3`. Qualquer acesso ao arquivo, como backup, cópia do ZIP ou máquina compartilhada, revela todas as respostas e permite ativar contas pendentes.

**Recomendação.** Guardar o hash (SHA-256) do token de verificação. Para respostas, guardar um HMAC da resposta normalizada com uma chave do servidor e comparar com `hmac.compare_digest`. Garantir que o banco nunca seja empacotado no ZIP da entrega.

---

### V12 — Reivindicação aprovada em item oculto ou expirado · **Baixa**

**Onde:** [app.py:993-1013](../../app.py).

**Descrição.** A decisão verifica o estado da *reivindicação*, mas não o do *item*. Um publicador cujo anúncio foi ocultado pela moderação ainda pode aprovar reivindicações pendentes, liberando a conversa privada, o que contorna a decisão da moderação.

**Recomendação.** Exigir `item.status in ('Aberto', 'No ponto de guarda')` para aprovar, e cancelar reivindicações pendentes quando o item for ocultado ou expirar.

---

### V13 — Divulgação de versão e informações · **Baixa**

**Evidência.** Cabeçalho `Server: EncontreiLocal/2.0 Python/3.15.1`. `/api/health` é público e informa a quantidade total de itens, inclusive ocultos e resolvidos.

**Recomendação.** Sobrescrever `sys_version`/`server_version` e restringir `/api/health` ou reduzir o que ele retorna.

---

### V14 — Sem validação do cabeçalho `Host` (DNS rebinding) · **Informativa**

O servidor aceita qualquer `Host`. Um site malicioso pode usar *DNS rebinding* para fazer o navegador de quem está com o MVP aberto enviar requisições a `127.0.0.1:8000`. As rotas protegidas exigem o token Bearer, que o atacante não tem, então o impacto se limita às rotas públicas (cadastro, busca). **Recomendação:** recusar requisições cujo `Host` não seja `127.0.0.1:8000` ou `localhost:8000`.

### V15 — SMTP sem TLS por configuração · **Informativa**

Com `ENCONTREI_SMTP_TLS=false` e `ENCONTREI_SMTP_SSL=false`, [app.py:484-491](../../app.py) faz login SMTP em texto puro. **Recomendação:** recusar `login()` quando a conexão não estiver criptografada.

---

## 3. Pontos positivos observados

- **SQL injection:** todas as consultas com dados do usuário usam parâmetros `?`. As únicas interpolações (`table_columns`, `ensure_column`) usam nomes fixos do próprio código.
- **XSS:** o frontend aplica `esc()` em todos os campos vindos da API antes de montar HTML, e `toast()` usa `textContent`.
- **Senhas:** PBKDF2 com sal aleatório por usuário e comparação em tempo constante (`hmac.compare_digest`).
- **Tokens:** gerados com `secrets.token_urlsafe(32)`. As sessões são revogadas na suspensão, e o perfil é relido do banco a cada requisição (mudança de papel vale na hora).
- **Path traversal em `/uploads/`:** bloqueado (`Path(...).name`, recusa de nomes com `/` e de arquivos ocultos). Os nomes salvos são aleatórios.
- **Upload:** tipo MIME restrito, checagem de assinatura do arquivo, limite de tamanho e `X-Content-Type-Options: nosniff`.
- **Autorização:** as rotas de moderação e administração checam o papel no servidor. As conversas checam participante e status. O usuário não pode reivindicar nem denunciar o próprio anúncio.
- **Privacidade:** a resposta de verificação e o e-mail do publicador não aparecem na API pública.
- **Rede:** bind em `127.0.0.1` por padrão. Sem CORS permissivo: o `OPTIONS` não envia `Access-Control-Allow-Origin`.

## 4. Plano de correção sugerido (por prioridade)

1. **V01:** parar de devolver `verification_url` fora do modo de desenvolvimento. É uma mudança pequena e com o maior ganho, porque também enfraquece V03.
2. **V02:** limite de tentativas na pergunta de verificação, com registro visível ao publicador.
3. **V04:** dados de demonstração apenas com `--demo`.
4. **V12 e V09:** pequenas correções de lógica na decisão de reivindicação e na edição de fotos.
5. **V05:** cabeçalhos de segurança (CSP após remover `onclick` inline). HTTPS e cookie `HttpOnly` ficam para quando houver implantação.
6. **V06, V07 e V08:** limites globais, limpeza de memória, mensagens genéricas e aumento das iterações do PBKDF2.
7. **V10, V11, V13, V14 e V15:** endurecimento complementar.

Sugere-se criar testes automatizados em `test_app.py` para V01, V02, V09 e V12, garantindo que não voltem (regressão).
