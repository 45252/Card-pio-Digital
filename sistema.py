
import customtkinter as ctk
import sqlite3
import os
import json
import time
import threading
from tkinter import messagebox, filedialog
from PIL import Image

# --- NOVOS IMPORTS DO TOTEM ADICIONADOS AQUI ---
import requests
import winsound

# --- CONFIGURAÇÃO DA INTEGRAÇÃO COM O CARDÁPIO WEB ---
URL_RENDER = "https://card-pio-digital-ctoj.onrender.com/api/pedidos_pendentes"

def checar_pedidos_web():
    while True:
        try:
            res = requests.get(URL_RENDER, timeout=5)
            if res.status_code == 200:
                pedidos = res.json()
                for p in pedidos:
                    # 1. 🔔 Som de alerta no PC (1200Hz por 1 segundo)
                    winsound.Beep(1200, 1000)
                    
                    # 2. 💾 Grava no banco local
                    salvar_no_historico_local(p)
                    
                    print(f"🎉 NOVO PEDIDO WEB RECEBIDO: #{p.get('id_pedido')} - {p.get('cliente')}")
        except Exception:
            pass  # Ignora oscilações temporárias de conexão
            
        time.sleep(4)

def salvar_no_historico_local(p):
    try:
        conn = sqlite3.connect("sistema_delivery.db")
        cursor = conn.cursor()
        
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
        
        import datetime
        data_hora = p.get("data_hora") or datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
        cursor.execute('''
            INSERT INTO vendas (data, cliente, total, pagamento, itens)
            VALUES (?, ?, ?, ?, ?)
        ''', (data_hora, p.get('cliente'), p.get('total'), p.get('forma_pagamento'), p.get('itens')))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao gravar pedido no caixa local: {e}")

