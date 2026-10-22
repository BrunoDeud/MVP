# Diagrama Entidade-Relacionamento (DER) — implementação Python + SQLite

Este DER representa o banco criado por `init_db()` em `app.py`, não o esquema previsto na arquitetura original Laravel/MySQL. O arquivo em execução é `data/encontrei.sqlite3`.

```mermaid
erDiagram
    USERS ||--o{ ITEMS : publica
    USERS ||--o{ CLAIMS : solicita
    ITEMS ||--o{ CLAIMS : recebe
    USERS ||--o{ REPORTS : denuncia_anuncio
    ITEMS ||--o{ REPORTS : denunciado
    USERS ||--o{ PROFILE_REPORTS : denuncia_perfil
    USERS ||--o{ PROFILE_REPORTS : alvo_denuncia
    USERS ||--o{ MESSAGES : envia
    CLAIMS ||--o{ MESSAGES : contem
    USERS ||--o{ NOTIFICATIONS : recebe
    ITEMS o|--o{ NOTIFICATIONS : referencia
    CLAIMS o|--o{ NOTIFICATIONS : referencia
    USERS ||--o{ MODERATION_ACTIONS : executa
    ITEMS o|--o{ MODERATION_ACTIONS : referencia
    REPORTS o|--o{ MODERATION_ACTIONS : analisada
    USERS o|--o{ CLAIMS : decide
    USERS o|--o{ REPORTS : decide
    USERS o|--o{ PROFILE_REPORTS : decide
    USERS ||--o{ ITEM_HISTORY : atua
    ITEMS ||--o{ ITEM_HISTORY : historico
    CATEGORIES o|--o{ ITEMS : classifica
    LOCATIONS o|--o{ ITEMS : localiza
    LOCATIONS ||--o{ GUARD_POINTS : contem
    GUARD_POINTS o|--o{ ITEMS : recebe

    USERS {
        integer id PK
        text name
        text email UK
        text role
        text status
        integer email_verified
        text salt
        text password_hash
        text verification_token
        text verification_expires_at
        integer email_notifications
        text created_at
    }
    INSTITUTIONAL_DOMAINS {
        integer id PK
        text domain UK
        integer active
        text created_at
    }
    CATEGORIES {
        integer id PK
        text name UK
        integer requires_guard
        integer active
        text created_at
    }
    LOCATIONS {
        integer id PK
        text name UK
        text block_name
        integer active
        text created_at
    }
    GUARD_POINTS {
        integer id PK
        text name
        integer location_id FK
        text reference
        integer retention_days
        integer active
        text created_at
    }
    ITEMS {
        integer id PK
        text title
        text type
        text category
        integer category_id FK
        text description
        text location
        integer location_id FK
        text event_date
        text status
        integer owner_id FK
        integer guard_point_id FK
        text verification_question
        text verification_answer
        text photos_json
        text created_at
        text updated_at
        text resolved_at
        text expiration_warned_at
    }
    CLAIMS {
        integer id PK
        integer item_id FK
        integer claimant_id FK
        text answer
        text status
        integer routed_to_moderation
        text created_at
        text updated_at
        integer decision_by FK
        text decision_note
        text returned_at
    }
    REPORTS {
        integer id PK
        integer item_id FK
        integer reporter_id FK
        text reason
        text status
        text created_at
        integer decision_by FK
        text decision_note
        text decided_at
    }
    PROFILE_REPORTS {
        integer id PK
        integer target_user_id FK
        integer reporter_id FK
        text reason
        text status
        text created_at
        integer decision_by FK
        text decision_note
        text decided_at
    }
    MESSAGES {
        integer id PK
        integer claim_id FK
        integer sender_id FK
        text body
        text created_at
    }
    NOTIFICATIONS {
        integer id PK
        integer user_id FK
        text type
        text title
        text body
        integer item_id FK
        integer claim_id FK
        integer is_read
        text created_at
    }
    MODERATION_ACTIONS {
        integer id PK
        integer moderator_id FK
        integer item_id FK
        integer report_id FK
        text action
        text justification
        text created_at
    }
    ITEM_HISTORY {
        integer id PK
        integer item_id FK
        integer actor_id FK
        text action
        text note
        text created_at
    }
```

