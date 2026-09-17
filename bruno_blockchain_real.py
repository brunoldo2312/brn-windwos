import hashlib
import time
import json
import sqlite3
import secrets
import socket
import threading
import sys

import webview

from cripto_wallet import WalletManager
from cripto_db import BlockchainDB
# CORRIGIDO: AutoPortForwarder não existe no projeto — import comentado
# from cripto_p2p_network import AutoPortForwarder


# ============================================================
# CONFIGURAÇÃO DA MOEDA
# ============================================================

COIN_NAME = "Bruno"
COIN_SYMBOL = "BRN"

# ============================================================
# RECOMPENSA DE MINERAÇÃO
# ============================================================

BLOCK_REWARD = 1.0

# ============================================================
# CONFIGURAÇÃO DA MINERAÇÃO
# ============================================================

DIFFICULTY_ADJUSTMENT_INTERVAL = 5
TARGET_BLOCK_TIME = 10.0
MAX_TX_PER_BLOCK = 200          # ✅ NOVO: Limite de transações por bloco
MAX_FUTURE_TIMESTAMP = 3600     # ✅ NOVO: Máx 1h no futuro
MAX_PAST_TIMESTAMP = 86400 * 7  # ✅ NOVO: Máx 7 dias no passado
MAX_DIFFICULTY_CHANGE = 0.20    # ✅ NOVO: Máx ±20% por ajuste

# ============================================================
# IDENTIFICAÇÃO DA REDE
# ============================================================

MONERO_FORK_NETWORK_ID = [
    0xAA,
    0xBB,
    0xCC,
    0xDD,
    0x11,
    0x22,
    0x33,
    0x44
]

# ============================================================
# PEERS INICIAIS
# ============================================================

BOOTSTRAP_PEERS = [
    ("192.168.0.17", 6001)
]


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
        self.timestamp = (
            float(timestamp)
            if timestamp is not None
            else time.time()
        )
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
        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "previous_hash": self.previous_hash,
                "transactions": self.transactions,
                "difficulty": self.difficulty,
                "nonce": self.nonce,
                "network_id": self.network_id
            },
            sort_keys=True
        ).encode()
        return hashlib.sha256(block_string).hexdigest()


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
# API PRINCIPAL
# ============================================================

