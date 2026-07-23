import os
import sqlite3
import datetime
import json
import re
import unicodedata
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permite que o tablet e celulares conectem ao computador

# Lista temporária na memória para enviar os alertas ao Caixa
pedidos_pendentes_caixa = []

# Define o caminho absoluto para o banco no servidor
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sistema_delivery.db')

def inicializar_banco():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Tabela de Produtos
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
    
    # 2. Tabela de Taxas de Entrega
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS taxas_entrega (
            bairro TEXT PRIMARY KEY,
            valor REAL NOT NULL
        )
    ''')
    
    # 3. Tabela de Vendas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            cliente TEXT NOT NULL,
            total REAL NOT NULL,
            pagamento TEXT,
            itens TEXT,
            status TEXT DEFAULT 'Pendente'
        )
    ''')
    
    # Salva todas as tabelas e fecha a conexão no FINAL
    conn.commit()
    conn.close()

# Chama a inicialização do banco
inicializar_banco()

def listar_produtos():
    conn = sqlite3.connect(DB_PATH) 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos")
    produtos = cursor.fetchall()
    conn.close()
    return produtos

def listar_taxas_entrega():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT bairro, valor FROM taxas_entrega ORDER BY bairro ASC")
    taxas = cursor.fetchall()
    conn.close()
    return [{"bairro": bairro, "valor": float(valor)} for bairro, valor in taxas]

# --- ROTAS PARA O CARDÁPIO WEB ---

@app.route('/')
def index():
    return render_template('index.html')

def normalizar_texto(texto):
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r'[^a-z0-9]+', '', texto)
    return texto

def resolver_nome_foto(img_path, nome_produto=None):
    if not img_path and not nome_produto:
        return None

    base_static = os.path.join(os.path.dirname(__file__), 'static')
    if not os.path.isdir(base_static):
        return os.path.basename(str(img_path).strip()) if img_path else None

    candidatos = []

    if img_path:
        nome_original = str(img_path).strip().replace('\\', '/')
        nome_base = os.path.basename(nome_original)
        if nome_base:
            candidatos.append(nome_base)

    if nome_produto:
        nome_produto_limpo = str(nome_produto).strip()
        if nome_produto_limpo:
            candidatos.append(nome_produto_limpo)

    for nome_em_teste in candidatos:
        nome_normalizado = normalizar_texto(nome_em_teste)
        if not nome_normalizado:
            continue

        for nome_arquivo in os.listdir(base_static):
            caminho_arquivo = os.path.join(base_static, nome_arquivo)
            if not os.path.isfile(caminho_arquivo):
                continue

            nome_arquivo_normalizado = normalizar_texto(nome_arquivo)
            if not nome_arquivo_normalizado:
                continue

            if nome_normalizado == nome_arquivo_normalizado:
                return nome_arquivo

            if nome_normalizado in nome_arquivo_normalizado or nome_arquivo_normalizado in nome_normalizado:
                return nome_arquivo

    if nome_produto:
        nome_produto_limpo = str(nome_produto).strip().lower()
        tokens = [t for t in re.split(r'[^a-z0-9]+', nome_produto_limpo) if t]
        tokens = [t for t in tokens if t not in {'no', 'na', 'de', 'da', 'do', 'e', 's', 'com'}]
        if tokens:
            for nome_arquivo in os.listdir(base_static):
                caminho_arquivo = os.path.join(base_static, nome_arquivo)
                if not os.path.isfile(caminho_arquivo):
                    continue
                nome_arquivo_normalizado = normalizar_texto(nome_arquivo)
                if not nome_arquivo_normalizado:
                    continue
                score = 0
                for token in tokens:
                    if token in nome_arquivo_normalizado:
                        score += 1
                if score > 0:
                    return nome_arquivo

    if img_path:
        return os.path.basename(str(img_path).strip().replace('\\', '/'))
    return None

@app.route('/static/<path:filename>')
def servir_imagem_static(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)

@app.route('/imagens/<path:filename>')
def servir_imagem(filename):
    caminho_static = os.path.join(os.path.dirname(__file__), 'static', filename)
    if os.path.exists(caminho_static):
        return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'imagens'), filename)

@app.route('/api/categorias', methods=['GET'])
def obtener_categorias():
    try:
        produtos_banco = listar_produtos()
        categorias_set = set()
        for p in produtos_banco:
            cat = p[5]
            cat_formatada = str(cat).strip().lower() if cat else "yakisoba"
            categorias_set.add(cat_formatada.capitalize()) 
        return jsonify({"sucesso": True, "categorias": sorted(list(categorias_set))})
    except Exception as e:
        return jsonify({"sucesso": False, "categorias": [], "erro": str(e)})

