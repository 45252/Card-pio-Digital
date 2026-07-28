import os
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

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

# ==========================================================
# 🕒 LÓGICA DE HORÁRIO DE FUNCIONAMENTO (BRASÍLIA UTC-3)
# ==========================================================
def verificar_loja_aberta():
    # Ajusta o fuso horário para Brasília (UTC-3)
    fuso_brasilia = datetime.timezone(datetime.timedelta(hours=-3))
    agora = datetime.datetime.now(fuso_brasilia)
    
    dia_semana = agora.weekday() # 0: Seg, 1: Ter, 2: Qua, 3: Qui, 4: Sex, 5: Sáb, 6: Dom
    hora_minuto = agora.hour * 60 + agora.minute # Converte a hora atual em minutos do dia

    # Segunda-feira (0): Fechado
    if dia_semana == 0:
        return False, "Segunda-feira: Fechado"

    # Terça (1), Quarta (2), Quinta (3): 18:00 às 22:00
    elif dia_semana in [1, 2, 3]:
        inicio = 18 * 60        # 18:00 (1080 min)
        fim = 22 * 60           # 22:00 (1320 min)
        aberto = inicio <= hora_minuto < fim
        texto_horario = "Hoje (Ter-Qui): 18:00 às 22:00"
        return aberto, texto_horario

    # Sexta (4), Sábado (5), Domingo (6): 18:00 às 22:30
    elif dia_semana in [4, 5, 6]:
        inicio = 18 * 60        # 18:00 (1080 min)
        fim = 22 * 60 + 30      # 22:30 (1350 min)
        aberto = inicio <= hora_minuto < fim
        texto_horario = "Hoje (Sex-Dom): 18:00 às 22:30"
        return aberto, texto_horario

    return False, "Fechado"


# ==========================================================
# 🖼️ ROTA INTELIGENTE DE IMAGENS (TOLERANTE A ERROS DE NOME/PASTA)
# ==========================================================
@app.route('/static/<path:filename>')
def servir_static_inteligente(filename):
    pasta_static = os.path.join(BASE_DIR, "static")
    nome_arquivo = os.path.basename(filename)

    # 1. Busca direta exata na pasta 'static'
    caminho_direto = os.path.join(pasta_static, nome_arquivo)
    if os.path.exists(caminho_direto):
        return send_from_directory(pasta_static, nome_arquivo)

    # 2. Varredura com tolerância a case-sensitive / extensões
    nome_base_busca = os.path.splitext(nome_arquivo)[0].strip().lower()

    if os.path.exists(pasta_static):
        for arquivo_real in os.listdir(pasta_static):
            nome_real_base = os.path.splitext(arquivo_real)[0].strip().lower()
            
            # Se o nome sem extensão for igual
            if nome_real_base == nome_base_busca:
                return send_from_directory(pasta_static, arquivo_real)

    # 3. Busca de backup na pasta 'imagens'
    pasta_imagens_backup = os.path.join(BASE_DIR, "imagens")
    if os.path.exists(pasta_imagens_backup):
        caminho_backup = os.path.join(pasta_imagens_backup, nome_arquivo)
        if os.path.exists(caminho_backup):
            return send_from_directory(pasta_imagens_backup, nome_arquivo)

    return abort(404)


@app.route('/')
def index():
    loja_aberta, texto_horario = verificar_loja_aberta()
    return render_template('index.html', loja_aberta=loja_aberta, texto_horario=texto_horario)


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
    
    # 🛑 Trava de Segurança: Bloqueia se a loja estiver fechada
    loja_aberta, texto_horario = verificar_loja_aberta()
    if not loja_aberta:
        return jsonify({
            "sucesso": False, 
            "mensagem": f"Estamos fechados no momento! ({texto_horario})"
        }), 400

    dados = request.get_json() or {}
    
    cliente = dados.get("cliente", "Cliente Web")
    total = dados.get("total", 0)
    forma_pagamento = dados.get("forma_pagamento") or dados.get("pagamento") or "PIX"
    itens = dados.get("itens", "")
    
    fuso_brasilia = datetime.timezone(datetime.timedelta(hours=-3))
    data_hora = datetime.datetime.now(fuso_brasilia).strftime("%d/%m/%Y %H:%M")
    
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