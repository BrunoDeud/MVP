# Correções de segurança aplicadas

**Data:** 2026-11-11
**Base:** commit `ef131bb`, corrigindo os achados de [relatorio-vulnerabilidades.md](relatorio-vulnerabilidades.md) (V01–V15) e da [auditoria com a skill](auditoria-skill-run-1/REPORT.md) (NV01–NV09).
**Arquivos alterados:** `app.py`, `index.html`, `test_app.py`, `executar.bat`, `executar-demo.bat` (novo), `.gitignore`, `README.md`, `COMECE-AQUI.txt`.

Cada correção tem um teste de regressão em `test_app.py`. Os testes 32 a 47 são novos. A suíte completa (47 testes) passa.

## Mudança de comportamento importante: modo demonstração

As contas com senha pública e o link de verificação na tela agora só existem no **modo demonstração**: `executar-demo.bat`, `python app.py --demo` ou `ENCONTREI_DEMO=1`.

O modo normal (`executar.bat` ou `python app.py`) funciona assim:
- **Banco novo:** cria apenas um administrador com senha aleatória, exibida uma vez no terminal.
- **Banco existente:** troca as senhas públicas das contas de demonstração por senhas aleatórias, também exibidas uma vez no terminal.
- **Sem SMTP:** o link de verificação de cadastro aparece somente no terminal do servidor.

## Correções

