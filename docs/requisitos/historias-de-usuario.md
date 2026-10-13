### Histórias de Usuário e Critérios de Aceite (BDD)

**US01 — Cadastro e login (RF01)** Como estudante, quero entrar com meu e-mail institucional para que somente a comunidade acadêmica use a plataforma.

- **CA01.1** Dado que informo um e-mail de domínio institucional válido, quando envio o cadastro, então o sistema envia um link de verificação e cria a conta com status "pendente".
- **CA01.2** Dado que informo um e-mail de domínio não institucional, quando envio o cadastro, então o sistema recusa e exibe a mensagem "Use seu e-mail institucional".
- **CA01.3** Dado que cliquei no link de verificação válido, quando a página carrega, então a conta passa para "ativa" e sou autenticado.
- **CA01.4** Dado que o link de verificação expirou (mais de 24h), quando o acesso, então o sistema oferece reenvio do link.

**US02 — Publicar item achado (RF02)** Como pessoa que encontrou um objeto, quero publicá-lo rapidamente para que o dono o encontre.

- **CA02.1** Dado que estou autenticado, quando preencho título, categoria, local, data e ao menos 1 foto e envio, então o item é publicado com status "Aberto" e tipo "Achado".
- **CA02.2** Dado que deixei um campo obrigatório vazio, quando envio, então o sistema destaca o campo e não publica.
- **CA02.3** Dado que anexei foto maior que 5 MB ou formato diferente de JPG/PNG/WEBP, quando envio, então o sistema recusa a foto com mensagem clara.
- **CA02.4** Dado que escolhi a categoria "Documentos", quando visualizo o formulário, então o sistema orienta a entrega ao ponto de guarda e oculta dados sensíveis na descrição.
- **CA02.5** Dado que cadastrei a pergunta de verificação, quando publico, então ela não aparece na página pública do item.

**US03 — Publicar item perdido (RF03)** Como pessoa que perdeu algo, quero registrar o que perdi para ser avisado se alguém encontrar.

- **CA03.1** Dado que estou autenticado, quando informo título, categoria, local provável e data e envio, então o item é publicado com tipo "Perdido".
- **CA03.2** Dado que existe item achado compatível, quando publico o perdido, então o sistema exibe até 5 sugestões de correspondência na confirmação.

**US04 — Buscar e filtrar (RF04, RF05)** Como usuário, quero buscar itens por palavra e filtros para achar o meu objeto rapidamente.

- **CA04.1** Dado que digito um termo, quando busco, então a lista exibe apenas itens abertos cujo título ou descrição contenham o termo.
- **CA04.2** Dado que aplico filtros de tipo, categoria e local, quando confirmo, então a lista respeita todos os filtros combinados.
- **CA04.3** Dado que nenhum item corresponde, quando a busca termina, então o sistema mostra estado vazio com atalho "Publicar item perdido".
- **CA04.4** Dado que abro o detalhe de um item, quando a página carrega, então vejo fotos, descrição, local, data e status, mas não a pergunta/resposta de verificação.

**US05 — Reivindicar item achado (RF06)** Como dono de um objeto, quero comprovar que é meu para recuperá-lo.

- **CA05.1** Dado que vejo um item achado aberto, quando clico em "É meu" e respondo às perguntas de verificação, então a reivindicação é criada com status "Pendente" e o publicador é notificado.
- **CA05.2** Dado que já tenho uma reivindicação pendente para o item, quando tento criar outra, então o sistema bloqueia a duplicidade.
- **CA05.3** Dado que sou o publicador do item, quando tento reivindicá-lo, então o botão não é exibido.
- **CA05.4** Dado que o item está resolvido ou expirado, quando acesso o detalhe, então a opção de reivindicar não está disponível.

**US06 — Analisar reivindicação (RF07, RF08)** Como publicador de um item achado, quero aprovar ou recusar quem diz ser dono.

- **CA06.1** Dado que há reivindicação pendente, quando aprovo, então o status muda para "Aprovada", o canal de mensagens é liberado e o solicitante é notificado.
- **CA06.2** Dado que recuso, quando informo o motivo, então o status muda para "Recusada" e o solicitante é notificado.
- **CA06.3** Dado que a reivindicação foi aprovada, quando troco mensagens, então nenhum e-mail ou telefone é exibido à outra parte.
- **CA06.4** Dado que o item está no ponto de guarda, quando há reivindicação, então apenas moderadores podem aprová-la ou recusá-la.

**US07 — Concluir devolução (RF09)** Como publicador ou moderador, quero marcar o item como devolvido para encerrar o anúncio.

- **CA07.1** Dado que a reivindicação está aprovada, quando marco "Devolvido", então o item muda para "Resolvido" e some das buscas.
- **CA07.2** Dado que o item foi resolvido, quando consulto o histórico, então vejo data, reivindicação vinculada e responsável pelo fechamento.

**US08 — Notificações e correspondências (RF10, RF11)** Como usuário, quero ser avisado sobre eventos do meu item sem precisar abrir o sistema.

- **CA08.1** Dado que um item achado compatível com meu item perdido é publicado, quando o sistema processa, então recebo notificação in-app e e-mail em até 15 minutos.
- **CA08.2** Dado que desativei e-mails nas preferências, quando ocorre um evento, então recebo apenas notificação in-app.

**US09 — Denunciar conteúdo (RF12)** Como usuário, quero denunciar anúncios suspeitos ou impróprios.

- **CA09.1** Dado que estou em um anúncio, quando envio denúncia com motivo, então ela entra na fila de moderação com status "Aberta".
- **CA09.2** Dado que já denunciei o mesmo anúncio, quando tento novamente, então o sistema informa que a denúncia já foi registrada.

**US10 — Moderar e operar ponto de guarda (RF13, RF14)** Como moderador, quero tratar denúncias e cadastrar itens recebidos presencialmente.

- **CA10.1** Dado que há denúncia aberta, quando removo o anúncio com justificativa, então ele é ocultado, o autor é notificado e a ação é registrada em log.
- **CA10.2** Dado que recebi um objeto fisicamente, quando o cadastro com foto, categoria e prateleira/local de guarda, então ele aparece como "No ponto de guarda".
- **CA10.3** Dado que sou usuário comum, quando tento acessar o painel de moderação, então recebo erro 403.

**US11 — Meus itens (RF16)** Como usuário, quero acompanhar meus anúncios e reivindicações em um só lugar.

- **CA11.1** Dado que estou autenticado, quando abro "Meus itens", então vejo meus anúncios e reivindicações com status atualizado.
- **CA11.2** Dado que tenho anúncio aberto, quando edito título, descrição ou fotos, então as mudanças são salvas e registradas com data de atualização.

**US12 — Administração (RF17)** Como administrador, quero configurar categorias, locais e moderadores.

- **CA12.1** Dado que sou administrador, quando crio ou desativo uma categoria, então a mudança reflete nos formulários sem apagar itens antigos.
- **CA12.2** Dado que promovo um usuário a moderador, quando confirmo, então o acesso ao painel é liberado no próximo login.