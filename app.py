import customtkinter as ctk
import sqlite3
from tkinter import messagebox

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def inicializar_banco():
    conn = sqlite3.connect("sistema_delivery.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, descricao TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (telefone TEXT PRIMARY KEY, nome TEXT NOT NULL, endereco TEXT NOT NULL, bairro TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS taxas_entrega (bairro TEXT PRIMARY KEY, valor REAL NOT NULL)")
    conn.commit(); conn.close()

def listar_produtos():
    conn = sqlite3.connect("sistema_delivery.db"); cursor = conn.cursor()
    cursor.execute("SELECT id, nome, preco, descricao FROM produtos")
    dados = cursor.fetchall(); conn.close()
    return dados

def listar_taxas():
    conn = sqlite3.connect("sistema_delivery.db"); cursor = conn.cursor()
    cursor.execute("SELECT bairro, valor FROM taxas_entrega ORDER BY bairro ASC")
    dados = cursor.fetchall(); conn.close()
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

class AppPDV:
    def __init__(self, root):
        self.root = root
        self.root.title("DELIV_RED - Painel PDV")
        self.root.geometry("1100x700")
        inicializar_banco()
        self.carrinho = CarrinhoDeCompras()
        self.configurar_layout()
        
    def configurar_layout(self):
        self.menu_lateral = ctk.CTkFrame(self.root, width=200, fg_color="#1A1A1A", corner_radius=0)
        self.menu_lateral.pack(side="left", fill="y")
        ctk.CTkLabel(self.menu_lateral, text="🚀 DELIV_RED", font=("Arial", 22, "bold"), text_color="#D32F2F").pack(pady=20)
        ctk.CTkButton(self.menu_lateral, text="🍔 Cadastrar Itens", fg_color="#D32F2F", command=self.abrir_gerenciador).pack(pady=10, padx=15, fill="x")
        ctk.CTkButton(self.menu_lateral, text="👥 Cadastrar Clientes", fg_color="#2E7D32", command=self.abrir_gerenciador_clientes).pack(pady=5, padx=15, fill="x")
        ctk.CTkButton(self.menu_lateral, text="📍 Configurar Taxas", fg_color="#1976D2", command=self.abrir_gerenciador_taxas).pack(pady=5, padx=15, fill="x")
        
        self.area_central = ctk.CTkFrame(self.root, fg_color="#121212", corner_radius=0)
        self.area_central.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(self.area_central, text="🍔 Cardápio Disponível", font=("Arial", 20, "bold")).pack(anchor="w", pady=10, padx=10)
        self.scroll_vitrine = ctk.CTkScrollableFrame(self.area_central, fg_color="transparent")
        self.scroll_vitrine.pack(fill="both", expand=True)
        self.atualizar_vitrine_tela()

        self.aba_direita = ctk.CTkFrame(self.root, width=400, fg_color="#1A1A1A", corner_radius=0)
        self.aba_direita.pack(side="right", fill="y")
        ctk.CTkLabel(self.aba_direita, text="🛒 Carrinho", font=("Arial", 16, "bold")).pack(pady=10)
        self.scroll_carrinho = ctk.CTkScrollableFrame(self.aba_direita, height=180, fg_color="#121212")
        self.scroll_carrinho.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(self.aba_direita, text="📍 Cliente", font=("Arial", 14, "bold"), text_color="#D32F2F").pack(anchor="w", padx=15, pady=5)
        self.txt_tel = ctk.CTkEntry(self.aba_direita, placeholder_text="Telefone", fg_color="#121212")
        self.txt_tel.pack(fill="x", padx=15, pady=3)
        self.txt_tel.bind("<FocusOut>", self.buscar_cliente_automatico)
        self.txt_nome = ctk.CTkEntry(self.aba_direita, placeholder_text="Nome", fg_color="#121212")
        self.txt_nome.pack(fill="x", padx=15, pady=3)
        self.txt_end = ctk.CTkEntry(self.aba_direita, placeholder_text="Endereço", fg_color="#121212")
        self.txt_end.pack(fill="x", padx=15, pady=3)
        
        self.combo_bairros_pdv = ctk.CTkOptionMenu(self.aba_direita, values=["Selecione o Bairro"], fg_color="#333", button_color="#444", command=self.ao_selecionar_bairro_pdv)
        self.combo_bairros_pdv.pack(fill="x", padx=15, pady=3)
        self.atualizar_dropdown_bairros_pdv()
        
        self.combo_pag = ctk.CTkOptionMenu(self.aba_direita, values=["Pix", "Cartão", "Dinheiro"], fg_color="#D32F2F")
        self.combo_pag.pack(fill="x", padx=15, pady=5); self.combo_pag.set("Pix")
        
        self.lbl_sub = ctk.CTkLabel(self.aba_direita, text="Subtotal: R$ 0.00"); self.lbl_sub.pack(anchor="w", padx=15)
        self.lbl_tx = ctk.CTkLabel(self.aba_direita, text="Taxa: R$ 0.00"); self.lbl_tx.pack(anchor="w", padx=15)
        self.lbl_tot = ctk.CTkLabel(self.aba_direita, text="TOTAL: R$ 0.00", font=("Arial", 18, "bold"), text_color="#D32F2F")
        self.lbl_tot.pack(anchor="w", padx=15, pady=5)
        
        ctk.CTkButton(self.aba_direita, text="🚀 ENVIAR PEDIDO", height=45, fg_color="#D32F2F", font=("Arial", 14, "bold"), command=self.finalizar_pedido_completo).pack(fill="x", padx=15, pady=10)

    def atualizar_dropdown_bairros_pdv(self):
        lista = [b[0] for b in listar_taxas()]
        if lista:
            self.combo_bairros_pdv.configure(values=lista); self.combo_bairros_pdv.set(lista[0])
        else:
            self.combo_bairros_pdv.configure(values=["Selecione o Bairro"]); self.combo_bairros_pdv.set("Selecione o Bairro")

    def ao_selecionar_bairro_pdv(self, escolha):
        conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
        c.execute("SELECT valor FROM taxas_entrega WHERE bairro=?", (escolha,))
        res = c.fetchone(); conn.close()
        self.carrinho.taxa_entrega = res[0] if res else 0.0
        self.atualizar_carrinho_tela()

    def buscar_cliente_automatico(self, event):
        tel = self.txt_tel.get()
        if tel:
            conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
            c.execute("SELECT nome, endereco, bairro FROM clientes WHERE telefone=?", (tel,))
            res = c.fetchone()
            if res:
                self.txt_nome.delete(0, 'end'); self.txt_nome.insert(0, res[0])
                self.txt_end.delete(0, 'end'); self.txt_end.insert(0, res[1])
                if res[2]: self.combo_bairros_pdv.set(res[2]); self.ao_selecionar_bairro_pdv(res[2])
            conn.close()

    def atualizar_vitrine_tela(self):
        for w in self.scroll_vitrine.winfo_children(): w.destroy()
        for p in listar_produtos():
            pid, nome, preco, desc = p
            desc_val = desc if desc else "Sem descrição"
            card = ctk.CTkFrame(self.scroll_vitrine, fg_color="#1A1A1A", height=75)
            card.pack(fill="x", pady=4, padx=5); card.pack_propagate(False)
            f_txt = ctk.CTkFrame(card, fg_color="transparent")
            f_txt.pack(side="left", fill="both", expand=True, padx=10, pady=5)
            ctk.CTkLabel(f_txt, text=nome, font=("Arial", 15, "bold")).pack(anchor="w")
            ctk.CTkLabel(f_txt, text=desc_val, font=("Arial", 11), text_color="gray").pack(anchor="w")
            ctk.CTkLabel(f_txt, text=f"R$ {preco:.2f}", text_color="#D32F2F", font=("Arial", 12, "bold")).pack(anchor="w")
            ctk.CTkButton(card, text="➕", width=35, fg_color="#D32F2F", command=lambda id_p=pid, n=nome, pr=preco: self.add_carrinho(id_p, n, pr)).pack(side="right", padx=15, pady=15)

    def add_carrinho(self, pid, nome, preco):
        self.carrinho.adicionar(pid, nome, preco); self.atualizar_carrinho_tela()

    def atualizar_carrinho_tela(self):
        for w in self.scroll_carrinho.winfo_children(): w.destroy()
        for pid, info in self.carrinho.itens.items():
            f = ctk.CTkFrame(self.scroll_carrinho, fg_color="transparent"); f.pack(fill="x", pady=2)
            ctk.CTkLabel(f, text=f"{info['qtd']}x {info['nome']}").pack(side="left")
            ctk.CTkButton(f, text="❌", width=20, fg_color="transparent", text_color="red", command=lambda id_p=pid: self.remover_item(id_p)).pack(side="right")
            ctk.CTkLabel(f, text=f"R$ {(info['preco']*info['qtd']):.2f}", text_color="gray").pack(side="right", padx=10)
        sub, tot = self.carrinho.obter_totais()
        self.lbl_sub.configure(text=f"Subtotal: R$ {sub:.2f}")
        self.lbl_tx.configure(text=f"Taxa: R$ {self.carrinho.taxa_entrega:.2f}")
        self.lbl_tot.configure(text=f"TOTAL: R$ {tot:.2f}")

    def remover_item(self, pid):
        self.carrinho.remover(pid); self.atualizar_carrinho_tela()

    def finalizar_pedido_completo(self):
        sub, tot = self.carrinho.obter_totais()
        if not self.carrinho.itens or not self.txt_nome.get(): 
            messagebox.showwarning("Aviso", "Preencha o nome do cliente e os itens!"); return
        nome_c, tel_c, end_c, bair_c, pag = self.txt_nome.get(), self.txt_tel.get(), self.txt_end.get(), self.combo_bairros_pdv.get(), self.combo_pag.get()
        conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO clientes (telefone, nome, endereco, bairro) VALUES (?,?,?,?)", (tel_c, nome_c, end_c, bair_c))
        conn.commit(); conn.close()
        messagebox.showinfo("Sucesso", f"Pedido de {nome_c} salvo com sucesso!")
        self.carrinho.itens.clear(); self.carrinho.taxa_entrega = 0.0; self.atualizar_carrinho_tela()

    def abrir_gerenciador(self):
        g_win = ctk.CTkToplevel(self.root); g_win.title("Gerenciar Produtos"); g_win.geometry("650x450"); g_win.grab_set()
        self.id_produto_em_edicao = None
        
        f_esq = ctk.CTkFrame(g_win, width=240); f_esq.pack(side="left", fill="both", padx=10, pady=10)
        lbl_status = ctk.CTkLabel(f_esq, text="✨ Novo Produto", font=("Arial", 12, "bold"), text_color="gray"); lbl_status.pack(pady=5)
        
        txt_n = ctk.CTkEntry(f_esq, placeholder_text="Nome do Item"); txt_n.pack(fill="x", padx=10, pady=5)
        txt_d = ctk.CTkEntry(f_esq, placeholder_text="Descrição (Ingredientes)"); txt_d.pack(fill="x", padx=10, pady=5)
        txt_p = ctk.CTkEntry(f_esq, placeholder_text="Preço (Ex: 29.90)"); txt_p.pack(fill="x", padx=10, pady=5)

        scr_p = ctk.CTkScrollableFrame(g_win); scr_p.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        def atualizar_lista_gerenciador():
            for w in scr_p.winfo_children(): w.destroy()
            conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
            c.execute("SELECT id, nome, preco, descricao FROM produtos")
            for item in c.fetchall():
                pid, nome, preco, desc = item
                f_item = ctk.CTkFrame(scr_p, fg_color="#222"); f_item.pack(fill="x", pady=2, padx=5)
                ctk.CTkLabel(f_item, text=f"{nome} - R$ {preco:.2f}", font=("Arial", 11, "bold")).pack(side="left", padx=5, pady=5)
                ctk.CTkButton(f_item, text="❌", width=25, fg_color="transparent", text_color="red", command=lambda id_p=pid: remover_produto(id_p)).pack(side="right", padx=2)
                ctk.CTkButton(f_item, text="✏️", width=25, fg_color="transparent", text_color="yellow", command=lambda p=item: carregar_para_edicao(p)).pack(side="right", padx=2)
            conn.close()

        def carregar_para_edicao(item):
            pid, nome, preco, desc = item
            self.id_produto_em_edicao = pid
            lbl_status.configure(text="✏️ Editando Produto", text_color="yellow")
            btn_salvar.configure(text="Atualizar Produto", fg_color="#E65100")
            txt_n.delete(0, 'end'); txt_n.insert(0, nome)
            txt_d.delete(0, 'end'); txt_d.insert(0, desc if desc else "")
            txt_p.delete(0, 'end'); txt_p.insert(0, str(preco))

        def remover_produto(pid):
            if messagebox.askyesno("Confirmar", "Excluir item do cardápio?"):
                conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
                c.execute("DELETE FROM produtos WHERE id=?", (pid,))
                conn.commit(); conn.close()
                if self.id_produto_em_edicao == pid: cancelando_edicao()
                atualizar_lista_gerenciador(); self.atualizar_vitrine_tela()

        def cancelando_edicao():
            self.id_produto_em_edicao = None
            lbl_status.configure(text="✨ Novo Produto", text_color="gray")
            btn_salvar.configure(text="Salvar Produto", fg_color="#D32F2F")
            txt_n.delete(0, 'end'); txt_p.delete(0, 'end'); txt_d.delete(0, 'end')

        def salvar():
            if not txt_n.get() or not txt_p.get(): return
            conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
            nome, preco, desc = txt_n.get(), float(txt_p.get().replace(",", ".")), txt_d.get()
            if self.id_produto_em_edicao:
                c.execute("UPDATE produtos SET nome=?, preco=?, descricao=? WHERE id=?", (nome, preco, desc, self.id_produto_em_edicao))
            else:
                c.execute("INSERT INTO produtos (nome, preco, descricao) VALUES (?,?,?)", (nome, preco, desc))
            conn.commit(); conn.close(); cancelando_edicao(); atualizar_lista_gerenciador(); self.atualizar_vitrine_tela()

        btn_salvar = ctk.CTkButton(f_esq, text="Salvar Produto", fg_color="#D32F2F", command=salvar); btn_salvar.pack(pady=10, padx=10, fill="x")
        ctk.CTkButton(f_esq, text="Cancelar", fg_color="#333", command=cancelando_edicao).pack(pady=2, padx=10, fill="x")
        atualizar_lista_gerenciador()

    def abrir_gerenciador_clientes(self):
        c_win = ctk.CTkToplevel(self.root); c_win.title("Clientes"); c_win.geometry("400x320"); c_win.grab_set()
        txt_t = ctk.CTkEntry(c_win, placeholder_text="Telefone"); txt_t.pack(fill="x", padx=20, pady=5)
        txt_n = ctk.CTkEntry(c_win, placeholder_text="Nome"); txt_n.pack(fill="x", padx=20, pady=5)
        txt_e = ctk.CTkEntry(c_win, placeholder_text="Endereço"); txt_e.pack(fill="x", padx=20, pady=5)
        combo_b = ctk.CTkOptionMenu(c_win, values=[b[0] for b in listar_taxas()] if listar_taxas() else ["Padrão"]); combo_b.pack(fill="x", padx=20, pady=5)
        def salvar():
            if not txt_t.get() or not txt_n.get(): return
            conn = sqlite3.connect("sistema_delivery.db"); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO clientes (telefone, nome, endereco, bairro) VALUES (?,?,?,?)", (txt_t.get(), txt_n.get(), txt_e.get(), combo_b.get()))
            conn.commit(); conn.close(); c_win.destroy(); self.atualizar_dropdown_bairros_pdv()
        ctk.CTkButton(c_win, text="Salvar Cliente", fg_color="#2E7D32", command=salvar).pack(pady=15)

    def abrir_gerenciador_taxas(self):
        t_win = ctk.CTkToplevel(self.root); t_win.title("Taxas de Entrega"); t_win.geometry("500x350"); t_win.grab_set()
        f_esq = ctk.CTkFrame