## Tabelas e responsabilidades

| Tabela | Finalidade |
|---|---|
| `users` | Contas, papel, status, hash da senha e estado/token de verificação. |
| `institutional_domains` | Lista administrável de domínios de e-mail aceitos no cadastro. |
| `categories` | Catálogo de categorias, com sinalizador para obrigatoriedade de ponto de guarda e estado ativo. |
| `locations` | Catálogo de locais do campus e seu bloco/prédio. |
| `guard_points` | Pontos físicos autorizados, locais e prazo de retenção. |
| `items` | Anúncios de achados/perdidos, classificação, publicador, estado, fotos e pergunta/resposta privada. `category` e `location` também são mantidos como snapshot textual para preservar a leitura histórica caso o catálogo mude. |
| `claims` | Reivindicações, estado, encaminhamento à moderação, decisão e data da devolução. |
| `reports` | Denúncias de anúncios com status e decisão de moderação. |
| `profile_reports` | Denúncias de perfil com integridade que impede autodenúncia e repetição da mesma denúncia pela mesma conta. |
| `messages` | Conversas associadas à reivindicação aprovada. |
| `notifications` | Notificações in-app do usuário, com referência opcional ao item e à reivindicação. |
| `moderation_actions` | Auditoria de ações de moderação com autor, ação, data e justificativa. |
| `item_history` | Histórico de alterações, resolução, devolução e expiração de um anúncio. |

## Integridade, restrições e índices

- Todas as tabelas têm chave primária `INTEGER PRIMARY KEY AUTOINCREMENT`.
- As referências relacionais usam `REFERENCES`; `PRAGMA foreign_keys=ON` é habilitado em cada conexão.
- `users.email`, `institutional_domains.domain`, `categories.name` e `locations.name` são únicos, com comparação sem distinção entre maiúsculas/minúsculas quando configurada no esquema.
- `users.role` aceita `Estudante`, `Moderador` ou `Administrador`; `status` é validado na lógica entre `Ativo`, `Suspenso` e o estado de cadastro `Pendente`.
- `items.type` limita-se a `Achado` ou `Perdido`; o restante das transições de status é validado no backend.
- `guard_points.retention_days` deve estar entre 30 e 365; `messages.body` deve ter de 1 a 500 caracteres; booleanos guardados em SQLite usam `CHECK` de 0/1.
- `reports` possui unicidade `(item_id, reporter_id)`, e `profile_reports` possui unicidade `(target_user_id, reporter_id)` e `CHECK(target_user_id <> reporter_id)`.
- Índice único parcial `one_active_claim_per_user_item` impede duas reivindicações pendentes/aprovadas do mesmo usuário para o mesmo item. O índice único parcial `one_approved_claim_per_item` garante RN09 também no banco: apenas uma reivindicação pode permanecer aprovada por item.
- Índices auxiliares cobrem status/tipo/data de anúncios, publicador/status, status/data de reivindicação e denúncia, notificações por usuário/leitura/data, mensagens por reivindicação/data, histórico por item/data e denúncias de perfil por alvo/status.
- `photos_json` guarda caminhos relativos às fotos em JSON; os binários ficam em `uploads/`.
- A resposta de verificação fica no banco local e não é devolvida nos detalhes públicos. É informação de demonstração; não usar itens/dados reais neste pacote acadêmico.

## Dados iniciais

Na primeira execução, `init_db()` cria os catálogos de categorias e locais, domínios de teste `campus.edu.br` e `alunos.campus.edu.br`, o ponto de guarda da portaria, quatro usuários de demonstração e cinco anúncios fictícios com imagens geradas localmente. A operação é idempotente: usuários/catálogos existentes não são inseridos novamente.

## Observação de coerência

O DER aqui apresentado corresponde ao schema da versão local atual. Ele substitui, para esta implementação, o modelo original feito para a arquitetura Laravel/MySQL. O `README.md` e a matriz `docs/implementacao/escopo-mvp.md` identificam as adaptações e os requisitos parcialmente atendidos.
