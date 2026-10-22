# Adaptação para apresentação local

Esta versão mantém o objetivo do projeto acadêmico Encontrei — Achados e Perdidos e os principais fluxos demonstráveis, mas simplifica a arquitetura para que a aplicação possa ser executada num computador com o mínimo de configuração.

## Arquitetura da versão atual

- **Interface:** HTML, CSS e JavaScript nativos em `index.html`.
- **Servidor e API:** Python 3.10 ou superior, usando a biblioteca padrão, especialmente `http.server` e `json`.
- **Persistência:** SQLite via `sqlite3`; o arquivo `data/encontrei.sqlite3` é criado automaticamente.
- **Arquivos de imagem:** armazenados localmente em `uploads/`.
- **Inicialização:** `executar.bat` inicia o servidor e abre o navegador em `http://127.0.0.1:8000`.
- **Dependências externas:** nenhuma biblioteca Python, pacote npm ou serviço de banco separado.

As escolhas atuais estão registradas nos [ADRs](ADRs/README.md). Os ADRs anteriores que definiam React, Laravel e MySQL foram substituídos para a versão local simplificada.

## Documentação de origem e implementação atual

Os requisitos, histórias de usuário, regras de negócio e wireframes originais continuam sendo a referência de escopo desejado. Nem todos os itens dessa especificação estão implementados nesta versão local; os limites conhecidos estão listados no `README.md` principal.

O [DER](Modelagem-de-dados/der.md) descreve as tabelas SQLite da implementação atual. O contrato OpenAPI que originalmente acompanhava a arquitetura Laravel foi preservado como referência do desenho técnico anterior; ele não deve ser usado como contrato exato da API local. Os endpoints atuais estão descritos em [API local](api/api-local.md).

## Funcionalidades principais demonstráveis

A versão local inclui consulta e filtros, detalhes, publicação, fotos locais, pergunta e resposta de verificação, reivindicação, aprovação/recusa, mensagens após aprovação, resolução de anúncios, denúncias e um painel básico de moderação.

## Limitações

- É uma aplicação de demonstração local, não para exposição direta na internet.
- As contas de demonstração já são criadas no primeiro início; cadastro e verificação de e-mail institucional real não estão integrados.
- Não há envio real de e-mails, expiração agendada, notificações externas ou todos os painéis administrativos da arquitetura original.
- Tokens ficam em memória e expiram quando o servidor é reiniciado.
- As fotos e o banco são armazenados no computador local.
