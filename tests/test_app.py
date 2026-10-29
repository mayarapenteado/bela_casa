import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as sistema  # noqa: E402

CLIENTE = {
    "nome": "Maria Silva", "cpf": "529.982.247-25", "telefone": "(19) 99999-1234",
    "email": "maria@email.com", "cep": "13610-000", "logradouro": "Rua das Flores",
    "numero": "10", "bairro": "Centro", "cidade": "Leme", "estado": "SP",
}


class BaseTeste(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        sistema.app.config["DATABASE"] = os.path.join(self.pasta.name, "teste.db")
        sistema.app.config["TESTING"] = True
        with sistema.app.app_context():
            sistema.init_db()
        self.client = sistema.app.test_client()

    def tearDown(self):
        self.pasta.cleanup()

    # --- auxiliares ---
    def token(self, url="/login"):
        html = self.client.get(url).get_data(as_text=True)
        return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)

    def entrar(self):
        return self.client.post("/login", data={
            "_csrf": self.token(), "login": "admin", "senha": "belacasa123"})

    def cadastrar_cliente(self, **extra):
        dados = dict(CLIENTE, _csrf=self.token("/clientes/novo"), **extra)
        return self.client.post("/clientes/novo", data=dados)

    def preparar(self):
        self.entrar()
        self.cadastrar_cliente()
        self.client.post("/produtos", data={
            "_csrf": self.token("/produtos"), "nome": "Jogo de panelas", "preco": "129,90"})

    def criar_pedido(self, quantidade="2", valor="50,00", status="Pendente"):
        return self.client.post("/pedidos/novo", data={
            "_csrf": self.token("/pedidos/novo"), "cliente_id": "1", "produto_id": "1",
            "data": "2026-10-10", "quantidade": quantidade, "valor_unitario": valor,
            "forma_pagamento": "Pix", "status": status, "observacoes": ""})


class TestFuncoes(unittest.TestCase):
    def test_cpf_valido(self):
        self.assertTrue(sistema.cpf_valido("529.982.247-25"))
        self.assertFalse(sistema.cpf_valido("111.111.111-11"))
        self.assertFalse(sistema.cpf_valido("529.982.247-24"))
        self.assertFalse(sistema.cpf_valido("123"))

    def test_converter_valor(self):
        self.assertEqual(sistema.converter_valor("89,90"), 89.90)
        self.assertEqual(sistema.converter_valor("R$ 1.234,56"), 1234.56)
        self.assertIsNone(sistema.converter_valor("abc"))


class TestAcesso(BaseTeste):
    def test_exige_login(self):
        r = self.client.get("/clientes")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_login_errado(self):
        r = self.client.post("/login", data={
            "_csrf": self.token(), "login": "admin", "senha": "errada"})
        self.assertIn("incorretos", r.get_data(as_text=True))

    def test_post_sem_csrf_e_barrado(self):
        r = self.client.post("/login", data={"login": "admin", "senha": "belacasa123"})
        self.assertEqual(r.status_code, 400)

    def test_troca_de_senha(self):
        self.entrar()
        r = self.client.post("/configuracoes", data={
            "_csrf": self.token("/configuracoes"), "acao": "senha", "atual": "belacasa123",
            "nova": "novasenha1", "confirmar": "novasenha1"})
        self.assertEqual(r.status_code, 302)


class TestClientes(BaseTeste):
    def test_cadastro(self):
        self.entrar()
        self.assertEqual(self.cadastrar_cliente().status_code, 302)
        html = self.client.get("/clientes").get_data(as_text=True)
        self.assertIn("Maria Silva", html)
        self.assertIn("529.982.247-25", html)

    def test_cpf_invalido(self):
        self.entrar()
        r = self.cadastrar_cliente(cpf="111.111.111-11")
        self.assertIn("CPF inválido", r.get_data(as_text=True))

    def test_cpf_repetido(self):
        self.entrar()
        self.cadastrar_cliente()
        r = self.cadastrar_cliente()
        self.assertIn("Esse CPF já está cadastrado.", r.get_data(as_text=True))

    def test_cliente_com_pedido_nao_exclui(self):
        self.preparar()
        self.criar_pedido()
        self.client.post("/clientes/1/excluir", data={"_csrf": self.token("/clientes")})
        self.assertIn("Maria Silva", self.client.get("/clientes").get_data(as_text=True))


class TestPedidos(BaseTeste):
    def test_pedido_completo(self):
        self.preparar()
        r = self.criar_pedido()
        self.assertEqual(r.status_code, 302)
        detalhe = self.client.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("R$ 100,00", detalhe)

        lista = self.client.get("/pedidos?status=Pendente").get_data(as_text=True)
        self.assertIn("Maria Silva", lista)
        vazia = self.client.get("/pedidos?status=Entregue").get_data(as_text=True)
        self.assertIn("Nenhum pedido encontrado", vazia)

    def test_valor_invalido(self):
        self.preparar()
        r = self.criar_pedido(valor="0")
        self.assertIn("Valor errado.", r.get_data(as_text=True))

    def test_mudar_status(self):
        self.preparar()
        self.criar_pedido()
        self.client.post("/pedidos/1/status", data={
            "_csrf": self.token("/pedidos/1"), "status": "Entregue"})
        self.assertIn("Entregue", self.client.get("/pedidos/1").get_data(as_text=True))


