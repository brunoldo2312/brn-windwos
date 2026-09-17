"""
bruno_coin.py — Versão P2P Pura (Sem Servidor Central)
========================================================
✅ Nenhum servidor central necessário
✅ Conexões diretas entre os nós
✅ Descoberta automática na rede local
✅ Conexão via IP público entre redes diferentes
✅ Cada nó conhece e se conecta a vários outros nós
"""

import hashlib
import time
import json
import sqlite3
import socket
import threading
import sys
import re

import webview

from cripto_wallet import WalletManager
from cripto_db import BlockchainDB
from cripto_p2p_network import AutoNodeDiscovery


# ============================================================
# CONFIGURAÇÕES
# ============================================================

COIN_NAME = "Bruno"
COIN_SYMBOL = "BRN"
VERSION = "3.0-p2p"

BLOCK_REWARD = 1.0

DIFFICULTY_ADJUSTMENT_INTERVAL = 5
TARGET_BLOCK_TIME = 10.0
MAX_TX_PER_BLOCK = 200
MAX_FUTURE_TIMESTAMP = 3600
MAX_PAST_TIMESTAMP = 86400 * 7
MAX_DIFFICULTY_CHANGE = 0.20

MONERO_FORK_NETWORK_ID = [
    0xAA, 0xBB, 0xCC, 0xDD,
    0x11, 0x22, 0x33, 0x44
]

# ----------------------------------------------------------------
# 📌 LISTA DE NÓS CONHECIDOS (SEED NODES)
# Você e seus amigos trocam IPs e portas entre si
# Adicione aqui os IPs públicos dos outros computadores
# Formato: ("IP", PORTA)
# Exemplo: [("200.10.20.30", 6001), ("187.20.30.40", 6001)]
# Deixe VAZIO se só usar rede local
# ----------------------------------------------------------------
SEED_NODES = [
    # ("IP_DO_AMIGO", 6001),   # ← adicione os IPs dos outros aqui
]

# Tempo entre tentativas de reconectar a nós conhecidos
SEED_RECONNECT_INTERVAL = 60  # segundos


# ============================================================
# BLOCO
# ============================================================

class BrunoBlock:
    def __init__(
        self,
        index,
        previous_hash,
        transactions,
        difficulty=4,
        nonce=0,
        timestamp=None,
        block_hash=None
    ):
        self.index = int(index)
        self.timestamp = float(timestamp) if timestamp is not None else time.time()
        self.previous_hash = str(previous_hash)

        if isinstance(transactions, list):
            self.transactions = transactions
        else:
            self.transactions = json.loads(transactions)

        self.difficulty = int(difficulty)
        self.nonce = int(nonce)
        self.network_id = MONERO_FORK_NETWORK_ID

        if block_hash:
            self.hash = str(block_hash)
        else:
            self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        return hashlib.sha256(json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "transactions": self.transactions,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "network_id": MONERO_FORK_NETWORK_ID
        }, sort_keys=True).encode()).hexdigest()

    def mine_block(self, stop_event=None):
        target = "0" * self.difficulty
        while self.hash[:self.difficulty] != target:
            if stop_event and stop_event.is_set():
                return False
            self.nonce += 1
            self.hash = self.calculate_hash()
        return True

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "transactions": self.transactions,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "hash": self.hash
        }


# ============================================================
# API PRINCIPAL — P2P PURA
# ============================================================

