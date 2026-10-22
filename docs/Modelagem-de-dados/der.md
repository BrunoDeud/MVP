# Diagrama Entidade-Relacionamento (DER) — versão local simplificada

Este DER corresponde ao esquema SQLite criado pela função `init_db()` em `app.py`. Ele representa o banco que é realmente utilizado pela versão simplificada, e não o esquema planejado originalmente para Laravel/MySQL.

```mermaid
erDiagram
    USERS ||--o{ ITEMS : publica
    USERS ||--o{ CLAIMS : solicita
    ITEMS ||--o{ CLAIMS : recebe
    USERS ||--o{ REPORTS : denuncia
    ITEMS ||--o{ REPORTS : recebe
    USERS ||--o{ MESSAGES : envia
    CLAIMS ||--o{ MESSAGES : possui
    USERS ||--o{ MODERATION_ACTIONS : executa
    ITEMS o|--o{ MODERATION_ACTIONS : referencia
    REPORTS o|--o{ MODERATION_ACTIONS : analisa
    USERS o|--o{ CLAIMS : decide

    USERS {
        integer id PK
        text name
        text email UK
        text role
        text salt
        text password_hash
        text created_at
    }
    ITEMS {
        integer id PK
        text title
        text type
        text category
        text description
        text location
        text event_date
        text status
        integer owner_id FK
        text verification_question
        text verification_answer
        text photos_json
        text created_at
        text updated_at
    }
    CLAIMS {
        integer id PK
        integer item_id FK
        integer claimant_id FK
        text answer
        text status
        text created_at
        text updated_at
        integer decision_by FK
        text decision_note
    }
    REPORTS {
        integer id PK
        integer item_id FK
        integer reporter_id FK
        text reason
        text status
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
    MESSAGES {
        integer id PK
        integer claim_id FK
        integer sender_id FK
        text body
        text created_at
    }
```

## Tabelas e relacionamentos

- **`users`** armazena contas de demonstração. `email` é único, sem diferenciar maiúsculas de minúsculas. A senha não é guardada em texto puro: o sistema armazena um salt e o hash PBKDF2.
- **`items`** armazena anúncios de achados e perdidos. `owner_id` referencia quem publicou o anúncio. `photos_json` guarda uma lista de caminhos de imagem em formato JSON textual, e as imagens ficam no diretório `uploads/`.
- **`claims`** registra reivindicações de um item por um usuário. `decision_by` é opcional e referencia o usuário que tomou a decisão.
- **`reports`** registra denúncias. A combinação `(item_id, reporter_id)` é única, impedindo a mesma conta de denunciar repetidamente o mesmo item.
- **`moderation_actions`** registra decisões de moderação com justificativa. As referências a item e denúncia podem ser nulas quando a ação não está ligada a uma denúncia específica.
- **`messages`** guarda mensagens da conversa associada a uma reivindicação aprovada.

## Integridade e regras relevantes

- O SQLite é acessado por `sqlite3`, e `PRAGMA foreign_keys = ON` é ativado em cada conexão.
- `items.type` aceita `Achado` ou `Perdido`; o estado inicial do anúncio é `Aberto`.
- O índice único parcial `one_active_claim_per_user_item` impede mais de uma reivindicação `Pendente` ou `Aprovada` da mesma conta para o mesmo item.
- As tabelas utilizam chaves primárias autoincrementais. As relações entre anúncios, reivindicações, denúncias, mensagens e ações de moderação são protegidas por chaves estrangeiras.
- As validações adicionais (como foto obrigatória para item achado, pergunta/resposta de verificação, limites de publicação, permissões e estados) são aplicadas pela lógica da aplicação em `app.py`.

## Limitações desta modelagem local

Este é um esquema pequeno, voltado para execução em uma máquina e apresentação acadêmica. Categorias e locais são textos em `items`, em vez de entidades normalizadas; fotos são guardadas em uma lista JSON; não existem as tabelas separadas de notificações, correspondências, domínios institucionais e pontos de guarda planejadas para a arquitetura original. A resposta de verificação permanece armazenada em `items.verification_answer` no banco local, embora não seja exposta pela consulta pública de detalhes. Não use esta configuração para dados sensíveis ou produção.
