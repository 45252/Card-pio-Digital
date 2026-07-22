import requests
print("[PASSO 1] Importando bibliotecas...")
import customtkinter as ctk
from tkinter import messagebox
import sqlite3
import os
import datetime
import time

try:
    import win32print
    print("[PASSO 2] Biblioteca win32print importada com sucesso.")
except Exception as e:
    print(f"[AVISO] Falha ao importar win32print: {e}")

# Configuração de Aparência
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TotemRenshuSushi(ctk.CTk):
    def __init__(self):
        print("[PASSO 4] Inicializando a classe principal TotemRenshuSushi...")
        super().__init__()
        
        self.geometry("1280x720")
        self.title("Totem Renshu Sushi")
        
        # self.attributes("-fullscreen", True) # Ative para o totem físico
        self.bind("<Escape>", lambda e: self.destroy()) 
        
        self.COR_FUNDO = "#141414"
        self.COR_CARD = "#222222"
        self.COR_BOTAO_ADD = "#4CAF50"   
        self.COR_PRIMARY = "#FF5722"      
        self.COR_TEXTO = "#FFFFFF"
        self.IP_SERVIDOR = "http://192.168.0.103:5000" # <-- Alterado aqui!
        
        self.configure(fg_color=self.COR_FUNDO)
        self.carrinho = {}
        self.campo_foco_atual = None
        
        self.grid_columnconfigure(0, weight=4) 
        self.grid_columnconfigure(1, weight=3) 
        self.grid_rowconfigure(0, weight=1)
        
        self.frame_esquerda = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_esquerda.grid(row=0, column=0, sticky="nsew", padx=20, pady=25)
        
        self.frame_direita = ctk.CTkFrame(self, fg_color=self.COR_CARD, corner_radius=20)
        self.frame_direita.grid(row=0, column=1, sticky="nsew", padx=20, pady=25)
        
        print("[PASSO 5] Montando área de produtos...")
        self.montar_area_produtos()
        print("[PASSO 6] Montando área de carrinho...")
        self.montar_area_carrinho()
        print("[PASSO 7] Inicialização concluída. Abrindo janela...")
        
    def montar_area_produtos(self):
        self.exibir_menu_categorias()

    def exibir_menu_categorias(self):
        for w in self.frame_esquerda.winfo_children():
            w.destroy()
            
        lbl_topo = ctk.CTkLabel(self.frame_esquerda, text="RENSHU SUSHI", font=("Arial", 32, "bold"), text_color=self.COR_PRIMARY)
        lbl_topo.pack(anchor="w", pady=(10, 5), padx=15)
        
        lbl_sub = ctk.CTkLabel(self.frame_esquerda, text="Toque em uma categoria para começar:", font=("Arial", 16), text_color="#AAAAAA")
        lbl_sub.pack(anchor="w", pady=(0, 20), padx=15)
        
        grid_menu = ctk.CTkFrame(self.frame_esquerda, fg_color="transparent")
        grid_menu.pack(fill="both", expand=True, padx=10, pady=10)
        
        try:
            resposta = requests.get(f"{self.IP_SERVIDOR}/api/categorias")
            dados = resposta.json()
            
            categorias = dados.get("categorias", []) if dados.get("sucesso") else []
            
            if not categorias:
                lbl_aviso = ctk.CTkLabel(grid_menu, text="Nenhum produto disponível no momento.", font=("Arial", 18))
                lbl_aviso.pack(pady=50)
                return
            
            COLUNAS = 2 
            for i in range(COLUNAS):
                grid_menu.grid_columnconfigure(i, weight=1)
                
            num_linhas = (len(categorias) + COLUNAS - 1) // COLUNAS
            for i in range(num_linhas):
                grid_menu.grid_rowconfigure(i, weight=1)
            
            for index, cat in enumerate(categorias):
                linha = index // COLUNAS
                coluna = index % COLUNAS
                
                btn_cat = ctk.CTkButton(
                    grid_menu,
                    text=cat.upper(), 
                    font=("Arial", 20, "bold"),
                    fg_color="#2A2A2A", 
                    hover_color=self.COR_PRIMARY,
                    height=90,  
                    corner_radius=15,
                    command=lambda c_nome=cat: self.exibir_pratos_da_categoria(c_nome)
                )
                btn_cat.grid(row=linha, column=coluna, padx=12, pady=12, sticky="nsew")
                
        except Exception as e:
            print(f"[ERRO AO BUSCAR CATEGORIAS VIA API]: {e}")
            lbl_aviso = ctk.CTkLabel(grid_menu, text="Erro de conexão com o servidor.", font=("Arial", 18), text_color="red")
            lbl_aviso.pack(pady=50)

    def exibir_pratos_da_categoria(self, categoria_selecionada):
        from PIL import Image
        import os
        
        for w in self.frame_esquerda.winfo_children():
            w.destroy()
            
        f_topo_categoria = ctk.CTkFrame(self.frame_esquerda, fg_color="transparent")
        f_topo_categoria.pack(fill="x", pady=(10, 15), padx=10)
        
        btn_voltar = ctk.CTkButton(
            f_topo_categoria,
            text="VOLTAR",
            font=("Arial", 14, "bold"),
            fg_color="#333333",
            hover_color="#555555",
            width=120,
            height=45,
            corner_radius=10,
            command=self.exibir_menu_categorias
        )
        btn_voltar.pack(side="left")
        
        lbl_titulo_cat = ctk.CTkLabel(f_topo_categoria, text=categoria_selecionada.upper(), font=("Arial", 24, "bold"), text_color=self.COR_PRIMARY)
        lbl_titulo_cat.pack(side="right", padx=10)
        
        scroll_itens = ctk.CTkScrollableFrame(self.frame_esquerda, fg_color="transparent")
        scroll_itens.pack(fill="both", expand=True)
        
        try:
            resposta = requests.get(f"{self.IP_SERVIDOR}/api/produtos/{categoria_selecionada}")
            dados = resposta.json()
            
            produtos = dados.get("produtos", []) if dados.get("sucesso") else []
            
            for p in produtos:
                p_id = p["id"]
                p_nome = p["nome"]
                p_preco = p["preco"]
                p_desc = p["descricao"]
                p_img_nome = p["foto"]
                
                if not p_desc:
                    p_desc = "Delicioso prato preparado com ingredientes frescos."
                
                f_card = ctk.CTkFrame(scroll_itens, fg_color="#2A2A2A", height=130, corner_radius=12)
                f_card.pack(fill="x", pady=8, padx=10)
                f_card.pack_propagate(False)
                
                img_prato = None
                if p_img_nome:
                    try:
                        import io
                        from urllib.parse import quote
                        # Busca a foto direto do seu servidor Flask na pasta static
                        url_foto = f"{self.IP_SERVIDOR}/static/{quote(p_img_nome)}"
                        reposta_img = requests.get(url_foto, timeout=3)
                        
                        if reposta_img.status_code == 200:
                            # Converte os bytes recebidos em uma imagem utilizável
                            dados_img = io.BytesIO(reposta_img.content)
                            pil_img = Image.open(dados_img).convert("RGB")
                            img_prato = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(100, 100))
                    except Exception as e:
                        print(f"Erro ao carregar foto via URL: {e}")
                
                if img_prato:
                    lbl_foto = ctk.CTkLabel(f_card, text="", image=img_prato)
                    lbl_foto.pack(side="left", padx=(12, 5), pady=15)
                else:
                    lbl_foto_padrao = ctk.CTkLabel(f_card, text="-", font=("Arial", 36), width=100)
                    lbl_foto_padrao.pack(side="left", padx=(12, 5), pady=15)
                
                f_info = ctk.CTkFrame(f_card, fg_color="transparent")
                f_info.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                
                lbl_nome = ctk.CTkLabel(f_info, text=p_nome, font=("Arial", 16, "bold"), text_color=self.COR_TEXTO, anchor="w")
                lbl_nome.pack(fill="x")
                
                lbl_desc = ctk.CTkLabel(f_info, text=p_desc, font=("Arial", 12), text_color="#AAAAAA", anchor="w", justify="left", wraplength=320)
                lbl_desc.pack(fill="x", pady=(2, 4))
                
                lbl_preco = ctk.CTkLabel(f_info, text=f"R$ {p_preco:.2f}", font=("Consolas", 15, "bold"), text_color="#4CAF50", anchor="w")
                lbl_preco.pack(fill="x")
                
                btn_add = ctk.CTkButton(
                    f_card, 
                    text="INCLUIR", 
                    font=("Arial", 14, "bold"), 
                    fg_color=self.COR_BOTAO_ADD, 
                    hover_color="#388E3C", 
                    width=110, 
                    height=55, 
                    corner_radius=8,
                    command=lambda idx=p_id, nome=p_nome, preco=p_preco: self.adicionar_ao_carrinho(idx, nome, preco)
                )
                btn_add.pack(side="right", padx=15, pady=35)
                
        except Exception as e:
            print(f"[ERRO AO CARREGAR ITENS VIA API]: {e}")

    def montar_area_carrinho(self):
        lbl_cart = ctk.CTkLabel(self.frame_direita, text="SEU CARRINHO", font=("Arial", 20, "bold"), text_color=self.COR_TEXTO)
        lbl_cart.pack(pady=(20, 10))
        
        self.scroll_carrinho = ctk.CTkScrollableFrame(self.frame_direita, fg_color="#1E1E1E", corner_radius=10)
        self.scroll_carrinho.pack(fill="both", expand=True, padx=15, pady=10)
        
        self.frame_rodape_cart = ctk.CTkFrame(self.frame_direita, fg_color="transparent")
        self.frame_rodape_cart.pack(fill="x", side="bottom", padx=15, pady=20)
        
        self.lbl_total_cart = ctk.CTkLabel(self.frame_rodape_cart, text="Total: R$ 0.00", font=("Arial", 22, "bold"), text_color=self.COR_PRIMARY)
        self.lbl_total_cart.pack(pady=10)
        
        self.btn_avancar = ctk.CTkButton(
            self.frame_rodape_cart, text="FINALIZAR PEDIDO", font=("Arial", 18, "bold"), 
            fg_color=self.COR_PRIMARY, hover_color="#D84315", height=55, corner_radius=10,
            command=self.abrir_tela_pagamento
        )
        self.btn_avancar.pack(fill="x", pady=5)
        self.atualizar_visual_carrinho()

    def adicionar_ao_carrinho(self, p_id, nome, preco):
        if p_id in self.carrinho:
            self.carrinho[p_id]["qtd"] += 1
        else:
            self.carrinho[p_id] = {"nome": nome, "preco": preco, "qtd": 1}
        self.atualizar_visual_carrinho()
        
    def alterar_quantidade(self, p_id, mudanca):
        if p_id in self.carrinho:
            self.carrinho[p_id]["qtd"] += mudanca
            if self.carrinho[p_id]["qtd"] <= 0:
                del self.carrinho[p_id]
        self.atualizar_visual_carrinho()

    def obter_total_carrinho(self):
        return sum(item["preco"] * item["qtd"] for item in self.carrinho.values())

    def atualizar_visual_carrinho(self):
        for w in self.scroll_carrinho.winfo_children():
            w.destroy()
        if not self.carrinho:
            lbl_vazio = ctk.CTkLabel(self.scroll_carrinho, text="Carrinho vazio.\nAdicione itens ao lado!", font=("Arial", 16), text_color="#777777")
            lbl_vazio.pack(pady=80)
            self.lbl_total_cart.configure(text="Total: R$ 0.00")
            self.btn_avancar.configure(state="disabled")
            return
            
        self.btn_avancar.configure(state="normal")
        
        for p_id, info in self.carrinho.items():
            f_item = ctk.CTkFrame(self.scroll_carrinho, fg_color="#2A2A2A", corner_radius=10)
            f_item.pack(fill="x", pady=6, padx=5)
            
            total_item = info["preco"] * info["qtd"]
            texto_item = f"{info['nome']}\nR$ {total_item:.2f}"
            
            lbl_item_info = ctk.CTkLabel(f_item, text=texto_item, font=("Arial", 14, "bold"), text_color=self.COR_TEXTO, justify="left", anchor="w", wraplength=180)
            lbl_item_info.pack(side="left", padx=15, pady=10, fill="x", expand=True)
            
            f_controles = ctk.CTkFrame(f_item, fg_color="transparent")
            f_controles.pack(side="right", padx=10, pady=10)
            
            btn_menos = ctk.CTkButton(f_controles, text="-", width=38, height=38, font=("Arial", 18, "bold"), fg_color="#E53935", hover_color="#C62828", command=lambda idx=p_id: self.alterar_quantidade(idx, -1))
            btn_menos.pack(side="left", padx=3)
            
            lbl_qtd = ctk.CTkLabel(f_controles, text=str(info["qtd"]), font=("Arial", 16, "bold"), width=35)
            lbl_qtd.pack(side="left")
            
            btn_mais = ctk.CTkButton(f_controles, text="+", width=38, height=38, font=("Arial", 18, "bold"), fg_color="#4CAF50", hover_color="#2E7D32", command=lambda idx=p_id: self.alterar_quantidade(idx, 1))
            btn_mais.pack(side="left", padx=3)
            
        self.lbl_total_cart.configure(text=f"Total: R$ {self.obter_total_carrinho():.2f}")

    def abrir_tela_pagamento(self):
        win_pag = ctk.CTkToplevel(self)
        win_pag.title("Finalizar no Totem")
        win_pag.geometry("900x700")  
        win_pag.configure(fg_color=self.COR_FUNDO)
        win_pag.grab_set()
        win_pag.resizable(False, False)
        
        win_pag.update_idletasks()
        x = (win_pag.winfo_screenwidth() // 2) - (900 // 2)
        y = (win_pag.winfo_screenheight() // 2) - (700 // 2)
        win_pag.geometry(f"+{x}+{y}")
        
        total_totem = self.obter_total_carrinho()
        self.campo_foco_atual = None  

        frame_principal = ctk.CTkFrame(win_pag, fg_color="transparent")
        frame_principal.pack(fill="both", expand=True, padx=20, pady=20)
        frame_principal.grid_columnconfigure(0, weight=1, minsize=400)
        frame_principal.grid_columnconfigure(1, weight=1, minsize=440)
        frame_principal.grid_rowconfigure(0, weight=1)

        f_esquerda = ctk.CTkFrame(frame_principal, fg_color="transparent")
        f_esquerda.grid(row=0, column=0, sticky="nsew", padx=10)

        ctk.CTkLabel(f_esquerda, text="IDENTIFICAÇÃO", font=("Arial", 20, "bold"), text_color=self.COR_PRIMARY).pack(pady=(0, 10))
        
        ctk.CTkLabel(f_esquerda, text="Seu Nome:", font=("Arial", 14, "bold")).pack(anchor="w")
        txt_nome_t = ctk.CTkEntry(f_esquerda, placeholder_text="Toque aqui para digitar seu nome", font=("Arial", 14), height=40, fg_color="#2A2A2A")
        txt_nome_t.pack(fill="x", pady=(2, 10))
        txt_nome_t.bind("<FocusIn>", lambda e: self.definir_foco_campo(txt_nome_t, "letras"))
        
        ctk.CTkLabel(f_esquerda, text="Seu Celular (WhatsApp):", font=("Arial", 14, "bold")).pack(anchor="w")
        txt_tel_t = ctk.CTkEntry(f_esquerda, placeholder_text="Toque aqui para digitar seu celular", font=("Arial", 14), height=40, fg_color="#2A2A2A")
        txt_tel_t.pack(fill="x", pady=(2, 10))
        txt_tel_t.bind("<FocusIn>", lambda e: self.definir_foco_campo(txt_tel_t, "numeros"))

        ctk.CTkLabel(f_esquerda, text="Observação do Pedido (Restrições/Retirar itens):", font=("Arial", 14, "bold")).pack(anchor="w")
        txt_obs_t = ctk.CTkEntry(f_esquerda, placeholder_text="Ex: Sem cebola, sem gergelim...", font=("Arial", 14), height=40, fg_color="#2A2A2A")
        txt_obs_t.pack(fill="x", pady=(2, 15))
        txt_obs_t.bind("<FocusIn>", lambda e: self.definir_foco_campo(txt_obs_t, "letras"))
        
        f_instrucoes = ctk.CTkFrame(f_esquerda, fg_color="#1E1E1E", corner_radius=12)
        f_instrucoes.pack(fill="x", pady=5)
        
        lbl_val = ctk.CTkLabel(f_instrucoes, text=f"VALOR A PAGAR: R$ {total_totem:.2f}", font=("Arial", 18, "bold"), text_color="#4CAF50")
        lbl_val.pack(pady=5)
        
        forma_escolhida = ctk.StringVar(value="Cartão de Débito")
        
        def set_forma(opcao):
            forma_escolhida.set(opcao)
            btn_deb.configure(border_width=2 if opcao == "Cartão de Débito" else 0)
            btn_cred.configure(border_width=2 if opcao == "Cartão de Crédito" else 0)
            btn_pix.configure(border_width=2 if opcao == "Pix" else 0)
            
        f_meios = ctk.CTkFrame(f_esquerda, fg_color="transparent")
        f_meios.pack(fill="x", pady=10)
        
        btn_deb = ctk.CTkButton(f_meios, text="DEBITO", height=40, font=("Arial", 11, "bold"), border_color=self.COR_PRIMARY, command=lambda: set_forma("Cartão de Débito"))
        btn_deb.pack(side="left", fill="x", expand=True, padx=2)
        
        btn_cred = ctk.CTkButton(f_meios, text="CREDITO", height=40, font=("Arial", 11, "bold"), border_color=self.COR_PRIMARY, command=lambda: set_forma("Cartão de Crédito"))
        btn_cred.pack(side="left", fill="x", expand=True, padx=2)
        
        btn_pix = ctk.CTkButton(f_meios, text="PIX", height=40, font=("Arial", 11, "bold"), border_color=self.COR_PRIMARY, command=lambda: set_forma("Pix"))
        btn_pix.pack(side="left", fill="x", expand=True, padx=2)
        
        set_forma("Cartão de Débito")

        self.f_direita_teclado = ctk.CTkFrame(frame_principal, fg_color="#1E1E1E", corner_radius=15)
        self.f_direita_teclado.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.lbl_aviso_teclado = ctk.CTkLabel(self.f_direita_teclado, text="Toque em um campo de texto\npara abrir o teclado na tela.", font=("Arial", 16), text_color="#777777")
        self.lbl_aviso_teclado.pack(expand=True)

        def processar_venda_totem():
            nome = txt_nome_t.get().strip()
            telefone = txt_tel_t.get().strip()
            observacao = txt_obs_t.get().strip()
            
            if not nome or not telefone:
                messagebox.showwarning("Totem", "Por favor, digite seu Nome e Telefone!", parent=win_pag)
                return
                
            try:
                agora = datetime.datetime.now()
                data_hora_br = agora.strftime("%d/%m/%Y %H:%M")
                
                conn = sqlite3.connect("sistema_delivery.db")
                c = conn.cursor()
                
                c.execute("SELECT COUNT(*) FROM vendas WHERE data LIKE ?", (f"{agora.strftime('%d/%m/%Y')}%",))
                qtd_hoje = c.fetchone()[0]
                numero_pedido = qtd_hoje + 1
                
                lista_resumo = [f"{info['qtd']}x {info['nome']}" for info in self.carrinho.values()]
                resumo_itens = ", ".join(lista_resumo)
                if observacao:
                    resumo_itens += f" (OBS: {observacao})"
                resumo_com_formatacao = f"#{numero_pedido} | {resumo_itens} | [TOTEM]"
                
                c.execute("INSERT OR REPLACE INTO clientes (telefone, nome, endereco, bairro) VALUES (?,?, 'RETIRADA NO TOTEM', 'Balcão')", (telefone, nome))
                c.execute("INSERT INTO vendas (data, cliente, total, pagamento, itens) VALUES (?,?,?,?,?)", (data_hora_br, nome, total_totem, f"{forma_escolhida.get()} (Totem)", resumo_com_formatacao))
                
                for p_id, info in self.carrinho.items():
                    c.execute("UPDATE produtos SET estoque = MAX(0, estoque - ?) WHERE id = ?", (info['qtd'], p_id))
                    
                conn.commit()
                conn.close()
                
                imprimir_via_cozinha_totem(numero_pedido, nome, telefone, forma_escolhida.get(), total_totem, self.carrinho, data_hora_br, observacao)
                
                messagebox.showinfo("Totem Renshu", f"Pedido #{numero_pedido} Enviado!\n\nAguarde a chamada do seu nome no Balcão.", parent=win_pag)
                
                self.carrinho.clear()
                self.atualizar_visual_carrinho()
                win_pag.destroy()
            except Exception as e:
                messagebox.showerror("Erro Totem", f"Erro crítico ao salvar venda: {e}", parent=win_pag)

        btn_confirmar_pago = ctk.CTkButton(f_esquerda, text="CONFIRMAR PAGAMENTO", font=("Arial", 16, "bold"), fg_color="#4CAF50", hover_color="#388E3C", height=50, command=processar_venda_totem)
        btn_confirmar_pago.pack(fill="x", pady=(10, 5))
        
        btn_cancelar = ctk.CTkButton(f_esquerda, text="Voltar e Alterar Itens", fg_color="transparent", text_color="#E53935", command=win_pag.destroy)
        btn_cancelar.pack()

    def definir_foco_campo(self, campo, tipo_teclado):
        self.campo_foco_atual = campo
        if hasattr(self, 'lbl_aviso_teclado') and self.lbl_aviso_teclado.winfo_exists():
            self.lbl_aviso_teclado.destroy()
            
        for w in self.f_direita_teclado.winfo_children():
            w.destroy()
            
        f_linhas = ctk.CTkFrame(self.f_direita_teclado, fg_color="transparent")
        f_linhas.pack(expand=True, fill="both", padx=5, pady=10)

        def pressionar_tecla(char):
            if self.campo_foco_atual:
                self.campo_foco_atual.insert(len(self.campo_foco_atual.get()), char)

        def apagar_tecla():
            if self.campo_foco_atual:
                conteudo = self.campo_foco_atual.get()
                if conteudo:
                    self.campo_foco_atual.delete(len(conteudo)-1, "end")

        if tipo_teclado == "numeros":
            layout = [
                ['1', '2', '3'],
                ['4', '5', '6'],
                ['7', '8', '9'],
                ['0', 'Apagar']
            ]
            for linha in layout:
                f_row = ctk.CTkFrame(f_linhas, fg_color="transparent")
                f_row.pack(expand=True, fill="both", pady=4)
                for char in linha:
                    cmd = apagar_tecla if char == 'Apagar' else lambda c=char: pressionar_tecla(c)
                    cor = "#E53935" if char == 'Apagar' else "#333333"
                    btn = ctk.CTkButton(f_row, text=char, font=("Arial", 18, "bold"), fg_color=cor, height=60, command=cmd)
                    btn.pack(side="left", expand=True, fill="both", padx=4)
        else:
            linhas_letras = [
                ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
                ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'Ç'],
                ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ' ', 'Apagar']
            ]
            for linha in linhas_letras:
                f_row = ctk.CTkFrame(f_linhas, fg_color="transparent")
                f_row.pack(anchor="center", pady=4) 
                for char in linha:
                    cmd = apagar_tecla if char == 'Apagar' else lambda c=char: pressionar_tecla(c)
                    
                    if char == 'Apagar':
                        texto_exibido = "Apagar"
                        cor = "#E53935"
                        largura = 75
                        expandir = False
                    elif char == ' ':
                        texto_exibido = "ESPAÇO"
                        cor = "#444444"
                        largura = 85
                        expandir = False
                    else:
                        texto_exibido = char
                        cor = "#333333"
                        largura = 28 
                        expandir = False
                        
                    btn = ctk.CTkButton(
                        f_row, 
                        text=texto_exibido, 
                        font=("Arial", 13, "bold"), 
                        fg_color=cor, 
                        height=50, 
                        width=largura, 
                        command=cmd
                    )
                    btn.pack(side="left", padx=2, expand=expandir)


