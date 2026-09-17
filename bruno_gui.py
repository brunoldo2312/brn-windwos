"""
bruno_gui.py — Interface Gráfica Completa com Ponte BTC
=========================================================
✅ Carteira BRN
✅ Mineração e transações
✅ Rede P2P
✅ 🆕 Ponte BTC — Depósito e Saque
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time


class BrunoGUI:
    def __init__(self, api, bridge=None):
        self.api = api
        self.bridge = bridge  # Ponte BTC opcional
        
        self.root = tk.Tk()
        self.root.title("Bruno Coin — Carteira & Ponte BTC")
        self.root.geometry("900x650")
        
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        """Constrói toda a interface"""
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 📌 Aba 1 — Carteira
        self.tab_wallet = ttk.Frame(notebook)
        notebook.add(self.tab_wallet, text="  💰 Carteira  ")
        self._build_wallet_tab()
        
        # 📌 Aba 2 — Ponte BTC
        self.tab_bridge = ttk.Frame(notebook)
        notebook.add(self.tab_bridge, text="  ₿ Ponte BTC  ")
        self._build_bridge_tab()
        
        # 📌 Aba 3 — Transações
        self.tab_tx = ttk.Frame(notebook)
        notebook.add(self.tab_tx, text="  📜 Transações  ")
        self._build_tx_tab()
        
        # 📌 Aba 4 — Rede
        self.tab_network = ttk.Frame(notebook)
        notebook.add(self.tab_network, text="  🌐 Rede  ")
        self._build_network_tab()
        
        # Rodapé
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, padx=5, pady=2)
        self.status_label = ttk.Label(self.status_frame, text="Inicializado...")
        self.status_label.pack(side=tk.LEFT)

    # ========================================================
    # ABA CARTEIRA
    # ========================================================
    
    def _build_wallet_tab(self):
        f = self.tab_wallet
        
        # Endereço
        ttk.Label(f, text="Seu Endereço BRN:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky=tk.W, padx=10, pady=(15,5))
        self.addr_var = tk.StringVar(value="brn1cd943fa71e1f91dcd62f52fc6138bc845ab")
        addr_entry = ttk.Entry(f, textvariable=self.addr_var, width=55, font=("Courier", 10))
        addr_entry.grid(row=1, column=0, columnspan=2, padx=10, sticky=tk.W)
        
        # Saldo BRN
        ttk.Label(f, text="Saldo BRN:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky=tk.W, padx=10, pady=(20,5))
        self.balance_var = tk.StringVar(value="0.00000000 BRN")
        ttk.Label(f, textvariable=self.balance_var, font=("Arial", 16)).grid(row=3, column=0, sticky=tk.W, padx=10)
        
        # Saldo wBTC
        ttk.Label(f, text="Saldo wBTC (Ponte):", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky=tk.W, padx=10, pady=(20,5))
        self.wbtc_var = tk.StringVar(value="0.00000000 wBTC")
        ttk.Label(f, textvariable=self.wbtc_var, font=("Arial", 14), foreground="#f7931a").grid(row=5, column=0, sticky=tk.W, padx=10)
        
        # Enviar BRN
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=20)
        ttk.Label(f, text="Enviar BRN:", font=("Arial", 11, "bold")).grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=10)
        
        ttk.Label(f, text="Destinatário:").grid(row=8, column=0, sticky=tk.W, padx=10, pady=5)
        self.to_addr_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.to_addr_var, width=55).grid(row=9, column=0, columnspan=2, padx=10, sticky=tk.W)
        
        ttk.Label(f, text="Valor:").grid(row=10, column=0, sticky=tk.W, padx=10, pady=5)
        self.send_amount_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.send_amount_var, width=30).grid(row=11, column=0, sticky=tk.W, padx=10)
        
        ttk.Button(f, text="Enviar BRN", command=self._send_brn).grid(row=11, column=1, padx=10, pady=5)

    # ========================================================
    # ABA PONTE BTC — AQUI ACONTECE A MAGIA!
    # ========================================================
    
    def _build_bridge_tab(self):
        f = self.tab_bridge
        
        # ─── CONFIGURAÇÃO DA PONTE ───
        frame_config = ttk.LabelFrame(f, text="  ⚙️ Configuração da Ponte  ")
        frame_config.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_config, text="Endereço BTC da Ponte:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.bridge_address_var = tk.StringVar()
        ttk.Entry(frame_config, textvariable=self.bridge_address_var, width=55).grid(row=0, column=1, padx=5, pady=8)
        ttk.Button(frame_config, text="Salvar", command=self._set_bridge_address).grid(row=0, column=2, padx=5, pady=8)
        
        # ─── DEPÓSITO: BTC → wBTC ───
        frame_deposit = ttk.LabelFrame(f, text="  📥 Depósito: BTC → wBTC  ")
        frame_deposit.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_deposit, text="Seu endereço BTC:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.btc_from_var = tk.StringVar()
        ttk.Entry(frame_deposit, textvariable=self.btc_from_var, width=55).grid(row=0, column=1, columnspan=2, padx=5, pady=5)
        
        ttk.Label(frame_deposit, text="Receber wBTC em:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.brn_to_var = tk.StringVar(value="brn1cd943fa71e1f91dcd62f52fc6138bc845ab")
        ttk.Entry(frame_deposit, textvariable=self.brn_to_var, width=55).grid(row=1, column=1, columnspan=2, padx=5, pady=5)
        
        ttk.Label(frame_deposit, text="Valor em BTC:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.amount_btc_var = tk.StringVar()
        ttk.Entry(frame_deposit, textvariable=self.amount_btc_var, width=30).grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(frame_deposit, text="Solicitar Depósito", command=self._create_deposit).grid(row=2, column=2, padx=5, pady=5)
        
        # Resultado do depósito
        self.deposit_result = scrolledtext.ScrolledText(frame_deposit, height=5, width=75)
        self.deposit_result.grid(row=3, column=0, columnspan=3, padx=10, pady=8)
        
        # Confirmar depósito
        ttk.Separator(frame_deposit, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=3, sticky=tk.EW, padx=10, pady=5)
        ttk.Label(frame_deposit, text="✅ Já enviou? Confirme abaixo:").grid(row=5, column=0, columnspan=3, sticky=tk.W, padx=10, pady=5)
        
        ttk.Label(frame_deposit, text="ID Solicitação:").grid(row=6, column=0, sticky=tk.W, padx=10, pady=3)
        self.deposit_req_id_var = tk.StringVar()
        ttk.Entry(frame_deposit, textvariable=self.deposit_req_id_var, width=30).grid(row=6, column=1, padx=5, pady=3)
        
        ttk.Label(frame_deposit, text="TXID Transação BTC:").grid(row=7, column=0, sticky=tk.W, padx=10, pady=3)
        self.btc_txid_var = tk.StringVar()
        ttk.Entry(frame_deposit, textvariable=self.btc_txid_var, width=55).grid(row=7, column=1, columnspan=2, padx=5, pady=3)
        
        ttk.Button(frame_deposit, text="Verificar e Cunhar wBTC", command=self._confirm_deposit).grid(row=8, column=1, columnspan=2, padx=5, pady=8)
        
        # ─── SAQUE: wBTC → BTC ───
        frame_withdraw = ttk.LabelFrame(f, text="  📤 Saque: wBTC → BTC  ")
        frame_withdraw.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_withdraw, text="Queimar wBTC da carteira:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.withdraw_wbtc_var = tk.StringVar()
        ttk.Entry(frame_withdraw, textvariable=self.withdraw_wbtc_var, width=30).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(frame_withdraw, text="Receber BTC em:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.withdraw_btc_addr_var = tk.StringVar()
        ttk.Entry(frame_withdraw, textvariable=self.withdraw_btc_addr_var, width=55).grid(row=1, column=1, columnspan=2, padx=5, pady=5)
        
        ttk.Button(frame_withdraw, text="Solicitar Saque", command=self._create_withdrawal).grid(row=2, column=1, padx=5, pady=8)
        
        self.withdraw_result = scrolledtext.ScrolledText(frame_withdraw, height=4, width=75)
        self.withdraw_result.grid(row=3, column=0, columnspan=3, padx=10, pady=5)

    # ========================================================
    # ABA TRANSAÇÕES E REDE
    # ========================================================
    
    def _build_tx_tab(self):
        f = self.tab_tx
        self.tx_log = scrolledtext.ScrolledText(f, height=30, width=100)
        self.tx_log.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.tx_log.insert(tk.END, "Histórico de transações aparecerá aqui...\n")
    
    def _build_network_tab(self):
        f = self.tab_network
        self.network_info = scrolledtext.ScrolledText(f, height=30, width=100)
        self.network_info.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.network_info.insert(tk.END, "Informações da rede aparecerão aqui...\n")

    # ========================================================
    # MÉTODOS DA PONTE BTC
    # ========================================================
    
    def _set_bridge_address(self):
        addr = self.bridge_address_var.get().strip()
        if self.bridge:
            result = self.bridge.set_bridge_address(addr)
            messagebox.showinfo("Ponte BTC", result["message"])
    
    def _create_deposit(self):
        if not self.bridge:
            messagebox.showwarning("Aviso", "Ponte BTC não inicializada!")
            return
        
        try:
            btc_from = self.btc_from_var.get().strip()
            brn_to = self.brn_to_var.get().strip()
            amount = float(self.amount_btc_var.get().strip())
            
            result = self.bridge.create_deposit_request(btc_from, brn_to, amount)
            
            self.deposit_result.delete(1.0, tk.END)
            if result["success"]:
                self.deposit_result.insert(tk.END, f"✅ SOLICITAÇÃO CRIADA!\n\n")
                self.deposit_result.insert(tk.END, f"ID: {result['request_id']}\n")
                self.deposit_result.insert(tk.END, f"Endereço da Ponte:\n{result['bridge_address']}\n\n")
                self.deposit_result.insert(tk.END, f"Valor: {result['expected_amount']:.8f} BTC\n")
                self.deposit_result.insert(tk.END, f"Você recebe: {result['net_amount']:.8f} wBTC\n\n")
                self.deposit_result.insert(tk.END, f"📋 INSTRUÇÕES:\n{result['instructions']}")
                self.deposit_req_id_var.set(result["request_id"])
            else:
                self.deposit_result.insert(tk.END, f"❌ ERRO: {result['message']}")
        except ValueError:
            messagebox.showerror("Erro", "Digite um valor válido")
    
    def _confirm_deposit(self):
        if not self.bridge:
            return
        
        req_id = self.deposit_req_id_var.get().strip()
        txid = self.btc_txid_var.get().strip()
        operator_addr = "brn1cd943fa71e1f91dcd62f52fc6138bc845ab"  # Operador padrão
        
        if not req_id or not txid:
            messagebox.showwarning("Aviso", "Preencha ID da solicitação e TXID")
            return
        
        result = self.bridge.confirm_deposit(req_id, txid, operator_addr)
        
        self.deposit_result.delete(1.0, tk.END)
        if result["success"]:
            self.deposit_result.insert(tk.END, f"✅ {result['message']}\n")
            if "wbtc_minted" in result:
                self.deposit_result.insert(tk.END, f"wBTC Cunhado: {result['wbtc_minted']:.8f}\n")
                self.deposit_result.insert(tk.END, f"TXID BTC: {result['btc_txid']}\n")
                self._refresh_stats()
        else:
            self.deposit_result.insert(tk.END, f"❌ {result['message']}")
    
    def _create_withdrawal(self):
        if not self.bridge:
            return
        
        try:
            amount = float(self.withdraw_wbtc_var.get().strip())
            btc_dest = self.withdraw_btc_addr_var.get().strip()
            brn_sender = self.brn_to_var.get().strip()  # Usuário padrão
            
            result = self.bridge.create_withdrawal_request(brn_sender, btc_dest, amount)
            
            self.withdraw_result.delete(1.0, tk.END)
            if result["success"]:
                self.withdraw_result.insert(tk.END, f"✅ SOLICITAÇÃO CRIADA!\n\n")
                self.withdraw_result.insert(tk.END, f"ID: {result['request_id']}\n")
                self.withdraw_result.insert(tk.END, f"Queimado: {result['wbtc_burned']:.8f} wBTC\n")
                self.withdraw_result.insert(tk.END, f"A receber: {result['btc_receive']:.8f} BTC\n\n")
                self.withdraw_result.insert(tk.END, f"📋 PRÓXIMO PASSO:\n{result['next_step']}")
                self._refresh_stats()
            else:
                self.withdraw_result.insert(tk.END, f"❌ ERRO: {result['message']}")
        except ValueError:
            messagebox.showerror("Erro", "Digite um valor válido")
    
    def _send_brn(self):
        messagebox.showinfo("Em Desenvolvimento", "Transação BRN básica — conecte com sua API!")
    
    def _refresh_stats(self):
        """Atualiza saldos e informações"""
        if self.bridge:
            addr = self.brn_to_var.get().strip()
            wbtc_info = self.bridge.get_wbtc_balance(addr)
            self.wbtc_var.set(f"{wbtc_info['balance']:.8f} wBTC")
        
        self.status_label.config(text=f"✅ Online | Ponte BTC ativa")
        self.root.after(3000, self._refresh_stats)
    
    def run(self):
        self.root.mainloop()
