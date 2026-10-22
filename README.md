# Encontrei — Achados e Perdidos (MVP local)

## 1. Descrição do sistema

O **Encontrei** é uma aplicação web acadêmica para a comunidade de uma instituição de ensino registrar objetos perdidos e encontrados, buscar anúncios, solicitar a devolução de itens, trocar mensagens internas após a aprovação de uma reivindicação e acionar a moderação quando necessário.

## 2. Objetivo do MVP

Entregar um fluxo demonstrável de ponta a ponta com interface web, API HTTP, persistência relacional, validações, regras de negócio, autorização por perfil, dados iniciais e testes automatizados. Esta edição utiliza Python e SQLite para reduzir a configuração necessária no computador da apresentação.

> **Importante sobre a arquitetura:** a documentação técnica original previa React + Laravel + MySQL. Para facilitar a execução local, a implementação deste pacote foi adaptada para HTML/CSS/JavaScript, Python e SQLite. O escopo e os requisitos originais continuam documentados; a matriz de rastreabilidade descreve honestamente quais critérios estão implementados e quais dependem de serviço externo ou são parciais.

## 3. Tecnologias utilizadas

- Python 3.10 ou superior;
- `http.server` para o servidor HTTP e a API JSON;
- `sqlite3` para persistência SQL;
- `hashlib.pbkdf2_hmac` para derivação/hash de senhas;
- HTML5, CSS3 e JavaScript nativo no frontend;
- `unittest` para testes automatizados;
- SQLite, banco em arquivo criado automaticamente.

Não são necessários Flask, Django, Laravel, PHP, Composer, Node.js, npm, Docker ou um serviço MySQL. Não há dependências de terceiros para instalar.

## 4. Arquitetura da aplicação

```text
Navegador (index.html)
      │ fetch() / JSON + token Bearer
      ▼
Servidor Python (app.py :8000)
      ├── validações e regras de negócio
      ├── autorização (Estudante / Moderador / Administrador)
      ├── arquivos de fotos em uploads/
      └── sqlite3
             ▼
      data/encontrei.sqlite3
```

- `app.py`: servidor web, API, autenticação, autorização, regras e acesso ao banco.
- `index.html`: interface responsiva que consome a API por `fetch`.
- `data/encontrei.sqlite3`: banco criado em tempo de execução.
- `uploads/`: imagens carregadas e imagens demonstrativas.
- `test_app.py`: testes de integração HTTP/API executáveis com a biblioteca padrão.
- `docs/`: requisitos, histórias, regras de negócio, DER, ADRs, protótipos, contrato da API e rastreabilidade.

## 5. Pré-requisitos

- Windows 10/11, macOS ou Linux;
- Python 3.10+ disponível no terminal;
- navegador moderno (Chrome, Edge ou Firefox).

No Windows, instale o Python em https://www.python.org/downloads/windows/ e marque **Add python.exe to PATH** durante a instalação.

## 6. Instalação e execução

### Windows (recomendado para apresentação)

1. Extraia o ZIP completo para uma pasta local.
2. Dê dois cliques em `executar.bat`.
3. O script tenta localizar `python` e, em seguida, `py`; o servidor inicia em `http://127.0.0.1:8000` e tenta abrir o navegador automaticamente.
4. Mantenha o terminal aberto durante a apresentação. Use `Ctrl+C` nessa janela para encerrar.

### Terminal em qualquer sistema

Na pasta do projeto, execute:

```bash
python app.py
```

Se sua instalação usa `python3`:

```bash
python3 app.py
```

Abra http://127.0.0.1:8000. Se a porta 8000 estiver ocupada, encerre o outro processo antes de iniciar; o MVP está configurado para a porta 8000.

### Verificação rápida

Com o servidor ligado, acesse http://127.0.0.1:8000/api/health. Uma resposta saudável contém `"ok": true` e `"database": "SQLite"`.

## 7. Variáveis de ambiente

Esta versão não exige arquivo `.env` nem variáveis de ambiente para iniciar. O endereço local é definido pelas constantes `HOST` e `PORT` em `app.py` (padrões `127.0.0.1` e `8000`). A configuração de e-mail institucional (domínios permitidos) é feita pelo catálogo de domínios, acessível pelo administrador.

O cadastro cria uma URL de verificação válida por 24 horas. Sem SMTP, a URL é devolvida pela interface para abrir manualmente em modo local. O envio real de verificação e de notificações pode ser habilitado opcionalmente pelas variáveis SMTP abaixo; credenciais nunca devem ser gravadas no código ou versionadas no Git.

