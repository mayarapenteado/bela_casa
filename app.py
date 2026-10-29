import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("BELACASA_SECRET_KEY", "chave-local-bela-casa-troque-em-producao")
app.config["DATABASE"] = os.path.join(app.instance_path, "belacasa.db")

STATUS = ["Pendente", "Em separação", "Entregue", "Cancelado"]
PAGAMENTOS = ["Pix", "Cartão de Crédito", "Cartão de Débito", "Dinheiro"]
ESTADOS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
           "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
           "SP", "SE", "TO"]
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
POR_PAGINA = 10

def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def fechar_db(_erro):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())

    # Gambiarra caso o banco seja o antigo sem perfil
    colunas = [c["name"] for c in db.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "perfil" not in colunas:
        db.execute("ALTER TABLE usuarios ADD COLUMN perfil TEXT NOT NULL DEFAULT 'colaborador'")
        db.execute("UPDATE usuarios SET perfil = 'administrador' WHERE login = 'admin'")
    if "ativo" not in colunas:
        db.execute("ALTER TABLE usuarios ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")

    # Cria uma conta inicial para facilitar a primeira execução local.
    if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        db.execute("INSERT INTO usuarios (nome, login, senha_hash, perfil) VALUES (?, ?, ?, ?)",
                   ("Usuária", "admin", generate_password_hash("belacasa123"), "administrador"))

    padroes = {
        "nome_fantasia": "Bela Casa Presentes", "razao_social": "", "cnpj": "",
        "telefone": "", "email": "", "endereco": "", "bairro": "",
        "cidade": "", "estado": "SP",
    }
    for chave, valor in padroes.items():
        db.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))
    db.commit()

def gerar_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]

app.jinja_env.globals["csrf_token"] = gerar_csrf

@app.before_request
def checar_csrf():
    if request.method == "POST":
        token = session.get("_csrf")
        if not token or token != request.form.get("_csrf"):
            abort(400)

def usuario_logado():
    if "usuario_id" not in session:
        return None
    if "usuario" not in g:
        u = get_db().execute("SELECT * FROM usuarios WHERE id = ? AND ativo = 1",
                             (session["usuario_id"],)).fetchone()
        g.usuario = u
    return g.usuario

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        usuario = usuario_logado()
        if usuario is None:
            session.clear()
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if usuario_logado()["perfil"] != "administrador":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")

