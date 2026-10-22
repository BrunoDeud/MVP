# Encontrei — versão simplificada (Python + SQLite)

Esta é uma implementação local simplificada do sistema acadêmico **Encontrei — Achados e Perdidos**. Foi criada para facilitar a execução e a apresentação, reduzindo as dependências técnicas da versão original Laravel + React + MySQL.

## Tecnologias

- Python 3.10 ou superior;
- `http.server`, `sqlite3`, `hashlib` e demais módulos da biblioteca padrão do Python;
- HTML, CSS e JavaScript no navegador;
- SQLite: o banco é criado automaticamente no arquivo `data/encontrei.sqlite3`.

## Decisões arquiteturais (ADRs)

Os ADRs desta versão descrevem a implementação local simplificada: [ADR-001 — interface nativa](docs/ADRs/ADR-001.md), [ADR-002 — backend Python](docs/ADRs/ADR-002.md), [ADR-003 — banco SQLite](docs/ADRs/ADR-003.md) e [ADR-004 — execução local](docs/ADRs/ADR-004.md). O índice está em [docs/ADRs/README.md](docs/ADRs/README.md).

A documentação de requisitos e wireframes representa o escopo originalmente desejado. A implementação local não contempla integralmente todos os requisitos; consulte [ADAPTAÇÃO LOCAL](docs/ADAPTACAO-LOCAL.md) e as limitações desta página. O DER atual está em [docs/Modelagem-de-dados/der.md](docs/Modelagem-de-dados/der.md), e a API desta versão está em [docs/api/api-local.md](docs/api/api-local.md).

## Como executar no Windows

1. Extraia `Encontrei-Simples.zip` para uma pasta, por exemplo `C:\Projetos\Encontrei-Simples`.
2. Instale o Python 3.10+ em https://www.python.org/downloads/windows/ caso ainda não esteja instalado. Durante a instalação, marque **Add python.exe to PATH**.
3. Dê dois cliques em `executar.bat`.
4. Uma janela de terminal ficará aberta e o navegador será aberto em `http://127.0.0.1:8000`.
5. Use a aplicação e não feche a janela do terminal. Para encerrar o servidor, volte à janela e pressione `Ctrl+C`.

Se o navegador não abrir automaticamente, digite manualmente: http://127.0.0.1:8000

### Se aparecer “Unable to create process using C:\Python314\python.exe”

Essa mensagem normalmente significa que o launcher `py` está apontando para um caminho antigo ou que o Python não está instalado nesse local. A versão atual de `executar.bat` tenta primeiro `python` e depois `py`. Se o erro continuar:

1. Abra o Menu Iniciar e procure por **Python**. Se não encontrar, instale novamente pelo site oficial: https://www.python.org/downloads/windows/
2. Durante a instalação, marque **Add python.exe to PATH**.
3. Feche e abra novamente o CMD/VS Code e teste `python --version`.
4. Se `python --version` funcionar, execute `executar.bat` novamente.

Para ver as instalações reconhecidas pelo launcher, execute `py -0p` no CMD.

## Contas para demonstração

| Perfil | E-mail | Senha |
|---|---|---|
| Estudante | `estudante@campus.edu.br` | `Estudante@12345` |
| Outro estudante | `lucas@campus.edu.br` | `Lucas@12345` |
| Moderador | `moderador@campus.edu.br` | `Moderador@12345` |
| Administrador | `admin@campus.edu.br` | `Admin@12345` |

As contas são fictícias e somente para apresentação local. Use a seleção de contas da tela de login para preencher os campos automaticamente.

## Funcionalidades incluídas

- Consulta de anúncios achados e perdidos com busca por texto, categoria, local, tipo e status;
- Visualização de detalhes sem expor a resposta de verificação ou e-mail do publicador;
- Publicação de achados e perdidos com validação de campos;
- Até três fotos JPG, PNG ou WEBP, até 5 MB cada; item achado exige ao menos uma foto;
- Pergunta e resposta de verificação privada para itens achados;
- Reivindicação de item achado, validação da resposta, prevenção de reivindicação ativa duplicada, aprovação ou recusa pelo publicador/moderação;
- Cancelamento das demais reivindicações pendentes quando uma é aprovada;
- Mensagens internas após aprovação, sem mostrar contato pessoal;
- Marcar anúncio como resolvido;
- Denúncias de anúncios, ocultação após três denunciantes distintos e painel de moderação com justificativa registrada;
- Banco SQLite persistente criado automaticamente e dados de exemplo inseridos no primeiro início.

## Banco de dados

O banco fica em `data/encontrei.sqlite3`. Ele é criado automaticamente ao executar `executar.bat` ou `python app.py`. Não é necessário configurar usuário, senha, serviço ou porta de MySQL.

Os dados permanecem entre execuções. Para reiniciar a demonstração do zero, encerre a aplicação e exclua o arquivo `data/encontrei.sqlite3`. Na próxima execução, o banco e os dados de exemplo serão recriados. As fotos enviadas ficam na pasta `uploads/`; para limpar todas as imagens de demonstração, apague também os arquivos dessa pasta.

## Executar pelo terminal

Na pasta extraída, execute:

```powershell
python app.py
```

Ou, se o comando `python` não for encontrado, tente:

```powershell
py -3 app.py
```

Abra `http://127.0.0.1:8000`.

## Testes

Não é necessário instalar `pytest`. Com Python instalado, rode:

```powershell
python -m unittest -v test_app.py
```

## Limitações importantes desta versão didática

- A aplicação é destinada a execução local em um computador de demonstração, não para exposição direta na internet;
- O cadastro de novas contas e a verificação real de e-mail institucional não estão integrados; as contas de demonstração já existem e o login é funcional;
- Expiração automática de anúncios, notificações por e-mail, ponto de guarda institucional, gestão completa de domínios/categorias/locais e todas as funcionalidades de administração da versão técnica original não estão implementadas integralmente;
- A autenticação local usa tokens em memória, que expiram quando o servidor é reiniciado;
- Fotos são armazenadas na pasta `uploads/`, junto ao projeto.
