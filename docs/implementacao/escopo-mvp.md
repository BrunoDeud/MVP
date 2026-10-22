# Matriz de rastreabilidade e validação do MVP

> **Nota sobre a versão local simplificada:** esta matriz foi criada para a arquitetura completa originalmente planejada (Laravel + React + MySQL) e não é um retrato fiel de todos os endpoints ou funcionalidades existentes em `app.py`. Para a versão atual, consulte `README.md`, `docs/ADAPTACAO-LOCAL.md`, `docs/ADRs/` e `docs/api/api-local.md`. Os requisitos e critérios abaixo continuam sendo a referência de escopo desejado, mas itens não implementados na versão local permanecem pendentes.


Esta matriz relaciona os requisitos funcionais da documentação técnica às histórias de usuário, à interface, aos endpoints e às validações implementadas. **Parcial** significa que existe um fluxo funcional, mas nem todos os critérios/regras previstos estão completos; os limites estão destacados para não confundir o MVP acadêmico com uma versão pronta para produção.

| Requisito | História / critérios principais | Interface e API | Estado no MVP |
|---|---|---|---|
| RF01 — Cadastro, login e e-mail institucional | US01 / CA01.1–CA01.4 | `/cadastro`, `/login`; `POST /auth/register`, `/auth/verify-email`, `/auth/resend-verification`, `POST /auth/login` | **Implementado para desenvolvimento.** Verificação de 24h e bloqueio de domínios não autorizados; envio SMTP real depende de configuração do ambiente. |
| RF02 — Publicar item achado | US02 / CA02.1–CA02.5 | `/novo`; `POST /items` | **Implementado.** Valida campos, pergunta/resposta, pelo menos uma foto, até três arquivos e regras para categorias sensíveis. |
| RF03 — Publicar item perdido | US03 / CA03.1–CA03.2 | `/novo`; `POST /items` | **Implementado.** Foto opcional; pesquisa possíveis correspondências ao publicar. |
| RF04 — Busca e filtros | US04 / CA04.1–CA04.3 | Página inicial; `GET /items` | **Implementado no MVP.** Texto, tipo, categoria, local, status público e período; lista paginada e estado vazio. |
| RF05 — Detalhes sem dados secretos | US04 / CA04.4 | `/item/:id`; `GET /items/{id}` | **Implementado.** Pergunta/resposta esperada não são enviadas pela rota pública; a pergunta é entregue por endpoint autenticado separado durante a reivindicação. |
| RF06 — Reivindicar achado | US05 / CA05.1–CA05.4 | Detalhe do item; `GET /items/{id}/verification-question`, `POST /items/{id}/claims` | **Implementado.** Bloqueia item próprio, item indisponível e reivindicação ativa duplicada. |
| RF07 — Aprovar/recusar reivindicação | US06 / CA06.1, CA06.2, CA06.4 | Meus itens e painel de moderação; `PATCH /claims/{id}/decision` | **Implementado.** O publicador decide nos anúncios comuns; a equipe decide nos itens guardados ou nas solicitações encaminhadas. |
| RF08 — Chat privado | US06 / CA06.3 | Cartão de reivindicação; `GET/POST /claims/{id}/messages` | **Implementado.** Só após aprovação, limite de 500 caracteres e respostas limitadas a ID/nome do remetente, sem expor e-mail. |
| RF09 — Confirmar devolução | US07 / CA07.1–CA07.2 | Meus itens e reivindicações de ponto de guarda; `POST /claims/{id}/returned` | **Parcial.** Marca o item como resolvido e registra o responsável; uma tela de histórico detalhado acessível ao usuário ainda não foi concluída. |
| RF10 — Notificações por e-mail e in-app | US08 / CA08.1–CA08.2 | Notificações e preferências; `/notifications`, `/auth/preferences` | **Parcial.** Notificações in-app e tentativas de e-mail síncronas; SLA de 15 min, fila transacional e confirmação de entrega exigem infraestrutura adicional. |
| RF11 — Sugestões de correspondência | US08 / CA08.1 | Publicação e rotina do backend; serviço de correspondências | **Implementado como heurística inicial.** Categoria, mesmo bloco/local e janela de 15 dias; a classificação não usa similaridade semântica avançada. |
| RF12 — Denúncia | US09 / CA09.1–CA09.2 | Detalhe do item; `POST /items/{id}/reports` | **Parcial.** Denúncia de anúncio, bloqueio de duplicidade e ocultação após três denunciantes e suspensão automática após três denúncias procedentes; denúncia direta de perfil não foi incluída no DER/código. |
| RF13 — Painel de moderação | US10 / CA10.1, CA10.3 | `/moderacao`; `/moderation/reports`, `/moderation/claims`, `/moderation/log` | **Implementado para o fluxo principal.** Decisões exigem justificativa e geram log; painel protegido por papel. |
| RF14 — Itens recebidos no ponto de guarda | US10 / CA10.2 | Formulário de publicação da equipe; `POST /moderation/guard-items` | **Implementado.** Exige perfil autorizado, tipo achado, ponto de guarda ativo e local consistente. |
| RF15 — Expiração automática | RN11 / rotina do sistema | Comando `items:expire` e Scheduler às 02:00 | **Parcial.** Expira anúncios e gera aviso interno com sete dias para item guardado; política institucional configurável, envio formal e fluxo de descarte/doação ainda dependem de complementação. |
| RF16 — Consultar/gerenciar anúncios e reivindicações | US11 / CA11.1–CA11.2 | `/meus-itens`; `GET /my-items`, `PATCH /items/{id}` | **Implementado no essencial.** Lista status e permite editar título, descrição e fotos de anúncios abertos; exclusão/anonimização de conta não foi incluída. |
| RF17 — Administração | US12 / CA12.1–CA12.2 | `/administracao`; rotas `/admin/categories`, `/admin/locations`, `/admin/guard-points`, `/admin/users`, `/admin/domains` | **Implementado no essencial.** Cadastro/ativação de categorias, locais, pontos, domínios e gestão de perfis/status; sem workflow completo de aprovação e auditoria de todas as mudanças. |

## Testes automatizados incluídos

O conjunto `backend/tests/Feature/ItemRulesTest.php` contém testes para foto obrigatória em item achado, publicação de item perdido sem foto, privacidade de dados de verificação, pergunta de verificação protegida, duplicidade de reivindicação ativa, impedimento de autodenúncia, mensagens de chat sem e-mail, bloqueio de token de conta suspensa e rejeição de domínio não institucional.

Execute com `cd backend && php artisan test` após instalar as dependências e configurar o ambiente. A preparação deste pacote permitiu validar sintaxe PHP/JSX e o YAML do contrato; os testes integrados e o build precisam ser executados em ambiente com Composer, driver PDO compatível e dependências npm instaladas.
