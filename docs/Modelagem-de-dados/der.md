### Diagrama Entidade-Relacionamento

```mermaid
erDiagram
    USUARIO ||--o{ ITEM : publica
    USUARIO ||--o{ REIVINDICACAO : solicita
    USUARIO ||--o{ MENSAGEM : envia
    USUARIO ||--o{ DENUNCIA : registra
    USUARIO ||--o{ NOTIFICACAO : recebe
    USUARIO ||--o{ LOG_MODERACAO : executa
    CATEGORIA ||--o{ ITEM : classifica
    LOCAL_CAMPUS ||--o{ ITEM : ocorre_em
    PONTO_GUARDA ||--o{ ITEM : armazena
    LOCAL_CAMPUS ||--o{ PONTO_GUARDA : abriga
    ITEM ||--o{ ITEM_FOTO : possui
    ITEM ||--o{ REIVINDICACAO : recebe
    ITEM ||--o{ DENUNCIA : alvo
    REIVINDICACAO ||--o{ MENSAGEM : contem
    ITEM }o--o{ ITEM : correspondencia

    USUARIO {
        uuid id PK
        string nome
        string email UK
        string senha_hash
        string papel
        string status
        timestamp criado_em
    }
    ITEM {
        uuid id PK
        uuid usuario_id FK
        uuid categoria_id FK
        uuid local_id FK
        uuid ponto_guarda_id FK
        string tipo
        string titulo
        text descricao
        date data_ocorrencia
        string pergunta_verificacao
        string resposta_verificacao
        string status
        timestamp expira_em
        timestamp criado_em
    }
    REIVINDICACAO {
        uuid id PK
        uuid item_id FK
        uuid solicitante_id FK
        text resposta_verificacao
        string status
        text motivo_recusa
        timestamp criado_em
        timestamp decidido_em
    }
```

### Relacionamentos e restrições

- Usuário 1:N Item; Usuário 1:N Reivindicação; Usuário 1:N Notificação.
- Categoria 1:N Item; Local 1:N Item; Ponto de guarda 1:N Item.
- Item 1:N Item\_foto (máximo de 3, garantido por restrição ordem BETWEEN 1 AND 3 e unicidade de item\_id + ordem).
- Item 1:N Reivindicação; Reivindicação 1:N Mensagem.
- Item N:N Item via Correspondência (perdido × achado).
- Índice único parcial em reivindicacao (item\_id, solicitante\_id) onde status in (PENDENTE, APROVADA), garantindo a RN08.
- Índice único parcial em reivindicacao (item\_id) onde status = APROVADA, garantindo a RN09.
- Índice único em denuncia (item\_id, denunciante\_id), garantindo a regra de denúncia única (CA09.2).
- Restrição CHECK: itens do tipo ACHADO exigem pergunta\_verificacao não nula (RN05).
- Índices recomendados: item (status, tipo, categoria\_id, local\_id, criado\_em DESC) e GIN em item.busca (RNF01).