# Configuração global de tema e aparência
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def verificar_pedidos_totem(janela_principal):
    try:
        import requests
        import re
        import json 
        from collections import defaultdict
        from tkinter import messagebox
        import win32print
        import datetime
        import sqlite3
        import winsound

        # Pergunta ao servidor Flask se há alertas de novos pedidos
        resposta = requests.get("https://card-pio-digital-ctoj.onrender.com/api/caixa/alertas")
        dados = resposta.json()

        if dados.get("sucesso") and dados.get("alertas"):
            for alerta in dados["alertas"]:

                # --- DEBUG ---
                print("=" * 60)
                print("DADOS RECEBIDOS DA API (verificar_pedidos_totem):")
                print(alerta)
                print("=" * 60)

                # --- 1. ALARME SONORO ---
                try:
                    winsound.Beep(1000, 500)
                except Exception as e:
                    print(f"Erro no som: {e}")

                pag = alerta.get('forma_pagamento') or alerta.get('pagamento') or 'Pix'
                tot = float(alerta.get('total', 0.0) or 0.0)
                taxa_entrega = 0.0

                for chave in ('taxa_entrega', 'taxa', 'taxa_entrega_web'):
                    valor = alerta.get(chave)
                    if valor is None: continue
                    if isinstance(valor, (int, float)):
                        taxa_entrega = float(valor)
                        break
                    if isinstance(valor, str):
                        texto_valor = valor.strip()
                        if texto_valor:
                            match_valor = re.search(r'([0-9]+(?:[.,][0-9]{1,2})?)', texto_valor)
                            if match_valor:
                                taxa_entrega = float(match_valor.group(1).replace(',', '.'))
                                break

                texto_cliente_bruto = str(alerta.get('cliente', '')).strip()
                itens_brutos = str(alerta.get('itens', '')).strip()
                telefone_alerta = str(alerta.get('telefone', '') or '').strip()
                endereco_alerta = str(alerta.get('endereco', '') or '').strip()
                bairro_alerta = str(alerta.get('bairro', '') or '').strip()
                itens_detalhados = alerta.get('itens_detalhados', [])

                if isinstance(itens_detalhados, str):
                    try: 
                        itens_detalhados = json.loads(itens_detalhados)
                    except Exception: 
                        itens_detalhados = []

                agora = datetime.datetime.now()
                data_hoje = agora.strftime("%d/%m/%Y")
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM vendas WHERE data LIKE ?", (f"{data_hoje}%",))
                qtd_hoje = c.fetchone()[0]
                numero_pedido = qtd_hoje + 1
                conn.close()

                # ==========================================================
                # 🛑 VERIFICAÇÃO DO PIX ANTES DE IMPRIMIR
                # ==========================================================
                if str(pag).strip().upper() == "PIX":
                    confirmou = messagebox.askyesno(
                        "💳 CONFIRMAÇÃO DE PIX RECEBIDO",
                        f"🚨 NOVO PEDIDO WEB/TOTEM #{numero_pedido}\n\n"
                        f"Cliente: {texto_cliente_bruto[:40]}\n"
                        f"Total: R$ {tot:.2f}\n"
                        f"Forma de Pagamento: PIX\n\n"
                        f"O valor de R$ {tot:.2f} JÁ CAIU NA SUA CONTA BANCÁRIA?\n\n"
                        f"Clique em SIM para aprovar e IMPRIMIR na cozinha.\n"
                        f"Clique em NÃO para recusar/aguardar."
                    )
                    
                    if not confirmou:
                        print(f"⚠️ Pedido #{numero_pedido} PIX suspenso/não verificado pelo operador.")
                        continue # Pula a impressão se o operador disser que o dinheiro não caiu
                else:
                    # Se for Dinheiro/Cartão mostra apenas o aviso padrão
                    messagebox.showinfo(
                        "🚨 NOVO PEDIDO WEB/TOTEM", 
                        f"Pedido #{numero_pedido}\n"
                        f"Cliente: {texto_cliente_bruto[:40]}\n"
                        f"Forma de Pagamento: {pag}\n"
                        f"Total: R$ {tot:.2f}"
                    )

                # ==========================================================
                # INÍCIO DO TRATAMENTO DE STRING PARA O CUPOM
                # ==========================================================
                nome_c, tel_c, end_c, bair_c = "Cliente Web/Totem", "Não Informado", "Endereço não informado", "Não Informado"
                texto_cliente_limpo = texto_cliente_bruto.strip()

                if texto_cliente_limpo:
                    padrao_completo = re.match(
                        r'^(?P<nome>.+?)\s*\((?P<telefone>\d{10,11})\)\s*-\s*(?P<endereco>.+?),\s*(?P<numero>\d+)\s*-\s*Bairro:\s*(?P<bairro>.+)$',
                        texto_cliente_limpo, re.IGNORECASE
                    )
                    if padrao_completo:
                        nome_c = padrao_completo.group("nome").strip()
                        tel_c = padrao_completo.group("telefone").strip()
                        end_c = f"{padrao_completo.group('endereco').strip()}, {padrao_completo.group('numero').strip()}"
                        bair_c = padrao_completo.group("bairro").strip()
                    else:
                        match_tel = re.search(r'(\d{10,11})\s*$', texto_cliente_limpo)
                        if match_tel:
                            tel_c = match_tel.group(1).strip()
                            nome_c = texto_cliente_limpo[:match_tel.start()].strip()
                        else:
                            nome_c = texto_cliente_limpo.strip()

                if telefone_alerta and tel_c in ["Não Informado", "", "Endereço não informado"]: tel_c = telefone_alerta
                if endereco_alerta and end_c in ["Endereço não informado", "", "Não Informado"]: end_c = endereco_alerta
                if bairro_alerta and bair_c in ["Não Informado", "", "Endereço não informado"]: bair_c = bairro_alerta

                for prefixo in ["Nome:", "Tel:", "Telefone:", "End:", "Endereco:", "Endereço:", "Bairro:", "Bair:"]:
                    if nome_c.upper().startswith(prefixo.upper()): nome_c = nome_c[len(prefixo):].strip()
                    if tel_c.upper().startswith(prefixo.upper()): tel_c = tel_c[len(prefixo):].strip()
                    if end_c.upper().startswith(prefixo.upper()): end_c = end_c[len(prefixo):].strip()
                    if bair_c.upper().startswith(prefixo.upper()): bair_c = bair_c[len(prefixo):].strip()

                texto_produtos = itens_brutos
                if " | " in texto_produtos:
                    partes_pipe = [p.strip() for p in texto_produtos.split("|")]
                    produtos_filtrados = [p for p in partes_pipe if not ("Entrega:" in p or "taxa" in p.lower() or p.startswith("#"))]
                    texto_produtos = ", ".join(produtos_filtrados) if produtos_filtrados else partes_pipe[0]

                itens_contados = []
                if isinstance(itens_detalhados, list) and itens_detalhados:
                    for item in itens_detalhados:
                        if isinstance(item, dict):
                            nome_item = str(item.get('nome') or item.get('item') or '').strip()
                            qtd_item = int(item.get('qtd') or item.get('quantidade') or 1)
                            preco_unitario = float(item.get('preco_unitario') or item.get('preco') or 0.0)
                            preco_total_item = float(item.get('preco_total') or (preco_unitario * qtd_item) or 0.0)
                            if nome_item:
                                itens_contados.append({'nome': nome_item, 'qtd': qtd_item, 'preco': preco_unitario, 'preco_total': preco_total_item})
                else:
                    partes_virgula = [p.strip() for p in texto_produtos.split(",") if p.strip()]
                    agrupado = defaultdict(int)
                    for item_bruto in partes_virgula:
                        match = re.match(r'^(\d+)\s*x\s+(.+)$', item_bruto, re.IGNORECASE)
                        q = int(match.group(1)) if match else 1
                        n = match.group(2).strip() if match else item_bruto.strip()
                        if n: agrupado[n] += q
                    for nome_produto, qtd_produto in agrupado.items():
                        itens_contados.append({'nome': nome_produto, 'qtd': qtd_produto, 'preco': 0.0, 'preco_total': 0.0})

                sub = sum(item.get('preco_total', 0.0) or 0.0 for item in itens_contados)
                if not itens_contados or sub <= 0: sub = tot - taxa_entrega

                carrinho_itens_fake = {}
                id_ficticio = 1
                for item_info in itens_contados:
                    carrinho_itens_fake[id_ficticio] = {'qtd': item_info['qtd'], 'nome': item_info['nome'], 'preco': item_info['preco']}
                    id_ficticio += 1

                data_hora_cupom = agora.strftime("%d/%m/%Y %H:%M")
                data_hoje_cupom = agora.strftime("%d/%m/%Y")
                hora_cozinha = agora.strftime("%H:%M:%S")

                # ==========================================================
                # 💾 1. SALVANDO NO BANCO DE DADOS LOCAL (HISTÓRICO E CLIENTES)
                # ==========================================================
                try:
                    conn_bd = sqlite3.connect("sistema_delivery.db")
                    cursor_bd = conn_bd.cursor()

                    # A. Salva/Atualiza o cliente no banco local usando rowid para segurança
                    if nome_c and nome_c != "Cliente Web/Totem":
                        cursor_bd.execute("SELECT rowid FROM clientes WHERE nome = ? LIMIT 1", (nome_c,))
                        if not cursor_bd.fetchone():
                            try:
                                cursor_bd.execute(
                                    "INSERT INTO clientes (nome, telefone, endereco, bairro) VALUES (?, ?, ?, ?)",
                                    (nome_c, tel_c, end_c, bair_c)
                                )
                            except Exception as e_cli:
                                print(f"⚠️ Aviso ao registrar cliente: {e_cli}")

                    # B. Formata itens com a tag de taxa de entrega para o histórico
                    if taxa_entrega > 0:
                        itens_para_banco = f"{texto_produtos} | 🛵 Entrega: R$ {taxa_entrega:.2f}"
                    else:
                        itens_para_banco = texto_produtos

                    # C. Grava a venda na tabela 'vendas'
                    cursor_bd.execute('''
                        INSERT INTO vendas (data, cliente, total, pagamento, itens, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (data_hora_cupom, nome_c, tot, pag, itens_para_banco, 'Finalizado'))

                    conn_bd.commit()
                    conn_bd.close()
                    print(f"💾 [HISTÓRICO LOCAL] Pedido Web #{numero_pedido} salvo com sucesso no banco SQLite!")

                except Exception as err_bd:
                    print(f"❌ Erro ao salvar pedido no histórico local: {err_bd}")

                # Montagem do Cupom
                cupom = []
                cupom.append("------------------------------------------")
                cupom.append("              RENSHU SUSHI                ")
                cupom.append("        CNPJ: 23.248.904/0001-36          ") 
                cupom.append("    RUA MANOEL BOTELHO, 43 - PQ.SÃO RAFAEL    ") 
                cupom.append("------------------------------------------")
                cupom.append("            CUPOM NAO FISCAL              ")
                cupom.append("------------------------------------------")
                cupom.append(f"Data/Hora: {data_hora_cupom}")
                cupom.append(f"Cliente:   {nome_c[:30]}")
                cupom.append(f"Telefone:  {tel_c}")
                cupom.append(f"Endereco:  {end_c[:30]}")
                cupom.append(f"Bairro:    {bair_c[:30]}")
                cupom.append("------------------------------------------")
                cupom.append("Qtd Item                         Total    ")
                cupom.append("------------------------------------------")
                
                for pid, info in carrinho_itens_fake.items():
                    qtd = info['qtd']
                    nome_item = info['nome'][:24]
                    total_item = info['preco'] * qtd
                    cupom.append(f"{qtd:<3} {nome_item:<25} R$ {total_item:>7.2f}")
                    
                cupom.append("------------------------------------------")
                cupom.append(f"Subtotal:                     R$ {sub:>7.2f}")
                cupom.append(f"Taxa Entrega:                 R$ {taxa_entrega:>7.2f}")
                cupom.append(f"TOTAL DO PEDIDO:              R$ {tot:>7.2f}")
                cupom.append("------------------------------------------")
                cupom.append(f"Forma Pagamento: {pag}")
                cupom.append("------------------------------------------")
                cupom.append("         Obrigado pelo Pedido!            ")
                cupom.append("------------------------------------------")
                cupom.extend(["", "", "", ""])
                
                texto_cupom = "\r\n".join(cupom).replace("\n", "\r\n")

                # 1. IMPRESSÃO BALCÃO
                try:
                    lista_impressoras = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                    nome_da_impressora_do_balcao = "Balcao"
                    ip_cozinha = "POS58 10.0.0.6"
                    
                    if nome_da_impressora_do_balcao not in lista_impressoras:
                        for imp in lista_impressoras:
                            if ip_cozinha not in imp and "PDF" not in imp and "XPS" not in imp and "OneNote" not in imp:
                                nome_da_impressora_do_balcao = imp
                                break
                    if not nome_da_impressora_do_balcao:
                        nome_da_impressora_do_balcao = win32print.GetDefaultPrinter()

                    hPrinterB = win32print.OpenPrinter(nome_da_impressora_do_balcao)
                    try:
                        win32print.StartDocPrinter(hPrinterB, 1, ("Cupom Delivery", None, "RAW"))
                        win32print.StartPagePrinter(hPrinterB)
                        win32print.WritePrinter(hPrinterB, b"\x1b\x40\x1d\x21\x11\x1b\x61\x01")
                        win32print.WritePrinter(hPrinterB, f"PEDIDO #{numero_pedido}\n\n".encode("cp860", errors="ignore"))
                        win32print.WritePrinter(hPrinterB, b"\x1d\x21\x00\x1b\x61\x00\x1b\x45\x01")
                        win32print.WritePrinter(hPrinterB, texto_cupom.encode("cp860", errors="ignore"))
                        win32print.WritePrinter(hPrinterB, b"\x1b\x45\x00\n\n\n\n\n\x1bi")
                        win32print.EndPagePrinter(hPrinterB)
                        win32print.EndDocPrinter(hPrinterB)
                    finally:
                        win32print.ClosePrinter(hPrinterB)
                except Exception as e:
                    messagebox.showerror("Aviso de Impressão Balcão", f"O pedido foi gravado, mas a impressora do BALCÃO falhou: {e}")

                # 2. IMPRESSÃO COZINHA
                try:
                    nome_da_impressora_da_cozinha = "POS58 10.0.0.6" 
                    cupom_cozinha = [
                        "==========================================",
                        "               COZINHA                    ",
                        "==========================================",
                        f"Data: {data_hoje_cupom}         Hora: {hora_cozinha}",
                        "------------------------------------------",
                        "QTD  | ITEM",
                        "------------------------------------------"
                    ]
                    for pid, info in carrinho_itens_fake.items():
                        cupom_cozinha.append(f"{info['qtd']:<4} | {info['nome']}")
                        
                    cupom_cozinha.append("------------------------------------------\n\n\n\n\n")
                    texto_cozinha_final = "\n".join(cupom_cozinha)

                    hPrinterC = win32print.OpenPrinter(nome_da_impressora_da_cozinha)
                    try:
                        win32print.StartDocPrinter(hPrinterC, 1, (f"Pedido Cozinha {numero_pedido}", None, "RAW"))
                        win32print.StartPagePrinter(hPrinterC)
                        win32print.WritePrinter(hPrinterC, b"\x1b\x40\x1d\x21\x11\x1b\x61\x01")
                        win32print.WritePrinter(hPrinterC, f"COZINHA\nPEDIDO #{numero_pedido}\n\n".encode("cp860"))
                        win32print.WritePrinter(hPrinterC, b"\x1d\x21\x00\x1b\x61\x00")
                        win32print.WritePrinter(hPrinterC, texto_cozinha_final.encode("cp860", errors="ignore"))
                        win32print.WritePrinter(hPrinterC, b"\x1d\x56\x41\x00") 
                        win32print.EndPagePrinter(hPrinterC)
                        win32print.EndDocPrinter(hPrinterC)
                    finally:
                        win32print.ClosePrinter(hPrinterC)
                except Exception as erro_cozinha:
                    print(f"Aviso: Erro ao enviar para a impressora da cozinha: {erro_cozinha}")

    except Exception as e:
        print(f"⚠️ [MONITORAMENTO] Erro ao verificar alertas: {e}")
        
    finally:
        janela_principal.after(3000, lambda: verificar_pedidos_totem(janela_principal))
    
# Cores da Paleta RENSHU SUSHI - Neon Dark
COR_BG_LATERAL = "#0F0F11"     # Fundo lateral bem escuro, estilo app premium
COR_BG_CENTRAL = "#151518"     # Centro um tiquinho mais claro
COR_CARD = "#1F1F23"           # Cards modernos
COR_CARD_BORDA = "#2C2C32"     
COR_PRIMARY = "#E52E53"        # Vermelho melancia/cereja moderno, foge daquele vermelho antigo
COR_PRIMARY_HOVER = "#C02242"
COR_SUCCESS = "#00D26A"        
COR_INFO = "#2D7FF9"           
COR_WARNING = "#FF9F1C"

def inicializar_banco():
    conn = sqlite3.connect("sistema_delivery.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, descricao TEXT, imagem TEXT, categoria TEXT DEFAULT 'Geral', estoque INTEGER DEFAULT 999)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (telefone TEXT PRIMARY KEY, nome TEXT NOT NULL, endereco TEXT NOT NULL, bairro TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS taxas_entrega (bairro TEXT PRIMARY KEY, valor REAL NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, cliente TEXT, total REAL, pagamento TEXT, itens TEXT)")
    conn.commit()
    conn.close()

def listar_produtos():
    conn = sqlite3.connect("sistema_delivery.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, preco, descricao, imagem, categoria, estoque FROM produtos")
    dados = cursor.fetchall()
    conn.close()
    return dados

def listar_taxas():
    conn = sqlite3.connect("sistema_delivery.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bairro, valor FROM taxas_entrega ORDER BY bairro ASC")
    dados = cursor.fetchall()
    conn.close()
    return dados

class CarrinhoDeCompras:
    def __init__(self):
        self.itens = {}
        self.taxa_entrega = 0.0
    def adicionar(self, p_id, nome, preco):
        if p_id in self.itens: self.itens[p_id]['qtd'] += 1
        else: self.itens[p_id] = {'nome': nome, 'preco': preco, 'qtd': 1}
    def remover(self, p_id):
        if p_id in self.itens:
            if self.itens[p_id]['qtd'] > 1: self.itens[p_id]['qtd'] -= 1
            else: del self.itens[p_id]
    def obter_totais(self):
        sub = sum(item['preco'] * item['qtd'] for item in self.itens.values())
        return sub, sub + self.taxa_entrega
    def get_itens(self) -> dict:
        return self.itens

class AppPDV:
    def __init__(self, root):
        self.root = root
        self.root.title("Renshu Sushi - Painel Executivo PDV")
        
        # 1. Define o tamanho inicial e limites da janela
        self.root.geometry("1280x820")
        self.root.state('zoomed')     # Força o sistema a abrir em tela cheia (maximizado)
        self.root.minsize(1024, 720)  # Define um tamanho mínimo seguro para não esmagar os botões
        
        # --- CORREÇÃO DO PONTO CENTRAL: BLINDAGEM DO ROOT ---
        # Garante que o container principal use 100% da largura e altura do monitor
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Inicialização do sistema
        inicializar_banco()
        self.carrinho = CarrinhoDeCompras()
        self.caminho_imagem_selecionada = None
        
        # Constrói a interface
        self.configurar_layout()
        
        
    def configurar_layout(self):
        # Menu Lateral
        # MENU LATERAL - Ajustado para não expandir e esmagar o centro
        # --- MENU LATERAL (ESQUERDA) - Totalmente encostado e travado ---
        self.menu_lateral = ctk.CTkFrame(self.root, width=180, fg_color=COR_BG_LATERAL, corner_radius=0)
        self.menu_lateral.pack(side="left", fill="y", expand=False) # <--- expand=False impede que ele corra para o centro
        self.menu_lateral.pack_propagate(False) # <--- Trava a largura estritamente em 180px

        # Título oficial (Aparece apenas aqui no topo)
        #ctk.CTkLabel(self.menu_lateral, text="🍣 Renshu Sushi", font=("Segoe UI", 26, "bold"), text_color="#FFFFFF").pack(pady=(40, 5))
        ctk.CTkLabel(self.menu_lateral, text="Renshu Sushi", font=("Segoe UI", 12, "italic"), text_color="#888888").pack(pady=(0, 20))

        # --- FUNÇÃO DA COZINHA ---
        def disparar_impressao_cozinha():
            import datetime
            import win32print
            
            agora = datetime.datetime.now()
            hora_atual = agora.strftime("%H:%M:%S")
            hoje = agora.strftime("%d/%m/%Y")
            
            # --- CORREÇÃO SEGURA PARA EVITAR O ERRO 'NÃO DEFINIDO' ---
            id_comanda = None
            
            # 1. Tenta buscar das propriedades globais ou da classe do sistema
            for escopo in [self, globals(), locals()]:
                if hasattr(escopo, 'numero_pedido'):
                    id_comanda = getattr(escopo, 'numero_pedido')
                    break
                elif isinstance(escopo, dict) and 'numero_pedido' in escopo:
                    id_comanda = escopo['numero_pedido']
                    break
            
            # 2. Se não achou, tenta procurar se existe algum campo na tela mostrando o número
            if not id_comanda:
                for attr in dir(self):
                    if 'pedido' in attr.lower() or 'numero' in attr.lower():
                        comp = getattr(self, attr)
                        if hasattr(comp, 'get') and not attr.startswith('disparar'):
                            try:
                                valor = comp.get().strip().replace('#', '')
                                if valor.isdigit():
                                    id_comanda = valor
                                    break
                            except:
                                pass

            # 3. Rota de fuga: se o pedido ainda não foi gerado/salvo, usa os minutos e segundos 
            # para não travar o sistema e permitir a impressão
            if not id_comanda:
                id_comanda = agora.strftime("%M%S")
            
            cupom = [
                "==========================================",
                f"             PEDIDO #{id_comanda}         ", 
                "==========================================",
                f"Data: {hoje}          Hora: {hora_atual}",
                "------------------------------------------",
                "QTD  | ITEM",
                "------------------------------------------"
            ]
            
            # --- (O restante da lógica de busca de itens continua igual abaixo) ---
            itens_reais = []
            if hasattr(self.carrinho, 'itens') and isinstance(self.carrinho.itens, dict):
                for pid, info in self.carrinho.itens.items():
                    if isinstance(info, dict): itens_reais.append((info.get('qtd', 1), info.get('nome', 'Item')))
                    else: itens_reais.append((1, str(info)))
            elif hasattr(self.carrinho, 'itens') and isinstance(self.carrinho.itens, list):
                for item in self.carrinho.itens:
                    if isinstance(item, dict): itens_reais.append((item.get('qtd', 1), item.get('nome', 'Item')))
                    elif hasattr(item, 'nome'): itens_reais.append((getattr(item, 'qtd', 1), item.nome))
            elif callable(getattr(self.carrinho, 'get_itens', None)):
                res = self.carrinho.get_itens()
                if isinstance(res, dict):
                    for pid, info in res.items(): itens_reais.append((info.get('qtd', 1), info.get('nome', 'Item')))

            if not itens_reais:
                for attr in dir(self):
                    componente = getattr(self, attr)
                    if 'textbox' in attr.lower() and hasattr(componente, 'get'):
                        texto_tela = componente.get("1.0", "end").split("\n")
                        for linha in texto_tela:
                            if "x " in linha or " | " in list(linha): cupom.append(linha)
            else:
                for qtd, nome_item in itens_reais:
                    cupom.append(f"{qtd:<4} | {nome_item}")
            
            if len(cupom) <= 7:
                from tkinter import messagebox
                messagebox.showwarning("Aviso", "Os itens não puderam ser mapeados. Verifique se o carrinho possui produtos visíveis.")
                return
                
            cupom.append("------------------------------------------\n\n\n\n\n")
            texto_cozinha = "\n".join(cupom)

            try:
                nome_impressora = "POS58 10.0.0.6"
                hPrinter = win32print.OpenPrinter(nome_impressora)
                try:
                    win32print.StartDocPrinter(hPrinter, 1, (f"Pedido Cozinha {id_comanda}", None, "RAW"))
                    win32print.StartPagePrinter(hPrinter)
                    
                    win32print.WritePrinter(hPrinter, b"\x1b\x40\x1d\x21\x11\x1b\x61\x01")
                    # Imprime o número correto grande para o sushiman
                    win32print.WritePrinter(hPrinter, f"COZINHA\nPEDIDO #{id_comanda}\n\n".encode("cp860"))
                    
                    win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                    win32print.WritePrinter(hPrinter, texto_cozinha.encode("cp860", errors="ignore"))
                    win32print.WritePrinter(hPrinter, b"\x1d\x56\x41\x00") 
                    win32print.EndPagePrinter(hPrinter)
                    win32print.EndDocPrinter(hPrinter)
                finally:
                    win32print.ClosePrinter(hPrinter)
                from tkinter import messagebox
                messagebox.showinfo("Sucesso", f"Pedido #{id_comanda} enviado para a cozinha!")
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Erro", f"Falha na impressora: {e}")

       # --- BOTÃO LARANJA DA COZINHA (DESATIVADO) ---
        # btn_cozinha = ctk.CTkButton(
        #     self.menu_lateral, 
        #     text="🍳 Imprimir Cozinha", 
        #     fg_color="#FF9800", 
        #     hover_color="#F57C00", 
        #     font=("Segoe UI", 13, "bold"),
        #     command=disparar_impressao_cozinha
        # )
        # btn_cozinha.pack(fill="x", padx=20, pady=5)

        # NOTA: Se logo abaixo dessa linha existia outro ctk.CTkLabel com "Renshu", ele foi removido daqui!

        # --- FUNÇÃO DO FECHAMENTO DE CAIXA (Alinhado perfeitamente abaixo do botão) ---
        def abrir_fechamento_caixa_interno():
            import datetime
            import sqlite3
            from tkinter import messagebox
            hoje = datetime.datetime.now().strftime("%d/%m/%Y")

            caixa_win = ctk.CTkToplevel(None)
            caixa_win.title("Fechamento de Caixa - Renshu Sushi")
            caixa_win.geometry("500x670") 
            caixa_win.grab_set()

            def carregar_dados_caixa():
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("SELECT total, pagamento FROM vendas WHERE data LIKE ?", (f"{hoje}%",))
                vendas_hoje = c.fetchall()
                conn.close()

                total_geral = 0.0
                totais_por_pag = {"Pix": 0.0, "Cartão de Crédito": 0.0, "Cartão de Débito": 0.0, "Dinheiro": 0.0}
                qtd_pedidos = len(vendas_hoje)

                for total, pagamento in vendas_hoje:
                    total_geral += total
                    if pagamento in totais_por_pag:
                        totais_por_pag[pagamento] += total
                    else:
                        totais_por_pag[pagamento] = totais_por_pag.get(pagamento, 0.0) + total

                ticket_medio = total_geral / qtd_pedidos if qtd_pedidos > 0 else 0.0
                return total_geral, totais_por_pag, qtd_pedidos, ticket_medio

            total_geral, totais_por_pag, qtd_pedidos, ticket_medio = carregar_dados_caixa()

            ctk.CTkLabel(caixa_win, text=f"📊 Fechamento de Caixa ({hoje})", font=("Segoe UI", 20, "bold"), text_color="#FFFFFF").pack(pady=20)

            f_total = ctk.CTkFrame(caixa_win, fg_color=COR_PRIMARY, corner_radius=12, height=80)
            f_total.pack(fill="x", padx=30, pady=10)
            f_total.pack_propagate(False)
            
            ctk.CTkLabel(f_total, text="FATURAMENTO TOTAL DO DIA", font=("Segoe UI", 11, "bold"), text_color="#FFFFFF").pack(pady=(12,0))
            lbl_total_dinamico = ctk.CTkLabel(f_total, text=f"R$ {total_geral:.2f}", font=("Segoe UI", 24, "bold"), text_color="#FFFFFF")
            lbl_total_dinamico.pack()

            f_detalhes = ctk.CTkFrame(caixa_win, fg_color=COR_CARD, corner_radius=12)
            f_detalhes.pack(fill="both", expand=True, padx=30, pady=15)

            ctk.CTkLabel(f_detalhes, text="Entradas por Tipo:", font=("Segoe UI", 14, "bold"), text_color="#FFF").pack(anchor="w", padx=20, pady=(15, 10))

            labels_valores = {}
            for fpago, valor in totais_por_pag.items():
                f_linha = ctk.CTkFrame(f_detalhes, fg_color="transparent")
                f_linha.pack(fill="x", padx=20, pady=4)
                ctk.CTkLabel(f_linha, text=f"🔹 {fpago}:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
                lbl_val = ctk.CTkLabel(f_linha, text=f"R$ {valor:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF")
                lbl_val.pack(side="right")
                labels_valores[fpago] = lbl_val

            ctk.CTkLabel(f_detalhes, text="--------------------------------------------------", text_color="#444").pack(pady=5)

            f_estat_1 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
            f_estat_1.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(f_estat_1, text="Total de Pedidos:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
            lbl_qtd = ctk.CTkLabel(f_estat_1, text=str(qtd_pedidos), font=("Segoe UI", 13, "bold"), text_color="#FFF")
            lbl_qtd.pack(side="right")

            f_estat_2 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
            f_estat_2.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(f_estat_2, text="Ticket Médio p/ Pedido:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
            lbl_ticket = ctk.CTkLabel(f_estat_2, text=f"R$ {ticket_medio:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF")
            lbl_ticket.pack(side="right")

            def limpar_vendas_do_dia():
                resposta = messagebox.askyesno("⚠️ Atenção", "Você tem certeza que deseja APAGAR todas as vendas de hoje?\nIsso vai zerar o caixa atual!")
                if resposta:
                    try:
                        conn = sqlite3.connect("sistema_delivery.db")
                        c = conn.cursor()
                        c.execute("DELETE FROM vendas WHERE data LIKE ?", (f"{hoje}%",))
                        conn.commit()
                        conn.close()
                        
                        lbl_total_dinamico.configure(text="R$ 0.00")
                        lbl_qtd.configure(text="0")
                        lbl_ticket.configure(text="R$ 0.00")
                        
                        try:
                            for fpago in labels_valores:
                                labels_valores[fpago].configure(text="R$ 0.00")
                        except:
                            pass
                            
                        messagebox.showinfo("Sucesso", "O caixa de hoje foi zerado!")
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro ao limpar banco: {e}")

            def imprimir_relatorio_caixa():
                t_geral, t_pag, q_pedidos, t_medio = carregar_dados_caixa()
                cupom = [
                    "------------------------------------------",
                    "                RENSHU SUSHI              ",
                    "         CNPJ: 23.248.904/0001-36         ", # <-- ADICIONE O SEU CNPJ AQUI
                    "     RUA MANOEL BOTELHO , 43 - PQ. SÃO RAFAEL   ", # <-- ADICIONE O SEU ENDEREÇO AQUI
                    "------------------------------------------",
                    "            FECHAMENTO DE CAIXA            ",
                    "------------------------------------------",
                    f"Data de Referencia: {hoje}",
                    f"Impresso em:        {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    "------------------------------------------",
                    "RESUMO DE ENTRADAS:",
                    "------------------------------------------"
                ]
                for fpago, valor in t_pag.items():
                    cupom.append(f"{fpago:<25} R$ {valor:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append(f"Qtd Pedidos:                         {q_pedidos:>5}")
                cupom.append(f"Ticket Medio:                 R$ {t_medio:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append(f"FATURAMENTO TOTAL:            R$ {t_geral:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append("\n\nConferido por: _________________________\n\n\n\n\n")
                
                texto_cupom = "\n".join(cupom)
                try:
                    import win32print
                    # --- FORÇADO: Aponta direto para a impressora do Balcão ---
                    nome_impressora = "Balcao"
                    
                    hPrinter = win32print.OpenPrinter(nome_impressora)
                    try:
                        win32print.StartDocPrinter(hPrinter, 1, ("Fechamento Caixa", None, "RAW"))
                        win32print.StartPagePrinter(hPrinter)
                        win32print.WritePrinter(hPrinter, b"\x1b\x40\x1d\x21\x01\x1b\x61\x01")
                        win32print.WritePrinter(hPrinter, f"FECHAMENTO X\n\n".encode("cp860"))
                        win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                        win32print.WritePrinter(hPrinter, texto_cupom.encode("cp860", errors="ignore"))
                        win32print.EndPagePrinter(hPrinter)
                        win32print.EndDocPrinter(hPrinter)
                    finally:
                        win32print.ClosePrinter(hPrinter)
                    messagebox.showinfo("Sucesso", "Fechamento enviado para o BALCÃO!")
                except Exception as e:
                    messagebox.showerror("Erro", f"Falha ao mandar para impressora: {e}")

            # --- BOTÕES DA INTERFACE ---
            btn_print = ctk.CTkButton(caixa_win, text="🖨️ Imprimir Fechamento", height=42, fg_color="#4CAF50", hover_color="#388E3C", font=("Segoe UI", 13, "bold"), corner_radius=12, command=imprimir_relatorio_caixa)
            btn_print.pack(fill="x", padx=30, pady=(10, 5))

            btn_limpar = ctk.CTkButton(caixa_win, text="🗑️ Limpar Testes / Zerar Dia", height=42, fg_color="#D32F2F", hover_color="#C62828", font=("Segoe UI", 13, "bold"), corner_radius=12, command=limpar_vendas_do_dia)
            btn_limpar.pack(fill="x", padx=30, pady=(5, 20))

        # MENU LATERAL - Mais fino e elegante
        self.menu_lateral = ctk.CTkFrame(self.root, width=200, fg_color=COR_BG_LATERAL, corner_radius=0)
        self.menu_lateral.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.menu_lateral, text="🍣 Renshu", font=("Segoe UI", 26, "bold"), text_color="#FFFFFF").pack(pady=(40, 5))
        ctk.CTkLabel(self.menu_lateral, text="SUSHI & DELIVERY", font=("Segoe UI", 10, "bold"), text_color=COR_PRIMARY).pack(pady=(0, 40))
        
        # Botões laterais com cantos super arredondados
        ctk.CTkButton(self.menu_lateral, text="🍔 Itens / Estoque", fg_color="transparent", text_color="#E0E0E0", hover_color=COR_CARD, height=44, corner_radius=12, font=("Segoe UI", 13, "bold"), anchor="w", command=self.abrir_gerenciador).pack(pady=6, padx=15, fill="x")
        ctk.CTkButton(self.menu_lateral, text="👥 Clientes", fg_color="transparent", text_color="#E0E0E0", hover_color=COR_CARD, height=44, corner_radius=12, font=("Segoe UI", 13, "bold"), anchor="w", command=self.abrir_gerenciador_clientes).pack(pady=6, padx=15, fill="x")
        ctk.CTkButton(self.menu_lateral, text="📍 Taxas de Entrega", fg_color="transparent", text_color="#E0E0E0", hover_color=COR_CARD, height=44, corner_radius=12, font=("Segoe UI", 13, "bold"), anchor="w", command=self.abrir_gerenciador_taxas).pack(pady=6, padx=15, fill="x")
        ctk.CTkButton(self.menu_lateral, text="📊 Histórico", fg_color="transparent", text_color="#E0E0E0", hover_color=COR_CARD, height=44, corner_radius=12, font=("Segoe UI", 13, "bold"), anchor="w", command=self.abrir_historico_vendas).pack(pady=6, padx=15, fill="x")
        
        # BOTÃO DO FECHAMENTO CHAMANDO A FUNÇÃO INTERNA CORRETA
        ctk.CTkButton(self.menu_lateral, text="💰 Fechamento", fg_color="transparent", text_color="#E0E0E0", hover_color=COR_CARD, height=44, corner_radius=12, font=("Segoe UI", 13, "bold"), anchor="w", command=abrir_fechamento_caixa_interno).pack(pady=6, padx=15, fill="x")
        
        # ÁREA CENTRAL (VITRINE) - Ocupa 100% do espaço restante no centro
        self.area_central = ctk.CTkFrame(self.root, fg_color=COR_BG_CENTRAL, corner_radius=0)
        self.area_central.pack(side="left", fill="both", expand=True, padx=0)
        
        # Título do Cardápio com espaçamento otimizado
        ctk.CTkLabel(
            self.area_central, 
            text="Cardápio Principal", 
            font=("Segoe UI", 24, "bold"), 
            text_color="#FFFFFF"
        ).pack(anchor="w", pady=(20, 10), padx=25)
        
        # Scroll da Vitrine de pratos expandindo totalmente no espaço livre
        self.scroll_vitrine = ctk.CTkScrollableFrame(self.area_central, fg_color="transparent")
        self.scroll_vitrine.pack(fill="both", expand=True, padx=15, pady=5)
        
        self.atualizar_vitrine_tela()

       # ABA DIREITA (CARRINHO) - Ajustada para 340px e travada para não esmagar o centro
        self.aba_direita = ctk.CTkFrame(self.root, width=340, fg_color=COR_BG_LATERAL, corner_radius=0)
        self.aba_direita.pack(side="right", fill="y", expand=False)
        self.aba_direita.pack_propagate(False) # <--- Evita que o conteúdo interno altere o tamanho da barra
        
        # Scroll interno ajustado proporcionalmente para a nova largura
        self.scroll_aba_direita = ctk.CTkScrollableFrame(self.aba_direita, fg_color="transparent", width=320)
        self.scroll_aba_direita.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(self.scroll_aba_direita, text="🛒 Seu Carrinho", font=("Segoe UI", 18, "bold"), text_color="#FFFFFF").pack(anchor="w", padx=15, pady=(15, 15))
        
        self.scroll_carrinho = ctk.CTkScrollableFrame(self.scroll_aba_direita, height=180, fg_color=COR_CARD, corner_radius=16, border_width=0)
        self.scroll_carrinho.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.scroll_aba_direita, text="📍 Dados de Entrega", font=("Segoe UI", 13, "bold"), text_color="#888888").pack(anchor="w", padx=15, pady=(20, 8))
        
        self.txt_tel = ctk.CTkEntry(self.scroll_aba_direita, placeholder_text="Telefone", height=40, fg_color=COR_CARD, border_color=COR_CARD_BORDA, corner_radius=12, font=("Segoe UI", 12))
        self.txt_tel.pack(fill="x", padx=10, pady=5)
        self.txt_tel.bind("<FocusOut>", self.buscar_cliente_automatico)
        
        self.txt_nome = ctk.CTkEntry(self.scroll_aba_direita, placeholder_text="Nome do Cliente", height=40, fg_color=COR_CARD, border_color=COR_CARD_BORDA, corner_radius=12, font=("Segoe UI", 12))
        self.txt_nome.pack(fill="x", padx=10, pady=5)
        
        # --- RESTAURADO: de CTkTextbox de volta para CTkEntry (Otimizado) ---
        # Usamos o CTkEntry com placeholder nativo para eliminar travamentos e recuperar o espaço das categorias
        self.txt_end = ctk.CTkEntry(
            self.scroll_aba_direita, 
            placeholder_text="Endereço Completo", 
            height=40, 
            fg_color=COR_CARD, 
            border_color=COR_CARD_BORDA, 
            corner_radius=12, 
            font=("Segoe UI", 12)
        )
        self.txt_end.pack(fill="x", padx=10, pady=5)
        # ---------------------------------------------
        
        self.combo_bairros_pdv = ctk.CTkOptionMenu(self.scroll_aba_direita, values=["Selecione o Bairro"], height=40, fg_color=COR_CARD, button_color=COR_CARD_BORDA, button_hover_color="#444", corner_radius=12, font=("Segoe UI", 12))
        self.combo_bairros_pdv.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.scroll_aba_direita, text="💳 Pagamento", font=("Segoe UI", 13, "bold"), text_color="#888888").pack(anchor="w", padx=15, pady=(15, 5))
        
        def monitorar_pagamento(opcao_selecionada):
            if opcao_selecionada == "Dinheiro":
                self.txt_valor_recebido.configure(state="normal", fg_color=COR_CARD, border_color=COR_PRIMARY)
            else:
                self.txt_valor_recebido.delete(0, 'end')
                self.txt_valor_recebido.configure(state="disabled", fg_color="#2A2A2A", border_color=COR_CARD_BORDA)
                self.lbl_troco_resultado.configure(text="Troco: R$ 0.00", text_color="#FF9800")

        self.combo_pag = ctk.CTkOptionMenu(self.scroll_aba_direita, values=["Pix", "Cartão de Crédito", "Cartão de Débito", "Dinheiro"], height=40, fg_color=COR_CARD, button_color=COR_CARD_BORDA, button_hover_color="#444", corner_radius=12, font=("Segoe UI", 12), command=monitorar_pagamento)
        self.combo_pag.pack(fill="x", padx=10, pady=5)
        self.combo_pag.set("Pix")
        
        self.txt_valor_recebido = ctk.CTkEntry(self.scroll_aba_direita, placeholder_text="Valor em Dinheiro (Ex: 100.00)", height=40, fg_color="#2A2A2A", border_color=COR_CARD_BORDA, corner_radius=12, font=("Segoe UI", 12), state="disabled")
        self.txt_valor_recebido.pack(fill="x", padx=10, pady=4)
        
        self.lbl_troco_resultado = ctk.CTkLabel(self.scroll_aba_direita, text="Troco: R$ 0.00", font=("Segoe UI", 13, "bold"), text_color="#FF9800")
        self.lbl_troco_resultado.pack(anchor="w", padx=15, pady=2)
        
        def calcular_troco_instantaneo(event):
            try:
                texto_total = self.lbl_tot.cget("text").replace("TOTAL: R$ ", "").strip()
                total_pedido = float(texto_total)
                texto_digitado = self.txt_valor_recebido.get().replace(",", ".").strip()
                
                if texto_digitado:
                    valor_entregue = float(texto_digitado)
                    if valor_entregue >= total_pedido:
                        troco_instantaneo = valor_entregue - total_pedido
                        self.lbl_troco_resultado.configure(text=f"Troco: R$ {troco_instantaneo:.2f}", text_color="#4CAF50")
                    else:
                        self.lbl_troco_resultado.configure(text="Troco: Valor insuficiente", text_color="#F44336")
                else:
                    self.lbl_troco_resultado.configure(text="Troco: R$ 0.00", text_color="#FF9800")
            except ValueError:
                self.lbl_troco_resultado.configure(text="Troco: Valor inválido", text_color="#F44336")

        self.txt_valor_recebido.bind("<KeyRelease>", calcular_troco_instantaneo)
        
        f_valores = ctk.CTkFrame(self.scroll_aba_direita, fg_color="transparent")
        f_valores.pack(fill="x", padx=15, pady=20)
        
        self.lbl_sub = ctk.CTkLabel(f_valores, text="Subtotal: R$ 0.00", font=("Segoe UI", 13), text_color="#888888")
        self.lbl_sub.pack(anchor="w")
        self.lbl_tx = ctk.CTkLabel(f_valores, text="Taxa de Entrega: R$ 0.00", font=("Segoe UI", 13), text_color="#888888")
        self.lbl_tx.pack(anchor="w", pady=4)
        
        self.lbl_tot = ctk.CTkLabel(f_valores, text="TOTAL: R$ 0.00", font=("Segoe UI", 22, "bold"), text_color="#FFFFFF")
        self.lbl_tot.pack(anchor="w", pady=(10, 0))
        
        ctk.CTkButton(self.scroll_aba_direita, text="Finalizar Pedido", height=54, fg_color=COR_PRIMARY, hover_color=COR_PRIMARY_HOVER, font=("Segoe UI", 15, "bold"), corner_radius=16, command=self.finalizar_pedido_completo).pack(fill="x", padx=10, pady=(10, 20))
        
        self.atualizar_dropdown_bairros_pdv()

    def atualizar_vitrine_tela(self):
        for w in self.scroll_vitrine.winfo_children(): w.destroy()
        
        tabview = ctk.CTkTabview(self.scroll_vitrine, fg_color="transparent", segmented_button_selected_color=COR_PRIMARY, segmented_button_selected_hover_color=COR_PRIMARY_HOVER, segmented_button_unselected_color="#222222")
        tabview.pack(fill="both", expand=True)
        
        # Lista com todas as suas novas categorias organizadas
        categorias = ["Yakisoba", "Temaki", "Combos", "Pokes", "Sushis", "Sushi Unid", "Bebidas", "Acompanhamentos", "Sobremesa"]
        scrolls_abas = {}
        
        for cat in categorias:
            tabview.add(cat)
            # --- AJUSTE 1: Altura limitada para o scroll não esticar demais a tela ---
            scroll_aba = ctk.CTkScrollableFrame(tabview.tab(cat), fg_color="transparent", height=400)
            scroll_aba.pack(fill="both", expand=True)
            scrolls_abas[cat.strip().lower()] = scroll_aba

        for p in listar_produtos():
            pid, nome, preco, desc, img_path, cat, est = p
            
            cat_formatada = str(cat).strip().lower() if cat else "yakisoba"
            
            aba_alvo = scrolls_abas.get(cat_formatada, scrolls_abas["yakisoba"])
            
            # --- AJUSTE 2: Altura do card reduzida para 90 (ficam mais compactos) ---
            card = ctk.CTkFrame(aba_alvo, fg_color=COR_CARD, border_width=1, border_color=COR_CARD_BORDA, corner_radius=12, height=90)
            card.pack(fill="x", pady=4, padx=10)
            card.pack_propagate(False)

            # --- CORREÇÃO DE CAMINHO DA IMAGEM PARA A PASTA STATIC ---
            dir_atual = os.path.dirname(os.path.abspath(__file__))
            nome_arquivo = os.path.basename(img_path) if img_path else ""
            
            # Tenta encontrar primeiro na pasta 'static'
            caminho_final_imagem = os.path.join(dir_atual, "static", nome_arquivo) if nome_arquivo else None

            try:
                # Se não existir na pasta static, tenta procurar na pasta antiga 'imagens' por compatibilidade
                if caminho_final_imagem and not os.path.exists(caminho_final_imagem):
                    caminho_backup = os.path.join(dir_atual, "imagens", nome_arquivo)
                    if os.path.exists(caminho_backup):
                        caminho_final_imagem = caminho_backup

                # --- AJUSTE 3: Imagem reduzida para 65x65 para acompanhar o card compacto ---
                if caminho_final_imagem and os.path.exists(caminho_final_imagem):
                    img_obj = ctk.CTkImage(light_image=Image.open(caminho_final_imagem), size=(65, 65))
                else: 
                    img_obj = None
            except Exception as e: 
                print(f"Erro ao carregar imagem no balcão: {e}")
                img_obj = None

            if img_obj:
                lbl_i = ctk.CTkLabel(card, image=img_obj, text="")
                lbl_i.pack(side="left", padx=12, pady=12)
            else:
                lbl_p = ctk.CTkFrame(card, width=65, height=65, fg_color="#262626", corner_radius=8)
                lbl_p.pack(side="left", padx=12, pady=12)
                ctk.CTkLabel(lbl_p, text="🍣\nS/ Foto", font=("Arial", 10), text_color="#777777", justify="center").place(relx=0.5, rely=0.5, anchor="center")

            # --- CORREÇÃO DO TEXTO: Força limites para proteger o espaço do botão ---
            f_txt = ctk.CTkFrame(card, fg_color="transparent")
            f_txt.pack(side="left", fill="both", expand=True, padx=5, pady=5)
            
            # wraplength impede que o nome do Combo 7 empurre o botão para fora
            ctk.CTkLabel(f_txt, text=nome, font=("Arial", 14, "bold"), text_color="#FFFFFF", wraplength=250, anchor="w", justify="left").pack(anchor="w")
            
            detalhes_texto = f"{desc} | " if desc else ""
            cor_estoque = "#4CAF50" if est > 3 else "#FF9800" if est > 0 else "#F44336"
            
            f_sub_info = ctk.CTkFrame(f_txt, fg_color="transparent")
            f_sub_info.pack(anchor="w")
            
            # wraplength na descrição também evita o esmagamento lateral
            ctk.CTkLabel(f_sub_info, text=detalhes_texto, font=("Arial", 11), text_color="#888888", wraplength=180, justify="left").pack(side="left")
            ctk.CTkLabel(f_sub_info, text=f"Estoque: {est}", font=("Arial", 10, "bold"), text_color=cor_estoque).pack(side="left")
            
            ctk.CTkLabel(f_txt, text=f"R$ {preco:.2f}", text_color=COR_PRIMARY, font=("Consolas", 14, "bold")).pack(anchor="w", pady=(0, 0))
            
            if est > 0:
                ctk.CTkButton(card, text="➕ Adicionar", width=90, height=30, fg_color=COR_PRIMARY, hover_color=COR_PRIMARY_HOVER, font=("Arial", 11, "bold"), corner_radius=8, command=lambda id_p=pid, n=nome, pr=preco: self.add_carrinho(id_p, n, pr)).pack(side="right", padx=15)
            else:
                ctk.CTkButton(card, text="Esgotado", width=90, height=30, fg_color="#333333", text_color="#777777", state="disabled", corner_radius=8).pack(side="right", padx=15)
    def abrir_gerenciador(self):
        g_win = ctk.CTkToplevel(self.root)
        g_win.title("Gerenciar Itens e Estoque")
        g_win.geometry("1050x660")
        g_win.grab_set()

        self.id_produto_em_edicao = None
        self.caminho_imagem_selecionada = None

        # Painel Esquerdo (Formulário)
        f_esq = ctk.CTkFrame(g_win, width=330, fg_color=COR_BG_LATERAL, corner_radius=12)
        f_esq.pack(side="left", fill="both", padx=15, pady=15)

        lbl_status = ctk.CTkLabel(f_esq, text="✨ Cadastrar Novo Produto", font=("Arial", 14, "bold"), text_color="#FFF")
        lbl_status.pack(pady=15)

        txt_n = ctk.CTkEntry(f_esq, placeholder_text="Nome do Item", height=35)
        txt_n.pack(fill="x", padx=15, pady=6)

        txt_d = ctk.CTkEntry(f_esq, placeholder_text="Descrição / Ingredientes", height=35)
        txt_d.pack(fill="x", padx=15, pady=6)

        txt_p = ctk.CTkEntry(f_esq, placeholder_text="Preço (Ex: 29.90)", height=35)
        txt_p.pack(fill="x", padx=15, pady=6)

        txt_e = ctk.CTkEntry(f_esq, placeholder_text="Qtd Inicial em Estoque", height=35)
        txt_e.pack(fill="x", padx=15, pady=6)

        ctk.CTkLabel(f_esq, text="Categoria do Produto:", font=("Arial", 11), text_color="#AAA").pack(anchor="w", padx=18, pady=(8, 2))
        
        combo_c = ctk.CTkOptionMenu(
            f_esq, 
            values=["Yakisoba", "Temaki", "Combos", "Pokes", "Sushis", "Sushi Unid", "Bebidas", "Acompanhamentos", "Sobremesa"], 
            fg_color="#262626", 
            button_color="#333", 
            height=35
        )
        combo_c.pack(fill="x", padx=15, pady=4)

        lbl_img_status = ctk.CTkLabel(f_esq, text="Nenhuma foto anexada", text_color="gray", font=("Arial", 11))
        lbl_img_status.pack(pady=5)

        def selecionar_foto():
            caminho = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg *.png *.jpeg")])
            if caminho:
                self.caminho_imagem_selecionada = caminho
                lbl_img_status.configure(text="✅ Foto Pronta!", text_color="#4CAF50")

        ctk.CTkButton(f_esq, text="🖼️ Selecionar Foto", fg_color="#444444", hover_color="#555555", corner_radius=6, command=selecionar_foto).pack(pady=4, padx=15, fill="x")

        # Função Salvar (definida ANTES dos botões que a usam)
        def salvar():
            import shutil
            import os

            if not txt_n.get() or not txt_p.get():
                messagebox.showwarning("Atenção", "Preencha ao menos o Nome e o Preço do produto!")
                return

            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()

            n = txt_n.get()
            try:
                pr = float(txt_p.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Erro", "Formato de preço inválido!")
                conn.close()
                return

            d = txt_d.get()
            cat = combo_c.get()
            est = int(txt_e.get()) if txt_e.get().isdigit() else 0

            nome_imagem_db = None

            if self.caminho_imagem_selecionada:
                nome_arquivo = os.path.basename(self.caminho_imagem_selecionada)
                dir_atual = os.path.dirname(os.path.abspath(__file__))
                pasta_static = os.path.join(dir_atual, "static")

                os.makedirs(pasta_static, exist_ok=True)
                destino = os.path.join(pasta_static, nome_arquivo)

                try:
                    if os.path.abspath(self.caminho_imagem_selecionada) != os.path.abspath(destino):
                        shutil.copy(self.caminho_imagem_selecionada, destino)
                    nome_imagem_db = nome_arquivo
                except Exception as e:
                    print(f"Erro ao mover imagem: {e}")
                    nome_imagem_db = nome_arquivo

            if self.id_produto_em_edicao:
                if nome_imagem_db is None:
                    c.execute("""
                        UPDATE produtos 
                        SET nome=?, preco=?, descricao=?, categoria=?, estoque=? 
                        WHERE id=?
                    """, (n, pr, d, cat, est, self.id_produto_em_edicao))
                else:
                    c.execute("""
                        UPDATE produtos 
                        SET nome=?, preco=?, descricao=?, imagem=?, categoria=?, estoque=? 
                        WHERE id=?
                    """, (n, pr, d, nome_imagem_db, cat, est, self.id_produto_em_edicao))
            else:
                c.execute("""
                    INSERT INTO produtos (nome, preco, descricao, imagem, categoria, estoque) 
                    VALUES (?,?,?,?,?,?)
                """, (n, pr, d, nome_imagem_db, cat, est))

            conn.commit()
            conn.close()

            limpar_formulario()
            atualizar_lista_gerenciador()
            self.atualizar_vitrine_tela()

        def limpar_formulario():
            self.id_produto_em_edicao = None
            self.caminho_imagem_selecionada = None
            lbl_status.configure(text="✨ Cadastrar Novo Produto", text_color="#FFF")
            btn_salvar.configure(text="💾 Salvar Produto", fg_color="#4CAF50")
            txt_n.delete(0, 'end'); txt_p.delete(0, 'end'); txt_d.delete(0, 'end'); txt_e.delete(0, 'end')
            combo_c.set("Yakisoba")
            lbl_img_status.configure(text="Nenhuma foto anexada", text_color="gray")

        # Botões do formulário
        btn_salvar = ctk.CTkButton(f_esq, text="💾 Salvar Produto", fg_color="#4CAF50", hover_color="#388E3C", corner_radius=6, font=("Arial", 12, "bold"), command=salvar)
        btn_salvar.pack(pady=(10, 4), padx=15, fill="x")

        ctk.CTkButton(f_esq, text="🧹 Limpar Formulário", fg_color="#666666", hover_color="#777777", corner_radius=6, command=limpar_formulario).pack(pady=(4, 12), padx=15, fill="x")

        # Painel Direito (Lista de Produtos)
        scr_p = ctk.CTkScrollableFrame(g_win, fg_color=COR_BG_CENTRAL, corner_radius=12)
        scr_p.pack(side="right", fill="both", expand=True, padx=(0, 15), pady=15)

        def carregar(item):
            pid, nome, preco, desc, img, cat, est = item
            self.id_produto_em_edicao = pid
            self.caminho_imagem_selecionada = None
            
            lbl_status.configure(text=f"✏️ Editando: {nome}", text_color="#FFEB3B")
            btn_salvar.configure(text="🔄 Atualizar Produto", fg_color="#FF9800")
            
            txt_n.delete(0, 'end'); txt_n.insert(0, nome if nome else "")
            txt_d.delete(0, 'end'); txt_d.insert(0, desc if desc else "")
            txt_p.delete(0, 'end'); txt_p.insert(0, str(preco) if preco else "0.0")
            txt_e.delete(0, 'end'); txt_e.insert(0, str(est) if est else "0")
            combo_c.set(cat if cat else "Yakisoba")
            
            lbl_img_status.configure(
                text=f"📷 Foto atual: {img}" if img else "Nenhuma foto anexada", 
                text_color="#4CAF50" if img else "gray"
            )

        def remover(pid):
            if messagebox.askyesno("Excluir", "Deseja mesmo remover permanentemente este produto?"):
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("DELETE FROM produtos WHERE id=?", (pid,))
                conn.commit()
                conn.close()
                limpar_formulario()
                atualizar_lista_gerenciador()
                self.atualizar_vitrine_tela()

        def atualizar_lista_gerenciador():
            for w in scr_p.winfo_children(): 
                w.destroy()

            produtos = listar_produtos()
            ctk.CTkLabel(scr_p, text=f"Itens cadastrados ({len(produtos)})", font=("Arial", 13, "bold"), text_color="#FFF").pack(anchor="w", padx=12, pady=(10, 8))

            if not produtos:
                ctk.CTkLabel(scr_p, text="Nenhum item cadastrado ainda.", text_color="#AAAAAA", font=("Arial", 12)).pack(anchor="w", padx=12, pady=10)
                return

            for item in produtos:
                pid, nome, preco, desc, img, cat, est = item
                f = ctk.CTkFrame(scr_p, fg_color=COR_CARD, border_width=1, border_color=COR_CARD_BORDA, corner_radius=8)
                f.pack(fill="x", pady=4, padx=8)

                ctk.CTkLabel(f, text=f"{nome} [{cat or 'Geral'}]", font=("Arial", 12, "bold"), text_color="#FFF", wraplength=420, justify="left").pack(side="left", padx=12, pady=10, anchor="w")
                ctk.CTkLabel(f, text=f"Est: {est} | R$ {preco:.2f}", font=("Arial", 11), text_color="#CCCCCC").pack(side="left", padx=8, pady=10, anchor="w")
                
                ctk.CTkButton(f, text="❌", width=30, height=30, fg_color="transparent", text_color="#F44336", font=("Arial", 14, "bold"), hover_color="#2A1414", command=lambda id_p=pid: remover(id_p)).pack(side="right", padx=6)
                ctk.CTkButton(f, text="✏️", width=30, height=30, fg_color="transparent", text_color="#FFEB3B", font=("Arial", 14, "bold"), hover_color="#2A2A14", command=lambda p=item: carregar(p)).pack(side="right", padx=2)

        # Inicializa a lista
        atualizar_lista_gerenciador()

    def finalizar_pedido_completo(self):
        sub, tot = self.carrinho.obter_totais()
        if not self.carrinho.itens or not self.txt_nome.get(): 
            messagebox.showwarning("Erro de Validação", "Você precisa preencher os dados do cliente e ter itens no carrinho!")
            return
            
        nome_c = self.txt_nome.get()
        tel_c = self.txt_tel.get()
        
        # --- CORREÇÃO AQUI ---
        # Lê o endereço de CTkTextbox ou CTkEntry com reconhecimento de tipo estático.
        get_value = getattr(self.txt_end, 'get', None)
        end_c = ''
        if callable(get_value):
            try:
                end_c = str(get_value("1.0", "end-1c")).strip()
            except TypeError:
                end_c = str(get_value()).strip()
            except Exception:
                end_c = ''

        bair_c = self.combo_bairros_pdv.get()
        pag = self.combo_pag.get()
        
        # --- LÓGICA E CÁLCULO DO TROCO ---
        valor_pago = 0.0
        troco = 0.0
        texto_troco_banco = ""
        
        if pag == "Dinheiro":
            texto_digitado = self.txt_valor_recebido.get().replace(",", ".").strip()
            if texto_digitado:
                try:
                    valor_pago = float(texto_digitado)
                    if valor_pago < tot:
                        messagebox.showwarning("Erro de Troco", f"O valor em dinheiro (R$ {valor_pago:.2f}) é menor que o total do pedido (R$ {tot:.2f})!")
                        return
                    troco = valor_pago - tot
                    texto_troco_banco = f" | 💵 Pago: R$ {valor_pago:.2f} (Troco: R$ {troco:.2f})"
                except ValueError:
                    messagebox.showerror("Erro de Digitação", "Digite um valor numérico válido para o dinheiro!")
                    return
        
        import datetime
        agora = datetime.datetime.now()
        data_hora = agora.strftime("%d/%m/%Y %H:%M")
        data_hoje = agora.strftime("%d/%m/%Y")
        
        # --- BANCO DE DADOS ---
        conn = sqlite3.connect("sistema_delivery.db")
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM vendas WHERE data LIKE ?", (f"{data_hoje}%",))
        qtd_hoje = c.fetchone()[0]
        numero_pedido = qtd_hoje + 1
        
        resumo_itens = ", ".join([f"{info['qtd']}x {info['nome']}" for info in self.carrinho.itens.values()])
        resumo_com_taxa = f"#{numero_pedido} | {resumo_itens} | 🛵 Entrega: R$ {self.carrinho.taxa_entrega:.2f}{texto_troco_banco}"

        c.execute("INSERT OR REPLACE INTO clientes (telefone, nome, endereco, bairro) VALUES (?,?,?,?)", (tel_c, nome_c, end_c, bair_c))
        c.execute("INSERT INTO vendas (data, cliente, total, pagamento, itens) VALUES (?,?,?,?,?)", (data_hora, nome_c, tot, pag, resumo_com_taxa))

        for pid, info in self.carrinho.itens.items():
            c.execute("UPDATE produtos SET estoque = MAX(0, estoque - ?) WHERE id = ?", (info['qtd'], pid))
            
        conn.commit()
        conn.close()
        
        # --- MONTAGEM DO CUPOM IMPRESSO ---
        cupom = []
        cupom.append("------------------------------------------")
        cupom.append("              RENSHU SUSHI                ")
        cupom.append("        CNPJ: 23.248.904/0001-36          ") # <-- SEU CNPJ SALVO
        cupom.append("    RUA MANOEL BOTELHO, 43 - PQ.SÃO RAFAEL    ") # <-- SEU ENDEREÇO SALVO
        cupom.append("------------------------------------------")
        cupom.append("            CUPOM NAO FISCAL              ")
        cupom.append("------------------------------------------")
        cupom.append(f"Data/Hora: {data_hora}")
        cupom.append(f"Cliente:   {nome_c[:30]}")
        cupom.append(f"Telefone:  {tel_c}")
        cupom.append(f"Endereco:  {end_c[:30]}")
        cupom.append(f"Bairro:    {bair_c[:30]}")
        cupom.append("------------------------------------------")
        cupom.append("Qtd Item                         Total    ")
        cupom.append("------------------------------------------")
        
        for pid, info in self.carrinho.itens.items():
            qtd = info['qtd']
            nome_item = info['nome'][:24]
            total_item = info['preco'] * qtd
            cupom.append(f"{qtd:<3} {nome_item:<25} R$ {total_item:>7.2f}")
            
        cupom.append("------------------------------------------")
        cupom.append(f"Subtotal:                     R$ {sub:>7.2f}")
        cupom.append(f"Taxa Entrega:                 R$ {self.carrinho.taxa_entrega:>7.2f}")
        cupom.append(f"TOTAL DO PEDIDO:              R$ {tot:>7.2f}")
        cupom.append("------------------------------------------")
        cupom.append(f"Forma Pagamento: {pag}")
        
        if pag == "Dinheiro" and valor_pago > 0:
            cupom.append(f"Valor em Dinheiro:            R$ {valor_pago:>7.2f}")
            cupom.append(f"LEVAR DE TROCO:               R$ {troco:>7.2f}")
            
        cupom.append("------------------------------------------")
        cupom.append("         Obrigado pelo Pedido!            ")
        cupom.append("------------------------------------------")
        cupom.append("\n\n\n\n")
        
        texto_cupom = "\n".join(cupom)
        
        # ==========================================================
        # 1. IMPRESSÃO DO BALCÃO (Cupom Delivery Completo)
        # ==========================================================
        try:
            import win32print
            
            # --- ROTA DE FUGA DINÂMICA ---
            lista_impressoras = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
            
            nome_da_impressora_do_balcao = "Balcao"
            ip_cozinha = "POS58 10.0.0.6"
            
            if nome_da_impressora_do_balcao not in lista_impressoras:
                for imp in lista_impressoras:
                    if ip_cozinha not in imp and "PDF" not in imp and "XPS" not in imp and "OneNote" not in imp:
                        nome_da_impressora_do_balcao = imp
                        break
            
            if not nome_da_impressora_do_balcao:
                nome_da_impressora_do_balcao = win32print.GetDefaultPrinter()

            hPrinterB = win32print.OpenPrinter(nome_da_impressora_do_balcao)
            try:
                win32print.StartDocPrinter(hPrinterB, 1, ("Cupom Delivery", None, "RAW"))
                win32print.StartPagePrinter(hPrinterB)
                
                win32print.WritePrinter(hPrinterB, b"\x1b\x40")
                
                # Número do Pedido Grande no Balcão
                win32print.WritePrinter(hPrinterB, b"\x1d\x21\x11\x1b\x61\x01")
                texto_numero = f"PEDIDO #{numero_pedido}\n\n"
                win32print.WritePrinter(hPrinterB, texto_numero.encode("cp860", errors="ignore"))
                
                # Aviso de Troco Grande para o Motoboy
                if pag == "Dinheiro" and troco > 0:
                    win32print.WritePrinter(hPrinterB, b"\x1d\x21\x01\x1b\x61\x01")
                    texto_aviso_troco = f"** LEVAR TROCO DE R$ {troco:.2f} **\n\n"
                    win32print.WritePrinter(hPrinterB, texto_aviso_troco.encode("cp860", errors="ignore"))

                # Retorna ao padrão normal do Balcão
                win32print.WritePrinter(hPrinterB, b"\x1d\x21\x00\x1b\x61\x00\x1b\x45\x01")
                
                texto_bytes = texto_cupom.encode("cp860", errors="ignore")
                win32print.WritePrinter(hPrinterB, texto_bytes)
                
                # --- ALTERADO AQUI: Adicionado avanço de linha e comando \x1bi para acionar a guilhotina automaticamente ---
                comando_final = b"\x1b\x45\x00\n\n\n\n\n\x1bi"
                win32print.WritePrinter(hPrinterB, comando_final)
                
                win32print.EndPagePrinter(hPrinterB)
                win32print.EndDocPrinter(hPrinterB)
            finally:
                win32print.ClosePrinter(hPrinterB)
        except Exception as e:
            messagebox.showerror("Aviso de Impressão Balcão", f"O pedido foi gravado, mas a impressora do BALCÃO falhou: {e}")
                
        # ==========================================================
        # 2. IMPRESSÃO DA COZINHA (Apenas os Itens de Produção)
        # ==========================================================
        try:
            nome_da_impressora_da_cozinha = "POS58 10.0.0.6" 
            hora_cozinha = agora.strftime("%H:%M:%S")
            
            cupom_cozinha = [
                "==========================================",
                "               COZINHA                    ",
                "==========================================",
                f"Data: {data_hoje}          Hora: {hora_cozinha}",
                "------------------------------------------",
                "QTD  | ITEM",
                "------------------------------------------"
            ]
            
            for pid, info in self.carrinho.itens.items():
                qtd = info['qtd']
                nome_item = info['nome']
                cupom_cozinha.append(f"{qtd:<4} | {nome_item}")
                
            cupom_cozinha.append("------------------------------------------\n\n\n\n\n")
            texto_cozinha_final = "\n".join(cupom_cozinha)

            # Criamos uma conexão exclusiva chamada hPrinterC
            hPrinterC = win32print.OpenPrinter(nome_da_impressora_da_cozinha)
            try:
                win32print.StartDocPrinter(hPrinterC, 1, (f"Pedido Cozinha {numero_pedido}", None, "RAW"))
                win32print.StartPagePrinter(hPrinterC)
                
                # Título Grande e Centralizado na Cozinha
                win32print.WritePrinter(hPrinterC, b"\x1b\x40\x1d\x21\x11\x1b\x61\x01")
                win32print.WritePrinter(hPrinterC, f"COZINHA\nPEDIDO #{numero_pedido}\n\n".encode("cp860"))
                
                # Itens normais na Cozinha
                win32print.WritePrinter(hPrinterC, b"\x1d\x21\x00\x1b\x61\x00")
                win32print.WritePrinter(hPrinterC, texto_cozinha_final.encode("cp860", errors="ignore"))
                win32print.WritePrinter(hPrinterC, b"\x1d\x56\x41\x00") 
                
                win32print.EndPagePrinter(hPrinterC)
                win32print.EndDocPrinter(hPrinterC)
            finally:
                win32print.ClosePrinter(hPrinterC)
        except Exception as erro_cozinha:
            print(f"Aviso: Erro ao enviar para a impressora da cozinha: {erro_cozinha}")

        # Mensagem única de sucesso final
        messagebox.showinfo("Sucesso", f"Pedido #{numero_pedido} finalizado!\nCupons enviados para o Balcão e Cozinha.")
            
        # --- LIMPEZA E RESET COMPLETO DA TELA ---
        self.carrinho.itens.clear()
        self.carrinho.taxa_entrega = 0.0
        
        # Limpa os campos de texto do cliente
        self.txt_nome.delete(0, 'end')
        self.txt_tel.delete(0, 'end')
        self.txt_end.delete(0, 'end')
        self.combo_bairros_pdv.set("Selecione o Bairro")
        
        # Reseta o pagamento para o padrão (Pix)
        self.combo_pag.set("Pix")
        
        # Limpa e desativa o campo de troco com segurança
        self.txt_valor_recebido.delete(0, 'end')
        self.txt_valor_recebido.configure(state="disabled", fg_color="#2A2A2A")
        self.lbl_troco_resultado.configure(text="Troco: R$ 0.00", text_color="#FF9800")
        
        # Atualiza a interface gráfica do carrinho e valores
        if hasattr(self, 'atualizar_carrinho_tela'):
            self.atualizar_carrinho_tela()

    def abrir_historico_vendas(self):
        h_win = ctk.CTkToplevel(self.root)
        h_win.title("Histórico Consolidado de Vendas")
        h_win.geometry("980x600") # Aumentado levemente para acomodar o novo botão com folga
        h_win.grab_set()

        # --- PAINEL SUPERIOR: FILTROS E INDICADORES ---
        f_top = ctk.CTkFrame(h_win, height=85, fg_color=COR_BG_LATERAL, corner_radius=10)
        f_top.pack(fill="x", padx=15, pady=15)
        f_top.pack_propagate(False)

        # Filtro de Pagamento
        f_filtro = ctk.CTkFrame(f_top, fg_color="transparent")
        f_filtro.pack(side="left", padx=15, pady=10)
        
        ctk.CTkLabel(f_filtro, text="Filtrar por Pagamento:", font=("Arial", 11), text_color="#AAA").pack(anchor="w")
        cb_filtro_pag = ctk.CTkComboBox(f_filtro, values=["Todos", "Pix", "Cartão", "Dinheiro"], width=130, height=30, command=lambda _: carregar_vendas())
        cb_filtro_pag.set("Todos")
        cb_filtro_pag.pack(pady=2)

        # Indicadores Financeiros
        f_stats = ctk.CTkFrame(f_top, fg_color="transparent")
        f_stats.pack(side="right", fill="both", expand=True, padx=10)

        lbl_faturamento = ctk.CTkLabel(f_stats, text="Faturamento:\nR$ 0.00", font=("Arial", 14, "bold"), text_color="#4CAF50", justify="center")
        lbl_faturamento.pack(side="right", padx=15)

        lbl_ticket = ctk.CTkLabel(f_stats, text="Ticket Médio:\nR$ 0.00", font=("Arial", 13, "bold"), text_color="#00BCD4", justify="center")
        lbl_ticket.pack(side="right", padx=15)

        lbl_qtd_pedidos = ctk.CTkLabel(f_stats, text="Qtd Pedidos:\n0", font=("Arial", 13, "bold"), text_color="#FF9800", justify="center")
        lbl_qtd_pedidos.pack(side="right", padx=15)

        # --- ÁREA CENTRAL DOS CARDS ---
        scr_h = ctk.CTkScrollableFrame(h_win, fg_color=COR_BG_CENTRAL, corner_radius=10)
        scr_h.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # --- FUNÇÃO INTERNA PARA EXCLUIR PEDIDO ---
        def excluir_pedido(id_venda):
            if messagebox.askyesno("Confirmar Exclusão", "Tem certeza que deseja excluir permanentemente este pedido do histórico?"):
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("DELETE FROM vendas WHERE id = ?", (id_venda,))
                conn.commit()
                conn.close()
                carregar_vendas() # Recarrega a tela atualizando os totais automaticamente

        # --- NOVA FUNÇÃO INTERNA PARA EDITAR PEDIDO ---
        def editar_pedido(id_venda, cliente_nome, forma_pag):
            if messagebox.askyesno("Editar Pedido", "Isso jogará os dados do cliente de volta para o PDV e removerá o registro antigo para reabertura. Continuar?"):
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                
                # Busca as informações completas do cliente baseado no nome registrado na venda
                c.execute("SELECT telefone, endereco, bairro FROM clientes WHERE nome = ? LIMIT 1", (cliente_nome,))
                info_cliente = c.fetchone()
                
                # Exclui o histórico antigo para evitar duplicidade de faturamento
                c.execute("DELETE FROM vendas WHERE id = ?", (id_venda,))
                conn.commit()
                conn.close()
                
                # Preenche os campos de dados na interface principal
                self.txt_nome.delete(0, 'end')
                self.txt_nome.insert(0, cliente_nome)
                
                if info_cliente:
                    tel, end, bair = info_cliente
                    self.txt_tel.delete(0, 'end')
                    self.txt_tel.insert(0, str(tel))
                    self.txt_end.delete(0, 'end')
                    self.txt_end.insert(0, str(end))
                    self.combo_bairros_pdv.set(str(bair))
                
                # Seta a forma de pagamento que estava salva
                if "Pix" in forma_pag: self.combo_pag.set("Pix")
                elif "Dinheiro" in forma_pag: self.combo_pag.set("Dinheiro")
                elif "Crédito" in forma_pag or "Credito" in forma_pag: self.combo_pag.set("Cartão de Crédito")
                elif "Débito" in forma_pag or "Debito" in forma_pag: self.combo_pag.set("Cartão de Débito")
                
                # Fecha a janela do histórico e avisa o operador
                h_win.destroy()
                messagebox.showinfo("Pedido Reaberto", "Os dados do cliente foram recuperados!\n\nInsira novamente os itens desejados no carrinho e finalize o pedido normalmente.")
                
        # --- NOVA FUNÇÃO INTERNA PARA REIMPRIMIR SEGUNDA VIA ---
        # --- NOVA FUNÇÃO INTERNA PARA REIMPRIMIR SEGUNDA VIA ---
        def reimprimir_pedido(id_venda):
            try:
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                
                # Buscando os dados reais salvos na tabela vendas
                c.execute("SELECT data, cliente, total, pagamento, itens FROM vendas WHERE id = ?", (id_venda,))
                resultado = c.fetchone()
                
                if resultado:
                    data_hora, nome_c, total_venda, pag, itens_venda = resultado
                    
                    # Vamos buscar os dados de endereço do cliente para o cupom ficar completo
                    c.execute("SELECT telefone, endereco, bairro FROM clientes WHERE nome = ? LIMIT 1", (nome_c,))
                    info_cliente = c.fetchone()
                    conn.close()
                    
                    if info_cliente:
                        tel_c, end_c, bair_c = info_cliente
                    else:
                        tel_c, end_c, bair_c = "N/A", "Não encontrado", "N/A"
                    
                    # --- RECONSTRUINDO O SEU CUPOM EXATAMENTE COMO VOCÊ CONFIGUROU ---
                    cupom = []
                    cupom.append("------------------------------------------")
                    cupom.append("              RENSHU SUSHI                ")
                    cupom.append("        CNPJ: 00.000.000/0001-00          ") # <-- Seus dados reais aqui
                    cupom.append("    RUA EXEMPLO, 123 - BAIRRO - CIDADE    ") # <-- Seus dados reais aqui
                    cupom.append("------------------------------------------")
                    cupom.append("            CUPOM NAO FISCAL              ")
                    cupom.append("------------------------------------------")
                    cupom.append(f"Data/Hora: {data_hora}")
                    cupom.append(f"Cliente:   {nome_c[:30]}")
                    cupom.append(f"Telefone:  {tel_c}")
                    cupom.append(f"Endereco:  {end_c[:30]}")
                    cupom.append(f"Bairro:    {bair_c[:30]}")
                    cupom.append("------------------------------------------")
                    cupom.append("Qtd Item                         Total    ")
                    cupom.append("------------------------------------------")
                    
                   # Adiciona os itens salvos no cupom
                    # Tratando caso os itens venham separados por quebra de linha ou vírgula
                    linhas_itens = itens_venda.split("\n")
                    for linha in linhas_itens:
                        if linha.strip():
                            cupom.append(linha)
                            
                    cupom.append("------------------------------------------")
                    cupom.append(f"FORMA PAGTO: {pag}")
                    cupom.append(f"TOTAL DO PEDIDO: R$ {total_venda:.2f}")
                    cupom.append("------------------------------------------")
                    
                    texto_cupom = "\n".join(cupom)
                    
                    # --- ENVIANDO PARA A IMPRESSORA BALCÃO ---
                    import win32print
                    nome_impressora = "Balcao"
                    hPrinter = win32print.OpenPrinter(nome_impressora)
                    
                    try:
                        win32print.StartDocPrinter(hPrinter, 1, ("Segunda Via Pedido", None, "RAW"))
                        win32print.StartPagePrinter(hPrinter)
                        
                        # Cabeçalho indicando que é uma Segunda Via estilizada
                        win32print.WritePrinter(hPrinter, b"\x1b\x40\x1d\x21\x01\x1b\x61\x01")
                        win32print.WritePrinter(hPrinter, f"*** SEGUNDA VIA ***\n\n".encode("cp860"))
                        win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                        
                        # Conteúdo do cupom montado
                        win32print.WritePrinter(hPrinter, texto_cupom.encode("cp860", errors="ignore"))
                        
                        # Avanço de papel e corte
                        win32print.WritePrinter(hPrinter, b"\n\n\n\n\n\x1bi") 
                        
                        win32print.EndPagePrinter(hPrinter)
                        win32print.EndDocPrinter(hPrinter)
                        messagebox.showinfo("Sucesso", "Segunda via enviada para a impressora do BALCÃO!")
                    finally:
                        win32print.ClosePrinter(hPrinter)
                else:
                    conn.close()
                    messagebox.showwarning("Aviso", "Pedido não encontrado no banco de dados.")
                    
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao reimprimir: {e}")
                
        def carregar_vendas():
            for w in scr_h.winfo_children(): 
                w.destroy()
                
            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()
            
            filto_atual = cb_filtro_pag.get()
            
            if filto_atual == "Todos":
                c.execute("SELECT data, cliente, total, pagamento, itens, id FROM vendas ORDER BY id DESC")
            elif "Cart" in filto_atual:
                c.execute("SELECT data, cliente, total, pagamento, itens, id FROM vendas WHERE pagamento LIKE 'Cart%' ORDER BY id DESC")
            else:
                c.execute("SELECT data, cliente, total, pagamento, itens, id FROM vendas WHERE pagamento = ? ORDER BY id DESC", (filto_atual,))
                
            vendas = c.fetchall()
            conn.close()

            faturamento_acumulado = 0.0
            total_pedidos = len(vendas)

            for v in vendas:
                data, cliente, total, pag, itens, id_venda = v
                faturamento_acumulado += total

                if "| 🛵 Entrega: R$" in itens:
                    partes = itens.split("| 🛵 Entrega: R$")
                    texto_produtos = partes[0].strip()
                    try:
                        taxa_entrega = float(partes[1].replace(',', '.').strip())
                    except:
                        taxa_entrega = 0.0
                else:
                    texto_produtos = itens
                    taxa_entrega = 0.0

                subtotal = total - taxa_entrega

                # Card Principal do Pedido
                f_venda = ctk.CTkFrame(scr_h, fg_color=COR_CARD, border_width=1, border_color=COR_CARD_BORDA, corner_radius=10)
                f_venda.pack(fill="x", pady=6, padx=8)

                # Coluna da Esquerda: Info Gerais do Cliente
                f_info = ctk.CTkFrame(f_venda, fg_color="transparent")
                f_info.pack(side="left", fill="both", expand=True, padx=15, pady=10)
                
                txt_cliente = f"📅 {data}  -  👤 {cliente}"
                ctk.CTkLabel(f_info, text=txt_cliente, font=("Arial", 13, "bold"), text_color="#FFFFFF", justify="left").pack(anchor="w")
                
                txt_itens = f"🍣 Itens: {texto_produtos}\n💰 Subtotal: R$ {subtotal:.2f}  |  🛵 Taxa Entrega: R$ {taxa_entrega:.2f}"
                lbl_itens = ctk.CTkLabel(f_info, text=txt_itens, font=("Arial", 11), text_color="#BBBBBB", justify="left", wraplength=450)
                lbl_itens.pack(anchor="w", pady=(4, 0))

                # Coluna da Direita: Valores Totais e Painel de Ações
                f_valores = ctk.CTkFrame(f_venda, fg_color="transparent")
                f_valores.pack(side="right", padx=15, pady=10)
                
                ctk.CTkLabel(f_valores, text=f"Total: R$ {total:.2f}", font=("Consolas", 15, "bold"), text_color=COR_PRIMARY, justify="right").pack(anchor="e")
                ctk.CTkLabel(f_valores, text=f"💳 {pag}", font=("Arial", 11), text_color="#888888", justify="right").pack(anchor="e", pady=(0, 5))
                
                # Container para colocar os botões lado a lado de forma simétrica
                f_botoes_acao = ctk.CTkFrame(f_valores, fg_color="transparent")
                f_botoes_acao.pack(anchor="e")

                # NOVO BOTÃO: Imprimir Segunda Via
                btn_print = ctk.CTkButton(
                    f_botoes_acao, 
                    text="🖨️ Imprimir", 
                    fg_color="#00BCD4", 
                    hover_color="#0097A7", 
                    width=75, 
                    height=22, 
                    font=("Arial", 10, "bold"), 
                    corner_radius=5, 
                    command=lambda idx=id_venda: reimprimir_pedido(idx)
                )
                btn_print.pack(side="left", padx=3)

                # BOTÃO: Editar Pedido
                btn_edit = ctk.CTkButton(f_botoes_acao, text="✏️ Editar", fg_color="#FFA000", hover_color="#F57C00", width=75, height=22, font=("Arial", 10, "bold"), corner_radius=5, command=lambda idx=id_venda, cl=cliente, pg=pag: editar_pedido(idx, cl, pg))
                btn_edit.pack(side="left", padx=3)

                # BOTÃO: Excluir Pedido
                btn_del = ctk.CTkButton(f_botoes_acao, text="❌ Excluir", fg_color="#D32F2F", hover_color="#B71C1C", width=75, height=22, font=("Arial", 10, "bold"), corner_radius=5, command=lambda idx=id_venda: excluir_pedido(idx))
                btn_del.pack(side="left", padx=3)

            ticket_medio = faturamento_acumulado / total_pedidos if total_pedidos > 0 else 0.0

            lbl_faturamento.configure(text=f"Faturamento:\nR$ {faturamento_acumulado:.2f}")
            lbl_qtd_pedidos.configure(text=f"Qtd Pedidos:\n{total_pedidos}")
            lbl_ticket.configure(text=f"Ticket Médio:\nR$ {ticket_medio:.2f}")

    def add_carrinho(self, pid, nome, preco):
        self.carrinho.adicionar(pid, nome, preco)
        self.atualizar_carrinho_tela()

    def remover_item(self, pid):
        # Remove o item usando o método do seu carrinho e atualiza a tela
        if hasattr(self.carrinho, 'remover'):
            self.carrinho.remover(pid)
        elif hasattr(self.carrinho, 'itens') and pid in self.carrinho.itens:
            del self.carrinho.itens[pid]
        self.atualizar_carrinho_tela()

    def atualizar_carrinho_tela(self):
        for w in self.scroll_carrinho.winfo_children(): 
            w.destroy()
            
        for pid, info in self.carrinho.itens.items():
            f = ctk.CTkFrame(self.scroll_carrinho, fg_color="transparent")
            f.pack(fill="x", pady=3, padx=5)
            
            ctk.CTkLabel(f, text=f"{info['qtd']}x {info['nome']}", font=("Arial", 12, "bold"), text_color="#FFF").pack(side="left")
            
            v_total = info['preco'] * info['qtd']
            ctk.CTkLabel(f, text=f"R$ {v_total:.2f}", font=("Consolas", 12), text_color="#888").pack(side="right", padx=(0, 35))
            
            ctk.CTkButton(f, text="❌", width=22, height=22, fg_color="transparent", text_color="#F44336", hover_color="#2A1414", font=("Arial", 10, "bold"), command=lambda id_p=pid: self.remover_item(id_p)).place(relx=1.0, x=-5, rely=0.5, anchor="e")
            
        # Pega os totais brutos do carrinho (apenas os produtos)
        sub, _ = self.carrinho.obter_totais()
        
        # Garante que a taxa de entrega seja um número válido
        taxa = float(self.carrinho.taxa_entrega) if hasattr(self.carrinho, 'taxa_entrega') else 0.0
        
        # CALCULA O TOTAL SOMANDO A TAXA DIRETAMENTE AQUI
        total_com_taxa = sub + taxa
        
        # Atualiza os componentes corretos da interface
        self.lbl_sub.configure(text=f"Subtotal: R$ {sub:.2f}")
        self.lbl_tx.configure(text=f"Taxa de Entrega: R$ {taxa:.2f}")
        self.lbl_tot.configure(text=f"TOTAL: R$ {total_com_taxa:.2f}")

    def atualizar_dropdown_bairros_pdv(self):
        # Busca os bairros direto do banco para garantir que a lista esteja atualizada
        try:
            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()
            c.execute("SELECT bairro FROM taxas_entrega ORDER BY bairro ASC")
            lista = [b[0] for b in c.fetchall()]
            conn.close()
        except:
            lista = []

        if lista: 
            # Recarrega os valores e força o gatilho 'command' para o clique funcionar
            self.combo_bairros_pdv.configure(values=lista, command=self.ao_selecionar_bairro_pdv)
        else:
            self.combo_bairros_pdv.configure(values=["Nenhum bairro cadastrado"], command=self.ao_selecionar_bairro_pdv)
            
    def ao_selecionar_bairro_pdv(self, e=None):
        # 1. Pega o texto selecionado na caixinha
        bairro_selecionado = e if isinstance(e, str) else self.combo_bairros_pdv.get()

        if not bairro_selecionado or bairro_selecionado in ["Selecione o Bairro", "Nenhum bairro cadastrado"]:
            self.carrinho.taxa_entrega = 0.0
            self.atualizar_carrinho_tela()
            return

        # 2. Busca o valor exato no banco de dados
        conn = sqlite3.connect("sistema_delivery.db")
        c = conn.cursor()
        c.execute("SELECT valor FROM taxas_entrega WHERE LOWER(TRIM(bairro)) = LOWER(TRIM(?))", (bairro_selecionado.strip(),))
        res = c.fetchone()
        conn.close()

        # 3. Aloca a taxa encontrada no objeto do carrinho
        if res:
            self.carrinho.taxa_entrega = float(res[0])
            print(f"🎉 BANCO ENCONTROU: {bairro_selecionado} = R$ {res[0]}")
        else:
            self.carrinho.taxa_entrega = 0.0
            print(f"❌ BANCO NÃO ENCONTROU O BAIRRO: '{bairro_selecionado}'")

        # 4. Atualiza a tela e recalcula o TOTAL de forma síncrona
        self.atualizar_carrinho_tela()

    
    

    def buscar_cliente_automatico(self, e):
        tel = self.txt_tel.get()
        if tel:
            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()
            c.execute("SELECT nome, endereco, bairro FROM clientes WHERE telefone=?", (tel,))
            res = c.fetchone()
            if res:
                self.txt_nome.delete(0, 'end')
                self.txt_nome.insert(0, res[0])
                self.txt_end.delete(0, 'end')
                self.txt_end.insert(0, res[1])
                if res[2]: 
                    self.combo_bairros_pdv.set(res[2])
                    self.ao_selecionar_bairro_pdv(res[2])
            conn.close()

    def abrir_gerenciador_clientes(self):
        # Janela do Gerenciador de Clientes
        cl_win = ctk.CTkToplevel(self.root)
        cl_win.title("Gerenciador de Clientes - Renshu Sushi")
        cl_win.geometry("900(x)550")
        cl_win.grab_set()

        # Variável para controlar se estamos editando um cliente existente
        self.telefone_cliente_em_edicao = None

        # --- PAINEL DA ESQUERDA: FORMULÁRIO (CADASTRO / EDIÇÃO) ---
        f_esq = ctk.CTkFrame(cl_win, width=320, fg_color=COR_BG_LATERAL, corner_radius=10)
        f_esq.pack(side="left", fill="both", padx=15, pady=15)
        f_esq.pack_propagate(False)

        lbl_titulo_form = ctk.CTkLabel(f_esq, text="👤 Cadastrar Novo Cliente", font=("Arial", 16, "bold"), text_color="#FFFFFF")
        lbl_titulo_form.pack(pady=15)

        # Campos do Formulário
        ctk.CTkLabel(f_esq, text="Telefone (WhatsApp):", font=("Arial", 11), text_color="#AAA").pack(anchor="w", padx=15)
        txt_cl_tel = ctk.CTkEntry(f_esq, placeholder_text="Ex: 11999999999", height=30)
        txt_cl_tel.pack(fill="x", padx=15, pady=(2, 10))

        ctk.CTkLabel(f_esq, text="Nome do Cliente:", font=("Arial", 11), text_color="#AAA").pack(anchor="w", padx=15)
        txt_cl_nome = ctk.CTkEntry(f_esq, placeholder_text="Nome Completo", height=30)
        txt_cl_nome.pack(fill="x", padx=15, pady=(2, 10))

        ctk.CTkLabel(f_esq, text="Endereço (Rua, Número, Apt):", font=("Arial", 11), text_color="#AAA").pack(anchor="w", padx=15)
        txt_cl_end = ctk.CTkEntry(f_esq, placeholder_text="Ex: Av. Principal, 123", height=30)
        txt_cl_end.pack(fill="x", padx=15, pady=(2, 10))

        ctk.CTkLabel(f_esq, text="Bairro:", font=("Arial", 11), text_color="#AAA").pack(anchor="w", padx=15)
        # Copia os mesmos bairros que você já usa no combo_bairros_pdv
        txt_cl_bair = ctk.CTkComboBox(f_esq, values=self.combo_bairros_pdv.cget("values"), height=30)
        txt_cl_bair.pack(fill="x", padx=15, pady=(2, 15))

        # --- FUNÇÃO PARA SALVAR / ATUALIZAR ---
        def salvar_cliente():
            tel = txt_cl_tel.get().strip()
            nome = txt_cl_nome.get().strip()
            end = txt_cl_end.get().strip()
            bair = txt_cl_bair.get().strip()

            if not tel or not nome:
                messagebox.showwarning("Campos Obrigatórios", "Telefone e Nome são obrigatórios!")
                return

            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()

            if self.telefone_cliente_em_edicao:
                # Se o telefone antigo mudou ou estamos salvando uma alteração
                c.execute("""
                    UPDATE clientes 
                    SET telefone=?, nome=?, endereco=?, bairro=? 
                    WHERE telefone=?
                """, (tel, nome, end, bair, self.telefone_cliente_em_edicao))
                msg = "Cliente atualizado com sucesso!"
            else:
                # Cadastro Novo
                try:
                    c.execute("""
                        INSERT INTO clientes (telefone, nome, endereco, bairro) 
                        VALUES (?,?,?,?)
                    """, (tel, nome, end, bair))
                    msg = "Cliente cadastrado com sucesso!"
                except sqlite3.IntegrityError:
                    messagebox.showerror("Erro", "Este número de telefone já está cadastrado!")
                    conn.close()
                    return

            conn.commit()
            conn.close()
            
            messagebox.showinfo("Sucesso", msg)
            limpar_formulario()
            carregar_clientes()

        def limpar_formulario():
            self.telefone_cliente_em_edicao = None
            txt_cl_tel.delete(0, 'end')
            txt_cl_nome.delete(0, 'end')
            txt_cl_end.delete(0, 'end')
            txt_cl_tel.configure(state="normal") # Reativa o campo caso estivesse bloqueado
            lbl_titulo_form.configure(text="👤 Cadastrar Novo Cliente", text_color="#FFFFFF")
            btn_salvar.configure(text="💾 Gravar Cliente", fg_color=COR_PRIMARY)

        btn_salvar = ctk.CTkButton(f_esq, text="💾 Gravar Cliente", fg_color=COR_PRIMARY, hover_color=COR_PRIMARY_HOVER, height=35, font=("Arial", 12, "bold"), command=salvar_cliente)
        btn_salvar.pack(fill="x", padx=15, pady=5)

        ctk.CTkButton(f_esq, text="🧹 Limpar / Novo", fg_color="#555555", hover_color="#444444", height=30, command=limpar_formulario).pack(fill="x", padx=15, pady=5)


        # --- PAINEL DA DIREITA: BUSCA E LISTAGEM ---
        f_dir = ctk.CTkFrame(cl_win, fg_color=COR_BG_CENTRAL, corner_radius=10)
        f_dir.pack(side="right", fill="both", expand=True, padx=(0, 15), pady=15)

        # Barra de Pesquisa
        f_busca = ctk.CTkFrame(f_dir, fg_color="transparent")
        f_busca.pack(fill="x", padx=15, pady=15)

        txt_busca = ctk.CTkEntry(f_busca, placeholder_text="🔎 Buscar por Nome ou Telefone...", height=35)
        txt_busca.pack(side="left", fill="x", expand=True, padx=(0, 10))
        txt_busca.bind("<KeyRelease>", lambda e: carregar_clientes(txt_busca.get()))

        # Área com Scroll para listar os clientes
        scr_cl = ctk.CTkScrollableFrame(f_dir, fg_color="transparent")
        scr_cl.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # --- FUNÇÕES DE LISTAGEM E EDIÇÃO ---
        # --- FUNÇÕES DE LISTAGEM, EDIÇÃO E EXCLUSÃO ---
        def preparar_edicao(cliente_dados):
            tel, nome, end, bair = cliente_dados
            self.telefone_cliente_em_edicao = tel
            
            # Preenche os campos do formulário
            txt_cl_tel.delete(0, 'end'); txt_cl_tel.insert(0, tel)
            txt_cl_nome.delete(0, 'end'); txt_cl_nome.insert(0, nome)
            txt_cl_end.delete(0, 'end'); txt_cl_end.insert(0, end)
            txt_cl_bair.set(bair)
            
            # Modifica o visual do formulário para modo Edição
            lbl_titulo_form.configure(text="✏️ Editando Cliente", text_color="#FF9800")
            btn_salvar.configure(text="🔄 Atualizar Dados", fg_color="#FF9800")

        def excluir_cliente(telefone_cl, nome_cl):
            if messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir permanentemente o cliente '{nome_cl}'?"):
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("DELETE FROM clientes WHERE telefone = ?", (telefone_cl,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Sucesso", "Cliente removido com sucesso!")
                limpar_formulario()
                carregar_clientes(txt_busca.get()) # Recarrega mantendo o filtro atual

        def carregar_clientes(termo_busca=""):
            for w in scr_cl.winfo_children():
                w.destroy()

            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()

            if termo_busca:
                c.execute("""
                    SELECT telefone, nome, endereco, bairro FROM clientes 
                    WHERE nome LIKE ? OR telefone LIKE ?
                    ORDER BY nome ASC
                """, (f"%{termo_busca}%", f"%{termo_busca}%"))
            else:
                c.execute("SELECT telefone, nome, endereco, bairro FROM clientes ORDER BY nome ASC")

            lista_clientes = c.fetchall()
            conn.close()

            for cl in lista_clientes:
                tel, nome, end, bair = cl

                # Card do Cliente
                f_card = ctk.CTkFrame(scr_cl, fg_color=COR_CARD, border_width=1, border_color=COR_CARD_BORDA, corner_radius=8)
                f_card.pack(fill="x", pady=4, padx=5)

                f_info = ctk.CTkFrame(f_card, fg_color="transparent")
                f_info.pack(side="left", fill="both", expand=True, padx=10, pady=8)

                ctk.CTkLabel(f_info, text=f"👤 {nome}", font=("Arial", 12, "bold"), text_color="#FFF").pack(anchor="w")
                ctk.CTkLabel(f_info, text=f"📞 Tel: {tel}  |  📍 Bairro: {bair}", font=("Arial", 11), text_color="#AAA").pack(anchor="w")
                ctk.CTkLabel(f_info, text=f"🏠 End: {end}", font=("Arial", 11), text_color="#888", justify="left").pack(anchor="w")

                # Coluna lateral para os botões de Ação
                f_botoes = ctk.CTkFrame(f_card, fg_color="transparent")
                f_botoes.pack(side="right", padx=10, pady=5)

                # Botão Editar
                btn_edit = ctk.CTkButton(f_botoes, text="✏️ Editar", fg_color="#333", hover_color="#444", width=75, height=22, font=("Arial", 10, "bold"), command=lambda dados=cl: preparar_edicao(dados))
                btn_edit.pack(pady=2)

                # Botão Excluir (Abaixo do editar)
                btn_excluir = ctk.CTkButton(f_botoes, text="🗑️ Excluir", fg_color="#D32F2F", hover_color="#B71C1C", width=75, height=22, font=("Arial", 10, "bold"), command=lambda t=tel, n=nome: excluir_cliente(t, n))
                btn_excluir.pack(pady=2)

        # Inicializa a lista
        carregar_clientes()

    def abrir_gerenciador_taxas(self):
        t_win = ctk.CTkToplevel(self.root)
        t_win.title("Tabela de Taxas por Bairro")
        t_win.geometry("420x320")
        t_win.grab_set()
        
        txt_b = ctk.CTkEntry(t_win, placeholder_text="Nome do Bairro", height=35)
        txt_b.pack(fill="x", padx=25, pady=8)
        
        txt_v = ctk.CTkEntry(t_win, placeholder_text="Valor da Taxa (Ex: 7.00)", height=35)
        txt_v.pack(fill="x", padx=25, pady=8)
        
        def salvar():
            bairro_nome = txt_b.get().strip()
            if not bairro_nome:
                return
            
            try:
                valor_taxa = float(txt_v.get().replace(",", "."))
            except ValueError:
                return
                
            conn = sqlite3.connect("sistema_delivery.db")
            c = conn.cursor()
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS taxas_entrega (
                    bairro TEXT PRIMARY KEY,
                    valor REAL
                )
            """)
            
            c.execute("INSERT OR REPLACE INTO taxas_entrega (bairro, valor) VALUES (?,?)", (bairro_nome, valor_taxa))
            conn.commit()
            
            # --- ATUALIZAÇÃO FORÇADA DA CAIXINHA DIRETAMENTE AQUI ---
            c.execute("SELECT bairro FROM taxas_entrega ORDER BY bairro ASC")
            todos_bairros = [row[0] for row in c.fetchall()]
            conn.close()
            
            # Atualiza os valores visuais do menu suspenso para incluir o novo bairro na mesma hora
            if hasattr(self, 'combo_bairros_pdv'):
                self.combo_bairros_pdv.configure(values=todos_bairros)
            
            t_win.destroy()
            
            # Se a sua função antiga existir, executa ela por garantia
            if hasattr(self, 'atualizar_dropdown_bairros_pdv'):
                self.atualizar_dropdown_bairros_pdv()
            
        ctk.CTkButton(t_win, text="💾 Salvar Configuração de Taxa", fg_color=COR_INFO, hover_color="#0A3678", height=40, font=("Arial", 13, "bold"), command=salvar).pack(pady=20, padx=25, fill="x")

if __name__ == "__main__":
    root = ctk.CTk()
    app = AppPDV(root)
    
    # --- ATIVA O RELÓGIO DE ALERTAS DO TOTEM AQUI ---
    verificar_pedidos_totem(root)
    
    root.mainloop()

    # --- FUNÇÃO DO FECHAMENTO E IMPRESSÃO ---
    def abrir_fechamento_caixa_interno():
            import datetime
            import sqlite3
            from tkinter import messagebox
            hoje = datetime.datetime.now().strftime("%d/%m/%Y")

            caixa_win = ctk.CTkToplevel(None)
            caixa_win.title("Fechamento de Caixa - Renshu Sushi")
            caixa_win.geometry("500x670") 
            caixa_win.grab_set()

            # Função que calcula os valores (colocada em uma função interna para podermos atualizar a tela)
            def carregar_dados_caixa():
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                c.execute("SELECT total, pagamento FROM vendas WHERE data LIKE ?", (f"{hoje}%",))
                vendas_hoje = c.fetchall()
                conn.close()

                total_geral = 0.0
                totais_por_pag = {"Pix": 0.0, "Cartão de Crédito": 0.0, "Cartão de Débito": 0.0, "Dinheiro": 0.0}
                qtd_pedidos = len(vendas_hoje)

                for total, pagamento in vendas_hoje:
                    total_geral += total
                    
                    # Normaliza as formas de pagamento vindas do Totem para somar no caixa unificado
                    forma_limpa = pagamento
                    if "(Totem)" in pagamento:
                        forma_limpa = pagamento.replace(" (Totem)", "").strip()

                    if forma_limpa in totais_por_pag:
                        totais_por_pag[forma_limpa] += total
                    else:
                        totais_por_pag[forma_limpa] = totais_por_pag.get(forma_limpa, 0.0) + total

                ticket_medio = total_geral / qtd_pedidos if qtd_pedidos > 0 else 0.0
                return total_geral, totais_por_pag, qtd_pedidos, ticket_medio

            total_geral, totais_por_pag, qtd_pedidos, ticket_medio = carregar_dados_caixa()

            ctk.CTkLabel(caixa_win, text=f"📊 Fechamento de Caixa ({hoje})", font=("Segoe UI", 20, "bold"), text_color="#FFFFFF").pack(pady=20)

            # --- CARD DO TOTAL ---
            f_total = ctk.CTkFrame(caixa_win, fg_color=COR_PRIMARY, corner_radius=12, height=80)
            f_total.pack(fill="x", padx=30, pady=10)
            f_total.pack_propagate(False)
            
            ctk.CTkLabel(f_total, text="FATURAMENTO TOTAL DO DIA", font=("Segoe UI", 11, "bold"), text_color="#FFFFFF").pack(pady=(12,0))
            lbl_total_dinamico = ctk.CTkLabel(f_total, text=f"R$ {total_geral:.2f}", font=("Segoe UI", 24, "bold"), text_color="#FFFFFF")
            lbl_total_dinamico.pack()

            # --- DETALHES ---
            f_detalhes = ctk.CTkFrame(caixa_win, fg_color=COR_CARD, corner_radius=12)
            f_detalhes.pack(fill="both", expand=True, padx=30, pady=15)

            ctk.CTkLabel(f_detalhes, text="Entradas por Tipo:", font=("Segoe UI", 14, "bold"), text_color="#FFF").pack(anchor="w", padx=20, pady=(15, 10))

            # Guardar referências das labels para atualizar se limpar
            labels_valores = {}
            for fpago, valor in totais_por_pag.items():
                f_linha = ctk.CTkFrame(f_detalhes, fg_color="transparent")
                f_linha.pack(fill="x", padx=20, pady=4)
                ctk.CTkLabel(f_linha, text=f"🔹 {fpago}:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
                lbl_val = ctk.CTkLabel(f_linha, text=f"R$ {valor:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF")
                lbl_val.pack(side="right")
                labels_valores[fpago] = lbl_val

            ctk.CTkLabel(f_detalhes, text="--------------------------------------------------", text_color="#444").pack(pady=5)

            f_estat_1 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
            f_estat_1.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(f_estat_1, text="Total de Pedidos:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
            lbl_qtd = ctk.CTkLabel(f_estat_1, text=str(qtd_pedidos), font=("Segoe UI", 13, "bold"), text_color="#FFF")
            lbl_qtd.pack(side="right")

            f_estat_2 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
            f_estat_2.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(f_estat_2, text="Ticket Médio p/ Pedido:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
            lbl_ticket = ctk.CTkLabel(f_estat_2, text=f"R$ {ticket_medio:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF")
            lbl_ticket.pack(side="right")

            # --- FUNÇÃO EXCLUSIVA PARA LIMPAR OS TESTES ---
            def limpar_vendas_do_dia():
                resposta = messagebox.askyesno("⚠️ Atenção", "Você tem certeza que deseja APAGAR todas as vendas de hoje?\nIsso vai zerar o caixa atual!")
                if resposta:
                    try:
                        conn = sqlite3.connect("sistema_delivery.db")
                        c = conn.cursor()
                        c.execute("DELETE FROM vendas WHERE data LIKE ?", (f"{hoje}%",))
                        conn.commit()
                        conn.close()
                        
                        lbl_total_dinamico.configure(text="R$ 0.00")
                        lbl_qtd.configure(text="0")
                        lbl_ticket.configure(text="R$ 0.00")
                        
                        try:
                            for fpago in labels_valores:
                                labels_valores[fpago].configure(text="R$ 0.00")
                        except:
                            pass
                            
                        messagebox.showinfo("Sucesso", "O caixa de hoje foi zerado!")
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro ao limpar banco: {e}")

            # --- CÓDIGO DA IMPRESSÃO ---
            def imprimir_relatorio_caixa():
                t_geral, t_pag, q_pedidos, t_medio = carregar_dados_caixa()
                cupom = []
                cupom.append("------------------------------------------")
                cupom.append("              RENSHU SUSHI                ")
                cupom.append("          FECHAMENTO DE CAIXA             ")
                cupom.append("------------------------------------------")
                cupom.append(f"Data de Referencia: {hoje}")
                cupom.append(f"Impresso em:        {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
                cupom.append("------------------------------------------")
                cupom.append("RESUMO DE ENTRADAS:")
                cupom.append("------------------------------------------")
                for fpago, valor in t_pag.items():
                    cupom.append(f"{fpago:<25} R$ {valor:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append(f"Qtd Pedidos:                         {q_pedidos:>5}")
                cupom.append(f"Ticket Medio:                 R$ {t_medio:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append(f"FATURAMENTO TOTAL:            R$ {t_geral:>10.2f}")
                cupom.append("------------------------------------------")
                cupom.append("\n\nConferido por: _________________________\n\n\n\n\n")
                
                texto_cupom = "\n".join(cupom)
                try:
                        import win32print
                        lista_impre = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                        
                        if "Balcao" in lista_impre:
                            nome_impressora = "Balcao"
                        elif "Balcão" in lista_impre:
                            nome_impressora = "Balcão"
                        else:
                            nome_impressora = win32print.GetDefaultPrinter()
                        
                        hPrinter = win32print.OpenPrinter(nome_impressora)
                        try:
                            win32print.StartDocPrinter(hPrinter, 1, ("Fechamento Caixa", None, "RAW"))
                            win32print.StartPagePrinter(hPrinter)
                            win32print.WritePrinter(hPrinter, b"\x1b\x40\x1d\x21\x01\x1b\x61\x01")
                            win32print.WritePrinter(hPrinter, f"FECHAMENTO X\n\n".encode("cp860"))
                            win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                            win32print.WritePrinter(hPrinter, texto_cupom.encode("cp860", errors="ignore"))
                            win32print.EndPagePrinter(hPrinter)
                            win32print.EndDocPrinter(hPrinter)
                        finally:
                            win32print.ClosePrinter(hPrinter)
                        messagebox.showinfo("Sucesso", f"Relatório enviado para: {nome_impressora}")
                except Exception as e:
                     messagebox.showerror("Erro", f"Falha ao mandar para impressora: {e}")

            btn_print = ctk.CTkButton(caixa_win, text="🖨️ Imprimir Fechamento", height=42, fg_color="#4CAF50", hover_color="#388E3C", font=("Segoe UI", 13, "bold"), corner_radius=12, command=imprimir_relatorio_caixa)
            btn_print.pack(fill="x", padx=30, pady=(10, 5))

            btn_limpar = ctk.CTkButton(caixa_win, text="🗑️ Limpar Testes / Zerar Dia", height=42, fg_color="#D32F2F", hover_color="#C62828", font=("Segoe UI", 13, "bold"), corner_radius=12, command=limpar_vendas_do_dia)
            btn_limpar.pack(fill="x", padx=30, pady=(5, 20))


    def abrir_fechamento_caixa(self):
        import datetime
        import sqlite3
        from tkinter import messagebox
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")

        caixa_win = ctk.CTkToplevel(self.root)
        caixa_win.title("TESTE DO CAIXA NOVO")
        caixa_win.geometry("500x600")
        caixa_win.grab_set()

        # --- BUSCA OS DADOS NO BANCO ---
        conn = sqlite3.connect("sistema_delivery.db")
        c = conn.cursor()
        c.execute("SELECT total, pagamento FROM vendas WHERE data LIKE ?", (f"{hoje}%",))
        vendas_hoje = c.fetchall()
        conn.close()

        total_geral = 0.0
        totais_por_pag = {"Pix": 0.0, "Cartão de Crédito": 0.0, "Cartão de Débito": 0.0, "Dinheiro": 0.0}
        qtd_pedidos = len(vendas_hoje)

        for total, pagamento in vendas_hoje:
            total_geral += total
            
            # Normaliza as formas de pagamento vindas do Totem nesta segunda janela também
            forma_limpa = pagamento
            if "(Totem)" in pagamento:
                forma_limpa = pagamento.replace(" (Totem)", "").strip()

            if forma_limpa in totais_por_pag:
                totais_por_pag[forma_limpa] += total
            else:
                totais_por_pag[forma_limpa] = totais_por_pag.get(forma_limpa, 0.0) + total

        ticket_medio = total_geral / qtd_pedidos if qtd_pedidos > 0 else 0.0

        # --- INTERFACE GRÁFICA ---
        ctk.CTkLabel(caixa_win, text=f"📊 Fechamento de Caixa ({hoje})", font=("Segoe UI", 20, "bold"), text_color="#FFFFFF").pack(pady=20)

        f_total = ctk.CTkFrame(caixa_win, fg_color=COR_PRIMARY, corner_radius=12, height=80)
        f_total.pack(fill="x", padx=30, pady=10)
        f_total.pack_propagate(False)
        
        ctk.CTkLabel(f_total, text="FATURAMENTO TOTAL DO DIA", font=("Segoe UI", 11, "bold"), text_color="#FFFFFF").pack(pady=(12,0))
        ctk.CTkLabel(f_total, text=f"R$ {total_geral:.2f}", font=("Segoe UI", 24, "bold"), text_color="#FFFFFF").pack()

        f_detalhes = ctk.CTkFrame(caixa_win, fg_color=COR_CARD, corner_radius=12)
        f_detalhes.pack(fill="both", expand=True, padx=30, pady=15)

        ctk.CTkLabel(f_detalhes, text="Entradas por Tipo:", font=("Segoe UI", 14, "bold"), text_color="#FFF").pack(anchor="w", padx=20, pady=(15, 10))

        for fpago, valor in totais_por_pag.items():
            f_linha = ctk.CTkFrame(f_detalhes, fg_color="transparent")
            f_linha.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(f_linha, text=f"🔹 {fpago}:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
            ctk.CTkLabel(f_linha, text=f"R$ {valor:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF").pack(side="right")

        ctk.CTkLabel(f_detalhes, text="--------------------------------------------------", text_color="#444").pack(pady=10)

        f_estat_1 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
        f_estat_1.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(f_estat_1, text="Total de Pedidos:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
        ctk.CTkLabel(f_estat_1, text=str(qtd_pedidos), font=("Segoe UI", 13, "bold"), text_color="#FFF").pack(side="right")

        f_estat_2 = ctk.CTkFrame(f_detalhes, fg_color="transparent")
        f_estat_2.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(f_estat_2, text="Ticket Médio p/ Pedido:", font=("Segoe UI", 12), text_color="#AAA").pack(side="left")
        ctk.CTkLabel(f_estat_2, text=f"R$ {ticket_medio:.2f}", font=("Segoe UI", 13, "bold"), text_color="#FFF").pack(side="right")

        def imprimir_relatorio_caixa():
            cupom = []
            cupom.append("------------------------------------------")
            cupom.append("              RENSHU SUSHI                ")
            cupom.append("          FECHAMENTO DE CAIXA             ")
            cupom.append("------------------------------------------")
            cupom.append(f"Data de Referencia: {hoje}")
            cupom.append(f"Impresso em:        {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
            cupom.append("------------------------------------------")
            cupom.append("RESUMO DE ENTRADAS:")
            cupom.append("------------------------------------------")
            for fpago, valor in totais_por_pag.items():
                cupom.append(f"{fpago:<25} R$ {valor:>10.2f}")
            cupom.append("------------------------------------------")
            cupom.append(f"Qtd Pedidos:                         {qtd_pedidos:>5}")
            cupom.append(f"Ticket Medio:                 R$ {ticket_medio:>10.2f}")
            cupom.append("------------------------------------------")
            cupom.append(f"FATURAMENTO TOTAL:            R$ {total_geral:>10.2f}")
            cupom.append("------------------------------------------")
            cupom.append("\n\nConferido por: _________________________\n\n\n\n\n")
            
            texto_cupom = "\n".join(cupom)
            
            try:
                import win32print
                nome_impressora = win32print.GetDefaultPrinter()
                hPrinter = win32print.OpenPrinter(nome_impressora)
                try:
                    win32print.StartDocPrinter(hPrinter, 1, ("Fechamento Caixa", None, "RAW"))
                    win32print.StartPagePrinter(hPrinter)
                    win32print.WritePrinter(hPrinter, b"\x1b\x40\x1d\x21\x01\x1b\x61\x01")
                    win32print.WritePrinter(hPrinter, f"FECHAMENTO X\n\n".encode("cp860"))
                    win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                    win32print.WritePrinter(hPrinter, texto_cupom.encode("cp860", errors="ignore"))
                    win32print.EndPagePrinter(hPrinter)
                    win32print.EndDocPrinter(hPrinter)
                finally:
                    win32print.ClosePrinter(hPrinter)
                messagebox.showinfo("Sucesso", "Fechamento impresso!")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao mandar para impressora: {e}")

        btn_print = ctk.CTkButton(caixa_win, text="🖨️ Imprimir Fechamento", height=45, fg_color="#4CAF50", hover_color="#388E3C", font=("Segoe UI", 14, "bold"), corner_radius=12, command=imprimir_relatorio_caixa)
        btn_print.pack(fill="x", padx=30, pady=(5, 25))