| ID | Problema | Correção | Teste |
|---|---|---|---|
| V01 / NV01 | O link de verificação era devolvido pela API, permitindo ativar a conta de um e-mail alheio | O link só é enviado por e-mail. Sem SMTP, aparece apenas no terminal do servidor. Ele só volta na resposta no modo demonstração | 32 |
| V02 / NV02 | Tentativas ilimitadas na pergunta de verificação | Nova tabela `claim_attempts`. Cada usuário tem 3 erros por item em 24 h (depois disso, 429 mesmo com a resposta certa). Com 10 erros no item, somando todos os usuários, o item é bloqueado. O publicador e a moderação são avisados | 33 |
| V03 | Ocultação automática manipulável com contas fantoche | Só denúncias de contas com mais de 24 h contam para ocultar. Limite de 10 denúncias por usuário por dia e de 10 cadastros por IP por hora. Também se apoia na correção de V01 | 34 |
| NV03 | Um moderador conseguia suspender um Administrador pelo caminho das denúncias | A suspensão automática vale só para Estudantes; para contas da equipe, a administração é notificada. Moderadores não decidem casos em que são parte (denunciante, denunciado ou dono do item) nem a própria reivindicação | 36 |
| V04 / NV06 | Contas com senha pública criadas sempre e reativadas a cada início | Essas contas existem só no modo demonstração. Uma conta suspensa nunca é reativada. Fora do demo, as senhas públicas são trocadas e um administrador inicial recebe senha aleatória | 38 |
| NV04 | `/returned` tornava público um item ocultado pela moderação | Exige que o item esteja `Aberto` ou `No ponto de guarda` e que a devolução ainda não tenha sido registrada | 37 |
| NV05 | Dispensar denúncias reabria como `Aberto` um item encerrado ou guardado | O status anterior é salvo em `items.status_before_hide` e restaurado. Itens encerrados não são ocultados automaticamente | 35 |
| V05 | Sem cabeçalhos de segurança; token em `localStorage` | Novos cabeçalhos: CSP (com `connect-src`, `img-src` e `frame-ancestors` restritos), `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP/CORP e `Permissions-Policy`. A sessão do navegador passa a usar o cookie `HttpOnly; SameSite=Strict`, e o token saiu do `localStorage`. Requisições que alteram estado e usam o cookie exigem o cabeçalho `X-Encontrei: 1` (proteção CSRF) | 45 |
| V06 | Força bruta no login e hash fraco | Três limites de login: 30 tentativas por minuto por IP, 8 por minuto por IP + e-mail, e bloqueio de 15 min após 10 erros por conta. PBKDF2 passa de 120 mil para 600 mil iterações, com migração automática no login. Senhas comuns são recusadas. As sessões expiram por inatividade (2 h), e cada usuário pode ter no máximo 5 | 40, 41, 47 |
| V07 | Negação de serviço por consumo de recursos | Limite de 64 conexões simultâneas e timeout de 20 s por conexão. O corpo da requisição fica limitado a 64 KB, exceto nas rotas de foto, que exigem autenticação antes de aceitar até 24 MB. Sessões e contadores em memória são limpos periodicamente | 47 |
| V08 | Enumeração de contas | Cadastro e reenvio dão a mesma resposta para e-mails existentes e inexistentes. O login calcula o hash mesmo quando o usuário não existe | 32 |
| NV07 / V14 | Host não validado (DNS rebinding) | Requisições com `Host` diferente de `127.0.0.1`, `localhost` ou `[::1]` na porta do servidor recebem 421. Outros nomes podem ser liberados com `ENCONTREI_ALLOWED_HOSTS` | 39 |
| NV08 | `LOGIN_ATTEMPTS` crescia sem limite | O e-mail é truncado em 190 caracteres antes de virar chave, e as janelas antigas são removidas na manutenção e quando há muitas chaves | 40 |
| V09 / NV09 | Fotos órfãs e erro 500 na edição | Todas as fotos e os catálogos são validados antes de gravar qualquer arquivo. Se a transação falhar, os arquivos novos são apagados. Um item que não seja objeto devolve 400 | 42 |
| V10 | EXIF/GPS preservado nas fotos | Metadados removidos ao receber a foto: JPEG (APP1/APP13/comentários), PNG (`eXIf`/`tEXt`/`iTXt`/`zTXt`/`tIME`) e WEBP (`EXIF`/`XMP`) | 43 |
| V11 | Segredos em texto puro no banco | O token de verificação é guardado como SHA-256. As respostas de verificação são guardadas como HMAC-SHA256 com a chave `data/secret.key`. Dados antigos são migrados no início | 33, 44 |
| V12 | Aprovação de reivindicação em item oculto ou expirado | A aprovação exige o item ativo. Pendências são canceladas quando o item expira | 37 |
| V13 | Versão no cabeçalho `Server` e contagem em `/api/health` | O cabeçalho passa a ser `Server: Encontrei`, e `/api/health` responde só `{"ok": true}` | 01, 45 |
| V15 | Login SMTP sem criptografia | O envio é recusado se houver usuário SMTP e nem TLS nem SSL estiverem ativos | 46 |

Também foram corrigidos itens das notas de endurecimento da auditoria:
- caracteres de controle removidos do log do terminal;
- curingas de `LIKE` escapados na busca;
- `/returned` não pode ser repetido;
- denúncia de item oculto responde 404 para quem não é da moderação.

## O que continua pendente (exige implantação, fora do código local)

- **HTTPS:** o servidor local é HTTP. Em qualquer uso fora do `localhost` é preciso um proxy com TLS, e aí o cookie deve receber o atributo `Secure`.
- **CSP com `'unsafe-inline'`:** o `index.html` usa muitos `onclick` inline. Por isso a CSP ainda permite scripts inline. Mesmo assim, ela impede o envio de dados para outros domínios (`connect-src`/`img-src 'self'`) e o uso em iframe. Removê-la exige reescrever os handlers com `addEventListener`.
- **Orientação das fotos:** a remoção do EXIF também apaga a tag de orientação. Uma foto de celular pode aparecer girada se a câmera dependia dela.
- **Bloqueio por conta (V06):** como contrapartida, quem errar a senha de outra pessoa 10 vezes a bloqueia por 15 minutos.
- **Itens adiados pela auditoria, que não foram tratados:** revogação de estado do catálogo e corridas em verificações sem lock.
