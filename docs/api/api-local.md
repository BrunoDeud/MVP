# Referência da API HTTP local

Contrato da implementação atual (`app.py`), não do desenho anterior Laravel. A API responde JSON em `http://127.0.0.1:8000/api`; exceções são as páginas HTML da verificação de e-mail, a interface `/` e arquivos em `/uploads/`.

## Convenções

- JSON UTF-8 em requests com corpo.
- Para endpoints autenticados: `Authorization: Bearer <token>`; o token é retornado por `POST /api/login` e expira após 8 horas ou no encerramento do servidor.
- Códigos frequentes: `200` sucesso, `201` criado, `400` validação/parâmetro inválido, `401` sem sessão/expirada, `403` papel ou acesso insuficiente, `404` recurso/rota inexistente, `409` conflito/duplicidade/regra de estado, `410` link de verificação expirado, `413` corpo acima do limite, `500` falha inesperada.
- Erros de API usam `{ "error": "mensagem legível" }`. O backend não retorna stack trace ao navegador; detalhes inesperados vão para o terminal local.
- Datas usam `AAAA-MM-DD`; timestamps usam ISO local.
- Fotos são uma lista `photos` de objetos `{ "mime": "image/png", "data": "data:image/png;base64,..." }`. Máximo três, JPG/JPEG, PNG ou WEBP, 5 MB por imagem, com verificação da assinatura do arquivo.

## Saúde, configuração e sessão

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/health` | Público | Confere o banco e responde estado, nome e total de itens. |
| `GET` | `/api/config` | Público | Lista categorias e locais ativos para os formulários. |
| `POST` | `/api/register` | Público | Cadastra usuário como pendente. Body: `name`, `email`, `password`, `password_confirmation`. Retorna `verification_url` no modo local. |
| `GET` | `/api/verify-email?token=...` | Link secreto | Verifica e ativa a conta se o token não expirou (24 horas). Retorna HTML explicativo. |
| `POST` | `/api/resend-verification` | Público | Solicita novo link para uma conta pendente. Body: `email`. A URL é devolvida para uso local e, quando configurado, também enviada por SMTP. |
| `POST` | `/api/login` | Público | Autentica por `email` e `password`; retorna `token`, usuário e expiração. |
| `POST` | `/api/logout` | Token | Invalida a sessão atual. |
| `GET` | `/api/me` | Token | Retorna dados públicos da conta autenticada. |
| `PATCH` | `/api/me/preferences` | Token | Atualiza `email_notifications` booleano; o envio depende das variáveis SMTP opcionais. |

## Catálogos públicos

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/items/categories` | Público | Categorias ativas (`id`, `name`, `requires_guard`). |
| `GET` | `/api/items/locations` | Público | Locais ativos (`id`, `name`, `block_name`). |
| `GET` | `/api/guard-points` | Token | Pontos de guarda ativos e local vinculado. |

## Anúncios

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/items` | Público, com exceção do filtro oculto | Lista com `q`, `type`, `category`, `location`, `status`, `date_from`, `date_to`, `page`, `per_page`. Retorna `items` e `pagination`. A busca pública padrão mostra anúncios abertos e itens no ponto de guarda. |
| `POST` | `/api/items` | Token | Cria anúncio `Achado` ou `Perdido`. Campos obrigatórios: `title`, `type`, `category`, `description`, `location`, `event_date`; categoria e local devem existir e estar ativos no catálogo administrativo. `photos` é opcional para perdido e obrigatória para achado. Achado requer `verification_question` e `verification_answer`. |
| `GET` | `/api/items/{id}` | Público (anúncio oculto só para dono/moderação) | Detalhe público sem pergunta/resposta secreta, telefone ou e-mail. |
| `PATCH` | `/api/items/{id}` | Dono | Atualiza anúncio aberto: `title`, `description`, `category`, `location`, `event_date` e/ou `photos`. O backend revalida limites e registra histórico. |
| `DELETE` | `/api/items/{id}` | Dono ou administrador | Exclui anúncio somente quando não há reivindicações/denúncias associadas; caso exista histórico, retorna `409` para preservar auditoria. |
| `POST` | `/api/items/{id}/resolve` | Dono ou moderação | Marca anúncio aberto/no ponto de guarda como resolvido e registra histórico. |
| `GET` | `/api/items/{id}/verification-question` | Token | Retorna só a pergunta de verificação; bloqueia o publicador e anúncios incompatíveis com reivindicação. |
| `GET` | `/api/items/{id}/claims` | Dono ou moderação | Lista reivindicações do anúncio, sem expor resposta privada. |
| `GET` | `/api/items/{id}/matches` | Dono ou moderação | Sugere até cinco anúncios opostos que compartilham categoria, local/bloco e janela temporal direcional de até 15 dias após a data da perda. |
| `GET` | `/api/items/{id}/history` | Dono ou moderação | Lista eventos de histórico do anúncio. |
| `POST` | `/api/items/{id}/claims` | Token | Cria reivindicação de achado. Body: `answer`. Bloqueia autorrivindicação, item encerrado, resposta incorreta, duplicidade ativa e nova solicitação quando já há reivindicação aprovada. |
| `POST` | `/api/items/{id}/reports` | Token | Denuncia anúncio. Body: `reason` (5–500 caracteres); impede autodenúncia e duplicidade por usuário. |
| `POST` | `/api/guard-points/items` | Moderador/administrador | Registra achado recebido num ponto de guarda. Requer `guard_point_id`, local compatível, foto e pergunta/resposta quando aplicável. |
| `GET` | `/api/my/items` | Token | Lista os próprios anúncios. |
| `GET` | `/api/my/claims` | Token | Lista reivindicações abertas pelo usuário e status relacionados. |
| `GET` | `/api/my/history` | Token | Retorna histórico recente dos próprios anúncios. |

## Reivindicações, conversas e devolução

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `POST` | `/api/claims/{id}/decision` | Publicador ou moderação conforme o item | Body `decision` (`Aprovada`/`Recusada`) e `note`. Item guardado exige moderação; justificativa e decisão ficam registradas. Ao aprovar, outras pendentes para o mesmo item são canceladas. |
| `POST` | `/api/claims/{id}/returned` | Publicador ou moderação; guarda exige moderação | Confirma devolução somente para reivindicação aprovada, encerra item e registra histórico. |
| `GET` | `/api/claims/{id}/messages` | Participante da reivindicação aprovada | Lista mensagem, nome do remetente, data e ID; não inclui e-mail. |
| `POST` | `/api/claims/{id}/messages` | Participante da reivindicação aprovada | Body `body` (1–500 caracteres). Cria mensagem e notificação in-app ao outro participante. |

## Notificações

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/notifications` | Token | Lista até 100 notificações da conta e quantidade não lida. |
| `GET` | `/api/notifications/unread-count` | Token | Retorna quantidade não lida. |
| `PATCH` | `/api/notifications/{id}/read` | Dono da notificação | Marca uma notificação como lida. |
| `POST` | `/api/notifications/read-all` | Token | Marca todas as notificações próprias como lidas. |

