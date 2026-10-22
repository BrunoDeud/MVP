# API HTTP — versão local simplificada

Este documento descreve os endpoints realmente implementados em `app.py`. A API recebe e devolve JSON, salvo o conteúdo estático da interface e os arquivos de imagem. A URL base é `http://127.0.0.1:8000`.

Rotas protegidas exigem o cabeçalho `Authorization: Bearer <token>`. O token é obtido por `POST /api/login` e permanece em memória até o servidor ser encerrado.

## Saúde e sessão

| Método | Caminho | Autenticação | Finalidade |
|---|---|---|---|
| `GET` | `/api/health` | Não | Verifica se o servidor responde e informa que o banco é SQLite. |
| `POST` | `/api/login` | Não | Autentica com `email` e `password`; devolve `token` e dados básicos do usuário. |
| `POST` | `/api/logout` | Token no cabeçalho recomendado | Remove o token da sessão local. |
| `GET` | `/api/me` | Sim | Retorna os dados básicos da conta autenticada. |

## Itens

| Método | Caminho | Autenticação | Finalidade |
|---|---|---|---|
| `GET` | `/api/items` | Não | Lista anúncios públicos. Aceita filtros `q`, `type`, `category`, `location` e `status`. |
| `GET` | `/api/items/{id}` | Não | Obtém os detalhes públicos de um anúncio sem expor a resposta de verificação. |
| `POST` | `/api/items` | Sim | Cria anúncio. Campos: `title`, `type`, `category`, `description`, `location`, `event_date`, `photos` e, para achados, `verification_question` e `verification_answer`. |
| `GET` | `/api/items/{id}/verification-question` | Sim | Retorna a pergunta de verificação para uma possível reivindicação, após validar as permissões. |
| `GET` | `/api/items/{id}/claims` | Publicador ou moderação | Lista as reivindicações de um anúncio. |
| `POST` | `/api/items/{id}/claims` | Sim | Cria reivindicação. Recebe `answer` e verifica a resposta. |
| `POST` | `/api/items/{id}/resolve` | Publicador ou moderação | Marca o anúncio como resolvido. |
| `POST` | `/api/items/{id}/reports` | Sim | Registra denúncia com o campo `reason`. |

Para enviar fotos ao criar um item, `photos` é uma lista de objetos que contêm `mime` e `data`. O campo `data` deve conter uma data URL de imagem codificada em Base64. São aceitos JPG/JPEG, PNG e WEBP, até três imagens e 5 MB por imagem.

## Reivindicações, mensagens e moderação

| Método | Caminho | Autenticação | Finalidade |
|---|---|---|---|
| `GET` | `/api/my/items` | Sim | Lista os anúncios da conta autenticada. |
| `GET` | `/api/my/claims` | Sim | Lista as reivindicações feitas pela conta autenticada. |
| `POST` | `/api/claims/{id}/decision` | Publicador do item ou moderação | Aprova ou recusa uma reivindicação. Recebe `decision` (`Aprovada` ou `Recusada`) e opcionalmente `note`. |
| `GET` | `/api/claims/{id}/messages` | Participante da conversa | Lista mensagens da reivindicação aprovada. |
| `POST` | `/api/claims/{id}/messages` | Participante da conversa | Envia uma mensagem no campo `body`, com até 500 caracteres. |
| `GET` | `/api/moderation/reports` | Moderador ou administrador | Lista denúncias pendentes. |
| `POST` | `/api/reports/{id}/decision` | Moderador ou administrador | Analisa denúncia. Recebe `decision` (`Manter anúncio` ou `Ocultar anúncio`) e justificativa em `note`. |

## Erros

Erros de regra ou validação retornam JSON no formato `{"error":"mensagem"}` e um status HTTP apropriado, como `400`, `401`, `403`, `404` ou `409`. Erros inesperados retornam `500`; a mensagem técnica detalhada fica no terminal local.

## Observações

- Os endpoints e nomes de campos desta API local diferem do contrato OpenAPI originalmente criado para Laravel. Esse contrato original foi preservado como referência de planejamento e não é o contrato exato desta implementação simplificada.
- A autenticação e o servidor foram projetados para demonstração local; não exponha essa API diretamente à internet.