### SMTP opcional (somente se houver provedor e credenciais)

O servidor usa os módulos `smtplib` e `ssl` da biblioteca padrão. Configure estas variáveis de ambiente **antes** de executar `app.py`: `ENCONTREI_SMTP_HOST`, `ENCONTREI_SMTP_PORT` (padrão `587`), `ENCONTREI_SMTP_USER`, `ENCONTREI_SMTP_PASSWORD`, `ENCONTREI_SMTP_FROM`, `ENCONTREI_SMTP_TLS` (`true` por padrão) e `ENCONTREI_SMTP_SSL` (`false` por padrão; use SSL direto, normalmente na porta `465`, quando exigido pelo provedor).

Exemplo de configuração temporária em PowerShell (substitua pelos dados do provedor; não compartilhe o terminal com credenciais):

```powershell
$env:ENCONTREI_SMTP_HOST = "smtp.seu-provedor.com"
$env:ENCONTREI_SMTP_PORT = "587"
$env:ENCONTREI_SMTP_USER = "conta@seu-provedor.com"
$env:ENCONTREI_SMTP_PASSWORD = "SENHA_DE_APLICATIVO"
$env:ENCONTREI_SMTP_FROM = "conta@seu-provedor.com"
$env:ENCONTREI_SMTP_TLS = "true"
python app.py
```

Quando essas variáveis não estiverem definidas, a aplicação continua funcionando localmente e mantém as notificações in-app. Quando e-mails forem habilitados na tela “Meus registros”, notificações por e-mail são tentadas apenas se o usuário tiver verificado a conta e existir uma configuração SMTP válida.

## 8. Banco de dados

- Banco: SQLite;
- Arquivo: `data/encontrei.sqlite3`;
- Criação do schema, índices, catálogo e contas de demonstração: automática na inicialização (`init_db()` em `app.py`);
- Integridade: chaves primárias, chaves estrangeiras com `PRAGMA foreign_keys=ON`, restrições `CHECK`, valores únicos e índices;
- Imagens: arquivos no diretório `uploads/`; o banco guarda seus caminhos;
- Persistência: os dados permanecem após fechar/reabrir o servidor.

Para reiniciar a demonstração do zero, encerre o servidor e exclua `data/encontrei.sqlite3`. Na inicialização seguinte, o banco e os dados fictícios serão recriados. Para eliminar imagens enviadas, exclua os arquivos em `uploads/`, preservando imagens `demo-*.png` se desejar manter as imagens iniciais.

O esquema efetivo está documentado em [`docs/Modelagem-de-dados/der.md`](docs/Modelagem-de-dados/der.md).

## 9. Contas iniciais para demonstração

| Perfil | E-mail | Senha |
|---|---|---|
| Estudante | `estudante@campus.edu.br` | `Estudante@12345` |
| Estudante | `lucas@campus.edu.br` | `Lucas@12345` |
| Moderador | `moderador@campus.edu.br` | `Moderador@12345` |
| Administrador | `admin@campus.edu.br` | `Admin@12345` |

São contas totalmente fictícias para teste local. Não reutilize as credenciais em nenhum ambiente público ou com dados reais.

## 10. Funcionalidades do MVP

- Cadastro, login, logout, verificação local de e-mail, reenvio de link expirado e validação de domínio institucional permitido;
- Busca textual, filtros combinados por tipo/categoria/local/período/status e paginação;
- Visualização de anúncios sem revelar resposta de verificação ou contato pessoal;
- Publicação de achados e perdidos, limite de 3 fotos, limite de tamanho/tipo, validação de pergunta/resposta para achados;
- Regra de ponto de guarda para categorias sensíveis;
- Consulta e edição de anúncios próprios, exclusão quando não há histórico e preservação de histórico quando necessário;
- Sugestões de correspondência por categoria, localização/bloco e diferença de data de até 15 dias;
- Reivindicação, prevenção de duplicidade, pergunta de verificação, decisão de aprovar/recusar e cancelamento de reivindicações pendentes concorrentes;
- Mensagens privadas somente após aprovação, restritas aos participantes e sem expor e-mail;
- Confirmação de devolução e histórico;
- Notificações in-app, marcar uma/todas como lidas e preferências para e-mail (SMTP é opcional e configurável por ambiente);
- Denúncias de anúncios e perfis, fila de moderação, justificativas e registro de ações;
- Painel de administração para categorias, locais, pontos de guarda, domínios institucionais e perfis/status de usuários;
- Expiração automática por rotina periódica em segundo plano enquanto o servidor está ligado (a cada 60 segundos) e por acionamento na API: anúncios abertos após 60 dias sem atividade; itens no ponto de guarda conforme prazo configurado, com aviso interno 7 dias antes; reivindicações pendentes há 7 dias são encaminhadas à fila da moderação.

