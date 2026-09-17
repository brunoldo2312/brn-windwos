"""
bruno_gui.py — Interface Gráfica Nativa (Sem Navegador!)
=========================================================
✅ Usa Tkinter (nativo do Python — não precisa de navegador)
✅ Conecta diretamente com a API do bruno_coin.py
✅ Mesmas funcionalidades do HTML, mas em app de desktop
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
import json


class BrunoGUI:
    def __init__(self, api):
        self.api = api
        self.wallet = {"address": "", "sk": "", "pk": ""}
        self.mining = False
        self.auto_refresh_running = True
        
        # Janela principal
        self.root = tk.Tk()
        self.root.title(f"🏦 BRN Coin v{self.api.__class__.__module__} — Porta {self.api.p2p_port}")
        self.root.geometry("900x750")
        self.root.minsize(800, 600)
        
        # Cores (tema escuro)
        self.colors = {
            "bg": "#0d1117",
            "fg": "#e6edf3",
            "card": "#161b22",
            "border": "#30363d",
            "accent": "#58a6ff",
            "success": "#238636",
            "warning": "#d29922",
            "error": "#f85149",
            "input_bg": "#0d1117"
        }
        
        self._setup_style()
        self._build_ui()
        self._start_auto_refresh()
        
        self.log("✅ Interface iniciada! Clique em 'Criar Nova Carteira' para começar.")

    # ========================================================
    # ESTILO
    # ========================================================
    def _setup_style(self):
        self.root.configure(bg=self.colors["bg"])
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        
        # Configurar estilos
        self.style.configure("TFrame", background=self.colors["card"])
        self.style.configure("Card.TFrame", background=self.colors["card"], 
                            borderwidth=1, relief="solid")
        self.style.configure("TLabel", background=self.colors["card"], 
                            foreground=self.colors["fg"], font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", foreground=self.colors["accent"], 
                            font=("Segoe UI", 14, "bold"), background=self.colors["bg"])
        self.style.configure("Section.TLabel", foreground=self.colors["accent"], 
                            font=("Segoe UI", 11, "bold"), background=self.colors["card"])
        self.style.configure("Status.TLabel", font=("Consolas", 9))
        
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=5)
        self.style.configure("Success.TButton", background=self.colors["success"], 
                            foreground="white")
        self.style.map("Success.TButton", background=[("active", "#2ea043")])
        self.style.configure("Warning.TButton", background=self.colors["warning"], 
                            foreground="black")
        self.style.map("Warning.TButton", background=[("active", "#d29922")])
        self.style.configure("Secondary.TButton", background="#21262d", 
                            foreground=self.colors["fg"])
        self.style.map("Secondary.TButton", background=[("active", "#30363d")])

    # ========================================================
    # CONSTRUIR INTERFACE
    # ========================================================
    def _build_ui(self):
        # Container principal com scroll
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Título
        ttk.Label(main_container, text="🏦 BRN Coin — Carteira P2P", 
                 style="Header.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Canvas para rolagem
        canvas = tk.Canvas(main_container, bg=self.colors["bg"], 
                          highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Construir seções
        self._build_p2p_section()
        self._build_wallet_section()
        self._build_balance_section()
        self._build_backup_section()
        self._build_send_section()
        self._build_mining_section()
        self._build_log_section()

    def _build_section(self, title):
        """Helper para criar seções com borda e título"""
        frame = ttk.Frame(self.scrollable_frame, style="Card.TFrame", padding=15)
        frame.pack(fill="x", padx=5, pady=(0, 12))
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        return frame

    def _build_p2p_section(self):
        frame = self._build_section("🌐 Rede P2P")
        
        self.p2p_status = tk.Text(frame, height=5, wrap="word", 
                                 bg="#010409", fg="#7ee787", 
                                 font=("Consolas", 10), relief="flat", padx=10, pady=10)
        self.p2p_status.pack(fill="x", pady=(0, 10))
        self.p2p_status.insert("1.0", "Consultando rede…")
        self.p2p_status.config(state="disabled")
        
        ttk.Button(frame, text="🔄 Atualizar Rede", 
                  command=self.refresh_p2p).pack(anchor="w")

    def _build_wallet_section(self):
        frame = self._build_section("🔑 Carteira")
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        self.gen_btn = ttk.Button(btn_frame, text="🎲 Criar Nova Carteira", 
                                 command=self.generate_wallet, style="Success.TButton")
        self.gen_btn.pack(side="left")
        
        self.api_status_label = ttk.Label(btn_frame, text="API: pronta ✓", 
                                         style="Status.TLabel", foreground="#3fb950")
        self.api_status_label.pack(side="left", padx=15)
        
        # Endereço
        ttk.Label(frame, text="Endereço Público").pack(anchor="w", pady=(5, 2))
        self.addr_entry = tk.Entry(frame, bg=self.colors["input_bg"], fg="#58a6ff", 
                                  insertbackground="white", relief="solid", borderwidth=1)
        self.addr_entry.pack(fill="x", pady=(0, 8))
        self.addr_entry.insert(0, "Nenhuma carteira ativa")
        self.addr_entry.config(state="readonly")
        
        # Chaves
        row = ttk.Frame(frame)
        row.pack(fill="x")
        
        col1 = ttk.Frame(row)
        col1.pack(side="left", fill="x", expand=True)
        ttk.Label(col1, text="Chave Privada").pack(anchor="w", pady=(0, 2))
        self.sk_entry = tk.Entry(col1, bg=self.colors["input_bg"], show="•", 
                                relief="solid", borderwidth=1)
        self.sk_entry.pack(fill="x", padx=(0, 5))
        self.sk_entry.config(state="readonly")
        
        col2 = ttk.Frame(row)
        col2.pack(side="right", fill="x", expand=True)
        ttk.Label(col2, text="Chave Pública").pack(anchor="w", pady=(0, 2))
        self.pk_entry = tk.Entry(col2, bg=self.colors["input_bg"], 
                                relief="solid", borderwidth=1)
        self.pk_entry.pack(fill="x", padx=(5, 0))
        self.pk_entry.config(state="readonly")

    def _build_balance_section(self):
        frame = self._build_section("📊 Saldo")
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(btn_frame, text="🔄 Atualizar Saldo", 
                  command=self.check_balance, style="Secondary.TButton").pack(side="left")
        
        self.balance_box = tk.Text(frame, height=4, wrap="word", 
                                  bg="#1f6feb1a", fg="#58a6ff", 
                                  font=("Consolas", 12, "bold"), relief="flat", padx=12, pady=12)
        self.balance_box.pack(fill="x")
        self.balance_box.insert("1.0", "Nenhuma carteira ativa.")
        self.balance_box.config(state="disabled")

    def _build_backup_section(self):
        frame = self._build_section("💾 Backup")
        
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 10))
        
        col1 = ttk.Frame(row)
        col1.pack(side="left", fill="x", expand=True)
        ttk.Label(col1, text="Nome do Arquivo").pack(anchor="w", pady=(0, 2))
        self.filename_entry = tk.Entry(col1, bg=self.colors["input_bg"], relief="solid")
        self.filename_entry.insert(0, "carteira_brn")
        self.filename_entry.pack(fill="x", padx=(0, 5))
        
        col2 = ttk.Frame(row)
        col2.pack(side="right", fill="x", expand=True)
        ttk.Label(col2, text="Senha").pack(anchor="w", pady=(0, 2))
        self.password_entry = tk.Entry(col2, bg=self.colors["input_bg"], show="•", 
                                      relief="solid")
        self.password_entry.pack(fill="x", padx=(5, 0))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="💾 Salvar Backup", 
                  command=self.export_wallet, style="Success.TButton").pack(side="left")
        ttk.Button(btn_frame, text="📂 Carregar Backup", 
                  command=self.import_wallet, style="Secondary.TButton").pack(side="left", padx=5)

    def _build_send_section(self):
        frame = self._build_section("💸 Enviar BRN")
        
        row1 = ttk.Frame(frame)
        row1.pack(fill="x", pady=(0, 8))
        
        col1 = ttk.Frame(row1)
        col1.pack(side="left", fill="x", expand=True)
        ttk.Label(col1, text="Ativo").pack(anchor="w", pady=(0, 2))
        self.asset_entry = tk.Entry(col1, bg=self.colors["input_bg"], relief="solid")
        self.asset_entry.insert(0, "BRN")
        self.asset_entry.config(state="readonly")
        self.asset_entry.pack(fill="x", padx=(0, 5))
        
        col2 = ttk.Frame(row1)
        col2.pack(side="right", fill="x", expand=True)
        ttk.Label(col2, text="Quantidade").pack(anchor="w", pady=(0, 2))
        self.amount_entry = tk.Entry(col2, bg=self.colors["input_bg"], relief="solid")
        self.amount_entry.pack(fill="x", padx=(5, 0))
        
        ttk.Label(frame, text="Destinatário (brn1...)").pack(anchor="w", pady=(5, 2))
        self.to_entry = tk.Entry(frame, bg=self.colors["input_bg"], relief="solid")
        self.to_entry.pack(fill="x", pady=(0, 10))
        
        ttk.Button(frame, text="✉️ Assinar e Enviar", 
                  command=self.send_transaction, style="Warning.TButton").pack(anchor="w")

    def _build_mining_section(self):
        frame = self._build_section("⛏️ Mineração")
        
        row = ttk.Frame(frame)
        row.pack(fill="x")
        
        self.mining_btn = ttk.Button(row, text="▶ Iniciar Mineração", 
                                    command=self.toggle_mining, style="Success.TButton")
        self.mining_btn.pack(side="left")
        
        self.mining_status = ttk.Label(row, text="Parada", style="Status.TLabel", 
                                      foreground="#f85149")
        self.mining_status.pack(side="left", padx=15)
        
        ttk.Label(frame, text="Recompensa: 1.0 BRN por bloco", 
                 font=("Segoe UI", 9), foreground="#8b949e").pack(anchor="w", pady=(8, 0))

    def _build_log_section(self):
        frame = self._build_section("📋 Console")
        
        self.log_box = scrolledtext.ScrolledText(frame, height=10, wrap="word",
                                                 bg="#010409", fg="#7ee787",
                                                 font=("Consolas", 9), relief="flat")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.config(state="disabled")

    # ========================================================
    # LOG
    # ========================================================
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ========================================================
    # AÇÕES
    # ========================================================
    def refresh_p2p(self):
        try:
            status = self.api.get_network_status()
            text = (
                f"🔹 Peers conectados: {len(status['connected_peers'])}\n"
                f"🔹 Peers conhecidos: {len(status['known_peers'])}\n"
                f"🔹 Rede local: {status['local_endpoint']}\n"
                f"🔹 Descobertos na LAN: {len(status['discovered_lan'])}"
            )
            self.p2p_status.config(state="normal")
            self.p2p_status.delete("1.0", "end")
            self.p2p_status.insert("1.0", text)
            self.p2p_status.config(state="disabled")
        except Exception as e:
            self.log(f"❌ Erro ao atualizar rede: {e}")

    def generate_wallet(self):
        self.log("Gerando nova carteira…")
        try:
            kp = self.api.generate_wallet()
            self.wallet["address"] = kp["address"]
            self.wallet["sk"] = kp["spend_secret_key"]
            self.wallet["pk"] = kp["public_key"]
            
            # Atualizar campos
            self.addr_entry.config(state="normal")
            self.addr_entry.delete(0, "end")
            self.addr_entry.insert(0, kp["address"])
            self.addr_entry.config(state="readonly")
            
            self.sk_entry.config(state="normal")
            self.sk_entry.delete(0, "end")
            self.sk_entry.insert(0, kp["spend_secret_key"])
            self.sk_entry.config(state="readonly")
            
            self.pk_entry.config(state="normal")
            self.pk_entry.delete(0, "end")
            self.pk_entry.insert(0, kp["public_key"])
            self.pk_entry.config(state="readonly")
            
            self.log(f"✅ Carteira criada: {kp['address'][:16]}…")
            self.check_balance()
        except Exception as e:
            self.log(f"❌ Erro: {e}")

    def check_balance(self):
        if not self.wallet["address"]:
            self.log("⚠️ Crie uma carteira primeiro.")
            return
        
        try:
            result = self.api.get_balance(self.wallet["address"])
            self.balance_box.config(state="normal")
            self.balance_box.delete("1.0", "end")
            self.balance_box.insert("1.0", f"💰 Saldo: {result['balance']:.8f} BRN")
            self.balance_box.config(state="disabled")
            self.log("✅ Saldo atualizado.")
        except Exception as e:
            self.log(f"❌ Erro: {e}")

    def export_wallet(self):
        filename = self.filename_entry.get().strip()
        password = self.password_entry.get()
        
        if not self.wallet["address"]:
            self.log("⚠️ Crie uma carteira primeiro.")
            return
        if len(password) < 12:
            self.log("❌ Senha precisa de pelo menos 12 caracteres.")
            return
        
        self.log("💾 Salvando carteira…")
        messagebox.showinfo("Info", "Funcionalidade de backup disponível em breve!")

    def import_wallet(self):
        self.log("📂 Carregando carteira…")
        messagebox.showinfo("Info", "Funcionalidade de backup disponível em breve!")

    def send_transaction(self):
        to = self.to_entry.get().strip()
        amount_text = self.amount_entry.get()
        
        if not self.wallet["address"]:
            self.log("⚠️ Crie uma carteira primeiro.")
            return
        
        try:
            amount = float(amount_text)
            if amount <= 0:
                raise ValueError()
        except:
            self.log("❌ Valor inválido.")
            return
        
        if not to.startswith("brn1") or len(to) != 44:
            self.log("❌ Endereço inválido.")
            return
        
        self.log(f"Enviando {amount} BRN para {to[:16]}…")
        
        def do_send():
            try:
                result = self.api.send_funds(
                    self.wallet["address"], to, amount,
                    self.wallet["sk"], self.wallet["pk"]
                )
                self.log(f"✅ {result['message']}")
                self.check_balance()
            except Exception as e:
                self.log(f"❌ Erro: {e}")
        
        threading.Thread(target=do_send, daemon=True).start()

    def toggle_mining(self):
        if not self.wallet["address"]:
            self.log("⚠️ Crie uma carteira primeiro.")
            return
        
        def do_toggle():
            try:
                result = self.api.toggle_mining(self.wallet["address"])
                self.mining = result["mining"]
                
                if self.mining:
                    self.mining_btn.config(text="🛑 Parar Mineração")
                    self.mining_status.config(text="Minerando…", foreground="#3fb950")
                else:
                    self.mining_btn.config(text="▶ Iniciar Mineração")
                    self.mining_status.config(text="Parada", foreground="#f85149")
                
                self.log(f"✅ {result['message']}")
            except Exception as e:
                self.log(f"❌ Erro: {e}")
        
        threading.Thread(target=do_toggle, daemon=True).start()

    # ========================================================
    # ATUALIZAÇÃO AUTOMÁTICA
    # ========================================================
    def _start_auto_refresh(self):
        def refresh_loop():
            while self.auto_refresh_running:
                try:
                    # Atualizar status da mineração
                    chain_info = self.api.get_full_chain()
                    if chain_info["is_mining"] != self.mining:
                        self.mining = chain_info["is_mining"]
                        if self.mining:
                            self.mining_btn.config(text="🛑 Parar Mineração")
                            self.mining_status.config(text="Minerando…", foreground="#3fb950")
                        else:
                            self.mining_btn.config(text="▶ Iniciar Mineração")
                            self.mining_status.config(text="Parada", foreground="#f85149")
                except:
                    pass
                time.sleep(5)
        
        threading.Thread(target=refresh_loop, daemon=True).start()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.auto_refresh_running = False


# ============================================================
# INTEGRAÇÃO COM O BRUNO_COIN
# ============================================================

def start_gui(api):
    gui = BrunoGUI(api)
    gui.run()