class CriptoAPI:
    def __init__(self, node_port):
        self.p2p_port = int(node_port)
        self.db_path = f"brn_node_{self.p2p_port}.db"
        self.db = BlockchainDB(self.db_path)

        # Mempool e peers
        self.mempool = []
        self.mempool_lock = threading.Lock()

        # Conjunto de peers conectados: (ip, porta)
        self.connected_peers = set()
        self.peers_lock = threading.Lock()

        # Lista de todos os nós conhecidos (conectados + descobertos + seeds)
        self.known_peers = set()  # formato "ip:porta"

        # Mineração
        self.is_mining = False
        self.mining_stop_event = threading.Event()
        self.miner_thread = None

        # Descoberta LAN automática
        self.discovery = AutoNodeDiscovery(p2p_port=self.p2p_port)

        # Inicialização
        self._init_database()
        self._load_seed_nodes()

        # Inicia threads
        self.server_running = True
        threading.Thread(target=self._start_p2p_server, daemon=True).start()
        threading.Thread(target=self._start_discovery_service, daemon=True).start()
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._cleanup_disconnected_peers, daemon=True).start()

        print(f"\n{'='*60}")
        print(f"  {COIN_NAME} Coin v{VERSION}")
        print(f"  Nó iniciado na porta {self.p2p_port}")
        print(f"  Modo: P2P Pura — Sem Servidor Central")
        print(f"{'='*60}\n")

    # ========================================================
    # CARREGAR NÓS CONHECIDOS
    # ========================================================

    def _load_seed_nodes(self):
        """Carrega os nós conhecidos da lista SEED_NODES"""
        for ip, port in SEED_NODES:
            if port != self.p2p_port or not self._is_local_ip(ip):
                self.known_peers.add(f"{ip}:{port}")
        if SEED_NODES:
            print(f"🌐 {len(SEED_NODES)} nó(s) conhecido(s) carregado(s)")

    def _is_local_ip(self, ip: str) -> bool:
        """Verifica se o IP é deste próprio computador"""
        local_ips = ["127.0.0.1", "localhost", self.discovery.local_ip]
        return ip in local_ips

    def _parse_peer_str(self, peer_str: str) -> tuple:
        """Converte 'ip:porta' para (ip, porta)"""
        try:
            ip, port = peer_str.rsplit(":", 1)
            return ip, int(port)
        except:
            return None, None

    # ========================================================
    # DESCOBERTA E MANUTENÇÃO DE PEERS
    # ========================================================

    def _start_discovery_service(self):
        time.sleep(1.5)
        self.discovery.run()

    def _peer_maintenance_loop(self):
        """
        Coração da rede P2P:
        - Descobre novos nós na LAN
        - Reconecta a nós conhecidos quando desconectado
        - Adiciona nós descobertos à lista de conhecidos
        """
        time.sleep(3)

        while self.server_running:
            try:
                # 1. Adiciona nós descobertos na LAN à lista de conhecidos
                discovered = self.discovery.get_discovered_peers()
                for peer_str in discovered:
                    if peer_str not in self.known_peers:
                        self.known_peers.add(peer_str)
                        print(f"✨ Novo nó descoberto na rede local: {peer_str}")

                # 2. Tenta conectar a nós conhecidos que estão desconectados
                for peer_str in list(self.known_peers):
                    ip, port = self._parse_peer_str(peer_str)
                    if not ip or not port:
                        continue

                    with self.peers_lock:
                        if (ip, port) in self.connected_peers:
                            continue  # já está conectado

                    # Tenta conectar
                    result = self.connect_and_sync(ip, port)
                    if result["status"] == "sucesso":
                        with self.peers_lock:
                            self.connected_peers.add((ip, port))
                        print(f"🔗 Conectado a {ip}:{port}")

            except Exception as e:
                print(f"⚠️ Erro na manutenção de peers: {e}")

            time.sleep(SEED_RECONNECT_INTERVAL)

    def _cleanup_disconnected_peers(self):
        """Remove peers que não respondem mais"""
        while self.server_running:
            time.sleep(30)
            # Aqui você poderia implementar um PING real
            # Por enquanto mantemos a lista como está
            pass

    # ========================================================
    # BANCO DE DADOS
    # ========================================================

    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    id_index INTEGER PRIMARY KEY,
                    timestamp REAL,
                    previous_hash TEXT,
                    transactions TEXT,
                    difficulty INTEGER,
                    nonce INTEGER,
                    hash TEXT
                )
            """)
            cursor.execute("SELECT COUNT(*) FROM blocks")
            count = cursor.fetchone()[0]

            if count == 0:
                genesis = BrunoBlock(
                    0, "0",
                    [{
                        "sender": "SISTEMA",
                        "receiver": "brn1111cd943fa71e1f91dcd62f52fc6138bc845ab",
                        "amount": 100000.0,
                        "is_genesis": True
                    }],
                    difficulty=4
                )
                genesis.mine_block()
                self.db.insert_block(genesis)
                print("🌱 Bloco gênese criado com sucesso!")

    # ========================================================
    # AJUSTE DE DIFICULDADE
    # ========================================================

    def _calculate_next_difficulty(self) -> int:
        chain = self.db.get_raw_chain()
        if not chain:
            return 4
        if len(chain) < DIFFICULTY_ADJUSTMENT_INTERVAL + 1:
            return chain[-1]["difficulty"]

        latest = chain[-1]
        if latest["index"] % DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
            return latest["difficulty"]

        prev_block = chain[-DIFFICULTY_ADJUSTMENT_INTERVAL]
        time_expected = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL
        time_taken = latest["timestamp"] - prev_block["timestamp"]
        current_diff = latest["difficulty"]

        if time_taken < time_expected / 2:
            new_diff = current_diff + 1
        elif time_taken > time_expected * 2:
            new_diff = max(1, current_diff - 1)
        else:
            new_diff = current_diff

        max_inc = max(1, int(current_diff * MAX_DIFFICULTY_CHANGE))
        new_diff = min(new_diff, current_diff + max_inc)
        new_diff = max(new_diff, current_diff - max_inc)
        return round(new_diff)

    def _get_difficulty_at_block(self, target_index: int) -> int:
        chain = self.db.get_raw_chain()
        if not chain or target_index <= 0:
            return 4
        if target_index >= len(chain):
            target_index = len(chain) - 1
        temp_diff = 4
        for i in range(1, target_index + 1):
            if i % DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
                prev_t = chain[i - DIFFICULTY_ADJUSTMENT_INTERVAL]["timestamp"]
                curr_t = chain[i]["timestamp"]
                half = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL / 2
                full = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL * 2
                if curr_t - prev_t < half:
                    temp_diff += 1
                elif curr_t - prev_t > full:
                    temp_diff = max(1, temp_diff - 1)
        return temp_diff

    def _get_balance_at_block(self, address: str, up_to_index: int) -> float:
        balance = 0.0
        chain = self.db.get_raw_chain()
        for block in chain:
            if block["index"] > up_to_index:
                break
            for tx in block["transactions"]:
                if tx.get("sender") == address:
                    balance -= float(tx.get("amount", 0))
                if tx.get("receiver") == address:
                    balance += float(tx.get("amount", 0))
        return balance

    # ========================================================
    # SERVIDOR P2P — RECEBE CONEXÕES DE OUTROS NÓS
    # ========================================================

    def _receive_all(self, sock, buffer_size=4096, max_size=10*1024*1024):
        data = b""
        try:
            sock.settimeout(None)
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    break
                data += chunk
                if len(data) > max_size:
                    raise ValueError("Pacote muito grande")
        except Exception:
            pass
        return data.decode("utf-8", errors="ignore")

    def _start_p2p_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.p2p_port))
        server.listen(10)
        server.settimeout(1.0)
        print(f"📡 Servidor P2P ouvindo na porta {self.p2p_port}")

        while self.server_running:
            try:
                conn, addr = server.accept()
                ip, port = addr

                # Adiciona à lista de conhecidos e conectados
                peer_str = f"{ip}:{port}"
                if not self._is_local_ip(ip):
                    with self.peers_lock:
                        self.known_peers.add(peer_str)
                        self.connected_peers.add((ip, port))
                    print(f"🔌 Conexão recebida de {ip}:{port}")

                # Processa mensagem
                data = self._receive_all(conn)
                self._process_message(data, ip, port)
                conn.close()

            except socket.timeout:
                continue
            except Exception as e:
                if self.server_running:
                    print(f"⚠️ Erro servidor: {e}")

        server.close()

    def _process_message(self, data: str, sender_ip: str, sender_port: int):
        """Processa mensagens recebidas de outros nós"""
        if not data:
            return

        try:
            if data == "GET_HEIGHT":
                chain = self.db.get_raw_chain()
                self._send_to_peer(sender_ip, sender_port, str(len(chain)))

            elif data == "GET_CHAIN":
                chain = self.db.get_raw_chain()
                self._send_to_peer(sender_ip, sender_port, json.dumps(chain))

            elif data.startswith("BROADCAST_TX:"):
                tx = json.loads(data.split(":", 1)[1])
                if self._verify_tx_structure(tx):
                    with self.mempool_lock:
                        if tx not in self.mempool:
                            self.mempool.append(tx)
                            print(f"📥 Transação recebida de {sender_ip}:{sender_port}")
                    # Repassa a transação para todos os outros nós (propagação)
                    self._propagate_transaction(tx, exclude=(sender_ip, sender_port))

            elif data.startswith("NEW_BLOCK:"):
                block_data = json.loads(data.split(":", 1)[1])
                ok, msg = self._validate_block(block_data)
                if ok:
                    # Verifica se já temos este bloco
                    chain = self.db.get_raw_chain()
                    if not any(b["hash"] == block_data["hash"] for b in chain):
                        self.db.insert_block(BrunoBlock(**block_data))
                        print(f"📦 Novo bloco recebido de {sender_ip}:{sender_port} — #{block_data['index']}")
                        # Repassa o bloco para todos os outros nós
                        self._propagate_block(block_data, exclude=(sender_ip, sender_port))
                else:
                    print(f"⚠️ Bloco de {sender_ip}:{sender_port} rejeitado: {msg}")

            elif data.startswith("SYNC_CHAIN:"):
                remote_chain = json.loads(data.split(":", 1)[1])
                result = self._resolve_consensus(remote_chain)
                print(f"🔄 Sincronização com {sender_ip}:{sender_port}: {result}")

        except Exception as e:
            print(f"⚠️ Erro ao processar mensagem de {sender_ip}:{sender_port}: {e}")

    def _send_to_peer(self, ip: str, port: int, message: str):
        """Envia uma mensagem para um peer específico"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((ip, port))
            s.sendall(message.encode("utf-8"))
            s.close()
            return True
        except Exception as e:
            with self.peers_lock:
                self.connected_peers.discard((ip, port))
            return False

    def _propagate_transaction(self, tx, exclude=None):
        """Envia uma transação para todos os nós conectados, exceto o remetente"""
        exclude = exclude or (None, None)
        msg = f"BROADCAST_TX:{json.dumps(tx)}"
        count = 0
        with self.peers_lock:
            for ip, port in list(self.connected_peers):
                if (ip, port) != exclude:
                    if self._send_to_peer(ip, port, msg):
                        count += 1
        if count > 0:
            print(f"📤 Transação propagada para {count} nó(s)")

    def _propagate_block(self, block_dict, exclude=None):
        """Envia um novo bloco para todos os nós conectados, exceto o remetente"""
        exclude = exclude or (None, None)
        msg = f"NEW_BLOCK:{json.dumps(block_dict)}"
        count = 0
        with self.peers_lock:
            for ip, port in list(self.connected_peers):
                if (ip, port) != exclude:
                    if self._send_to_peer(ip, port, msg):
                        count += 1
        if count > 0:
            print(f"📤 Bloco #{block_dict['index']} propagado para {count} nó(s)")

    # ========================================================
    # CONEXÃO COM OUTROS NÓS
    # ========================================================

    def connect_and_sync(self, ip: str, port: int) -> dict:
        """Conecta a um nó e sincroniza a blockchain"""
        try:
            # Pede altura da chain
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((ip, port))
            s.sendall(b"GET_HEIGHT")
            remote_height = int(s.recv(4096).decode("utf-8"))
            s.close()

            local_chain = self.db.get_raw_chain()
            local_height = len(local_chain)

            if remote_height <= local_height:
                return {"status": "sucesso", "message": "Já está atualizado"}

            # Pede a chain completa
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15.0)
            s.connect((ip, port))
            s.sendall(b"GET_CHAIN")
            remote_chain = json.loads(self._receive_all(s))
            s.close()

            with self.peers_lock:
                self.connected_peers.add((ip, port))
                self.known_peers.add(f"{ip}:{port}")

            result = self._resolve_consensus(remote_chain)
            return {"status": "sucesso", "message": result}

        except Exception as e:
            with self.peers_lock:
                self.connected_peers.discard((ip, port))
            return {"status": "erro", "message": str(e)}

    # ========================================================
    # VALIDAÇÕES
    # ========================================================

    def _validate_address(self, address: str):
        if not isinstance(address, str) or not address.startswith("brn1") or len(address) != 44:
            raise ValueError(f"Endereço inválido: {address}")
        try:
            int(address[4:], 16)
        except ValueError:
            raise ValueError("Caracteres hexadecimais inválidos")
        return True

    def _verify_tx_structure(self, tx: dict) -> bool:
        if not isinstance(tx, dict):
            return False
        if tx.get("sender") == "SISTEMA":
            allowed = {"sender", "receiver", "amount"}
            if tx.get("is_genesis"):
                allowed.add("is_genesis")
            if set(tx.keys()) != allowed:
                return False
            if not tx.get("is_genesis") and tx.get("amount") != BLOCK_REWARD:
                return False
            return True
        req = ["sender", "receiver", "amount", "public_key", "signature", "timestamp"]
        if not all(k in tx for k in req):
            return False
        try:
            amount = float(tx["amount"])
            if amount <= 0:
                return False
            self._validate_address(tx["sender"])
            self._validate_address(tx["receiver"])
            payload = {
                "sender": tx["sender"], "receiver": tx["receiver"],
                "amount": amount, "timestamp": tx["timestamp"]
            }
            return WalletManager.verify_signature(tx["public_key"], payload, tx["signature"])
        except Exception:
            return False

    def _validate_block(self, block_data: dict):
        try:
            block = BrunoBlock(**block_data)
        except Exception as e:
            return False, f"Bloco malformado: {e}"

        if block.calculate_hash() != block_data["hash"]:
            return False, "Hash inválido"
        diff = block.difficulty
        if diff < 1:
            return False, "Dificuldade inválida"
        if not block.hash.startswith("0" * diff):
            return False, "Prova de trabalho inválida"

        expected_diff = self._get_difficulty_at_block(block.index)
        if block.index > 0 and diff != expected_diff:
            return False, f"Dificuldade incorreta: esperada {expected_diff}, recebida {diff}"

        now = time.time()
        if block.timestamp > now + MAX_FUTURE_TIMESTAMP:
            return False, "Timestamp muito no futuro"
        if block.timestamp < now - MAX_PAST_TIMESTAMP:
            return False, "Timestamp muito antigo"

        txs = block.transactions
        if not isinstance(txs, list):
            return False, "Lista de transações inválida"
        if len(txs) > MAX_TX_PER_BLOCK:
            return False, f"Muitas transações no bloco: {len(txs)}"

        tx_hashes = set()
        for tx in txs:
            h = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
            if h in tx_hashes:
                return False, "Transação duplicada no bloco"
            tx_hashes.add(h)

        rewards = sum(1 for tx in txs if tx.get("sender") == "SISTEMA" and not tx.get("is_genesis"))
        if rewards > 1:
            return False, "Mais de uma recompensa no bloco"

        for tx in txs:
            if not self._verify_tx_structure(tx):
                return False, f"Transação inválida: {tx}"

        spent = {}
        for tx in txs:
            s = tx.get("sender")
            if s == "SISTEMA":
                continue
            spent[s] = spent.get(s, 0) + float(tx["amount"])
        for s, total in spent.items():
            bal = self._get_balance_at_block(s, block.index - 1)
            if bal < total:
                return False, f"Saldo insuficiente para {s}"

        return True, "OK"

    def _resolve_consensus(self, remote_chain: list) -> str:
        local = self.db.get_raw_chain()
        if len(remote_chain) <= len(local):
            return "Cadeia local já é mais longa ou igual"

        for i in range(1, len(remote_chain)):
            if remote_chain[i]["previous_hash"] != remote_chain[i-1]["hash"]:
                return "Cadeia remota corrompida — hashes não encadeiam"

        for block in remote_chain:
            ok, msg = self._validate_block(block)
            if not ok:
                return f"Bloco inválido: {msg}"

        self.db.replace_chain(remote_chain)
        print(f"🔄 Blockchain sincronizada — {len(remote_chain)} blocos")
        return f"Sincronizado com sucesso: {len(remote_chain)} blocos"

    # ========================================================
    # INTERFACE PÚBLICA
    # ========================================================

    def get_full_chain(self):
        with self.mempool_lock:
            mem_size = len(self.mempool)
        chain = self.db.get_raw_chain()
        return {
            "chain": chain,
            "length": len(chain),
            "mempool_size": mem_size,
            "is_mining": self.is_mining,
            "difficulty": chain[-1]["difficulty"] if chain else 4,
            "reward": BLOCK_REWARD,
            "symbol": COIN_SYMBOL,
            "peers_connected": len(self.connected_peers),
            "peers_known": len(self.known_peers),
            "known_peers": sorted(self.known_peers)
        }

    def get_network_status(self):
        return {
            "connected_peers": [f"{i}:{p}" for i, p in self.connected_peers],
            "known_peers": sorted(self.known_peers),
            "discovered_lan": self.discovery.get_discovered_peers(),
            "local_endpoint": self.discovery.get_local_endpoint(),
            "is_mining": self.is_mining
        }

    def add_peer_manually(self, ip: str, port: int):
        """Adiciona um nó conhecido manualmente pela interface"""
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError("Porta inválida")
            peer_str = f"{ip}:{port}"
            self.known_peers.add(peer_str)
            print(f"➕ Nó adicionado manualmente: {peer_str}")
            # Tenta conectar imediatamente
            threading.Thread(target=self.connect_and_sync, args=(ip, port), daemon=True).start()
            return {"status": "sucesso", "message": f"Nó {ip}:{port} adicionado"}
        except Exception as e:
            return {"status": "erro", "message": str(e)}

    def generate_wallet(self):
        return WalletManager.generate_keypair()

    def get_balance(self, address: str):
        try:
            self._validate_address(address)
            bal = 0.0
            for block in self.db.get_raw_chain():
                for tx in block["transactions"]:
                    if tx.get("sender") == address:
                        bal -= float(tx.get("amount", 0))
                    if tx.get("receiver") == address:
                        bal += float(tx.get("amount", 0))
            return {"address": address, "balance": bal}
        except ValueError as e:
            return {"status": "erro", "message": str(e)}

    def send_funds(self, sender, receiver, amount, secret_key, public_key):
        try:
            self._validate_address(sender)
            self._validate_address(receiver)
            amount = float(amount)
            if amount <= 0:
                return {"status": "erro", "message": "Valor inválido"}
            if self.get_balance(sender)["balance"] < amount:
                return {"status": "erro", "message": "Saldo insuficiente"}

            payload = {
                "sender": sender, "receiver": receiver,
                "amount": amount, "timestamp": time.time()
            }
            signature = WalletManager.sign_transaction(secret_key, payload)
            tx = {**payload, "public_key": public_key, "signature": signature}

            with self.mempool_lock:
                if tx not in self.mempool:
                    self.mempool.append(tx)

            # Propaga para todos os nós conectados
            self._propagate_transaction(tx)
            return {"status": "sucesso", "message": "Transação enviada e propagada!"}
        except Exception as e:
            return {"status": "erro", "message": str(e)}

    # ========================================================
    # MINERAÇÃO
    # ========================================================

    def toggle_mining(self, miner_address: str):
        if self.is_mining:
            self.is_mining = False
            self.mining_stop_event.set()
            return {"status": "sucesso", "message": "Mineração parada", "mining": False}
        try:
            self._validate_address(miner_address)
            self.is_mining = True
            self.mining_stop_event.clear()
            self.miner_thread = threading.Thread(
                target=self._mining_loop,
                args=(miner_address,), daemon=True
            )
            self.miner_thread.start()
            return {"status": "sucesso", "message": "Mineração iniciada!", "mining": True}
        except Exception as e:
            return {"status": "erro", "message": str(e)}

    def _mining_loop(self, miner_address: str):
        print(f"⛏️ Mineração iniciada para: {miner_address}")
        while self.is_mining and not self.mining_stop_event.is_set():
            try:
                chain = self.db.get_raw_chain()
                if not chain:
                    time.sleep(1)
                    continue

                last = chain[-1]
                next_diff = self._calculate_next_difficulty()

                reward_tx = {
                    "sender": "SISTEMA",
                    "receiver": miner_address,
                    "amount": BLOCK_REWARD
                }

                with self.mempool_lock:
                    seen = set()
                    unique = []
                    for tx in self.mempool:
                        h = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
                        if h not in seen:
                            seen.add(h)
                            unique.append(tx)
                    pending = unique[:MAX_TX_PER_BLOCK]

                new_block = BrunoBlock(
                    index=last["index"] + 1,
                    previous_hash=last["hash"],
                    transactions=[reward_tx] + pending,
                    difficulty=next_diff
                )

                print(f"⛏️ Minerando bloco #{new_block.index} (dificuldade: {next_diff})...")
                if new_block.mine_block(self.mining_stop_event):
                    block_dict = new_block.to_dict()
                    print(f"\n🎉 BLOCO MINERADO! #{new_block.index}")
                    print(f"    Hash: {new_block.hash[:30]}...")
                    print(f"    Recompensa: {BLOCK_REWARD} {COIN_SYMBOL}")

                    # Salva localmente
                    self.db.insert_block(new_block)

                    # Limpa transações mineradas da mempool
                    with self.mempool_lock:
                        mined_tx_hashes = set(
                            hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()
                            for t in new_block.transactions
                            if t["sender"] != "SISTEMA"
                        )
                        self.mempool = [
                            t for t in self.mempool
                            if hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()
                            not in mined_tx_hashes
                        ]

                    # ✅ Propaga o bloco para TODOS os outros nós conectados
                    self._propagate_block(block_dict)

            except Exception as e:
                print(f"⚠️ Erro na mineração: {e}")
                time.sleep(2)

        print("🛑 Mineração encerrada")


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    port = 6001
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"⚠️ Porta inválida, usando {port}")

    api = CriptoAPI(node_port=port)

    webview.create_window(
        title=f"{COIN_NAME} Coin v{VERSION} — Porta {port}",
        url="index.html",
        js_api=api,
        width=900,
        height=700,
        resizable=True
    )

    webview.start()

    # Encerramento limpo
    api.server_running = False
    if hasattr(api, 'discovery'):
        api.discovery.stop()

    print("\n👋 Programa encerrado")
