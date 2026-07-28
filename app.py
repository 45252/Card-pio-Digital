import os
import sqlite3
import datetime
import json
import re
import unicodedata
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permite integração segura com tablets/sistemas externos

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

    # 3. Tabela de Vendas / Pedidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            cliente TEXT,
            total REAL,
            pagamento TEXT,
            itens TEXT,
            status TEXT DEFAULT 'Novo (Web)',
            telefone TEXT,
            endereco TEXT,
            bairro TEXT,
            taxa_entrega REAL DEFAULT 0
        )
    ''')

    # Adiciona colunas faltantes de forma retrocompatível caso o banco já existisse
    colunas_novas = [
        ("status", "TEXT DEFAULT 'Novo (Web)'"),
        ("telefone", "TEXT"),
        ("endereco", "TEXT"),
        ("bairro", "TEXT"),
        ("taxa_entrega", "REAL DEFAULT 0")
    ]
    
    cursor.execute("PRAGMA table_info(vendas)")
    colunas_existentes = [col[1] for col in cursor.fetchall()]

    for nome_coluna, tipo_coluna in colunas_novas:
        if nome_coluna not in colunas_existentes:
            try:
                cursor.execute(f"ALTER TABLE vendas ADD COLUMN {nome_coluna} {tipo_coluna}")
            except Exception as e:
                print(f"Aviso ao ajustar coluna {nome_coluna}: {e}")

    conn.commit()
    conn.close()

inicializar_banco()


# ==========================================================
# 🕒 LÓGICA DE HORÁRIO DE FUNCIONAMENTO (BRASÍLIA UTC-3)
# ==========================================================
def verificar_loja_aberta():
    fuso_brasilia = datetime.timezone(datetime.timedelta(hours=-3))
    agora = datetime.datetime.now(fuso_brasilia)
    
    dia_semana = agora.weekday()  # 0: Seg, 1: Ter, 2: Qua, 3: Qui, 4: Sex, 5: Sáb, 6: Dom
    hora_minuto = agora.hour * 60 + agora.minute

    # Segunda-feira (0): Fechado
    if dia_semana == 0:
        return False, "Segunda-feira: Fechado"

    # Terça (1), Quarta (2), Quinta (3): 18:00 às 22:00
    elif dia_semana in [1, 2, 3]:
        inicio = 18 * 60         # 18:00 (1080 min)
        fim = 22 * 60            # 22:00 (1320 min)
        aberto = inicio <= hora_minuto < fim
        texto_horario = "Horário de Hoje (Ter-Qui): 18:00 às 22:00"
        return aberto, texto_horario

    # Sexta (4), Sábado (5), Domingo (6): 18:00 às 22:30
    elif dia_semana in [4, 5, 6]:
        inicio = 18 * 60         # 18:00 (1080 min)
        fim = 22 * 60 + 30       # 22:30 (1350 min)
        aberto = inicio <= hora_minuto < fim
        texto_horario = "Horário de Hoje (Sex-Dom): 18:00 às 22:30"
        return aberto, texto_horario

    return False, "Fechado"


# ==========================================================
# 🖼️ TRATAMENTO INTELIGENTE DE IMAGENS E ARQUIVOS
# ==========================================================
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

    base_static = os.path.join(BASE_DIR, 'static')
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
            if nome_normalizado == nome_arquivo_normalizado or nome_normalizado in nome_arquivo_normalizado:
                return nome_arquivo

    if img_path:
        return os.path.basename(str(img_path).strip().replace('\\', '/'))
    return None


@app.route('/static/<path:filename>')
def servir_static_inteligente(filename):
    pasta_static = os.path.join(BASE_DIR, "static")
    nome_arquivo = os.path.basename(filename)

    caminho_direto = os.path.join(pasta_static, nome_arquivo)
    if os.path.exists(caminho_direto):
        return send_from_directory(pasta_static, nome_arquivo)

    nome_base_busca = os.path.splitext(nome_arquivo)[0].strip().lower()

    if os.path.exists(pasta_static):
        for arquivo_real in os.listdir(pasta_static):
            nome_real_base = os.path.splitext(arquivo_real)[0].strip().lower()
            if nome_real_base == nome_base_busca:
                return send_from_directory(pasta_static, arquivo_real)

    pasta_imagens_backup = os.path.join(BASE_DIR, "imagens")
    if os.path.exists(pasta_imagens_backup):
        caminho_backup = os.path.join(pasta_imagens_backup, nome_arquivo)
        if os.path.exists(caminho_backup):
            return send_from_directory(pasta_imagens_backup, nome_arquivo)

    return abort(404)


@app.route('/imagens/<path:filename>')
def servir_imagem(filename):
    return servir_static_inteligente(filename)


# ==========================================================
# 🌐 ROTAS DO CARDÁPIO DIGITAL (CLIENTE)
# ==========================================================
@app.route('/')
def index():
    loja_aberta, texto_horario = verificar_loja_aberta()
    return render_template('index.html', loja_aberta=loja_aberta, texto_horario=texto_horario)


@app.route('/api/status_loja', methods=['GET'])
def obter_status_loja():
    loja_aberta, texto_horario = verificar_loja_aberta()
    return jsonify({
        "loja_aberta": loja_aberta,
        "texto_horario": texto_horario
    })


@app.route('/api/categorias', methods=['GET'])
def obter_categorias():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT categoria FROM produtos WHERE categoria IS NOT NULL AND categoria != ''")
        categorias = cursor.fetchall()
        conn.close()

        lista = sorted([c[0].strip().capitalize() for c in categorias if c[0]])
        return jsonify({"sucesso": True, "categorias": lista})
    except Exception as e:
        return jsonify({"sucesso": False, "categorias": [], "erro": str(e)})


@app.route('/api/produtos', methods=['GET'])
def get_produtos():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, descricao, foto, categoria, estoque FROM produtos")
        produtos = cursor.fetchall()
        conn.close()

        lista = []
        for p in produtos:
            lista.append({
                'id': p[0], 'nome': p[1], 'preco': p[2],
                'descricao': p[3] or "", 'foto': resolver_nome_foto(p[4], p[1]),
                'categoria': p[5], 'estoque': p[6]
            })
        return jsonify(lista)
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/produtos/<categoria>', methods=['GET'])
def obter_produtos_por_categoria(categoria):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, descricao, foto, categoria, estoque FROM produtos")
        produtos = cursor.fetchall()
        conn.close()

        filtrados = []
        for p in produtos:
            cat_banco = str(p[5]).strip().lower() if p[5] else ""
            if cat_banco == categoria.strip().lower():
                filtrados.append({
                    "id": p[0], "nome": p[1], "preco": p[2],
                    "descricao": p[3] or "", "foto": resolver_nome_foto(p[4], p[1]),
                    "estoque": p[6]
                })
        return jsonify({"sucesso": True, "produtos": filtrados})
    except Exception as e:
        return jsonify({"sucesso": False, "produtos": [], "erro": str(e)})


@app.route('/api/taxas', methods=['GET'])
def obter_taxas_entrega():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT bairro, valor FROM taxas_entrega ORDER BY bairro ASC")
        taxas = cursor.fetchall()
        conn.close()

        resultado = [{"bairro": t[0], "valor": float(t[1])} for t in taxas]
        return jsonify({"sucesso": True, "taxas": resultado})
    except Exception as e:
        return jsonify({"sucesso": False, "taxas": [], "erro": str(e)})


# ==========================================================
# 📥 PROCESSAMENTO DE PEDIDOS E CONTROLE DE PIX
# ==========================================================
@app.route('/api/pedido', methods=['POST'])
def receber_pedido():
    # Trava do Horário de Funcionamento no Backend
    loja_aberta, texto_horario = verificar_loja_aberta()
    if not loja_aberta:
        return jsonify({
            "sucesso": False, 
            "mensagem": f"🔒 Desculpe! Estamos fechados no momento. ({texto_horario})"
        }), 400

    dados = request.get_json() or {}
    if not dados:
        return jsonify({"sucesso": False, "mensagem": "Dados inválidos"}), 400

    cliente = dados.get("cliente", "Cliente Web")
    total = float(dados.get("total", 0))
    forma_pagamento = dados.get("forma_pagamento") or dados.get("pagamento") or "PIX"
    itens = dados.get("itens", "")
    telefone = dados.get("telefone", "")
    endereco = dados.get("endereco", "")
    bairro = dados.get("bairro", "")
    taxa_entrega = float(dados.get("taxa_entrega", 0))

    # Formata lista detalhada de itens se recebida como JSON/lista
    itens_detalhados = dados.get("itens_detalhados", [])
    if isinstance(itens_detalhados, str):
        try:
            itens_detalhados = json.loads(itens_detalhados)
        except Exception:
            itens_detalhados = []

    if isinstance(itens_detalhados, list) and len(itens_detalhados) > 0:
        itens_para_salvar = ", ".join([
            f"{i.get('qtd', 1)}x {i.get('nome', 'Item')}"
            for i in itens_detalhados if isinstance(i, dict) and i.get('nome')
        ])
        if not itens_para_salvar:
            itens_para_salvar = str(itens)
    else:
        itens_para_salvar = str(itens)

    # Define o status inicial dependendo do tipo de pagamento
    if str(forma_pagamento).upper() == "PIX":
        status_inicial = "Aguardando PIX"
    else:
        status_inicial = "Novo (Web)"

    fuso_brasilia = datetime.timezone(datetime.timedelta(hours=-3))
    data_hora = datetime.datetime.now(fuso_brasilia).strftime("%d/%m/%Y %H:%M")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO vendas (data, cliente, total, pagamento, itens, status, telefone, endereco, bairro, taxa_entrega)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data_hora, cliente, total, forma_pagamento, itens_para_salvar, status_inicial, telefone, endereco, bairro, taxa_entrega))

        pedido_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"✅ Pedido #{pedido_id} salvo com sucesso! Status: {status_inicial}")

        return jsonify({
            "sucesso": True, 
            "id_pedido": pedido_id,
            "status": status_inicial,
            "mensagem": "Pedido registrado com sucesso!"
        })

    except Exception as e:
        print(f"❌ Erro ao salvar pedido no banco: {e}")
        return jsonify({"sucesso": False, "mensagem": "Erro interno ao processar pedido"}), 500


# ==========================================================
# 🖥️ ROTAS DE INTEGRAÇÃO COM O CAIXA / PDV
# ==========================================================
@app.route('/api/pedidos_pendentes', methods=['GET'])
def buscar_pedidos_pendentes():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, data, cliente, total, pagamento, itens, status, telefone, endereco, bairro, taxa_entrega
            FROM vendas
            WHERE status IN ('Novo (Web)', 'Aguardando PIX')
            ORDER BY id ASC
        ''')
        
        pedidos = cursor.fetchall()
        conn.close()

        resultado = []
        for p in pedidos:
            resultado.append({
                "id_pedido": p[0],
                "data_hora": p[1],
                "cliente": p[2],
                "total": p[3],
                "forma_pagamento": p[4],
                "pagamento": p[4],
                "itens": p[5],
                "status": p[6],
                "telefone": p[7] or "",
                "endereco": p[8] or "",
                "bairro": p[9] or "",
                "taxa_entrega": p[10] or 0.0
            })

        return jsonify(resultado)
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/pedidos/aguardando_pix', methods=['GET'])
def listar_pedidos_aguardando_pix():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, data, cliente, total, pagamento, itens, status, telefone 
            FROM vendas 
            WHERE status = 'Aguardando PIX'
            ORDER BY id DESC
        ''')

        pedidos = cursor.fetchall()
        conn.close()

        resultado = [{
            "id_pedido": p[0], "data_hora": p[1], "cliente": p[2],
            "total": p[3], "forma_pagamento": p[4], "itens": p[5],
            "status": p[6], "telefone": p[7]
        } for p in pedidos]

        return jsonify({"sucesso": True, "pedidos": resultado})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/pedido/<int:pedido_id>/status', methods=['PUT'])
def atualizar_status_pedido(pedido_id):
    dados = request.get_json() or {}
    novo_status = dados.get("status")

    if not novo_status:
        return jsonify({"sucesso": False, "mensagem": "Status não fornecido"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE vendas 
            SET status = ? 
            WHERE id = ?
        ''', (novo_status, pedido_id))

        conn.commit()
        conn.close()

        print(f"🔄 Pedido #{pedido_id} teve o status alterado para: {novo_status}")
        return jsonify({"sucesso": True, "mensagem": f"Status alterado para {novo_status}"})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)