@app.route('/api/produtos/<categoria>', methods=['GET'])
def obter_produtos_por_categoria(categoria):
    try:
        produtos_banco = listar_produtos() 
        produtos_filtrados = []
        for p in produtos_banco:
            pid, nome, preco, desc, img_path, cat, est = p[0], p[1], p[2], p[3], p[4], p[5], p[6]
            cat_formatada = str(cat).strip().lower() if cat else "yakisoba"
            if cat_formatada == categoria.strip().lower():
                nome_foto = resolver_nome_foto(img_path, nome)
                produtos_filtrados.append({
                    "id": pid,
                    "nome": nome,
                    "preco": preco,
                    "descricao": desc if desc else "",
                    "foto": nome_foto,
                    "estoque": est
                })
        return jsonify({"sucesso": True, "produtos": produtos_filtrados})
    except Exception as e:
        return jsonify({"sucesso": False, "produtos": [], "erro": str(e)})

# --- ROTA DE RECEBIMENTO DO PEDIDO ---

@app.route('/api/pedido', methods=['POST'])
def receber_pedido():
    global pedidos_pendentes_caixa
    
    dados = request.get_json()

    print("\n==========================================")
    print("📩 NOVO PEDIDO RECEBIDO NO SERVIDOR!")
    print(json.dumps(dados, indent=4, ensure_ascii=False) if dados else "Nenhum dado recebido!")
    print("==========================================\n")

    if not dados:
        return jsonify({"sucesso": False, "mensagem": "Dados inválidos"}), 400

    itens = dados.get("itens", "")
    total = dados.get("total", 0)
    forma_pagamento = dados.get("forma_pagamento") or dados.get("pagamento") or "PIX"
    cliente = dados.get("cliente", "Cliente Web")
    telefone = dados.get("telefone", "")
    endereco = dados.get("endereco", "")
    bairro = dados.get("bairro", "")
    taxa_entrega = dados.get("taxa_entrega", 0)
    itens_detalhados = dados.get("itens_detalhados", [])

    if isinstance(itens_detalhados, str):
        try:
            itens_detalhados = json.loads(itens_detalhados)
        except Exception:
            itens_detalhados = []

    if itens_detalhados:
        itens_para_salvar = ", ".join([
            f"{item.get('qtd', 1)}x {item.get('nome', 'Item')}"
            for item in itens_detalhados
            if isinstance(item, dict) and item.get('nome')
        ])
        if not itens_para_salvar:
            itens_para_salvar = itens
    else:
        itens_para_salvar = itens

    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # Gravando no banco
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO vendas (data, cliente, total, pagamento, itens)
            VALUES (?, ?, ?, ?, ?)
        ''', (data_hora, cliente, total, forma_pagamento, itens_para_salvar))

        pedido_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"[SUCESSO] Pedido #{pedido_id} gravado no Histórico (vendas)!")
    except Exception as e:
        print(f"\n❌ [ERRO AO SALVAR NO HISTÓRICO]: {e}\n")
        pedido_id = len(pedidos_pendentes_caixa) + 1

    if str(forma_pagamento).upper() == "PIX":
        status_inicial = "Aguardando PIX"
    else:
        status_inicial = "Novo (Web)"

    novo_alerta = {
        "id_pedido": pedido_id,
        "itens": itens_para_salvar,
        "itens_detalhados": itens_detalhados,
        "total": total,
        "taxa_entrega": float(taxa_entrega or 0),
        "forma_pagamento": forma_pagamento,
        "pagamento": forma_pagamento,
        "cliente": cliente,
        "telefone": telefone,
        "endereco": endereco,
        "bairro": bairro,
        "status": status_inicial
    }
    
    pedidos_pendentes_caixa.append(novo_alerta)
    print(f"🔔 [ALERTA CRIADO]: Pedido #{pedido_id} adicionado à fila. Total pendente: {len(pedidos_pendentes_caixa)}")

    return jsonify({"sucesso": True, "mensagem": "Pedido salvo e enviado ao Caixa!"})

# --- ROTAS QUE ENTREGAM OS ALERTAS AO CAIXA ---

@app.route('/api/caixa/alertas', methods=['GET'])
def obter_alertas_caixa():
    global pedidos_pendentes_caixa
    alertas_para_enviar = list(pedidos_pendentes_caixa)
    if alertas_para_enviar:
        pedidos_pendentes_caixa.clear()
        print(f"📦 [ENTREGA DE ALERTAS]: {len(alertas_para_enviar)} alerta(s) enviado(s) ao Caixa!")

    return jsonify({
        "sucesso": True, 
        "alertas": alertas_para_enviar
    })

@app.route('/api/pedidos_pendentes', methods=['GET'])
def buscar_pedidos_pendentes():
    global pedidos_pendentes_caixa
    pedidos_para_enviar = list(pedidos_pendentes_caixa)
    pedidos_pendentes_caixa.clear()
    return jsonify(pedidos_para_enviar)

@app.route('/api/taxas', methods=['GET'])
def obter_taxas_entrega():
    try:
        return jsonify({"sucesso": True, "taxas": listar_taxas_entrega()})
    except Exception as e:
        return jsonify({"sucesso": False, "taxas": [], "erro": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)