## 11. Regras de negócio importantes

- E-mail deve pertencer a domínio ativo do catálogo institucional; o link local de verificação expira após 24 horas.
- Achados exigem pelo menos uma foto e pergunta/resposta privada; perdidos podem ficar sem foto.
- Até 3 fotos por anúncio, JPG/PNG/WEBP, no máximo 5 MB cada, com checagem de assinatura do arquivo.
- Usuário não pode reivindicar seu próprio anúncio; só pode manter uma reivindicação ativa por anúncio.
- Itens resolvidos, expirados e ocultos não aparecem na busca pública padrão.
- O limite de publicação é de 10 anúncios abertos por usuário e 5 anúncios por dia.
- Um anúncio com 3 denúncias pendentes de usuários distintos é ocultado para revisão; 3 denúncias procedentes podem suspender a conta.
- Toda decisão de moderação registra responsável, data e justificativa.

As regras correspondem aos IDs RN01–RN18 da documentação de requisitos; veja a matriz de rastreabilidade para critérios de aceite e eventuais limites.

## 12. API e endpoints

A API local usa `http://127.0.0.1:8000/api`. Salvo as rotas públicas, as requisições protegidas usam `Authorization: Bearer <token>`. Todas as rotas, payloads, papéis e códigos HTTP estão em [`docs/api/api-local.md`](docs/api/api-local.md). A especificação legível por ferramentas está em [`docs/api/openapi.yaml`](docs/api/openapi.yaml).

## 13. Testes

A suíte contém **31 testes automatizados de integração HTTP e manutenção**. Usa apenas `unittest`, `urllib` e banco temporário. Ela sobe um servidor HTTP isolado e testa a API, as validações, autorização, persistência e regras de negócio.

```bash
python -m unittest -v test_app.py
```

Os testes não modificam o banco de demonstração: criam um banco temporário. A listagem de cenários, resultado esperado e ligação com requisitos está em [`docs/testes/plano-de-testes.md`](docs/testes/plano-de-testes.md).

## 14. Protótipos e documentação técnica

- Wireframes Markdown: [`docs/prototipos/Wireframes.md`](docs/prototipos/Wireframes.md)
- Arquivo de protótipos Excalidraw: [`docs/prototipos/wireframes-achados-perdidos.excalidraw`](docs/prototipos/wireframes-achados-perdidos.excalidraw)
- Requisitos funcionais: [`docs/requisitos/Requisitos-funcionais .md`](docs/requisitos/Requisitos-funcionais%20.md)
- Histórias e critérios de aceite: [`docs/requisitos/historias-de-usuario.md`](docs/requisitos/historias-de-usuario.md)
- Regras de negócio: [`docs/requisitos/regras-de-negocios.md`](docs/requisitos/regras-de-negocios.md)
- DER atual: [`docs/Modelagem-de-dados/der.md`](docs/Modelagem-de-dados/der.md)
- Matriz de rastreabilidade: [`docs/implementacao/escopo-mvp.md`](docs/implementacao/escopo-mvp.md)
- Plano e evidências de testes: [`docs/testes/plano-de-testes.md`](docs/testes/plano-de-testes.md)
- Decisões arquiteturais: [`docs/ADRs/README.md`](docs/ADRs/README.md)

## 15. Limitações conhecidas e segurança

Este projeto é um MVP acadêmico local. O servidor da biblioteca padrão não é um servidor de produção e está vinculado a `127.0.0.1` por padrão. Sessões em token ficam em memória e terminam quando o servidor é encerrado. Redefinição de senha, autenticação institucional externa, implantação pública, backup/retention operacional e teste de carga não fazem parte desta configuração local. O envio de e-mail somente funciona se um servidor SMTP externo válido for configurado. A verificação de e-mail é real dentro da lógica da aplicação (conta pendente/ativa e token com expiração); sem SMTP o link deve ser aberto manualmente.

O projeto contém usuários e dados fictícios. Não o exponha diretamente à internet e não use dados pessoais reais. Para produção seriam necessários, no mínimo, servidor WSGI adequado, HTTPS, gestão segura de segredos, envio de e-mail configurado, sessões persistentes/seguras, política de backup e hardening adicional.