class CriptoAPI:

    def __init__(self, node_port):
        self.p2p_port = int(node_port)
        self.db_path = f"blockchain_node_{self.p2p_port}.db"
        self.db = BlockchainDB(self.db_path)
        self.mempool = []
        self.mempool_lock = threading.Lock()
        self.connected_peers = set()
        self.is_mining = False
        self.mining_stop_event = threading.Event()
        self.miner_thread = None
        self._init_database()

        self.server_thread = threading.Thread(
            target=self._start_p2p_server,
            daemon=True
        )
        self.server_thread.start()

        threading.Thread(
            target=self._run_bootstrap_discovery,
            daemon=True
        ).start()


    # ========================================================
    # BANCO DE DADOS / GÊNESIS
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
                    0,
                    "0",
                    [
                        {
                            "sender": "SISTEMA",
                            "receiver": "brn1111cd943fa71e1f91dcd62f52fc6138bc845ab",
                            "amount": 100000.0,
                            "is_genesis": True  # ✅ NOVO: Marca transação de gênese
                        }
                    ],
                    difficulty=4
                )
                genesis.mine_block()
                self.db.insert_block(genesis)


    def get_p2p_port(self):
        return self.p2p_port


    # ========================================================
    # ✅ AJUSTE DE DIFICULDADE — MELHORADO
    # ========================================================

    def _calculate_next_difficulty(self) -> int:
        chain = self.db.get_raw_chain()
        if not chain:
            return 4
        if len(chain) < DIFFICULTY_ADJUSTMENT_INTERVAL + 1:
            return chain[-1]["difficulty"]

        latest_block = chain[-1]

        if latest_block["index"] % DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
            return latest_block["difficulty"]

        prev_adjustment_block = chain[-DIFFICULTY_ADJUSTMENT_INTERVAL]
        time_expected = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL
        time_taken = latest_block["timestamp"] - prev_adjustment_block["timestamp"]
        current_diff = latest_block["difficulty"]

        # ✅ Melhorado: com limite de variação
        if time_taken < (time_expected / 2):
            new_diff = current_diff + 1
        elif time_taken > (time_expected * 2):
            new_diff = max(1, current_diff - 1)
        else:
            new_diff = current_diff

        # ✅ NOVO: Limite de variação máxima por ajuste
        max_inc = max(1, int(current_diff * MAX_DIFFICULTY_CHANGE))
        new_diff = min(new_diff, current_diff + max_inc)
        new_diff = max(new_diff, current_diff - max_inc)

        return round(new_diff)


    # ========================================================
    # ✅ OBTER DIFICULDADE ESPERADA PARA UM BLOCO
    # ========================================================

    def _get_difficulty_at_block(self, target_index: int) -> int:
        """Retorna a dificuldade que deveria ter em um dado índice"""
        chain = self.db.get_raw_chain()
        if not chain or target_index <= 0:
            return 4
        if target_index >= len(chain):
            target_index = len(chain) - 1

        temp_diff = 4
        for i in range(1, target_index + 1):
            if i % DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
                prev_time = chain[i - DIFFICULTY_ADJUSTMENT_INTERVAL]["timestamp"]
                curr_time = chain[i]["timestamp"]
                time_expected = TARGET_BLOCK_TIME * DIFFICULTY_ADJUSTMENT_INTERVAL
                if curr_time - prev_time < time_expected / 2:
                    temp_diff += 1
                elif curr_time - prev_time > time_expected * 2:
                    temp_diff = max(1, temp_diff - 1)
        return temp_diff


    # ========================================================
    # ✅ SALDO EM UM DADO PONTO DA CADEIA
    # ========================================================

    def _get_balance_at_block(self, address: str, up_to_index: int) -> float:
        """Calcula saldo de um endereço até um índice de bloco"""
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
    # REDE P2P — RECEBER DADOS
    # ========================================================

    def _receive_all(self, sock, buffer_size=4096, max_size=10 * 1024 * 1024):
        data = b""
        try:
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    break
                data += chunk
                if len(data) > max_size:
                    raise ValueError(f"Mensagem excede tamanho maximo de {max_size} bytes")
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Erro ao receber dados: {e}")
        return data.decode("utf-8", errors="ignore")


    # ========================================================
    # SERVIDOR P2P
    # ========================================================

    def _start_p2p_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(("0.0.0.0", self.p2p_port))
        server_socket.listen(10)
        print(f"[P2P] Servidor iniciado na porta {self.p2p_port}")

        while True:
            client_conn = None
            try:
                client_conn, client_addr = server_socket.accept()
                client_conn.settimeout(5.0)
                data = self._receive_all(client_conn)

                if client_addr[0] != "127.0.0.1":
                    self.connected_peers.add((client_addr[0], self.p2p_port))

                if data == "GET_HEIGHT":
                    chain = self.db.get_raw_chain()
                    client_conn.sendall(str(len(chain)).encode("utf-8"))

                elif data == "GET_CHAIN":
                    chain = self.db.get_raw_chain()
                    client_conn.sendall(json.dumps(chain).encode("utf-8"))

                elif data.startswith("BROADCAST_TX:"):
                    tx_data = json.loads(data.split(":", 1)[1])
                    if self._verify_tx_structure(tx_data):
                        with self.mempool_lock:
                            if tx_data not in self.mempool:
                                self.mempool.append(tx_data)

                elif data.startswith("SYNC_CHAIN:"):
                    incoming_chain = json.loads(data.split(":", 1)[1])
                    self._resolve_consensus(incoming_chain)

            except Exception:
                pass
            finally:
                if client_conn:
                    try:
                        client_conn.close()
                    except Exception:
                        pass


    # ========================================================
    # DESCOBERTA DE PEERS
    # ========================================================

    def _run_bootstrap_discovery(self):
        time.sleep(2)
        for ip, port in BOOTSTRAP_PEERS:
            if port == self.p2p_port:
                continue
            try:
                self.connect_and_sync(ip, port)
            except Exception:
                pass


    # ========================================================
    # BROADCAST DE TRANSAÇÃO
    # ========================================================

    def _broadcast_transaction_to_network(self, tx):
        for ip, port in list(self.connected_peers):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((ip, int(port)))
                payload = "BROADCAST_TX:" + json.dumps(tx)
                s.sendall(payload.encode("utf-8"))
                s.close()
            except Exception:
                self.connected_peers.discard((ip, port))


    # ========================================================
    # CONEXÃO E SINCRONIZAÇÃO
    # ========================================================

    def connect_and_sync(self, ip, port):
        try:
            s_height = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s_height.settimeout(3.0)
            s_height.connect((ip, int(port)))
            s_height.sendall(b"GET_HEIGHT")
            remote_height = int(s_height.recv(1024).decode("utf-8"))
            s_height.close()

            local_chain = self.db.get_raw_chain()
            if remote_height <= len(local_chain):
                return {"status": "sucesso", "message": "Sua blockchain ja esta atualizada."}

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10.0)
            client_socket.connect((ip, int(port)))
            client_socket.sendall(b"GET_CHAIN")
            response = self._receive_all(client_socket)
            client_socket.close()

            self.connected_peers.add((ip, int(port)))
            remote_chain = json.loads(response)

            return {
                "status": "sucesso",
                "message": self._resolve_consensus(remote_chain)
            }
        except Exception as e:
            return {"status": "erro", "message": str(e)}


    # ========================================================
    # VALIDAÇÃO DE ENDEREÇO
    # ========================================================

    def _validate_address(self, address):
        if (
            not isinstance(address, str)
            or not address.startswith("brn1")
            or len(address) != 44
        ):
            raise ValueError(f"Tamanho ou formato de endereco invalido: {address}")
        try:
            int(address[4:], 16)
        except ValueError:
            raise ValueError("Endereco contem caracteres hexadecimais invalidos")
        return True


    # ========================================================
    # ✅ VALIDAÇÃO DE TRANSAÇÃO — MELHORADA
    # ========================================================

    def _verify_tx_structure(self, tx):
        if not isinstance(tx, dict):
            return False

        # ✅ CORRIGIDO: Transações de sistema SÓ são permitidas nestes casos
        if tx.get("sender") == "SISTEMA":
            allowed_keys = {"sender", "receiver", "amount"}
            if tx.get("is_genesis"):
                allowed_keys.add("is_genesis")
            if set(tx.keys()) != allowed_keys:
                return False
            # ✅ A transação de recompensa DEVE ter valor exato de BLOCK_REWARD
            if not tx.get("is_genesis") and tx.get("amount") != BLOCK_REWARD:
                return False
            return True

        required_keys = [
            "sender", "receiver", "amount",
            "public_key", "signature", "timestamp"
        ]
        if not all(key in tx for key in required_keys):
            return False

        try:
            amount = float(tx["amount"])
            if amount <= 0:
                return False
            self._validate_address(tx["sender"])
            self._validate_address(tx["receiver"])

            payload = {
                "sender": tx["sender"],
                "receiver": tx["receiver"],
                "amount": amount,
                "timestamp": tx["timestamp"]
            }
            return WalletManager.verify_signature(
                tx["public_key"], payload, tx["signature"]
            )
        except Exception:
            return False


    # ========================================================
    # ✅ VALIDAÇÃO DE BLOCO — COMPLETAMENTE REVISADA
    # ========================================================

    def _validate_block(self, block_data):
        try:
            block = BrunoBlock(
                block_data["index"],
                block_data["previous_hash"],
                block_data["transactions"],
                block_data["difficulty"],
                block_data["nonce"],
                block_data["timestamp"],
                block_data["hash"]
            )
        except Exception as e:
            return False, f"Bloco malformado: {e}"

        # ✅ Verifica hash
        if block.calculate_hash() != block_data["hash"]:
            return False, "Hash nao corresponde"

        # ✅ Verifica prova de trabalho
        difficulty = int(block_data["difficulty"])
        if difficulty < 1:
            return False, "Dificuldade invalida"
        target = "0" * difficulty
        if not block_data["hash"].startswith(target):
            return False, "Prova de Trabalho invalida"

        # ✅ NOVO: Verifica se dificuldade é a esperada
        expected_diff = self._get_difficulty_at_block(block_data["index"])
        if block_data["index"] > 0 and difficulty != expected_diff:
            return False, f"Dificuldade incorreta: esperada {expected_diff}, recebida {difficulty}"

        # ✅ NOVO: Valida timestamp
        now = time.time()
        ts = block_data["timestamp"]
        if ts > now + MAX_FUTURE_TIMESTAMP:
            return False, "Timestamp muito no futuro"
        if ts < now - MAX_PAST_TIMESTAMP:
            return False, "Timestamp muito antigo"

        # ✅ NOVO: Limite de transações por bloco
        transactions = block_data["transactions"]
        if not isinstance(transactions, list):
            return False, "Lista de transacoes invalida"
        if len(transactions) > MAX_TX_PER_BLOCK:
            return False, f"Bloco muito grande: {len(transactions)} transacoes (max: {MAX_TX_PER_BLOCK})"

        # ✅ NOVO: Verifica transações duplicadas no bloco
        tx_hashes = set()
        for tx in transactions:
            tx_hash = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
            if tx_hash in tx_hashes:
                return False, "Transacao duplicada no bloco"
            tx_hashes.add(tx_hash)

        # ✅ NOVO: Apenas UMA transação de recompensa por bloco
        reward_count = sum(
            1 for tx in transactions
            if tx.get("sender") == "SISTEMA" and not tx.get("is_genesis")
        )
        if reward_count > 1:
            return False, f"Mais de uma recompensa por bloco: {reward_count}"

        # ✅ Valida estrutura de cada transação
        for tx in transactions:
            if not self._verify_tx_structure(tx):
                return False, f"Transacao invalida detectada no bloco: {tx}"

        # ✅ NOVO: Verifica saldo suficiente para cada transação
        temp_spent = {}
        for tx in transactions:
            sender = tx.get("sender")
            if sender == "SISTEMA":
                continue
            temp_spent[sender] = temp_spent.get(sender, 0) + float(tx["amount"])

        for sender, total_spent in temp_spent.items():
            balance = self._get_balance_at_block(sender, block_data["index"] - 1)
            if balance < total_spent:
                return False, f"Saldo insuficiente: {sender} tem {balance:.8f}, precisa de {total_spent:.8f}"

        return True, "OK"


    # ========================================================
    # CONSENSO
    # ========================================================

    def _resolve_consensus(self, remote_chain):
        local_chain = self.db.get_raw_chain()

        if len(remote_chain) <= len(local_chain):
            return "Cadeia local ja e dominante."
        if not remote_chain:
            return "Cadeia remota vazia."

        # Verifica ligação dos blocos
        for i in range(1, len(remote_chain)):
            if remote_chain[i]["previous_hash"] != remote_chain[i - 1]["hash"]:
                return "Hashes corrompidos na cadeia remota."

        # Valida todos os blocos
        for block_data in remote_chain:
            is_valid, message = self._validate_block(block_data)
            if not is_valid:
                return f"Bloco #{block_data['index']} rejeitado: {message}"

        # Substitui cadeia local
        self.db.replace_chain(remote_chain)
        return f"Sincronizado com sucesso para {len(remote_chain)} blocos."


    # ========================================================
    # INFORMAÇÕES DA BLOCKCHAIN
    # ========================================================

    def get_full_chain(self):
        with self.mempool_lock:
            mempool_size = len(self.mempool)
        chain = self.db.get_raw_chain()
        return {
            "chain": chain,
            "length": len(chain),
            "mempool_size": mempool_size,
            "is_mining": self.is_mining,
            "current_difficulty": (
                chain[-1]["difficulty"] if chain else 4
            ),
            "block_reward": BLOCK_REWARD,
            "coin": COIN_SYMBOL
        }


    # ========================================================
    # GERAR CARTEIRA
    # ========================================================

    def generate_wallet(self):
        return WalletManager.generate_keypair()


    # ========================================================
    # CONSULTAR SALDO
    # ========================================================

    def get_balance(self, address):
        try:
            self._validate_address(address)
            balance = 0.0
            chain = self.db.get_raw_chain()
            for block in chain:
                for tx in block["transactions"]:
                    if tx.get("sender") == address:
                        balance -= float(tx.get("amount", 0))
                    if tx.get("receiver") == address:
                        balance += float(tx.get("amount", 0))
            return {"address": address, "balance": balance}
        except ValueError as e:
            return {"status": "erro", "message": str(e)}


    # ========================================================
    # ENVIO DE FUNDOS
    # ========================================================

    def send_funds(self, sender, receiver, amount, spend_secret_key, public_key):
        try:
            self._validate_address(sender)
            self._validate_address(receiver)
            amount = float(amount)
            if amount <= 0:
                return {"status": "erro", "message": "Quantia invalida."}

            sender_balance = self.get_balance(sender).get("balance", 0)
            if sender_balance < amount:
                return {"status": "erro", "message": "Saldo insuficiente!"}

            tx_payload = {
                "sender": str(sender).strip(),
                "receiver": str(receiver).strip(),
                "amount": amount,
                "timestamp": time.time()
            }

            signature = WalletManager.sign_transaction(
                spend_secret_key, tx_payload
            )

            full_tx = {
                **tx_payload,
                "public_key": public_key,
                "signature": signature
            }

            with self.mempool_lock:
                if full_tx not in self.mempool:
                    self.mempool.append(full_tx)

            threading.Thread(
                target=self._broadcast_transaction_to_network,
                args=(full_tx,),
                daemon=True
            ).start()

            return {
                "status": "sucesso",
                "message": "Transacao assinada e enviada a mempool!"
            }
        except Exception as e:
            return {"status": "erro", "message": str(e)}


    # ========================================================
    # CONTROLE DA MINERAÇÃO
    # ========================================================

    def toggle_continuous_mining(self, miner_address):
        if self.is_mining:
            self.is_mining = False
            self.mining_stop_event.set()
            return {
                "status": "sucesso",
                "message": "Mineracao continua pausada.",
                "is_mining": False
            }
        try:
            self._validate_address(miner_address)
            self.is_mining = True
            self.mining_stop_event.clear()
            self.miner_thread = threading.Thread(
                target=self._continuous_mining_loop,
                args=(miner_address,),
                daemon=True
            )
            self.miner_thread.start()
            return {
                "status": "sucesso",
                "message": "Mineracao continua iniciada!",
                "is_mining": True,
                "block_reward": BLOCK_REWARD
            }
        except Exception as e:
            return {"status": "erro", "message": str(e)}


    # ========================================================
    # ✅ LOOP DE MINERAÇÃO — MELHORADO
    # ========================================================

    def _continuous_mining_loop(self, miner_address):
        print(f"⛏️ Loop de mineracao ativo para: {miner_address}")
        print(f"💰 Recompensa por bloco: {BLOCK_REWARD:.8f} {COIN_SYMBOL}")

        while self.is_mining and not self.mining_stop_event.is_set():
            try:
                local_chain = self.db.get_raw_chain()
                if not local_chain:
                    time.sleep(1)
                    continue

                last_block = local_chain[-1]
                next_difficulty = self._calculate_next_difficulty()

                reward_transaction = {
                    "sender": "SISTEMA",
                    "receiver": str(miner_address).strip(),
                    "amount": BLOCK_REWARD
                }

                # ✅ Remove transações duplicadas e limita quantidade
                with self.mempool_lock:
                    seen_tx_hashes = set()
                    unique_txs = []
                    for tx in self.mempool:
                        tx_hash = hashlib.sha256(
                            json.dumps(tx, sort_keys=True).encode()
                        ).hexdigest()
                        if tx_hash not in seen_tx_hashes:
                            seen_tx_hashes.add(tx_hash)
                            unique_txs.append(tx)
                    pending_transactions = unique_txs[:MAX_TX_PER_BLOCK]

                block_transactions = [reward_transaction] + pending_transactions

                new_block = BrunoBlock(
                    last_block["index"] + 1,
                    last_block["hash"],
                    block_transactions,
                    difficulty=next_difficulty
                )

                success = new_block.mine_block(stop_event=self.mining_stop_event)
                if not success:
                    continue
                if not self.is_mining:
                    continue

                self.db.insert_block(new_block)

                # ✅ Remove transações mineradas da mempool
                with self.mempool_lock:
                    mined_hashes = set(
                        json.dumps(tx, sort_keys=True)
                        for tx in block_transactions
                        if tx.get("sender") != "SISTEMA"
                    )
                    self.mempool = [
                        tx for tx in self.mempool
                        if json.dumps(tx, sort_keys=True) not in mined_hashes
                    ]

                # Sincroniza com peers
                raw_chain_json = json.dumps(self.db.get_raw_chain())
                for ip, port in list(self.connected_peers):
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(3.0)
                        s.connect((ip, int(port)))
                        s.sendall(("SYNC_CHAIN:" + raw_chain_json).encode("utf-8"))
                        s.close()
                    except Exception:
                        pass

                print(
                    f"✅ Bloco #{new_block.index} minerado "
                    f"(Diff: {next_difficulty}) "
                    f"Recompensa: {BLOCK_REWARD:.8f} {COIN_SYMBOL} "
                    f"Hash: {new_block.hash[:16]}..."
                )

            except Exception as e:
                print(f"⚠️ Erro no loop de mineracao: {e}")
                time.sleep(2)

        print("🛑 Loop de mineracao continua desligado.")


# ============================================================
# EXECUÇÃO DIRETA
# ============================================================

if __name__ == "__main__":
    p2p_port = 6001
    if len(sys.argv) > 1:
        try:
            p2p_port = int(sys.argv[1])
        except ValueError:
            pass

    # AutoPortForwarder.open_port_on_router(p2p_port)

    api_local = CriptoAPI(p2p_port)

    webview.create_window(
        title=f"Carteira Nativa {COIN_NAME} (Porta: {p2p_port})",
        url="index.html",
        js_api=api_local,
        width=740,
        height=800,
        resizable=True
    )

    webview.start()