## Moderação

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/moderation/reports` | Moderador/administrador | Lista denúncias de anúncios pendentes. |
| `POST` | `/api/reports/{id}/decision` | Moderador/administrador | Body `decision` (`Manter anúncio`/`Ocultar anúncio`) e `note` (justificativa). Registra decisão, histórico e notificação. |
| `GET` | `/api/moderation/profile-reports` | Moderador/administrador | Lista denúncias de perfil pendentes. |
| `POST` | `/api/users/{id}/reports` | Token | Denuncia perfil com `reason`; não permite autodenúncia ou repetição pela mesma conta. |
| `POST` | `/api/profile-reports/{id}/decision` | Moderador/administrador | Body `decision` (`Procedente`/`Improcedente`) e `note`; registra auditoria e aplica regra de suspensão. |
| `GET` | `/api/moderation/claims` | Moderador/administrador | Fila para reivindicações de ponto de guarda ou encaminhadas após sete dias. |
| `GET` | `/api/moderation/log` | Moderador/administrador | Lista as ações de moderação com responsável, data e justificativa. |

## Administração

| Método | Caminho | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/admin/categories` | Administrador | Lista todas as categorias, ativas ou não. |
| `POST` | `/api/admin/categories` | Administrador | Cria categoria com `name` e `requires_guard`. |
| `PATCH` | `/api/admin/categories/{id}` | Administrador | Altera nome, `requires_guard` e/ou `active`. |
| `GET` | `/api/admin/locations` | Administrador | Lista todos os locais. |
| `POST` | `/api/admin/locations` | Administrador | Cria local com `name` e `block_name` opcional. |
| `PATCH` | `/api/admin/locations/{id}` | Administrador | Altera nome, bloco e/ou estado ativo. |
| `GET` | `/api/admin/guard-points` | Administrador | Lista pontos de guarda. |
| `POST` | `/api/admin/guard-points` | Administrador | Cria ponto com `name`, `location_id`, `reference` e `retention_days` entre 30 e 365. |
| `PATCH` | `/api/admin/guard-points/{id}` | Administrador | Atualiza metadados, local, prazo ou estado ativo. |
| `GET` | `/api/admin/domains` | Administrador | Lista domínios permitidos. |
| `POST` | `/api/admin/domains` | Administrador | Adiciona domínio institucional sem `@` nem endereço completo. |
| `PATCH` | `/api/admin/domains/{id}` | Administrador | Ativa/desativa o domínio por `active` booleano. |
| `GET` | `/api/admin/users` | Administrador | Lista dados administrativos não sensíveis de usuários. |
| `PATCH` | `/api/admin/users/{id}/role` | Administrador | Altera papel para `Estudante`, `Moderador` ou `Administrador`. |
| `PATCH` | `/api/admin/users/{id}/status` | Administrador | Altera status para `Ativo` ou `Suspenso`; sessão é invalidada ao suspender. |

## Regras transversais e limitações de infraestrutura

As rotas validam dados no servidor, ainda que o navegador também aplique validação HTML. O SQLite aplica chaves primárias/estrangeiras, valores `CHECK`, unicidade e índices; regras entre vários registros são validadas na camada de negócio.

A verificação de e-mail usa link de uso único com expiração de 24 horas. Sem servidor SMTP configurado, `/api/register` e `/api/resend-verification` retornam a URL local para conclusão manual; com as variáveis `ENCONTREI_SMTP_*`, a aplicação também tenta enviá-la por e-mail. Notificações in-app são sempre persistidas no banco; e-mails de notificação são tentados quando o usuário verificou a conta, habilitou a preferência e SMTP está configurado. O servidor é para demonstração local, não para exposição direta na internet.