def imprimir_via_cozinha_totem(numero, nome, tel, pag, total, carrinho_itens, data_hora, observacao=""):
    import time
    import win32print

    cupom = []
    cupom.append("------------------------------------------")
    cupom.append(f"          PEDIDO TOTEM #{numero}          ")
    cupom.append("------------------------------------------")
    cupom.append(f"Data:    {data_hora}")
    cupom.append(f"Cliente: {nome[:30]}")
    cupom.append(f"Celular: {tel}")
    cupom.append("------------------------------------------")
    cupom.append("Qtd Item                         Total    ")
    cupom.append("------------------------------------------")
    for info in carrinho_itens.values():
        qtd = info['qtd']
        nome_item = info['nome'][:24]
        total_item = info['preco'] * qtd
        cupom.append(f"{qtd:<3} {nome_item:<25} R$ {total_item:>7.2f}")
    cupom.append("------------------------------------------")
    
    if observacao:
        cupom.append("  OBSERVACAO DO CLIENTE:")
        cupom.append(f"  >> {observacao[:38]}")
        if len(observacao) > 38:
            cupom.append(f"  >> {observacao[38:76]}")
        cupom.append("------------------------------------------")
        
    cupom.append(f"TOTAL GERAL:                  R$ {total:>7.2f}")
    cupom.append("------------------------------------------")
    cupom.append(f"PAGAMENTO: {pag}")
    cupom.append("------------------------------------------")
    cupom.append("\n\n\n\n\n\x1bi") 
    texto_cupom_final = "\n".join(cupom)

    def enviar_para_impressora(nome_impressora, titulo_documento, cabeçalho_especial, estilo_fonte):
        try:
            hPrinter = win32print.OpenPrinter(nome_impressora)
            try:
                win32print.StartDocPrinter(hPrinter, 1, (titulo_documento, None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, estilo_fonte)
                win32print.WritePrinter(hPrinter, cabeçalho_especial.encode("cp860", errors="ignore"))
                win32print.WritePrinter(hPrinter, b"\x1d\x21\x00\x1b\x61\x00")
                win32print.WritePrinter(hPrinter, texto_cupom_final.encode("cp860", errors="ignore"))
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
        except Exception as e:
            print(f"[ERRO IMPRESSÃO - {nome_impressora}]: {e}")

    # --- EXECUÇÃO DO FLUXO DE IMPRESSÃO ---
    enviar_para_impressora(
        nome_impressora="Balcao",
        titulo_documento="Via Cliente Totem",
        cabeçalho_especial=(
            "RENSHU SUSHI\n"
            "*** VIA DO CLIENTE (AGUARDE) ***\n\n"
            "CNPJ: 23.248.904/0001-36\n"
            "Rua Manoel Botelho, 43 - Pq. São Rafael\n\n"
        ),
        estilo_fonte=b"\x1b\x40\x1d\x21\x01\x1b\x61\x01"
    )

    time.sleep(1.2)

    enviar_para_impressora(
        nome_impressora="Balcao",
        titulo_documento="Via Caixa Totem",
        cabeçalho_especial="VIA DO CAIXA\nCHAMAR PELO NOME\n\n",
        estilo_fonte=b"\x1b\x40\x1d\x21\x11\x1b\x61\x01"
    )

    time.sleep(0.8)

    enviar_para_impressora(
        nome_impressora="POS58 10.0.0.6",
        titulo_documento="Via Cozinha Totem",
        cabeçalho_especial="COZINHA - PREPARO\n\n",
        estilo_fonte=b"\x1b\x40\x1d\x21\x11\x1b\x61\x01"
    )


if __name__ == "__main__":
    print("[PASSO 3] Bloco principal detectado, instanciando App...")
    app = TotemRenshuSushi()
    print("[PASSO 8] Entrando no mainloop da aplicação...")
    app.mainloop()