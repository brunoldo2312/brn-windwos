"""
bitcoin_bridge.py — Ponte Real BRN ↔ Bitcoin
===============================================
✅ BTC REAL via APIs públicas
✅ wBTC cunhado na rede BRN
✅ Sistema de operadores multiassinatura
✅ Sem baixar blockchain!
"""

import json
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
from bitcoin_api import BitcoinAPI


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BRIDGE_VERSION = "Britney-BTC-v2.0"

# 📌 CONFIGURE AQUI SEUS OPERADORES (pessoas de confiança!)
# Formato: { "endereco_brn_do_operador": "Nome" }
BRIDGE_OPERATORS = {
    "brn1cd943fa71e1f91dcd62f52fc6138bc845ab": "Operador-Princiapl",
    # Adicione mais operadores aqui, exemplo:
    # "brn1abcdefghijklmnopqrstuvwxyz123456789": "Operador-Maria",
}

# Quantos operadores precisam aprovar?
REQUIRED_APPROVALS = max(1, (len(BRIDGE_OPERATORS) // 2) + 1)

# Taxas e limites
BRIDGE_FEE = 0.0025       # 0.25% de taxa
MIN_BTC_AMOUNT = 0.0001   # Valor mínimo por transação
BTC_CONFIRMATIONS = 1     # Confirmações necessárias (mais = mais seguro)


# ============================================================
# ESTRUTURAS DE DADOS
# ============================================================

@dataclass
class BridgeDeposit:
    """Usuário envia BTC → recebe wBTC"""
    request_id: str
    btc_address_from: str      # Quem enviou o BTC
    brn_address_to: str        # Quem recebe wBTC
    expected_btc: float
    net_wbtc: float
    fee: float
    bridge_btc_address: str    # Endereço da ponte que recebe
    btc_txid: str = ""
    status: str = "AGUARDANDO_DEPOSITO"
    confirmations: int = 0
    operator_approvals: Set[str] = None
    brn_tx_hash: str = ""
    timestamp: float = 0
    
    def __post_init__(self):
        if self.operator_approvals is None:
            self.operator_approvals = set()
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    def to_dict(self):
        d = asdict(self)
        d["operator_approvals"] = list(self.operator_approvals)
        return d


@dataclass
class BridgeWithdrawal:
    """Usuário queima wBTC → recebe BTC"""
    request_id: str
    brn_address_from: str      # Quem queimou wBTC
    btc_address_to: str        # Quem recebe BTC
    wbtc_burned: float
    net_btc: float
    fee: float
    status: str = "AGUARDANDO_APROVACAO"
    operator_approvals: Set[str] = None
    btc_txid: str = ""
    timestamp: float = 0
    
    def __post_init__(self):
        if self.operator_approvals is None:
            self.operator_approvals = set()
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    def to_dict(self):
        d = asdict(self)
        d["operator_approvals"] = list(self.operator_approvals)
        return d


# ============================================================
# NÚCLEO DA PONTE
# ============================================================

class PonteBritneyBTC:
    def __init__(self, network: str = "testnet"):
        self.btc_api = BitcoinAPI(network=network)
        
        # Endereço da ponte (você configura abaixo)
        self.bridge_btc_address = ""
        
        # Armazenamento
        self.deposits: Dict[str, BridgeDeposit] = {}
        self.withdrawals: Dict[str, BridgeWithdrawal] = {}
        self.processed_txids: Set[str] = set()
        
        # Saldo de wBTC na rede BRN
        self.wbtc_balances: Dict[str, float] = {}
        
        print(f"\n🌉 PONTE BRITNEY-BTC INICIALIZADA")
        print(f"   Versão: {BRIDGE_VERSION}")
        print(f"   Rede Bitcoin: {self.btc_api.network_name}")
        print(f"   Operadores: {len(BRIDGE_OPERATORS)} | Aprovações necessárias: {REQUIRED_APPROVALS}")
        print(f"   Taxa da ponte: {BRIDGE_FEE * 100:.2f}%")
        print(f"   ⚠️ Configure o endereço BTC da ponte antes de usar!")

    def set_bridge_address(self, btc_address: str) -> Dict:
        """Define o endereço Bitcoin que recebe os depósitos"""
        if not self.btc_api.validate_address_format(btc_address):
            return {"success": False, "message": "Formato de endereço BTC inválido"}
        
        self.bridge_btc_address = btc_address
        print(f"₿ Endereço da ponte configurado: {btc_address}")
        return {"success": True, "message": "Endereço da ponte configurado com sucesso"}

    # ========================================================
    # DEPÓSITO: BTC → wBTC
    # ========================================================
    
    def create_deposit_request(self, btc_sender_address: str, 
                               brn_receiver_address: str, 
                               amount_btc: float) -> Dict:
        """
        📋 Passo 1: Usuário quer enviar BTC → recebe endereço da ponte
        
        Retorna: Instruções de para onde enviar o BTC
        """
        if not self.bridge_btc_address:
            return {"success": False, "message": "Endereço da ponte não configurado"}
        
        # Validações
        if amount_btc < MIN_BTC_AMOUNT:
            return {"success": False, "message": f"Valor mínimo: {MIN_BTC_AMOUNT} BTC"}
        if not brn_receiver_address.startswith("brn1") or len(brn_receiver_address) != 44:
            return {"success": False, "message": "Endereço BRN inválido"}
        if not self.btc_api.validate_address_format(btc_sender_address):
            return {"success": False, "message": "Endereço BTC inválido"}
        
        # Calcula taxa
        fee = amount_btc * BRIDGE_FEE
        net_amount = round(amount_btc - fee, 8)
        
        # Cria solicitação
        request_id = f"DEP-{int(time.time() * 1000)}"
        
        deposit = BridgeDeposit(
            request_id=request_id,
            btc_address_from=btc_sender_address,
            brn_address_to=brn_receiver_address,
            expected_btc=amount_btc,
            net_wbtc=net_amount,
            fee=fee,
            bridge_btc_address=self.bridge_btc_address
        )
        
        self.deposits[request_id] = deposit
        
        print(f"\n🌉 NOVA SOLICITAÇÃO DE DEPÓSITO — {request_id}")
        print(f"   De: {btc_sender_address}")
        print(f"   Para: {brn_receiver_address[:16]}…")
        print(f"   Valor: {amount_btc:.8f} BTC → {net_amount:.8f} wBTC")
        print(f"   Enviar para: {self.bridge_btc_address}")
        
        return {
            "success": True,
            "request_id": request_id,
            "bridge_address": self.bridge_btc_address,
            "expected_amount": amount_btc,
            "net_amount": net_amount,
            "fee": fee,
            "instructions": (
                f"Envie {amount_btc} BTC para o endereço:\n"
                f"{self.bridge_btc_address}\n\n"
                f"Após enviar, cole o TXID da transação aqui para confirmar.\n"
                f"Você receberá {net_amount:.8f} wBTC na sua carteira BRN."
            )
        }

    def confirm_deposit(self, request_id: str, btc_txid: str, 
                         operator_brn_address: str) -> Dict:
        """
        ✅ Passo 2: Operador verifica transação e cunha wBTC
        
        O usuário te dá o TXID → você verifica na API → cunha wBTC
        """
        # Validações
        if request_id not in self.deposits:
            return {"success": False, "message": "Solicitação não encontrada"}
        if operator_brn_address not in BRIDGE_OPERATORS:
            return {"success": False, "message": "Operador não autorizado"}
        
        deposit = self.deposits[request_id]
        
        if btc_txid in self.processed_txids:
            return {"success": False, "message": "Esta transação já foi processada"}
        
        if deposit["status"] == "CONCLUIDO":
            return {"success": False, "message": "Depósito já foi confirmado"}
        
        # ✅ Verifica transação REAL na rede Bitcoin
        verification = self.btc_api.verify_payment(
            txid=btc_txid,
            expected_address=self.bridge_btc_address,
            expected_amount=deposit["expected_btc"],
            min_confirmations=BTC_CONFIRMATIONS
        )
        
        if not verification["success"]:
            return verification
        
        # Adiciona aprovação do operador
        deposit["operator_approvals"].add(operator_brn_address)
        deposit["btc_txid"] = btc_txid
        deposit["confirmations"] = verification["confirmations"]
        
        # Verifica se tem aprovações suficientes
        if len(deposit["operator_approvals"]) >= REQUIRED_APPROVALS:
            return self._mint_wbtc(deposit, verification)
        
        return {
            "success": True,
            "status": "aguardando_aprovar",
            "message": f"Pagamento confirmado! Aguardando mais aprovações: {len(deposit['operator_approvals'])}/{REQUIRED_APPROVALS}",
            "txid": btc_txid,
            "confirmations": verification["confirmations"],
            "approvals": len(deposit["operator_approvals"])
        }

    def _mint_wbtc(self, deposit: BridgeDeposit, verification: Dict) -> Dict:
        """Cunha wBTC na rede BRN"""
        deposit["status"] = "CONCLUIDO"
        self.processed_txids.add(deposit["btc_txid"])
        
        # Adiciona saldo wBTC
        dest = deposit["brn_address_to"]
        if dest not in self.wbtc_balances:
            self.wbtc_balances[dest] = 0.0
        self.wbtc_balances[dest] += deposit["net_wbtc"]
        
        print(f"\n🪙 wBTC CUNHADO COM SUCESSO!")
        print(f"   TXID BTC: {deposit['btc_txid']}")
        print(f"   Valor: {deposit['net_wbtc']:.8f} wBTC")
        print(f"   Destinatário: {dest[:16]}…")
        
        return {
            "success": True,
            "status": "concluido",
            "message": "✅ BTC confirmado! wBTC enviado para sua carteira.",
            "btc_txid": deposit["btc_txid"],
            "amount_received": verification["amount_received"],
            "wbtc_minted": deposit["net_wbtc"],
            "destination": dest
        }

    # ========================================================
    # SAQUE: wBTC → BTC
    # ========================================================
    
    def create_withdrawal_request(self, brn_sender_address: str, 
                                   btc_receiver_address: str,
                                   amount_wbtc: float) -> Dict:
        """
        🔥 Passo 1: Usuário queima wBTC para receber BTC real
        """
        # Validações
        if amount_wbtc < MIN_BTC_AMOUNT:
            return {"success": False, "message": f"Valor mínimo: {MIN_BTC_AMOUNT} wBTC"}
        if not self.btc_api.validate_address_format(btc_receiver_address):
            return {"success": False, "message": "Endereço BTC de destino inválido"}
        
        # Verifica saldo
        balance = self.wbtc_balances.get(brn_sender_address, 0.0)
        if balance < amount_wbtc:
            return {
                "success": False,
                "message": f"Saldo insuficiente: tem {balance:.8f} wBTC, quer queimar {amount_wbtc:.8f} wBTC"
            }
        
        # Calcula taxa
        fee = amount_wbtc * BRIDGE_FEE
        net_btc = round(amount_wbtc - fee, 8)
        
        # Queima o wBTC
        self.wbtc_balances[brn_sender_address] -= amount_wbtc
        if self.wbtc_balances[brn_sender_address] == 0:
            del self.wbtc_balances[brn_sender_address]
        
        # Cria solicitação
        request_id = f"SAQ-{int(time.time() * 1000)}"
        
        withdrawal = BridgeWithdrawal(
            request_id=request_id,
            brn_address_from=brn_sender_address,
            btc_address_to=btc_receiver_address,
            wbtc_burned=amount_wbtc,
            net_btc=net_btc,
            fee=fee
        )
        
        self.withdrawals[request_id] = withdrawal
        
        print(f"\n🔥 NOVA SOLICITAÇÃO DE SAQUE — {request_id}")
        print(f"   Queimado: {amount_wbtc:.8f} wBTC")
        print(f"   A receber: {net_btc:.8f} BTC")
        print(f"   Endereço BTC: {btc_receiver_address}")
        
        return {
            "success": True,
            "request_id": request_id,
            "message": "wBTC queimado. Aguardando operadores aprovarem a liberação de BTC.",
            "wbtc_burned": amount_wbtc,
            "btc_receive": net_btc,
            "fee": fee,
            "next_step": f"Os operadores precisam aprovar. Depois de aprovado, envie {net_btc:.8f} BTC de sua carteira da ponte para {btc_receiver_address}"
        }

    def approve_withdrawal(self, request_id: str, operator_brn_address: str) -> Dict:
        """
        ✅ Passo 2: Operadores aprovam o saque
        """
        if request_id not in self.withdrawals:
            return {"success": False, "message": "Solicitação não encontrada"}
        if operator_brn_address not in BRIDGE_OPERATORS:
            return {"success": False, "message": "Operador não autorizado"}
        
        withdrawal = self.withdrawals[request_id]
        
        if withdrawal["status"] == "CONCLUIDO":
            return {"success": False, "message": "Saque já foi concluído"}
        
        # Adiciona aprovação
        withdrawal["operator_approvals"].add(operator_brn_address)
        count = len(withdrawal["operator_approvals"])
        
        print(f"✓ Operador {operator_brn_address[:16]}… aprovou — {count}/{REQUIRED_APPROVALS}")
        
        if count >= REQUIRED_APPROVALS:
            withdrawal["status"] = "APROVADO"
            return {
                "success": True,
                "status": "aprovado",
                "message": f"✅ Saque APROVADO! Envie {withdrawal['net_btc']:.8f} BTC da carteira da ponte para:\n{withdrawal['btc_address_to']}",
                "btc_amount": withdrawal["net_btc"],
                "btc_destination": withdrawal["btc_address_to"],
                "request_id": request_id
            }
        
        return {
            "success": True,
            "status": "pendente",
            "message": f"Aguardando aprovações: {count}/{REQUIRED_APPROVALS}",
            "approvals": count,
            "required": REQUIRED_APPROVALS
        }

    def confirm_btc_sent(self, request_id: str, btc_txid: str, 
                          operator_brn_address: str) -> Dict:
        """
        ✅ Passo 3: Operador confirma que enviou o BTC
        
        Depois de enviar manualmente o BTC da carteira da ponte,
        registre o TXID aqui para concluir a operação.
        """
        if request_id not in self.withdrawals:
            return {"success": False, "message": "Solicitação não encontrada"}
        
        withdrawal = self.withdrawals[request_id]
        
        if withdrawal["status"] != "APROVADO":
            return {"success": False, "message": "Saque ainda não foi aprovado pelos operadores"}
        
        withdrawal["status"] = "CONCLUIDO"
        withdrawal["btc_txid"] = btc_txid
        self.processed_txids.add(btc_txid)
        
        print(f"🔓 SAQUE CONCLUÍDO! BTC enviado — TXID: {btc_txid}")
        
        return {
            "success": True,
            "message": "✅ Saque concluído! BTC enviado para o usuário.",
            "btc_txid": btc_txid,
            "btc_amount": withdrawal["net_btc"],
            "btc_destination": withdrawal["btc_address_to"]
        }

    # ========================================================
    # CONSULTAS
    # ========================================================
    
    def get_wbtc_balance(self, brn_address: str) -> Dict:
        """Consulta saldo de wBTC"""
        balance = self.wbtc_balances.get(brn_address, 0.0)
        return {
            "address": brn_address,
            "balance": balance,
            "token": "wBTC",
            "equivalent_btc": balance
        }

    def get_deposit_status(self, request_id: str) -> Dict:
        """Status de um depósito"""
        if request_id not in self.deposits:
            return {"error": "Solicitação não encontrada"}
        return self.deposits[request_id].to_dict()

    def get_withdrawal_status(self, request_id: str) -> Dict:
        """Status de um saque"""
        if request_id not in self.withdrawals:
            return {"error": "Solicitação não encontrada"}
        return self.withdrawals[request_id].to_dict()

    def get_stats(self) -> Dict:
        """Estatísticas gerais da ponte"""
        total_wbtc = sum(self.wbtc_balances.values())
        return {
            "version": BRIDGE_VERSION,
            "network": self.btc_api.network_name,
            "bridge_address": self.bridge_btc_address,
            "total_wbtc": total_wbtc,
            "active_deposits": len([d for d in self.deposits.values() if d["status"] != "CONCLUIDO"]),
            "active_withdrawals": len([w for w in self.withdrawals.values() if w["status"] != "CONCLUIDO"]),
            "operators": len(BRIDGE_OPERATORS),
            "required_approvals": REQUIRED_APPROVALS,
            "fee_rate": BRIDGE_FEE
        }
