# Plano de testes e evidências — Encontrei

**Ambiente de teste:** Python 3.10+ e biblioteca padrão; servidor HTTP em porta livre; SQLite temporário em diretório isolado; contas fictícias criadas por `init_db()`.

**Comando de execução:**

```bash
python -m unittest -v test_app.py
```

A suíte contém 31 testes, usa HTTP real contra uma instância temporária do backend e não modifica o banco persistente da demonstração. O teste 27 usa um cliente SMTP simulado e não envia mensagens reais. Os testes abaixo foram executados na versão deste pacote e passaram. A interface é servida por `/`; o código JavaScript inline também foi validado sintaticamente com `node --check`. O contrato OpenAPI foi analisado como YAML válido. A navegação interativa com navegador gráfico não foi considerada evidência automatizada nesta execução porque o navegador disponível no ambiente de validação bloqueia o acesso local; recomenda-se abrir o sistema localmente para a verificação visual final.

| Teste | História / requisito relacionado | Cenário verificado | Resultado esperado | Evidência automatizada |
|---|---|---|---|---|
| 01 | Infraestrutura / DER | Endpoint de saúde consulta o SQLite | HTTP 200, banco informado e anúncios de exemplo presentes | Passou |
| 02 | US04 / RF05 | Lista e detalhe público de anúncio | Lista paginada e pergunta/resposta secreta não expostas | Passou |
| 03 | US01 / RF01 | Login com senha incorreta | HTTP 401, sem autenticar | Passou |
| 04 | US01 / RF01 / RN01–RN02 | Cadastro, domínio institucional, verificação e login | Domínio externo recusado; conta fica pendente; link ativa a conta; login passa depois | Passou |
| 05 | US02 / RF02 / RN03–RN05 | Publicar achado sem foto | HTTP 400 com mensagem de validação | Passou |
| 06 | US03 / RF03 | Publicar anúncio perdido e consultá-lo | HTTP 201 e persistência confirmada na busca | Passou |
| 07 | US02 / RF02 / RN03 | Conteúdo de arquivo não corresponde ao MIME informado | Upload recusado com HTTP 400 | Passou |
| 08 | US02 / RF02 / RN06 | Categoria sensível publicada fora do ponto de guarda | Publicação recusada com mensagem clara | Passou |
| 09 | US10 / RF14 / RN06 | Permissão de ponto de guarda | Estudante recebe HTTP 403; moderador cadastra item guardado | Passou |
| 10 | US05–US06 / RF06–RF08 / RN07–RN09 | Resposta errada, duplicidade, aprovação, exclusividade de aprovado e conversa privada | Erros recusados; apenas uma aprovação; mensagens somente aos participantes | Passou |
| 11 | US10 / RF07–RF09 / RN09, RN15 | Reivindicação de item de guarda | Estudante não decide; moderação aprova; devolução gera histórico | Passou |
| 12 | US04 / RF04 | Filtros, período inválido e paginação | Filtros limitam resultados; período invertido retorna HTTP 400 | Passou |
| 13 | US08 / RF10 | Privacidade e leitura de notificações | Notificações pertencem ao usuário e podem ser marcadas como lidas | Passou |
| 14 | US09 / RF12–RF13 / RN14, RN18 | Denúncia duplicada de perfil e decisão de moderação | Denúncia duplicada é recusada; decisão é registrada | Passou |
| 15 | US10 / RF13 | Acesso de estudante a rotas exclusivas da moderação | HTTP 403 para estudante; log disponível a moderador | Passou |
| 16 | US12 / RF17 | Administração de catálogos, domínios e autorização | Criação/ativação/desativação funciona; estudante não acessa administração | Passou |
| 17 | US11 / RF16 | Atualizar e excluir anúncio próprio sem dependências históricas | Alteração persiste; exclusão remove recurso e detalhe retorna 404 | Passou |
| 18 | US01 / RF01 / RN02 | Suspender conta com token ativo | Sessão antiga deixa de ser aceita | Passou |
| 19 | RF15 / RN10–RN11, RN16 | Manutenção de anúncio antigo | Item expira e evento é registrado no histórico | Passou |
| 20 | Tratamento de erros | Corpo da requisição contém JSON inválido | HTTP 400 com mensagem legível, sem stack trace no cliente | Passou |
| 21 | RF10 / frontend | Frontend servido e preferência de e-mail persistida | HTML é retornado; preferência altera o estado armazenado | Passou |
| 22 | RF02–RF03 / RN03 | Limite de três fotos | Upload com quatro fotos é recusado | Passou |
| 23 | RF02–RF03 / RN13 | Categoria/local não pertencem ao catálogo ativo | HTTP 400; nenhum catálogo é criado implicitamente | Passou |
| 24 | RF11 / RN17 | Direção da janela temporal de correspondência | Achado depois da perda pode corresponder; achado antes da perda não | Passou |
| 25 | RF02 / RN06 | Editar achado comum para categoria que exige guarda | Edição recusada, sem contornar a regra de negócio | Passou |
| 26 | DER / integridade | Chaves estrangeiras, índices e exclusividade de reivindicação aprovada | FK inválida e segunda aprovação são impedidas pelo banco | Passou |
| 27 | RF10 / notificações por e-mail | Envio SMTP habilitado com cliente de e-mail simulado | Configuração TLS é usada; mensagem contém destinatário e assunto; sem enviar e-mail externo real | Passou |
| 28 | RF15 / manutenção automática | Ciclo do worker de manutenção até sinal de parada | Rotina periódica é chamada e o worker encerra ao receber o sinal | Passou |
| 29 | US09 / RF12–RF13 | Denúncia de anúncio duplicada e decisão de moderação | Repetição recebe 409; decisão de manter é auditada e o anúncio continua aberto | Passou |
| 30 | US06 / RF07, RF10 | Recusa de reivindicação com motivo | Estado recusado é persistido e notificação chega ao solicitante | Passou |
| 31 | US01 / RF01 / CA01.4 | Reenvio de verificação expirada | Token expirado é recusado; novo token é criado e ativa a conta | Passou |

## O que a suíte não pretende provar

- A suíte não substitui uma avaliação de usabilidade com pessoas nem um teste visual em todos os navegadores/tamanhos de tela.
- O envio efetivo de e-mails precisa ser testado com uma conta SMTP autorizada e variáveis locais configuradas; a suíte não tenta enviar mensagens para endereços externos.
- A política de expiração é exercitada chamando a rotina de manutenção e testando o worker periódico. A execução continua apenas enquanto o servidor local está ligado.
- Não foi realizado teste de carga, revisão de segurança de produção ou implantação pública; o projeto é um MVP acadêmico local.