def cpf_valido(cpf):
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    numeros = [int(n) for n in cpf]
    for tamanho in (9, 10):
        soma = sum(numeros[i] * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != numeros[tamanho]:
            return False
    return True

def converter_valor(texto):
    t = (texto or "").replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        valor = float(t)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(valor):
        return None
    return round(valor, 2)

@app.template_filter("brl")
def filtro_brl(valor):
    valor = valor or 0
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s

@app.template_filter("databr")
def filtro_databr(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""

@app.template_filter("cpf")
def filtro_cpf(valor):
    d = so_digitos(valor)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else valor

@app.template_filter("fone")
def filtro_fone(valor):
    d = so_digitos(valor)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return valor

@app.template_filter("classe_status")
def classe_status(status):
    return {"Entregue": "ok", "Em separação": "aviso", "Pendente": "erro",
            "Cancelado": "neutro"}.get(status, "neutro")

def config_empresa():
    linhas = get_db().execute("SELECT chave, valor FROM configuracoes").fetchall()
    return {l["chave"]: l["valor"] for l in linhas}

@app.context_processor
def dados_globais():
    usuario = usuario_logado()
    if usuario is None:
        return {}
    return {"empresa": config_empresa(), "usuario_nome": usuario["nome"],
            "eh_admin": usuario["perfil"] == "administrador"}

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = get_db().execute("SELECT * FROM usuarios WHERE login = ?",
                                   (request.form.get("login", "").strip().lower(),)).fetchone()
        if usuario and check_password_hash(usuario["senha_hash"], request.form.get("senha", "")):
            if not usuario["ativo"]:
                flash("Conta desativada.", "erro")
                return render_template("login.html")
            session.clear()
            session["usuario_id"] = usuario["id"]
            destino = request.args.get("next", "")
            if not destino.startswith("/") or destino.startswith("//"):
                destino = url_for("inicio")
            return redirect(destino)
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("login.html")

@app.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def inicio():
    db = get_db()
    mes = date.today().strftime("%Y-%m")
    resumo = {
        "clientes": db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
        "pedidos_mes": db.execute(
            "SELECT COUNT(*) FROM pedidos WHERE strftime('%Y-%m', data) = ?", (mes,)).fetchone()[0],
        "entregues": db.execute(
            "SELECT COUNT(*) FROM pedidos WHERE status = 'Entregue' AND strftime('%Y-%m', data) = ?",
            (mes,)).fetchone()[0],
        "abertos": db.execute(
            "SELECT COUNT(*) FROM pedidos WHERE status IN ('Pendente', 'Em separação')").fetchone()[0],
    }
    recentes = db.execute(
        '''SELECT p.id, p.data, p.status, p.quantidade * p.valor_unitario AS total, c.nome AS cliente
           FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
           ORDER BY p.data DESC, p.id DESC LIMIT 5''').fetchall()
    return render_template("index.html", resumo=resumo, recentes=recentes, pagina="inicio")

def ler_cliente(form):
    dados = {
        "nome": form.get("nome", "").strip(),
        "cpf": so_digitos(form.get("cpf")),
        "telefone": so_digitos(form.get("telefone")),
        "email": form.get("email", "").strip().lower(),
        "cep": so_digitos(form.get("cep")),
        "logradouro": form.get("logradouro", "").strip(),
        "numero": form.get("numero", "").strip(),
        "bairro": form.get("bairro", "").strip(),
        "cidade": form.get("cidade", "").strip(),
        "estado": form.get("estado", "").strip().upper(),
    }
    erros = {}
    if len(dados["nome"]) < 3:
        erros["nome"] = "Informe um nome com pelo menos 3 caracteres."
    if not cpf_valido(dados["cpf"]):
        erros["cpf"] = "CPF inválido."
    if len(dados["telefone"]) not in (10, 11):
        erros["telefone"] = "Informe um telefone com DDD."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", dados["email"]):
        erros["email"] = "Informe um e-mail válido."
    if len(dados["cep"]) != 8:
        erros["cep"] = "CEP inválido."
    for campo in ("logradouro", "numero", "bairro", "cidade"):
        if not dados[campo]:
            erros[campo] = "Faltou preencher."
    if dados["estado"] not in ESTADOS:
        erros["estado"] = "Selecione um estado válido."
    return dados, erros

@app.route("/clientes")
@login_required
def clientes():
    busca = request.args.get("q", "").strip()
    sql = '''SELECT c.*, COUNT(p.id) AS qtd_pedidos
             FROM clientes c LEFT JOIN pedidos p ON p.cliente_id = c.id'''
    params = []
    if busca:
        sql += " WHERE c.nome LIKE ? OR c.cpf LIKE ? OR c.email LIKE ?"
        params = [f"%{busca}%", f"%{so_digitos(busca) or busca}%", f"%{busca}%"]
    sql += " GROUP BY c.id ORDER BY c.nome"
    lista = get_db().execute(sql, params).fetchall()
    return render_template("clientes.html", clientes=lista, busca=busca, pagina="clientes")

@app.route("/clientes/novo", methods=["GET", "POST"])
@app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
def cliente_form(cliente_id=None):
    db = get_db()
    atual = None
    if cliente_id:
        atual = db.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
        if atual is None:
            abort(404)

    dados, erros = (dict(atual) if atual else {}), {}
    if request.method == "POST":
        dados, erros = ler_cliente(request.form)
        if not erros:
            repetido = db.execute("SELECT id FROM clientes WHERE cpf = ? AND id != ?",
                                  (dados["cpf"], cliente_id or 0)).fetchone()
            if repetido:
                erros["cpf"] = "Esse CPF já está cadastrado."
        if not erros:
            campos = list(dados.keys())
            if cliente_id:
                db.execute(f"UPDATE clientes SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?",
                           [dados[c] for c in campos] + [cliente_id])
                flash("Atualizado.", "ok")
            else:
                db.execute(f"INSERT INTO clientes ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                           [dados[c] for c in campos])
                flash("Cadastrado.", "ok")
            db.commit()
            return redirect(url_for("clientes"))
    return render_template("cliente_form.html", dados=dados, erros=erros, editando=bool(cliente_id),
                           estados=ESTADOS, pagina="clientes")

@app.route("/clientes/<int:cliente_id>/excluir", methods=["POST"])
@login_required
def cliente_excluir(cliente_id):
    db = get_db()
    tem_pedidos = db.execute("SELECT COUNT(*) FROM pedidos WHERE cliente_id = ?", (cliente_id,)).fetchone()[0]
    if tem_pedidos:
        flash("Não é possível excluir um cliente que tem pedidos vinculados.", "erro")
    else:
        db.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        db.commit()
        flash("Excluido.", "ok")
    return redirect(url_for("clientes"))

@app.route("/produtos", methods=["GET", "POST"])
@login_required
def produtos():
    db = get_db()
    erro = ""
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        preco = converter_valor(request.form.get("preco"))
        if not nome:
            erro = "Escreve o nome."
        elif preco is None or preco < 0:
            erro = "Preco errado."
        elif db.execute("SELECT 1 FROM produtos WHERE nome = ?", (nome,)).fetchone():
            erro = "Ja cadastrado."
        else:
            db.execute("INSERT INTO produtos (nome, preco) VALUES (?, ?)", (nome, preco))
            db.commit()
            flash("Foi.", "ok")
            return redirect(url_for("produtos"))
    lista = db.execute("SELECT * FROM produtos ORDER BY ativo DESC, nome").fetchall()
    return render_template("produtos.html", produtos=lista, erro=erro, pagina="produtos")

@app.route("/produtos/<int:produto_id>/alternar", methods=["POST"])
@login_required
def produto_alternar(produto_id):
    db = get_db()
    db.execute("UPDATE produtos SET ativo = 1 - ativo WHERE id = ?", (produto_id,))
    db.commit()
    return redirect(url_for("produtos"))

@app.route("/pedidos")
@login_required
def pedidos():
    db = get_db()
    f = {
        "q": request.args.get("q", "").strip(),
        "cliente": request.args.get("cliente", ""),
        "status": request.args.get("status", ""),
        "ini": request.args.get("ini", ""),
        "fim": request.args.get("fim", ""),
    }
    pagina_atual = max(request.args.get("p", 1, type=int), 1)

    where, params = [], []
    if f["q"]:
        where.append("(CAST(p.id AS TEXT) = ? OR c.nome LIKE ? OR pr.nome LIKE ?)")
        params += [f["q"].lstrip("#").lstrip("0"), f"%{f['q']}%", f"%{f['q']}%"]
    if f["cliente"].isdigit():
        where.append("p.cliente_id = ?")
        params.append(int(f["cliente"]))
    if f["status"] in STATUS:
        where.append("p.status = ?")
        params.append(f["status"])
    if f["ini"]:
        try:
            datetime.strptime(f["ini"], "%Y-%m-%d")
            where.append("p.data >= ?")
            params.append(f["ini"])
        except ValueError:
            f["ini"] = ""
    if f["fim"]:
        try:
            datetime.strptime(f["fim"], "%Y-%m-%d")
            where.append("p.data <= ?")
            params.append(f["fim"])
        except ValueError:
            f["fim"] = ""
    filtro = (" WHERE " + " AND ".join(where)) if where else ""

    base = '''FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
              JOIN produtos pr ON pr.id = p.produto_id''' + filtro
    total = db.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
    paginas = max((total + POR_PAGINA - 1) // POR_PAGINA, 1)
    pagina_atual = min(pagina_atual, paginas)

    lista = db.execute(
        '''SELECT p.id, p.data, p.status, p.quantidade * p.valor_unitario AS total,
                  c.nome AS cliente, pr.nome AS produto ''' + base +
        " ORDER BY p.data DESC, p.id DESC LIMIT ? OFFSET ?",
        params + [POR_PAGINA, (pagina_atual - 1) * POR_PAGINA]).fetchall()
    todos_clientes = db.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()

    args_pag = {k: v for k, v in f.items() if v}
    return render_template("pedidos.html", pedidos=lista, f=f, clientes=todos_clientes, status=STATUS,
                           total=total, paginas=paginas, pagina_atual=pagina_atual,
                           args_pag=args_pag, pagina="pedidos")

@app.route("/pedidos/novo", methods=["GET", "POST"])
@login_required
def pedido_novo():
    db = get_db()
    dados = {"data": date.today().isoformat(), "quantidade": "1", "status": "Pendente",
             "cliente_id": request.args.get("cliente", "")}
    erros = {}
    if request.method == "POST":
        dados = {k: request.form.get(k, "").strip() for k in
                 ("cliente_id", "produto_id", "data", "quantidade", "valor_unitario",
                  "forma_pagamento", "status", "observacoes")}
        if not dados["cliente_id"].isdigit() or not db.execute(
                "SELECT 1 FROM clientes WHERE id = ?", (dados["cliente_id"],)).fetchone():
            erros["cliente_id"] = "Faltou cliente."
        if not dados["produto_id"].isdigit() or not db.execute(
                "SELECT 1 FROM produtos WHERE id = ?", (dados["produto_id"],)).fetchone():
            erros["produto_id"] = "Faltou produto."
        try:
            data_pedido = datetime.strptime(dados["data"], "%Y-%m-%d").date()
            if data_pedido > date.today() + timedelta(days=1):
                erros["data"] = "Data ta no futuro."
        except ValueError:
            erros["data"] = "Erro na data."
        if not dados["quantidade"].isdigit() or int(dados["quantidade"]) < 1:
            erros["quantidade"] = "Qtd errada."
        valor = converter_valor(dados["valor_unitario"])
        if valor is None or valor <= 0:
            erros["valor_unitario"] = "Valor errado."
        if dados["forma_pagamento"] not in PAGAMENTOS:
            erros["forma_pagamento"] = "Qual a forma pag?"
        if dados["status"] not in STATUS:
            erros["status"] = "Status erro."

        if not erros:
            cur = db.execute(
                '''INSERT INTO pedidos (cliente_id, produto_id, data, quantidade, valor_unitario,
                                        forma_pagamento, status, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (int(dados["cliente_id"]), int(dados["produto_id"]), dados["data"],
                 int(dados["quantidade"]), valor, dados["forma_pagamento"], dados["status"],
                 dados["observacoes"] or None))
            db.commit()
            flash(f"Salvo pedido #{cur.lastrowid:05d}.", "ok")
            return redirect(url_for("pedido_detalhe", pedido_id=cur.lastrowid))

    return render_template(
        "pedido_form.html", dados=dados, erros=erros, status=STATUS, pagamentos=PAGAMENTOS,
        clientes=db.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall(),
        produtos=db.execute("SELECT * FROM produtos WHERE ativo = 1 ORDER BY nome").fetchall(),
        pagina="pedidos")

@app.route("/pedidos/<int:pedido_id>")
@login_required
def pedido_detalhe(pedido_id):
    pedido = get_db().execute(
        '''SELECT p.*, p.quantidade * p.valor_unitario AS total, c.nome AS cliente, c.telefone,
                  c.email, pr.nome AS produto
           FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
           JOIN produtos pr ON pr.id = p.produto_id WHERE p.id = ?''', (pedido_id,)).fetchone()
    if pedido is None:
        abort(404)
    return render_template("pedido_detalhe.html", pedido=pedido, status=STATUS, pagina="pedidos")

@app.route("/pedidos/<int:pedido_id>/status", methods=["POST"])
@login_required
def pedido_status(pedido_id):
    novo = request.form.get("status")
    if novo not in STATUS:
        abort(400)
    db = get_db()
    db.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo, pedido_id))
    db.commit()
    return redirect(url_for("pedido_detalhe", pedido_id=pedido_id))

CORES_PIZZA = ["#4a2545", "#7b3f78", "#a86aa5", "#d3b0d1"]

@app.route("/relatorios")
@login_required
def relatorios():
    db = get_db()
    hoje = date.today()
    mes_ini = hoje.month - 4
    ano_ini = hoje.year
    if mes_ini < 1:
        mes_ini += 12
        ano_ini -= 1
    ini = request.args.get("ini") or date(ano_ini, mes_ini, 1).isoformat()
    fim = request.args.get("fim") or hoje.isoformat()
    tipo = request.args.get("tipo", "vendas")
    if tipo not in ("vendas", "clientes"):
        tipo = "vendas"

    periodo = "p.data BETWEEN ? AND ? AND p.status != 'Cancelado'"
    p = (ini, fim)

    resumo = db.execute(
        f'''SELECT COUNT(*) AS pedidos, COALESCE(SUM(p.quantidade * p.valor_unitario), 0) AS faturamento
            FROM pedidos p WHERE {periodo}''', p).fetchone()
    abertos = db.execute(
        "SELECT COUNT(*) FROM pedidos p WHERE p.data BETWEEN ? AND ? AND p.status IN ('Pendente', 'Em separação')",
        p).fetchone()[0]
    clientes_total = db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]

    por_mes = db.execute(
        f'''SELECT strftime('%Y-%m', p.data) AS mes, SUM(p.quantidade * p.valor_unitario) AS total
            FROM pedidos p WHERE {periodo} GROUP BY mes ORDER BY mes''', p).fetchall()
    maior = max([m["total"] for m in por_mes], default=0) or 1
    barras = [{"rotulo": MESES[int(m["mes"][5:]) - 1], "total": m["total"],
               "altura": round(m["total"] / maior * 100)} for m in por_mes]

    pagamentos = db.execute(
        f'''SELECT p.forma_pagamento AS forma, SUM(p.quantidade * p.valor_unitario) AS total
            FROM pedidos p WHERE {periodo} GROUP BY p.forma_pagamento ORDER BY total DESC''', p).fetchall()
    soma_pag = sum(x["total"] for x in pagamentos) or 1
    fatias, acumulado, gradiente = [], 0.0, []
    for i, x in enumerate(pagamentos):
        pct = x["total"] / soma_pag * 100
        cor = CORES_PIZZA[i % len(CORES_PIZZA)]
        gradiente.append(f"{cor} {acumulado:.2f}% {acumulado + pct:.2f}%")
        acumulado += pct
        fatias.append({"forma": x["forma"], "pct": round(pct), "cor": cor})
    pizza = f"conic-gradient({', '.join(gradiente)})" if gradiente else "#eee"

    top_clientes = db.execute(
        f'''SELECT c.nome, COUNT(p.id) AS pedidos, SUM(p.quantidade * p.valor_unitario) AS total
            FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
            WHERE {periodo} GROUP BY c.id ORDER BY total DESC LIMIT 10''', p).fetchall()
    ultimos = db.execute(
        f'''SELECT p.id, p.data, p.status, p.quantidade * p.valor_unitario AS total, c.nome AS cliente
            FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
            WHERE {periodo} ORDER BY p.data DESC, p.id DESC LIMIT 5''', p).fetchall()

    return render_template("relatorios.html", ini=ini, fim=fim, tipo=tipo, resumo=resumo, abertos=abertos,
                           clientes_total=clientes_total, barras=barras, fatias=fatias, pizza=pizza,
                           top_clientes=top_clientes, ultimos=ultimos, pagina="relatorios")

CAMPOS_EMPRESA = ["nome_fantasia", "razao_social", "cnpj", "telefone", "email",
                  "endereco", "bairro", "cidade", "estado"]

@app.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    db = get_db()
    erro_senha = ""
    erro_nome = ""
    if request.method == "POST":
        acao = request.form.get("acao", "")
        if acao == "nome":
            novo_nome = request.form.get("nome", "").strip()
            if len(novo_nome) < 2:
                erro_nome = "Nome curto."
            else:
                db.execute("UPDATE usuarios SET nome = ? WHERE id = ?", (novo_nome, session["usuario_id"]))
                db.commit()
                return redirect(url_for("configuracoes"))

        elif acao == "empresa":
            if usuario_logado()["perfil"] != "administrador":
                abort(403)
            for campo in CAMPOS_EMPRESA:
                db.execute("UPDATE configuracoes SET valor = ? WHERE chave = ?",
                           (request.form.get(campo, "").strip(), campo))
            db.commit()
            return redirect(url_for("configuracoes"))

        elif acao == "senha":
            usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (session["usuario_id"],)).fetchone()
            nova = request.form.get("nova", "")
            if not check_password_hash(usuario["senha_hash"], request.form.get("atual", "")):
                erro_senha = "Senha errada."
            elif len(nova) < 8:
                erro_senha = "A senha tem q ter 8 caracteres."
            elif nova != request.form.get("confirmar", ""):
                erro_senha = "A confirmaçao nao bate."
            else:
                db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                           (generate_password_hash(nova), usuario["id"]))
                db.commit()
                return redirect(url_for("configuracoes"))
        else:
            abort(400)
    return render_template("configuracoes.html", dados=config_empresa(), estados=ESTADOS,
                           erro_senha=erro_senha, erro_nome=erro_nome,
                           meu_nome=usuario_logado()["nome"], meu_login=usuario_logado()["login"],
                           pagina="configuracoes")

PERFIS = {"colaborador": "Colaborador", "administrador": "Administrador"}

def administradores_ativos():
    return get_db().execute(
        "SELECT COUNT(*) FROM usuarios WHERE perfil = 'administrador' AND ativo = 1").fetchone()[0]

@app.route("/colaboradores")
@admin_required
def colaboradores():
    lista = get_db().execute("SELECT * FROM usuarios ORDER BY ativo DESC, nome").fetchall()
    return render_template("colaboradores.html", colaboradores=lista, perfis=PERFIS,
                           meu_id=session["usuario_id"], pagina="colaboradores")

@app.route("/colaboradores/novo", methods=["GET", "POST"])
@app.route("/colaboradores/<int:colab_id>/editar", methods=["GET", "POST"])
@admin_required
def colaborador_form(colab_id=None):
    db = get_db()
    atual = None
    if colab_id:
        atual = db.execute("SELECT * FROM usuarios WHERE id = ?", (colab_id,)).fetchone()

    dados = dict(atual) if atual else {"perfil": "colaborador"}
    dados.pop("senha_hash", None)
    erros = {}

    if request.method == "POST":
        dados = {
            "nome": request.form.get("nome", "").strip(),
            "login": request.form.get("login", "").strip().lower(),
            "perfil": request.form.get("perfil", ""),
        }
        senha = request.form.get("senha", "")

        if len(dados["nome"]) < 2:
            erros["nome"] = "Informe o nome do colaborador."
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,40}", dados["login"]):
            erros["login"] = "O login deve ter de 3 a 40 caracteres (letras, números, ponto, hífen ou _)."
        if dados["perfil"] not in PERFIS:
            erros["perfil"] = "Selecione um perfil válido."
        if not colab_id and len(senha) < 8:
            erros["senha"] = "A senha deve ter pelo menos 8 caracteres."
        elif senha and len(senha) < 8:
            erros["senha"] = "A senha deve ter pelo menos 8 caracteres."

        existente = db.execute("SELECT id FROM usuarios WHERE login = ? AND id != ?",
                               (dados["login"], colab_id or 0)).fetchone()
        if existente:
            erros["login"] = "Esse login já está em uso."

        alvo = db.execute("SELECT * FROM usuarios WHERE id = ?", (colab_id,)).fetchone() if colab_id else None
        if colab_id and alvo is None:
            abort(404)
        if alvo and alvo["id"] == session["usuario_id"] and dados["perfil"] != "administrador":
            if alvo["perfil"] == "administrador" and administradores_ativos() <= 1:
                erros["perfil"] = "Não é possível rebaixar o único administrador ativo."
        if alvo and alvo["perfil"] == "administrador" and dados["perfil"] != "administrador" and alvo["ativo"]:
            if administradores_ativos() <= 1:
                erros["perfil"] = "Não é possível remover o único administrador ativo."

        if not erros:
            try:
                if colab_id:
                    db.execute("UPDATE usuarios SET nome = ?, login = ?, perfil = ? WHERE id = ?",
                               (dados["nome"], dados["login"], dados["perfil"], colab_id))
                    if senha:
                        db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                                   (generate_password_hash(senha), colab_id))
                else:
                    db.execute("INSERT INTO usuarios (nome, login, senha_hash, perfil) VALUES (?, ?, ?, ?)",
                               (dados["nome"], dados["login"], generate_password_hash(senha), dados["perfil"]))
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                erros["login"] = "Esse login já está em uso."
            else:
                return redirect(url_for("colaboradores"))

    return render_template("colaborador_form.html", dados=dados, erros=erros, perfis=PERFIS,
                           editando=bool(colab_id), pagina="colaboradores")

@app.route("/colaboradores/<int:colab_id>/alternar", methods=["POST"])
@admin_required
def colaborador_alternar(colab_id):
    db = get_db()
    alvo = db.execute("SELECT * FROM usuarios WHERE id = ?", (colab_id,)).fetchone()
    if alvo is None:
        abort(404)
    if alvo["id"] != session["usuario_id"]:
        if alvo["ativo"] and alvo["perfil"] == "administrador" and administradores_ativos() <= 1:
            flash("Não é possível desativar o único administrador ativo.", "erro")
        else:
            db.execute("UPDATE usuarios SET ativo = 1 - ativo WHERE id = ?", (colab_id,))
            db.commit()
    return redirect(url_for("colaboradores"))

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(port=8000, debug=os.environ.get("BELACASA_DEBUG") == "1")
