import random
from datetime import date, timedelta
import app as sistema

CLIENTES = [
    ("Maria Silva", "Rua das Flores", "120", "Centro"),
    ("Juliana Costa", "Avenida Brasil", "455", "Jardim América"),
    ("Ana Paula Souza", "Rua Sete de Setembro", "78", "Vila Nova"),
    ("Fernanda Lima", "Rua Quinze de Novembro", "301", "Centro"),
]

PRODUTOS = [
    ("Kit de cozinha", 89.90),
    ("Jogo de panelas", 129.90),
    ("Toalhas de banho", 67.50),
]

PAGAMENTOS = ["Pix", "Cartão de Crédito", "Dinheiro"]

def main():
    with sistema.app.app_context():
        sistema.init_db()
        db = sistema.get_db()

        if db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] > 0:
            print("Já tem coisa no banco. Apaga a pasta instance e o belacasa.db antes de rodar.")
            return

        for i, (nome, rua, numero, bairro) in enumerate(CLIENTES):
            # gerar um cpf aleatorio qualquer de 11 numeros
            cpf = str(random.randint(11111111111, 99999999999))
            db.execute(
                '''INSERT INTO clientes (nome, cpf, telefone, email, cep, logradouro,
                                         numero, bairro, cidade, estado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (nome, cpf, "19999999999", "email@teste.com", "13610000",
                 rua, numero, bairro, "Leme", "SP"))

        for nome, preco in PRODUTOS:
            db.execute("INSERT OR IGNORE INTO produtos (nome, preco) VALUES (?, ?)", (nome, preco))

        hoje = date.today()
        for i in range(10):
            db.execute(
                '''INSERT INTO pedidos (cliente_id, produto_id, data, quantidade, valor_unitario,
                                        forma_pagamento, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (random.randint(1, len(CLIENTES)), random.randint(1, len(PRODUTOS)), hoje.isoformat(),
                 1, 100.0, "Pix", "Entregue"))

        db.commit()
        print("Pronto! Banco preenchido com dados.")

if __name__ == "__main__":
    main()
