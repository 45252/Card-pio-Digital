import os
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Variável para armazenar os pedidos para o caixa
pedidos_pendentes_caixa = []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sistema_delivery.db')

def inicializar_banco():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco REAL NOT NULL,
            descricao TEXT,
            foto TEXT,
            categoria TEXT DEFAULT 'Geral',
            estoque INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            cliente TEXT,
            total REAL,
            pagamento TEXT,
            itens TEXT
        )
    ''')
    conn.commit()
    conn.close()

inicializar_banco()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/produtos', methods=['GET'])
def get_produtos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, preco, descricao, foto, categoria, estoque FROM produtos")
    produtos = cursor.fetchall()
    conn.close()
    
    lista = []
    for p in produtos:
        lista.append({
            'id': p[0], 'nome': p[1], 'preco': p[2],
            'descricao': p[3], 'foto': p[4], 'categoria': p[5], 'estoque': p[6]
        })
    return jsonify(lista)

@app.route('/api/pedido', methods=['POST'])
def receber_pedido():
    global pedidos_pendentes_caixa
    dados = request.get_json() or {}
    
    cliente = dados.get("cliente", "Cliente Web")
    total = dados.get("total", 0)
    forma_pagamento = dados.get("forma_pagamento") or dados.get("pagamento") or "PIX"
    itens = dados.get("itens", "")
    
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    
    # Adiciona na fila do caixa
    pedido_id = len(pedidos_pendentes_caixa) + 1
    novo_pedido = {
        "id_pedido": pedido_id,
        "cliente": cliente,
        "total": total,
        "forma_pagamento": forma_pagamento,
        "itens": itens,
        "data_hora": data_hora
    }
    pedidos_pendentes_caixa.append(novo_pedido)
    
    return jsonify({"sucesso": True, "mensagem": "Pedido enviado com sucesso!"})

@app.route('/api/pedidos_pendentes', methods=['GET'])
def buscar_pedidos_pendentes():
    global pedidos_pendentes_caixa
    pedidos_para_enviar = list(pedidos_pendentes_caixa)
    pedidos_pendentes_caixa.clear()
    return jsonify(pedidos_para_enviar)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)