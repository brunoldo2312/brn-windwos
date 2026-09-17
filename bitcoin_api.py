"""
bitcoin_api.py — Conexão com Rede Bitcoin (SEM BAIXAR BLOCKCHAIN!)
=====================================================================
✅ Usa APIs públicas gratuitas: Blockstream.info e Mempool.space
✅ Verifica transações, saldos e confirmações
✅ Funciona em Testnet e Mainnet
✅ Sem necessidade de nó Bitcoin
"""

import requests
import time
from typing import Dict, List, Optional, Tuple, Union


class BitcoinAPI:
    def __init__(self, network: str = "testnet"):
        """
        Inicializa a API do Bitcoin
        
        Args:
            network: "testnet" ou "mainnet"
        """
        self.network = network.lower()
        
        # URLs das APIs públicas
        if self.network == "testnet":
            self.apis = [
                "https://blockstream.info/testnet/api/",
                "https://mempool.space/testnet/api/"
            ]
        else:
            self.apis = [
                "https://blockstream.info/api/",
                "https://mempool.space/api/"
            ]
        
        self.network_name = "Bitcoin Testnet" if self.network == "testnet" else "Bitcoin Mainnet"
        print(f"₿ Bitcoin API inicializado — {self.network_name}")
        print(f"   ✅ Usando APIs públicas — sem baixar blockchain!")

    def _get(self, endpoint: str, max_tries: int = 2) -> Dict:
        """Faz requisição GET com fallback entre APIs"""
        last_error = None
        for api_url in self.apis:
            url = api_url + endpoint
            for _ in range(max_tries):
                try:
                    resp = requests.get(url, timeout=15)
                    resp.raise_for_status()
                    try:
                        return resp.json()
                    except:
                        return resp.text
                except Exception as e:
                    last_error = e
                    time.sleep(1)
        raise Exception(f"Falha ao conectar: {last_error}")

    # ========================================================
    # INFORMAÇÕES DA REDE
    # ========================================================
    
    def get_blockchain_info(self) -> Dict:
        """Retorna informações básicas da rede"""
        try:
            tip_hash = self._get("blocks/tip/hash")
            block = self._get(f"block/{tip_hash}")
            return {
                "network": self.network,
                "blocks": block.get("height", 0),
                "bestblockhash": tip_hash.strip() if isinstance(tip_hash, str) else tip_hash,
                "status": "online"
            }
        except Exception as e:
            return {"network": self.network, "status": "offline", "error": str(e)}

    # ========================================================
    # ENDEREÇOS E SALDOS
    # ========================================================
    
    def get_address(self, address: str) -> Dict:
        """Retorna informações de um endereço"""
        try:
            data = self._get(f"address/{address}")
            chain_stats = data.get("chain_stats", {})
            mempool_stats = data.get("mempool_stats", {})
            
            funded = chain_stats.get("funded_txo_sum", 0)
            spent = chain_stats.get("spent_txo_sum", 0)
            funded_mem = mempool_stats.get("funded_txo_sum", 0)
            
            return {
                "address": address,
                "balance": (funded - spent) / 1e8,
                "unconfirmed_balance": funded_mem / 1e8,
                "tx_count": chain_stats.get("tx_count", 0),
                "status": "active"
            }
        except Exception as e:
            return {"error": str(e), "address": address}

    # ========================================================
    # TRANSAÇÕES
    # ========================================================
    
    def get_transaction(self, txid: str) -> Dict:
        """Busca uma transação pelo ID"""
        try:
            tx = self._get(f"tx/{txid}")
            status = tx.get("status", {})
            
            outputs = []
            for vout in tx.get("vout", []):
                outputs.append({
                    "address": vout.get("scriptpubkey_address", ""),
                    "value": vout.get("value", 0) / 1e8
                })
            
            return {
                "txid": tx.get("txid", ""),
                "confirmations": status.get("block_height", 0) if status.get("confirmed") else 0,
                "block_time": status.get("block_time", 0),
                "fee": tx.get("fee", 0) / 1e8,
                "outputs": outputs,
                "vin_count": len(tx.get("vin", [])),
                "status": "confirmed" if status.get("confirmed") else "pending"
            }
        except Exception as e:
            return {"error": str(e), "txid": txid}

    def verify_payment(self, txid: str, expected_address: str, 
                       expected_amount: float, min_confirmations: int = 1) -> Dict:
        """
        ✅ Verifica se um pagamento foi feito corretamente
        
        Uso: Você pede o TXID para o usuário, verifica aqui se ele realmente
        enviou o valor correto para o endereço da ponte.
        """
        tx = self.get_transaction(txid)
        
        if "error" in tx:
            return {
                "success": False,
                "status": "error",
                "message": f"Transação não encontrada: {tx['error']}"
            }
        
        if tx["confirmations"] < min_confirmations:
            return {
                "success": False,
                "status": "pending",
                "message": f"Aguardando confirmações: {tx['confirmations']}/{min_confirmations}",
                "confirmations": tx["confirmations"],
                "required": min_confirmations
            }
        
        total_received = 0.0
        for out in tx["outputs"]:
            if out.get("address") == expected_address:
                total_received += out.get("value", 0)
        
        if total_received < expected_amount:
            return {
                "success": False,
                "status": "amount_mismatch",
                "message": f"Valor incorreto: esperado {expected_amount} BTC, recebido {total_received} BTC",
                "expected": expected_amount,
                "received": total_received
            }
        
        return {
            "success": True,
            "status": "confirmed",
            "message": "✅ Pagamento confirmado!",
            "txid": txid,
            "amount_received": total_received,
            "confirmations": tx["confirmations"],
            "block_time": tx["block_time"]
        }

    # ========================================================
    # UTILITÁRIOS
    # ========================================================
    
    @staticmethod
    def validate_address_format(address: str) -> bool:
        """Valida formato básico de endereço Bitcoin"""
        if not address or len(address) < 26 or len(address) > 90:
            return False
        invalid_chars = ['O', 'I', 'l', '0']
        return not any(c in address for c in invalid_chars) and address.isalnum()
    
    @staticmethod
    def format_btc(amount: float) -> str:
        """Formata valor em BTC"""
        return f"{amount:.8f} BTC"
