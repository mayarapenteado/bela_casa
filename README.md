# Bela Casa Presentes

Projeto Integrador da UNIVESP. É um sistema simples para cadastrar clientes, produtos, pedidos e colaboradores, além de consultar relatórios.

## Como executar no Windows

1. Instale o Python 3.10 ou mais recente.
2. Dê dois cliques em `rodar.bat` ou execute-o pelo terminal.
3. Abra `http://127.0.0.1:8000` no navegador.

Para iniciar manualmente, dentro da pasta do projeto, execute:

```bash
python -m pip install -r requirements.txt
python app.py
```

## Primeiro acesso

Na primeira execução, o sistema cria um usuário inicial:

- Login: `admin`
- Senha: `belacasa123`

Troque essa senha depois de entrar. A chave secreta usada nas sessões pode ser definida pela variável de ambiente `BELACASA_SECRET_KEY`. O valor padrão serve apenas para rodar localmente e não deve ser usado em uma implantação pública.

Para ativar o modo de depuração durante o desenvolvimento, defina `BELACASA_DEBUG=1`. Deixe essa opção desativada fora do computador de desenvolvimento.

## Dados para demonstração

O arquivo `dados_exemplo.py` insere dados de exemplo no banco atual. Execute `python dados_exemplo.py` na pasta do projeto. Ele não apaga os dados existentes; se já houver clientes cadastrados, ele encerra para evitar duplicar os exemplos.

O banco SQLite fica em `instance/belacasa.db`. Faça uma cópia desse arquivo antes de testar mudanças que possam afetar os dados.
