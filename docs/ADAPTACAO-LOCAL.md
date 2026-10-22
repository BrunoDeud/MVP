# Adaptação da arquitetura técnica para execução local

## Motivo da adaptação

A arquitetura de referência do planejamento anterior previa React + Laravel + MySQL. Para possibilitar a execução e a demonstração do MVP em computadores com poucas dependências, a implementação foi simplificada para Python com módulos da biblioteca padrão, interface web nativa e SQLite. A substituição está registrada nos ADRs 001–004.

## Componentes da implementação

- **Frontend:** `index.html`, HTML5/CSS3/JavaScript nativos.
- **Backend e API:** `app.py`, servidor HTTP baseado em `http.server`, rotas JSON, validações, autorização e regras de negócio.
- **Banco:** SQLite gerenciado pela biblioteca `sqlite3`, arquivo `data/encontrei.sqlite3`.
- **Fotos:** diretório `uploads/`, servido pelo próprio servidor local.
- **Testes:** `test_app.py`, `unittest`, chamadas HTTP contra um servidor de teste e banco SQLite temporário.
- **Execução:** `executar.bat` no Windows ou `python app.py` em terminal.

## Requisitos atendidos pela versão

A implementação inclui login, cadastro de conta com domínio autorizado e fluxo local de verificação, publicação/busca/edição de anúncios, foto validada, categorias e locais administráveis, reivindicações com verificação e aprovação/recusa, mensagens internas, confirmação de devolução, histórico, notificações in-app, correspondências iniciais, denúncias de item e perfil, fila e decisões de moderação, ponto de guarda, expiração, administração e restrições de publicação.

O link de reenvio de verificação também está disponível no modal de login. O link de reenvio de verificação também está disponível no modal de login. O mapeamento por requisito, história, regra, API e testes está em [`implementacao/escopo-mvp.md`](implementacao/escopo-mvp.md). A API está documentada em [`api/api-local.md`](api/api-local.md) e [`api/openapi.yaml`](api/openapi.yaml). O DER atual está em [`Modelagem-de-dados/der.md`](Modelagem-de-dados/der.md).

## Limites explícitos

- O link de verificação é criado e validado pela aplicação. Sem SMTP configurado, ele é disponibilizado para abrir manualmente; o backend agora pode enviar e-mails de verificação e notificações se as variáveis `ENCONTREI_SMTP_*` forem configuradas antes do início do servidor.
- As notificações internas são persistidas no SQLite. A preferência de e-mail é editável na interface. O envio externo só ocorre quando SMTP está configurado e o usuário verificado habilitou a preferência; sem SMTP, a aplicação não envia e-mail.
- A manutenção automática roda quando o servidor inicia, ao receber requisições e por thread daemon a cada 60 segundos enquanto o processo está ligado. Não é um worker separado e não opera quando a aplicação está fechada.
- A autenticação guarda tokens em memória, não em cookies de sessão persistentes; tokens são perdidos ao reiniciar o servidor.
- `http.server` e SQLite local são apropriados para demonstração acadêmica, não para expor na internet ou atender concorrência de produção.
- O processo de descarte/doação física de objetos depois do prazo de guarda deve seguir a política da instituição; o sistema registra expiração/avisos, mas não decide nem executa descarte físico.

Esses limites são apresentados de forma explícita para não declarar como implantados serviços externos que não fazem parte deste pacote.
