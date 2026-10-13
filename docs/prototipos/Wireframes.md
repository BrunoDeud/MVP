## Protótipos de Tela (Wireframes)

As telas abaixo cobrem as histórias de usuário do MVP. Os wireframes de baixa fidelidade navegáveis acompanham este documento como página separada (mobile-first). A tabela mostra a rastreabilidade entre tela e história.

| Código | Tela | Histórias | Elementos principais |
| --- | --- | --- | --- |
| T01 | Login / Cadastro | US01 | Campo de e-mail institucional, senha, botão "Entrar", link "Criar conta", mensagem de verificação. |
| T02 | Home / Lista de itens | US04 | Barra de busca, abas "Achados" e "Perdidos", filtros (categoria, local, período), cards com foto, título, local e data, botão flutuante "+". |
| T03 | Detalhe do item | US04, US05, US09 | Galeria de fotos, descrição, local, data, status, botão "É meu" (achados), botão "Denunciar". |
| T04 | Publicar item | US02, US03 | Seletor Achei/Perdi, título, categoria, descrição, local, data, upload de fotos, pergunta de verificação (achados). |
| T05 | Reivindicar item | US05 | Perguntas de verificação, campo de resposta, botão "Enviar solicitação". |
| T06 | Meus itens | US11, US06, US07 | Abas "Meus anúncios" e "Minhas solicitações", status por cartão, ações de aprovar/recusar/devolver. |
| T07 | Análise de reivindicação e mensagens | US06, US07 | Respostas do solicitante, botões Aprovar/Recusar, canal de mensagens, botão "Marcar como devolvido". |
| T08 | Notificações | US08 | Lista cronológica, indicador de não lidas, preferências de e-mail. |
| T09 | Painel do moderador | US09, US10 | Fila de denúncias, cadastro de item no ponto de guarda, histórico de ações. |
| T10 | Painel do administrador | US12 | CRUD de categorias, locais, pontos de guarda e moderadores. |

**Fluxo principal:** T01 → T02 → T03 → T05 → T06/T07 (reivindicação) e T02 → T04 → T06 (publicação).