class TestRelatorios(BaseTeste):
    def test_dashboard_e_relatorios(self):
        self.preparar()
        self.criar_pedido()
        self.assertEqual(self.client.get("/").status_code, 200)
        rel = self.client.get("/relatorios?ini=2026-10-01&fim=2026-10-31").get_data(as_text=True)
        self.assertIn("R$ 100,00", rel)
        self.assertEqual(self.client.get("/relatorios?tipo=clientes").status_code, 200)

    def test_cancelado_fora_do_faturamento(self):
        self.preparar()
        self.criar_pedido(status="Cancelado")
        rel = self.client.get("/relatorios?ini=2026-10-01&fim=2026-10-31").get_data(as_text=True)
        self.assertIn("Sem vendas no período", rel)


class TestColaboradores(BaseTeste):
    def novo_colaborador(self, login="ana", senha="senha1234", perfil="colaborador", nome="Ana Paula"):
        return self.client.post("/colaboradores/novo", data={
            "_csrf": self.token("/colaboradores/novo"), "nome": nome, "login": login,
            "senha": senha, "perfil": perfil})

    def entrar_como(self, login, senha):
        outro = sistema.app.test_client()
        html = outro.get("/login").get_data(as_text=True)
        token = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
        resposta = outro.post("/login", data={"_csrf": token, "login": login, "senha": senha})
        return outro, resposta

    def test_admin_cadastra_e_colaborador_entra(self):
        self.entrar()
        self.assertEqual(self.novo_colaborador().status_code, 302)
        self.assertIn("Ana Paula", self.client.get("/colaboradores").get_data(as_text=True))
        _, r = self.entrar_como("ana", "senha1234")
        self.assertEqual(r.status_code, 302)

    def test_login_repetido(self):
        self.entrar()
        self.novo_colaborador()
        r = self.novo_colaborador(nome="Outra Ana")
        self.assertIn("já está em uso", r.get_data(as_text=True))

    def test_senha_curta(self):
        self.entrar()
        r = self.novo_colaborador(senha="123")
        self.assertIn("pelo menos 8", r.get_data(as_text=True))

    def test_colaborador_nao_gerencia_colaboradores(self):
        self.entrar()
        self.novo_colaborador()
        ana, _ = self.entrar_como("ana", "senha1234")
        self.assertEqual(ana.get("/colaboradores").status_code, 403)
        self.assertEqual(ana.get("/colaboradores/novo").status_code, 403)
        # e o menu dela não mostra o item
        self.assertNotIn("Colaboradores", ana.get("/").get_data(as_text=True))

    def test_colaborador_altera_o_proprio_nome(self):
        self.entrar()
        self.novo_colaborador()
        ana, _ = self.entrar_como("ana", "senha1234")
        html = ana.get("/configuracoes").get_data(as_text=True)
        token = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
        ana.post("/configuracoes", data={"_csrf": token, "acao": "nome", "nome": "Ana Souza"})
        self.assertIn("Ana Souza", ana.get("/").get_data(as_text=True))

    def test_colaborador_nao_altera_dados_da_empresa(self):
        self.entrar()
        self.novo_colaborador()
        ana, _ = self.entrar_como("ana", "senha1234")
        html = ana.get("/configuracoes").get_data(as_text=True)
        token = re.search(r'name="_csrf" value="([^"]+)"', html).group(1)
        r = ana.post("/configuracoes", data={"_csrf": token, "acao": "empresa", "nome_fantasia": "X"})
        self.assertEqual(r.status_code, 403)

    def test_desativado_nao_entra_e_perde_a_sessao(self):
        self.entrar()
        self.novo_colaborador()
        ana, _ = self.entrar_como("ana", "senha1234")
        self.assertEqual(ana.get("/").status_code, 200)

        self.client.post("/colaboradores/2/alternar", data={"_csrf": self.token("/colaboradores")})
        self.assertEqual(ana.get("/").status_code, 302)  # sessão derrubada
        _, r = self.entrar_como("ana", "senha1234")
        self.assertEqual(r.status_code, 200)  # voltou para o login com aviso
        self.assertIn("Conta desativada.", r.get_data(as_text=True))

    def test_nao_desativa_a_si_mesmo(self):
        self.entrar()
        self.client.post("/colaboradores/1/alternar", data={"_csrf": self.token("/colaboradores")})
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_nao_remove_ultimo_administrador(self):
        self.entrar()
        r = self.client.post("/colaboradores/1/editar", data={
            "_csrf": self.token("/colaboradores/1/editar"), "nome": "Usuária", "login": "admin",
            "perfil": "colaborador", "senha": ""})
        self.assertIn("único administrador", r.get_data(as_text=True))

    def test_admin_redefine_senha_de_colaborador(self):
        self.entrar()
        self.novo_colaborador()
        self.client.post("/colaboradores/2/editar", data={
            "_csrf": self.token("/colaboradores/2/editar"), "nome": "Ana Paula", "login": "ana",
            "perfil": "colaborador", "senha": "outrasenha9"})
        _, r = self.entrar_como("ana", "outrasenha9")
        self.assertEqual(r.status_code, 302)


class TestMigracao(unittest.TestCase):
    def test_banco_antigo_ganha_colunas(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "antigo.db")
            con = sqlite3.connect(caminho)
            con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, "
                        "login TEXT NOT NULL UNIQUE, senha_hash TEXT NOT NULL)")
            con.execute("INSERT INTO usuarios (nome, login, senha_hash) VALUES ('Usuária', 'admin', 'x')")
            con.commit()
            con.close()

            sistema.app.config["DATABASE"] = caminho
            with sistema.app.app_context():
                sistema.init_db()
                linha = sistema.get_db().execute("SELECT perfil, ativo FROM usuarios").fetchone()
            self.assertEqual(linha["perfil"], "administrador")
            self.assertEqual(linha["ativo"], 1)


if __name__ == "__main__":
    unittest.main()