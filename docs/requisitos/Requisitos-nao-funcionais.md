## Requisitos Não Funcionais (RNF)

| ID | Categoria | Requisito mensurável | Como verificar |
| --- | --- | --- | --- |
| RNF01 | Desempenho | A listagem e a busca de itens devem responder em menos de 800 ms (p95) com até 50 usuários simultâneos e 10.000 itens. | Teste de carga (k6) |
| RNF02 | Desempenho | O carregamento inicial da página (LCP) deve ser inferior a 2,5 s em conexão 4G. | Lighthouse / WebPageTest |
| RNF03 | Desempenho | O upload de uma foto de 5 MB deve concluir em até 5 s em conexão 4G. | Teste manual/automatizado |
| RNF04 | Disponibilidade | Disponibilidade mensal mínima de 99,0% (cerca de 7 h de indisponibilidade tolerada/mês). | Monitor de uptime |
| RNF05 | Segurança | Senhas armazenadas com hash bcrypt ou Argon2 (custo mínimo equivalente a 12 rounds bcrypt); nenhuma senha em texto puro. | Revisão de código |
| RNF06 | Segurança | Todo tráfego via HTTPS com TLS 1.2 ou superior; cabeçalhos HSTS ativos. | SSL Labs: nota mínima A |
| RNF07 | Segurança | Proteção contra as vulnerabilidades do OWASP Top 10 (SQL Injection, XSS, CSRF); zero vulnerabilidades críticas ou altas na análise automatizada antes do deploy. | OWASP ZAP / Dependabot |
| RNF08 | Segurança | Rate limiting de 100 requisições/min por IP em endpoints gerais e 5 tentativas/min em login. | Teste automatizado |
| RNF09 | Segurança | Tokens de sessão (JWT) com expiração máxima de 1 h e refresh token de até 7 dias, revogáveis. | Teste de integração |
| RNF10 | Privacidade (LGPD) | Usuário deve poder excluir a conta e anonimizar seus dados em até 15 dias após a solicitação; coleta restrita ao necessário. | Revisão de processo |
| RNF11 | Usabilidade | Um usuário novo deve conseguir publicar um item achado em até 3 minutos, sem ajuda, em pelo menos 80% dos casos. | Teste de usabilidade com 5 a 8 pessoas |
| RNF12 | Usabilidade | Interface responsiva de 360 px a 1920 px de largura, com alvos de toque de no mínimo 44 px. | Teste em dispositivos |
| RNF13 | Acessibilidade | Conformidade com WCAG 2.1 nível AA nas telas principais (contraste mínimo 4,5:1, navegação por teclado, texto alternativo em imagens). | axe DevTools: 0 erros críticos |
| RNF14 | Compatibilidade | Funcionar nas duas últimas versões estáveis de Chrome, Firefox, Edge e Safari, e em Android 10+/iOS 15+. | Teste cross-browser |
| RNF15 | Manutenibilidade | Cobertura de testes automatizados mínima de 70% nas regras de negócio; pipeline de CI executa lint e testes a cada pull request. | Relatório de cobertura |
| RNF16 | Observabilidade | Logs estruturados com identificador de requisição; alerta disparado se a taxa de erros 5xx superar 2% em 5 minutos. | Painel de monitoramento |
| RNF17 | Backup e recuperação | Backup automático diário do banco com retenção de 14 dias; RPO máximo de 24 h e RTO máximo de 4 h. | Teste de restauração mensal |
| RNF18 | Escalabilidade | A arquitetura deve suportar crescimento de 10x (500 usuários simultâneos) apenas com ajuste de configuração/instâncias, sem reescrita. | Teste de carga |
| RNF19 | Notificações | E-mails transacionais enviados em até 5 minutos após o evento, com taxa de entrega superior a 95%. | Métricas do provedor |