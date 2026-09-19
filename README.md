📘 Manual do Código — BRN P2P

Versão: 1.0
Última atualização: 2026
Stack: Solidity + Python (aiohttp) + JavaScript (Ethers.js v5) + WebSocket + ngrok

---

📑 Índice

1. Visão Geral
2. Arquitetura do Sistema
3. Estrutura de Arquivos
4. Fluxo de Dados
5. Módulo 1 — Contrato Inteligente
6. Módulo 2 — Servidor Python
7. Módulo 3 — Interface HTML
8. Módulo 4 — Cliente JavaScript
9. Módulo 5 — Túnel ngrok
10. Configuração e Deploy
11. Protocolo WebSocket
12. Erros Comuns e Soluções
13. Segurança
14. Roadmap e Limitações

---

1. Visão Geral

O BRN P2P é uma carteira descentralizada que permite troca peer-to-peer entre USDC (Polygon) e BRL (PIX/dinheiro) usando:

· Assinaturas EIP-712 off-chain → o vendedor assina a ordem sem gastar gas.
· Mural WebSocket → as ordens assinadas ficam públicas em memória no servidor.
· Escrow on-chain → quando alguém compra, o contrato valida a assinatura e move os USDC.

O que ele faz

✅ Publicar ordem de venda de USDC com cotação em BRL
✅ Exibir mural compartilhado em tempo real
✅ Executar ordem on-chain com transferência de USDC
✅ Cancelar ordem via nonce (invalida assinatura)

O que ele não faz

❌ Não processa pagamento em BRL (isso é combinado entre as partes)
❌ Não custodia BRL
❌ Não faz matching automático

---

2. Arquitetura do Sistema

```
┌──────────────────┐         WebSocket          ┌──────────────────┐
│                  │ ◄────────────────────────► │                  │
│   NAVEGADOR      │      HTTP (index/app)      │   server.py      │
│  index.html      │ ◄────────────────────────► │   (aiohttp)      │
│  app.js          │                            │                  │
│  ethers.js       │                            │  MURAL (RAM)     │
└────────┬─────────┘                            └────────┬─────────┘
         │                                               │
         │ assina EIP-712                                │ ngrok
         │                                               ▼
         ▼                                       ┌──────────────────┐
┌──────────────────────┐                         │  Internet        │
│  MetaMask            │                         │  (URL pública)   │
│  (chave privada)     │                         └──────────────────┘
└────────┬─────────────┘
         │
         │ tx on-chain
         ▼
┌──────────────────────┐
│ EscrowP2POffChain    │  ← Polygon Mainnet
│ (Solidity)           │
└──────────────────────┘
```

Camadas

Camada Responsabilidade Onde roda
Apresentação UI, formulários, mural Navegador
Assinatura Chave privada, EIP-712 MetaMask (extensão)
Mural Broadcast de ordens server.py
Execução Transferência USDC Contrato na Polygon

---

3. Estrutura de Arquivos

```
brn-p2p/
│
├── contracts/
│   └── EscrowP2POffChain.sol    ← Contrato Solidity
│
├── server.py                    ← Servidor aiohttp (HTTP + WS)
├── ngrok_tunnel.py              ← Wrapper do pyngrok
│
├── index.html                   ← Interface visual
├── app.js                       ← Lógica Web3 + WS
│
├── requirements.txt             ← Dependências Python
├── ngrok_token.txt              ← Seu token ngrok (secreto)
├── ngrok_domain.txt             ← Domínio fixo ngrok
│
└── README.md                    ← Guia rápido
```

Matriz de dependências

```
index.html ──── carrega ──► ethers.js (CDN)
     │
     └── carrega ──► app.js ──► MetaMask ──► Polygon
                      │
                      └── conecta ──► server.py ──► ngrok ──► Internet
```

---

4. Fluxo de Dados

4.1 Criar ordem (vendedor)

```
[Vendedor preenche form]
        │
        ▼
[app.js: paraWei(valorUSDC), paraWei(cotacao)]
        │
        ▼
[MetaMask: eth_requestAccounts]  → endereço
        │
        ▼
[ERC20.approve(contrato, MAX_UINT)]  → tx  (gas)
        │
        ▼
[ethers._signTypedData(domain, types, value)]  → assinatura (sem gas)
        │
        ▼
[WebSocket: publicar_ordem]
        │
        ▼
[server.py: valida → MURAL[hash] = ordem]
        │
        ▼
[broadcast para todos os clientes WS]
```

4.2 Executar ordem (comprador)

```
[Comprador clica "Comprar"]
        │
        ▼
[app.js: confirma → contrato.executarOrdem(struct, assinatura, comprador)]
        │
        ▼
[Contrato Solidity:
   1. checa expiração
   2. checa nonce não usada
   3. recupera signer via ecrecover
   4. valida signer == criador
   5. marca nonce como usada
   6. transferFrom(criador → comprador, valor - taxa)
   7. transferFrom(criador → admin, taxa)
        ]
        │
        ▼
[WebSocket: ordem_executada → remove do mural]
```

4.3 Cancelar ordem

```
[Vendedor clica "Cancelar"]
        │
        ▼
[contrato.cancelarOrdemOffChain(nonce)]
        │
        ▼
[nonceUtilizado[criador][nonce] = true]  → assinatura morre
        │
        ▼
[WebSocket: cancelar_ordem → remove do mural]
```

---

5. Módulo 1 — Contrato Inteligente

Arquivo: contracts/EscrowP2POffChain.sol
Linguagem: Solidity ^0.8.20
Rede-alvo: Polygon Mainnet (chainId 137)

5.1 Estado

```solidity
address public admin;              // recebe a taxa
IERC20 public usdcToken;           // token aceito
uint256 public taxaAplicacao;      // 100 = 1%
bytes32 public DOMAIN_SEPARATOR;   // EIP-712
mapping(address => mapping(uint256 => bool)) public nonceUtilizado;
```

5.2 Struct Ordem

```solidity
struct Ordem {
    address payable criador;    // quem assinou
    uint256 valorUSDC;          // em wei (6 decimais)
    uint256 cotacao;            // BRL por USDC * 1e8
    uint256 nonce;              // único por criador
    uint256 expiracao;          // timestamp unix
}
```

⚠️ Atenção: valorUSDC NÃO é o total em BRL. É a quantidade de USDC que o vendedor está oferecendo. O preço em BRL fica em cotacao.

5.3 Função getSigner

Recupera o endereço que assinou a ordem:

```solidity
bytes32 structHash = keccak256(abi.encode(
    ORDEM_TYPEHASH, criador, valorUSDC, cotacao, nonce, expiracao
));
bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
return recoverSigner(digest, assinatura);
```

Deve produzir exatamente o mesmo hash que ethers._TypedDataEncoder.hash() no JS.

5.4 Função executarOrdem

Ordem de operações crítica:

1. require(block.timestamp <= expiracao) — ordem ainda válida
2. require(!nonceUtilizado[criador][nonce]) — não foi gasta
3. require(getSigner == criador) — assinatura legítima
4. nonceUtilizado[criador][nonce] = true — antes do transfer (padrão checks-effects-interactions)
5. transferFrom(criador → comprador, valor - taxa)
6. transferFrom(criador → admin, taxa)

5.5 Função cancelarOrdemOffChain

```solidity
nonceUtilizado[msg.sender][_nonce] = true;
```

Não devolve nada — só invalida. O vendedor mantém os USDC (nunca saíram da carteira dele).

5.6 recoverSigner

Assembly que extrai r, s, v dos 65 bytes da assinatura e chama ecrecover.

⚠️ Vulnerabilidade conhecida: não valida se s está na metade inferior da curva (EIP-2). Para produção séria, considere usar OpenZeppelin ECDSA.recover.

---

6. Módulo 2 — Servidor Python

Arquivo: server.py
Framework: aiohttp
Porta padrão: 8080

6.1 Responsabilidades

Componente Função
HTTP Serve index.html, app.js, /api/mural, /health
WebSocket Broadcast de ordens em tempo real (/ws)
CORS Permite origens externas (ngrok, mobile)
Rate limit Máx. 60 msgs / 10s por IP
Limpeza Remove ordens expiradas a cada 60s
Startup Inicia túnel ngrok se token disponível

6.2 Estado em memória

```python
MURAL: dict = {}         # hash -> ordem
CLIENTES_WS: set = set() # WebSockets conectados
LOCK = asyncio.Lock()    # protege acesso concorrente
RATE_LIMIT: dict = {}    # IP -> [timestamps]
TUNEL = None             # NgrokTunnel global
```

⚠️ Tudo se perde ao reiniciar. Para produção, troque por Redis.

6.3 Rotas

Método Rota Handler Descrição
GET / index_handler Serve index.html
GET /index.html index_handler Alias
GET /app.js app_js_handler Serve JS com MIME correto
GET /api/mural mural_rest_handler Lista ordens ativas (JSON)
GET /health health_handler Status + URL ngrok
GET /ws ws_handler Upgrade para WebSocket

6.4 Validação de ordem (validar_ordem)

```python
CAMPOS_OBRIGATORIOS = [
    "hash", "criador", "contratoAddress",
    "valorOferecido", "valorDesejado", "expiracao",
]
```

Checa:

· Todos os campos presentes e não vazios
· contratoAddress começa com 0x e tem 42 chars
· expiracao no futuro
· valorOferecido e valorDesejado positivos

6.5 Rate limit

```python
RATE_JANELA = 10    # segundos
RATE_MAX = 60       # msgs por janela
```

Chave: request.remote (IP). Se exceder, devolve erro via WS.

6.6 Broadcast

```python
async def broadcast(mensagem: dict):
    payload = json.dumps(mensagem)
    for ws in CLIENTES_WS:
        await ws.send_str(payload)
```

Clientes mortos são removidos automaticamente.

6.7 Descoberta de arquivos (PyInstaller-ready)

```python
if getattr(sys, "frozen", False):
    DIR = sys._MEIPASS                    # bundle interno
else:
    DIR = os.path.dirname(os.path.abspath(__file__))
```

E para .txt:

```python
def _pasta_config():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)  # ao lado do .exe
    return os.path.dirname(os.path.abspath(__file__))
```

6.8 Task de limpeza

Roda a cada 60s, remove ordens expiradas do MURAL e emite ordem_expirada.

6.9 Ciclo de vida

· iniciar_tasks — cria task de limpeza + tenta subir ngrok
· parar_tasks — cancela task + fecha túnel

Prioridade do token ngrok:

1. os.environ["NGROK_TOKEN"]
2. arquivo ngrok_token.txt

---

7. Módulo 3 — Interface HTML

Arquivo: index.html
Estilo: Dark theme (#0f172a), responsivo

7.1 Blocos principais

Bloco ID Conteúdo
Header endereco-carteira, btn-conectar Conexão MetaMask
Mensagem mensagem Feedback (erro/ok/aviso)
Aba Criar tab-criar Form de nova ordem
Aba Minhas tab-minhas Ordens do usuário
Mural lista-ordens Tabela P2P
Stats stat-total, stat-saldo-usdc Contadores
Status bar ws-dot, ws-status Conexão WS

7.2 Campos do formulário

ID Tipo Descrição
venda-usdc number (6 casas) USDC a vender
venda-cotacao number (2 casas) BRL por USDC
venda-expiracao select 15m / 30m / 1h / 6h / 24h
total-estimado div Calculado em tempo real

7.3 CDN obrigatório

```html
<script src="https://cdn.ethers.io/lib/ethers-5.7.2.umd.min.js"></script>
<script src="app.js"></script>
```

⚠️ A ordem importa. app.js depende de ethers global.

---

8. Módulo 4 — Cliente JavaScript

Arquivo: app.js
Biblioteca: Ethers.js v5
Padrão: IIFE com funções globais expostas via window

8.1 CONFIG (topo do arquivo)

```js
const CONFIG = {
  CONTRACT_ADDRESS: "0x0000...",   // ← OBRIGATÓRIO preencher
  CHAIN_ID: 137,                    // Polygon Mainnet
  USDC_ADDRESS: "0x2791Bca...",    // USDC nativo Polygon
  DEC_USDC: 6,                      // USDC tem 6 casas
  DEC_COTACAO: 8,                   // cotação armazenada com 8
  EXPLORER: "https://polygonscan.com",
};
```

8.2 Estado global

```js
let provider, signer, endereco, contrato, usdcContrato;
let ws, wsReconnectTimer;
let ordensMural = {};     // hash -> ordem
```

8.3 Utilitários numéricos

```js
// "1.23" + 6 decimais → BigNumber (sem erro de float)
function paraWei(str, decimals) { ... }

// BigNumber → string pt-BR formatada
function deWei(big, decimals, casas = 6) { ... }
```

🔑 Regra de ouro: nunca use Number() * 1e6. Sempre string → BigNumber.

8.4 Funções principais

Função Gatilho Ação
init() DOMContentLoaded Configura provider, listeners, WS
conectar() clique eth_requestAccounts + valida rede
atualizarSaldo() pós-conexão Lê balanceOf USDC
criarOrdem() clique Assina EIP-712 + publica no WS
executarOrdem(hash) clique Tx executarOrdem no contrato
cancelarOrdem(hash) clique Tx cancelarOrdemOffChain
renderizarMural() 1s + eventos WS Desenha tabela
renderizarMinhas() idem Aba "Minhas"
conectarWS() init Abre /ws com retry

8.5 Assinatura EIP-712 (coração do sistema)

```js
const domain = {
  name: "CarteiraBRN_P2P",
  version: "1",
  chainId: CONFIG.CHAIN_ID,
  verifyingContract: CONFIG.CONTRACT_ADDRESS,
};
const types = {
  Ordem: [
    { name: "criador",    type: "address" },
    { name: "valorUSDC",  type: "uint256" },
    { name: "cotacao",    type: "uint256" },
    { name: "nonce",      type: "uint256" },
    { name: "expiracao",  type: "uint256" },
  ],
};
const assinatura = await signer._signTypedData(domain, types, value);
```

O domain precisa ser idêntico ao constructor do Solidity:

Solidity JavaScript
keccak256("CarteiraBRN_P2P") name: "CarteiraBRN_P2P"
keccak256("1") version: "1"
block.chainid chainId: 137
address(this) verifyingContract: CONFIG.CONTRACT_ADDRESS

Se um só divergir → ecrecover retorna endereço errado → "Assinatura invalida".

8.6 Nonce

```js
nonce = Math.floor(Date.now() / 1000) * 1000 + Math.floor(Math.random() * 1000);
```

Combinação timestamp(ms) + aleatório(0-999). Na prática, evita colisão sem precisar de coordenação.

8.7 WebSocket

```js
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  switch (msg.tipo) {
    case "snapshot":         // lista inicial
    case "nova_ordem":       // ordem nova publicada
    case "ordem_cancelada":  // vendedor cancelou
    case "ordem_executada":  // comprador executou
    case "ordem_expirada":   // expirou no servidor
    case "erro":             // servidor rejeitou algo
  }
};
```

Reconexão automática a cada 3s se cair.

---

9. Módulo 5 — Túnel ngrok

Arquivo: ngrok_tunnel.py

9.1 Uso

```python
from ngrok_tunnel import NgrokTunnel

tunel = NgrokTunnel(
    token="seu_token",
    target="http://localhost:8080",
    domain="seventy-rigging-ploy.ngrok-free.dev",
)
url = tunel.start()   # retorna https://...
tunel.close()         # mata o processo ngrok
```

9.2 Detalhes importantes

· Faz ngrok.kill() no início → limpa configs anteriores
· Usa schemes=["https"] → só expõe HTTPS
· Se domain foi passado, usa domínio fixo (plano gratuito não permite)
· Guarda public_url para consulta posterior (usado em /health)

---

10. Configuração e Deploy

10.1 Checklist pré-deploy

```
[ ] Deploy do contrato EscrowP2POffChain na Polygon
[ ] Copiar endereço do contrato
[ ] Colar em app.js → CONFIG.CONTRACT_ADDRESS
[ ] Colar token em ngrok_token.txt
[ ] Domínio ngrok em ngrok_domain.txt
[ ] pip install -r requirements.txt
[ ] python server.py
[ ] Abrir http://localhost:8080 ou URL do ngrok
```

10.2 Parâmetros do contrato no Remix

Parâmetro Valor
_usdcToken 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
_admin seu endereço (recebe taxa)
Compiler 0.8.20+
EVM Version paris (ou shanghai)
Rede Polygon Mainnet (Injected Provider)

10.3 Variáveis de ambiente

Nome Descrição
NGROK_TOKEN Sobrescreve arquivo
NGROK_DOMAIN Sobrescreve arquivo
PORT Porta do servidor (default 8080)

10.4 Rodando como .exe (PyInstaller)

```bash
pyinstaller --onefile --add-data "index.html;." --add-data "app.js;." server.py
```

Os .txt (token, domínio) devem ficar ao lado do .exe, não dentro.

---

11. Protocolo WebSocket

11.1 Mensagens do cliente → servidor

tipo Payload Ação do servidor
publicar_ordem {ordem} Valida e adiciona ao mural
cancelar_ordem {hash} Remove do mural
ordem_executada {hash, txHash} Remove do mural
pedir_snapshot — Envia snapshot atual
ping — Responde pong

11.2 Mensagens do servidor → cliente

tipo Payload Quando
snapshot {ordens: [...]} Ao conectar ou quando pedido
nova_ordem {ordem} Alguém publicou
ordem_cancelada {hash} Vendedor cancelou
ordem_executada {hash, txHash} Comprador executou
ordem_expirada {hash} Task de limpeza removeu
pong {ts} Resposta a ping
erro {msg} Validação falhou

11.3 Formato da ordem

```json
{
  "hash": "0xabc...",              // digest EIP-712
  "criador": "0x123...",
  "contratoAddress": "0xdef...",
  "valorOferecido": "100000000",   // USDC em wei (string)
  "valorDesejado": "525000000",    // cotação * 1e8 (string)
  "valorUSDC": "100000000",
  "cotacao": "525000000",
  "nonce": "1729000123456",
  "expiracao": 1729001234,
  "assinatura": "0x1234...",       // 65 bytes
  "chainId": 137
}
```

---

12. Erros Comuns e Soluções

12.1 "Assinatura invalida" (contrato)

Causa: mismatch entre domain do JS e DOMAIN_SEPARATOR do Solidity.

Solução:

· Confirme name = "CarteiraBRN_P2P" (exato, com underscore)
· Confirme version = "1"
· Confirme chainId = 137
· Confirme verifyingContract = endereço do contrato

12.2 "Sem conexão com o servidor"

Causa: WS caiu ou URL errada.

Solução:

· Abrir DevTools → Network → WS
· Verificar se /ws retorna 101 (Upgrade)
· Verificar firewall/CORS

12.3 "Saldo USDC insuficiente"

Causa: carteira sem USDC na Polygon.

Solução: comprar USDC (Binance → Polygon) ou trocar MATIC.

12.4 MetaMask não abre

Causa: sem window.ethereum.

Solução: instalar extensão + recarregar página.

12.5 Rede errada

Causa: MetaMask em outra rede (Ethereum, BSC...).

Solução: trocar para Polygon Mainnet (chainId 137). O app.js avisa.

12.6 ngrok com erro 401

Causa: token inválido/expirado.

Solução: renovar em https://dashboard.ngrok.com/get-started/your-authtoken.

12.7 "nonceUtilizado" = true inesperadamente

Causa: nonce colidiu (raro) ou ordem já foi cancelada.

Solução: criar nova ordem (novo nonce).

12.8 Broadcast para 0 clientes

Causa: todos os WS desconectaram.

Solução: verificar /health → clientes_ws.

12.9 Math.floor(x * 1e6) com erro

Causa: float impreciso (0.1 * 1e6 = 99999.99...).

Solução: sempre usar paraWei(str, decimals) → BigNumber.

---

13. Segurança

13.1 Pontos fortes

· ✅ Chave privada nunca sai da MetaMask
· ✅ Assinatura off-chain → sem gas para publicar
· ✅ Nonce + expiração → replay protection
· ✅ nonceUtilizado marcado antes do transfer
· ✅ Rate limit por IP

13.2 Pontos de atenção

Risco Impacto Mitigação
Mural em memória Perde tudo ao reiniciar Trocar por Redis
ecrecover sem validação de s Malleability Usar OpenZeppelin ECDSA
Sem verificação de chainId no cliente WS Ordem de outra rede Assinar chainId no digest
Broadcast sem assinatura Ordem forjada no mural Assinar payload WS
CORS * Qualquer site pode conectar Restringir origens
Sem HTTPS local Sniffing em rede Sempre ngrok/HTTPS

13.3 Antes de mainnet com valores reais

```
[ ] Auditar contrato (Code4rena, Hacken, etc.)
[ ] Usar OpenZeppelin ECDSA + ReentrancyGuard
[ ] Persistir mural em Redis/Postgres
[ ] Adicionar assinatura HMAC nas mensagens WS
[ ] Restringir CORS a domínios conhecidos
[ ] Adicionar rate limit por endereço Ethereum (não só IP)
[ ] Logs estruturados + alertas
[ ] Testes unitários (Hardhat + Foundry)
[ ] Testes de integração (Playwright)
[ ] Monitoramento (Sentry, Datadog)
```

---

14. Roadmap e Limitações

14.1 Limitações atuais

· Mural em memória (volátil)
· Sem matching automático
· Sem custódia de BRL
· Sem KYC/AML
· Sem suporte a outros tokens além de USDC
· Cotação é informativa — pagamento em BRL é manual

14.2 Próximas features sugeridas

# Feature Complexidade
1 Persistência em SQLite Baixa
2 Redis + Pub/Sub (multi-instância) Média
3 Suporte a USDT, DAI Baixa
4 Webhooks para PIX (Gerencianet) Alta
5 Chat embutido vendedor↔comprador Média
6 Sistema de reputação on-chain Alta
7 Disputa com árbitro Alta
8 App mobile (React Native) Alta
9 Auditoria + bug bounty Alta
10 Deploy em Kubernetes Média

14.3 Roadmap sugerido

```
v1.0 ──► MVP atual (mural + EIP-712 + escrow)
v1.1 ──► Persistência SQLite + testes
v1.2 ──► Redis + múltiplas instâncias
v1.3 ──► Webhooks PIX automáticos
v2.0 ──► Reputação + disputas
v3.0 ──► App mobile nativo
```

---

📎 Apêndices

A. Glossário

Termo Significado
EIP-712 Padrão de assinatura tipada do Ethereum
Nonce Número único por criador; evita replay
Escrow Contrato que custodia valor até condição
Domain separator Hash do domínio EIP-712 (chain + contrato)
Mural Lista pública de ordens (off-chain)
Broadcast Enviar mensagem para todos os WS

B. Comandos úteis

```bash
# Instalar
pip install -r requirements.txt

# Rodar
python server.py

# Ver logs WS
tail -f /var/log/brn-p2p.log

# Matar ngrok preso
pkill ngrok

# Testar WS manualmente
wscat -c ws://localhost:8080/ws
```

C. Links úteis

· Polygon RPC: https://polygon-rpc.com
· PolygonScan: https://polygonscan.com
· USDC Polygon: https://polygonscan.com/token/0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
· Remix IDE: https://remix.ethereum.org
· Ethers v5 docs: https://docs.ethers.io/v5/
· EIP-712: https://eips.ethereum.org/EIPS/eip-712
· ngrok dashboard: https://dashboard.ngrok.com

---

Fim do manual. Para dúvidas específicas de código, consulte os comentários inline nos arquivos. Para arquitetura de alto nível, este documento é a fonte de verdade.
# 1. dependências
pip install pywebview cryptography argon2-cffi bitcoinlib
# opcional:
pip install miniupnpc

# 2. nó A (webview)
python launcher.py 6001

# 3. nó B (outro terminal / outro PC)
python launcher.py 6002

# 4. dashboard async (opcional)
python explorer.py

# 5. pipeline L2 (opcional)
python main.py
🧪 Como testar (dois nós, mesma máquina)

Terminal A — nó 1

```bash
export NGROK_AUTHTOKEN="SEU_TOKEN_NOVO"
export BRN_P2P_PORT=7777
export BRN_WEB_PORT=5000
export BRN_DB_PATH=node1.db
export BRN_IDENTITY_FILE=node1_identity.json
python node.py
```

Terminal B — nó 2 (aponta para o nó 1)

```bash
export BRN_P2P_PORT=7778
export BRN_WEB_PORT=5001
export BRN_DB_PATH=node2.db
export BRN_IDENTITY_FILE=node2_identity.json
export BRN_SEED_PEERS=127.0.0.1:7777
python node.py
```

O que observar

· No nó 1, o loop de consenso assina o bloco com a chave de node1_identity.json.
· No nó 2, ao receber a mensagem chain, o replace_chain valida cada bloco:
  · hash == calculate_hash()
  · validator == address_from_public_key(validator_public_key)
  · verify_signature(pubkey, {"block_hash", "index"}, signature)

# 1) Instalar dependências
pip install -r requirements.txt

# 2) Testar carteira
python main.py

# 3) Subir nó (em outra máquina ou terminal)
BRN_P2P_PORT=7777 python node.py
✅ O que você precisa fazer
Você ainda não baixou o projeto. Precisa clonar primeiro. Siga exatamente estes comandos, um de cada vez:

1. Volte uma pasta (para não clonar dentro de brn)
No terminal, digite:

cmd
cd ..
Agora você estará em C:\Users\mayra\OneDrive\Imagens\bruno crypto\.

2. Clone o repositório
cmd
git clone https://github.com/brunoldo2312/brnfinal.git
Isso vai criar uma nova pasta chamada brnfinal com todos os arquivos do projeto. Se der erro dizendo que git não é reconhecido, você precisa instalar o Git primeiro: https://git-scm.com/download/win

3. Entre na pasta clonada
cmd
cd brnfinal
4. Veja o que tem dentro
cmd
dir
Agora sim você deve ver os arquivos do projeto: package.json, iniciar.bat, README.md, etc. Só a partir daqui os comandos npm install e iniciar.bat vão funcionar.

5. A partir daqui, siga um destes caminhos:
Se existir iniciar.bat (o arquivo que você mencionou):

cmd
iniciar.bat
Se existir package.json (projeto Node.js):

cmd
npm install
npm start
⚠️ Um alerta importante sobre o OneDrive
Sua pasta está dentro do OneDrive (C:\Users\mayra\OneDrive\...). Isso costuma causar problemas com projetos de programação, porque:

O OneDrive fica sincronizando arquivos enquanto o npm/node tenta ler e escrever

Isso pode causar erros estranhos, lentidão e arquivos "travados"

Recomendação: clone o projeto em uma pasta fora do OneDrive, por exemplo:

cmd
cd C:\
mkdir projetos
cd projetos
git clone https://github.com/brunoldo2312/brnfinal.git
📋 Resumo do que aconteceu
O que você fez	O que deveria ter feito
Colou a URL no terminal	Rodar git clone <URL>
Rodou npm install numa pasta vazia	Clonar o projeto primeiro, depois entrar na pasta
Tentou rodar iniciar.bat que não existe	Primeiro clonar, depois conferir se o arquivo existe
Rode o passo 2 (git clone ...) e me diga o que apareceu. Se der certo, rode dir dentro da pasta brnfinal e me mande a lista de arquivos — assim eu te digo exatamente qual comando usar para iniciar.

Agora sim, deu certo! 🎉 O projeto foi clonado com sucesso e vejo que você já tem os arquivos dentro da pasta brnfinal. E olha só: é um projeto em Python, não em Node.js. Isso explica por que o npm install não funcionou antes — não tinha nada a ver com Node.

📋 O que você tem aí
Olhando a lista de arquivos, dá para identificar:

Arquivo	O que é
iniciar_brn.bat	✅ Provavelmente é o seu "iniciar tudo de uma vez"
iniciar_brn.cmd	Outra versão do inicializador
instalar_ngrok.bat	Instalador do ngrok (usado para expor serviços localmente)
main.py, explorer.py, crypto_wallet.py	Código Python do projeto
blockchain_node_6001.db	Banco de dados do nó da blockchain
index.html	Página web do projeto
README.md	Documentação
LICENSE	Licença
✅ Como executar
Como você está na pasta certa (brnfinal), agora basta rodar:

cmd
iniciar_brn.bat
explorador de blocos  no link https://seventy-rigging-ploy.ngrok-free.dev
1. Localmente (na sua própria máquina)
Abra o navegador em:

text
http://localhost:8080
ou

text
http://127.0.0.1:8080
Importante: o explorer.py é um processo separado. O main.py sobe o nó BRN (porta 6001) e o túnel Ngrok (porta 8080), mas não sobe o explorer. Você precisa rodar o explorer em outra janela do CMD, com o venv ativo:

cmd
cd "C:\Users\adnac\Desktop\bruno crypto\agora-brn"
env\Scripts\activate
python explorer.py
Saída esperada:

text
* Running on http://127.0.0.1:8080
Deixe essa janela aberta. Em outra janela, rode o main.py 6001. Aí o explorador aparece no navegador.

Se o explorer.py não estiver na pasta, é porque não foi baixado. Verifique com:

cmd
dir explorer.py
Se não achar, baixe do repositório original:

cmd
curl -L -o explorer.py https://raw.githubusercontent.com/brunoldo2312/brnfinal/main/explorer.py
(se o caminho não funcionar, abra o repositório no GitHub, clique em explorer.py → Raw → salve com Ctrl+S em explorer.py.)

2. Pelo painel do Ngrok (mostra a URL pública)
Enquanto o main.py estiver rodando, abra:

text
http://127.0.0.1:4040
Esse é o painel local do Ngrok. Ele mostra uma URL do tipo:

text
https://abcd-1234.ngrok-free.app

🖥️ Opção 1: Prompt de Comando (CMD)

No CMD, a sintaxe VAR=valor do Linux não funciona. Usamos set e && para encadear os comandos. Copie e cole:

```cmd
set "NGROK_AUTHTOKEN=3J8xHeVX46aXrOZeXnKrVVFMLTr_6tcrWjc6EaxX218rXJwJ4" && python main.py
```

⚡ Opção 2: PowerShell

Se você usa o PowerShell, a sintaxe é um pouco diferente:

```powershell
$env:NGROK_AUTHTOKEN="3J8xHeVX46aXrOZeXnKrVVFMLTr_6tcrWjc6EaxX218rXJwJ4"; python main.py
```

---

📄 Opção 3: Criar um Script .cmd (Recomendado)

Se você quiser dar apenas um duplo clique para rodar tudo, crie um arquivo chamado iniciar_brn.cmd na mesma pasta do seu main.py e cole o código abaixo. Ele configura o token e inicia o programa automaticamente:

```cmd
@echo off
title Iniciar Moeda Bruno (BRN) com Ngrok
cd /d "%~dp0"

echo ========================================================
echo       CONFIGURANDO TOKEN DO NGROK E INICIANDO O NO
echo ========================================================
echo.

:: Token configurado abaixo
set "NGROK_AUTHTOKEN=3J8xHeVX46aXrOZeXnKrVVFMLTr_6tcrWjc6EaxX218rXJwJ4"

echo Token configurado. Iniciando main.py...
echo.

python main.py

echo.
echo O programa foi encerrado.
pause
```

📌 Observações Importantes:

1. O main.py inicia o Ngrok sozinho? Se o seu main.py já estiver programado para ler a variável NGROK_AUTHTOKEN e criar o túnel automaticamente, os comandos acima funcionarão perfeitamente.
2. Se o main.py não iniciar o Ngrok: Você precisará abrir outro terminal e rodar ngrok http 8080 manualmente, como fizemos nos passos anteriores.
3. Substitua o token: Novamente, use o token apenas para testar e depois troque-o no painel do Ngrok por um novo, mantendo este em segredo.

🚀 Passo 1: Criar uma Conta no Ngrok

1. Acesse https://dashboard.ngrok.com/signup e crie uma conta gratuita.
2. Após o login, o painel exibirá o seu Authtoken (uma sequência longa de letras e números). Copie-o, pois você precisará dele no próximo passo.

💾 Passo 2: Instalar o Ngrok no Linux (Ubuntu/Debian)

No terminal do seu computador, execute os comandos abaixo para instalar via apt (a forma mais simples):

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
  sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
  sudo tee /etc/apt/sources.list.d/ngrok.list && \
  sudo apt update && \
  sudo apt install ngrok
```

Caso prefira baixar o binário diretamente:

```bash
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/
```

Após a instalação, verifique se funcionou com ngrok version.

🔑 Passo 3: Conectar o Ngrok à Sua Conta

Execute o comando abaixo, substituindo SEU_TOKEN_AQUI pelo Authtoken que você copiou no Passo 1:

```bash
ngrok config add-authtoken SEU_TOKEN_AQUI
```

Isso vincula o Ngrok instalado na sua máquina à sua conta.

⛓️ Passo 4: Iniciar o Explorador de Blocos

Em um terminal, navegue até a pasta do projeto e execute o explorador (criado anteriormente) na porta 8080:

```bash
python3 explorer.py
```

Mantenha este terminal aberto. O explorador precisa estar rodando para que o Ngrok consiga redirecionar o tráfego para ele.

🌐 Passo 5: Criar o Túnel Público com Ngrok

Abra outro terminal e execute:

```bash
ngrok http 8080
```

Você verá uma saída semelhante a esta (o link é um exemplo):

```
Forwarding    https://abcd-1234.ngrok-free.app -> http://localhost:8080
```

O endereço https://abcd-1234.ngrok-free.app é o seu link público temporário. Qualquer pessoa que acessá-lo verá o seu explorador de blocos.

📋 Passo 6: Preencher o Formulário da Exchange

No formulário da cexswap.cc, no campo "Explorador de blocos", cole o link que o Ngrok gerou (ex: https://abcd-1234.ngrok-free.app). O link deve começar com https://.

---

⚠️ Avisos Importantes sobre a "Opção Rápida"

· Temporário: O link gerado pelo Ngrok é efêmero. Ele expira assim que você fecha o terminal do Ngrok ou desliga o computador. Se a exchange fizer uma verificação depois, o link estará quebrado.
· Limitações do Plano Gratuito: Contas gratuitas do Ngrok têm restrições de tempo de sessão e número de conexões simultâneas. Para um uso mais estável, seria necessário um plano pago.
· Segurança: Expor seu computador local à internet traz riscos. O Ngrok cria um túnel, mas não substitui a segurança de um servidor dedicado. Certifique-se de que seu explorador não exponha dados sensíveis.
· Não é uma Solução Definitiva: Para que a exchange aceite e mantenha a listagem, o ideal é hospedar o explorador em uma VPS (Servidor Virtual Privado) com um domínio próprio. O Ngrok é excelente para testes rápidos, mas não é indicado para produção.

Resumo: Use o Ngrok para obter o link rapidamente e preencher o formulário, mas esteja ciente de que a exchange pode rejeitar a solicitação por causa da natureza temporária do link. O próximo passo recomendado é migrar o explorador para uma hospedagem permanente.
# 💼 Moeda Bruno (BRN) - Carteira Avançada & Blockchain P2P

A **Moeda Bruno (BRN)** é uma implementação experimental de um ecossistema de criptomoeda descentralizado baseado em princípios acadêmicos do protocolo *CryptoNote/Monero*. O projeto apresenta uma arquitetura modular com um livro-razão imutável, sincronização autônoma de nós Peer-to-Peer (P2P), propagação de transações via Mempool Broadcast e um utilitário automático de redirecionamento de portas (UPnP).

---

## 🚀 Funcionalidades

*   **Consenso de Maior Cadeia (*Longest Chain Rule*):** Algoritmo de resolução de consenso que substitui atomicamente a cadeia local se um par remoto apresentar uma blockchain estritamente mais longa e válida.
*   **Gênese Determinístico (Cadeia Única):** O bloco 0 tem timestamp, nonce e hash fixos (`GENESIS_HASH`), então **todo computador cria exatamente a mesma gênese** e todos compartilham **uma única blockchain**. Nós com gênese diferente (cadeias antigas/divergentes) são recusados na sincronização.
*   **Mempool Persistente com Gossip:** Transações pendentes são gravadas em disco (`mempool_node_<porta>.json`), sobrevivem a reinicializações, são retransmitidas aos demais pares (relay) e removidas automaticamente quando confirmadas em bloco ou após sincronização de cadeia. Transações recebidas com remetente ainda sem saldo local (nó atrasado) vão para uma fila de órfãs (`*.orphan.json`) e são promovidas assim que a cadeia se atualiza.
*   **Livro-Razão Relacional (SQLite3):** Persistência imutável indexada com auditoria histórica e reconstituição dinâmica de saldos em tempo real.
*   **Backup Criptografado de Chaves (.wallet):** Cifragem simétrica em fluxo utilizando derivação de chaves PBKDF de 5000 rounds para proteção de Spend Keys locais.
*   **Interface Gráfica Nativa (Desktop Puro):** Janela escura desacoplada construída sobre a ponte de injeção JavaScript-Python (`pywebview` + `PyQt6`).
*   **Endereço de Recebimento:** Botão para copiar o endereço público da carteira com um clique, facilitando o recebimento de BRN sem expor a chave privada.

---

## 📁 Estrutura Modular do Projeto

O ecossistema foi dividido em módulos isolados para garantir a consistência de dados, mitigar erros de tokenização e otimizar o tempo de compilação:

```text
├── bruno_blockchain_real.py  # Motor principal, API de controle, mempool e chamadas P2P
├── cripto_db.py              # Camada de persistência relacional e queries ordinais SQLite3
├── cripto_wallet.py          # Gerenciador de backup e criptografia PBKDF simétrica
├── index.html                # Interface visual baseada na ponte Javascript-Python Native
├── blockchain_node_<porta>.db   # Cadeia de blocos do nó (SQLite)
├── mempool_node_<porta>.json    # Transações pendentes do nó (persistidas em disco)
└── wallets/                     # Backups .wallet criptografados
```

### Receber BRN

1. Crie ou importe uma carteira.
2. Abaixo de **Seu Endereço Público**, clique em **Copiar endereço de recebimento**.
3. Envie somente esse endereço `brn1...` para quem fará o depósito. Nunca compartilhe a chave privada.

## Segurança e limites do protótipo

Esta é uma blockchain educacional, não indicada para valores reais. A versão atual valida a assinatura contra o endereço do remetente, impede gasto duplo na mempool, rejeita blocos/cadeias com gastos sem saldo e limita mensagens P2P recebidas.

Backups novos usam `cryptography` (Fernet com PBKDF2-SHA256 e 600.000 iterações), exigem senha de ao menos 12 caracteres e são gravados na pasta `wallets/`. Backups antigos Fernet ainda podem ser importados e devem ser reexportados. Instale as dependências antes de iniciar:

```bash
pip install ecdsa cryptography pywebview pyqt6
```

O UPnP deixou de ser ativado automaticamente. Só exponha a porta da carteira à internet se você entender e aceitar esse risco; para testes na mesma rede, use a sincronização manual da interface.

---

## 🛠️ Como Executar o Projeto (Máquina Local)

### 1. Preparação do Ambiente e Dependências (Linux Ubuntu)
Abra o terminal no diretório do projeto e execute os comandos para instalar as bibliotecas de sistema e isolar o ambiente virtual:

```bash
# Instalar pacotes de sistema necessários
sudo apt update && sudo apt install python3-venv python3-full python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 -y

# Criar e ativar o ambiente virtual (VENV)
python3 -m venv env
source env/bin/activate

# Instalar dependências de execução e o motor gráfico isolado PyQt6
pip install --upgrade pip
pip install pywebview flask pyqt6 PyQt6-WebEngine qtpy
```

### 2. Inicialização do Nó Principal
Sempre limpe os bancos de dados corrompidos ou inconsistentes de sessões anteriores antes de iniciar o nó na porta de sua escolha (Ex: `6001`):

```bash
rm -rf __pycache__
rm -f *.db mempool_node_*.json
python3 bruno_blockchain_real.py 6001
```

---

## 🌐 Sincronização entre Máquinas Físicas Diferentes

Para rodar a Moeda Bruno em múltiplos computadores conectados na mesma rede Wi-Fi ou cabo:

### 1. Identificar o IP da Máquina Principal
No terminal do seu nó principal (Ex: Seu HP Pavilion), execute:
```bash
hostname -I
# Retornará algo como: 192.168.0.17
```

### 2. Executar o Nó na Segunda Máquina

> **IMPORTANTE — cadeia única:** antes de iniciar, apague os bancos antigos/divergentes em **todos** os computadores (`blockchain_node_*.db`, `mempool_node_*.json`). Cadeias criadas por versões anteriores têm gênese com hash diferente e **não sincronizam** (o nó avisa "gênese pertence a outra rede"). Com a gênese determinística, cada nó recria o mesmo bloco 0 e todos passam a compartilhar **uma única blockchain**.

Copie os arquivos do projeto para o segundo computador. Abra o terminal dele e inicie o script alterando a porta de escuta para não gerar conflitos:

*   **No Linux:** `python3 bruno_blockchain_real.py 6002`
*   **No Windows (CMD Administrador):** 
    ```cmd
    python -m venv env
    .\env\Scripts\activate
    pip install pywebview flask pyqt6 PyQt6-WebEngine qtpy
    python bruno_blockchain_real.py 6002
    ```

### 3. Sincronizar as Cadeias de Blocos
1. Vá até a tela do aplicativo na **Segunda Máquina**.
2. No painel superior rosa (**Rede Descentralizada**), insira o IP do seu nó principal: `192.168.0.17`.
3. Defina a porta remota do nó principal: `6001`.
4. Clique em **"Conectar e Sincronizar Cadeira"**. O ecossistema fará o download e a verificação criptográfica do livro-razão automaticamente.

*Nota de Firewall:* A conexão P2P precisa de **porta de entrada liberada nos dois computadores**.
- **Windows (CMD Administrador):** `netsh advfirewall firewall add rule name="Bruno BRN 6001" dir=in action=allow protocol=TCP localport=6001` (troque 6001 pela porta do nó; faça em cada máquina para a sua porta).
- **Linux:** `sudo ufw allow 6001/tcp`.

### 4. Os dois computadores DEVEM compartilhar a mesma blockchain

Se um micro "envia mas o outro não recebe", quase sempre é porque estão em cadeias diferentes. Checklist:

1. **Código atualizado nos dois:** copie `bruno_blockchain_real.py`, `cripto_db.py`, `cripto_wallet.py` e `index.html` atualizados para o outro computador. Nó com código antigo cria gênese divergente.
2. **Convergência automática:** ao iniciar com o código novo, se o banco local tiver gênese antiga/divergente o nó faz backup (`*.divergent-*.bak`) e recria a gênese padrão `0000d904…`. Não é preciso apagar nada manualmente.
3. **Confirme na tela:** o card "🌐 Rede" mostra `🟢 cadeia única compartilhada` com a gênese. Se aparecer `🔴 cadeia divergente`, reinicie o nó. Os dois computadores devem mostrar o **mesmo** hash de gênese.
4. **Firewall nos dois sentidos:** cada máquina deve aceitar entrada na própria porta (veja acima).
5. **Mesma rede:** os dois IPs devem se enxergar (mesmo Wi-Fi/cabo). Teste com `ping <IP-do-outro>`.
6. **Sincronize:** em um dos nós, informe o IP/porta do outro e clique em "Conectar e Sincronizar". A cadeia maior vence e ambos ficam idênticos; transações pendentes se propagam via mempool/gossip.

---

## 📦 Como Gerar o Executável Binário (.App / .Exe)

Para distribuir a carteira de privacidade como um aplicativo desktop nativo e independente (sem a necessidade de instalação prévia do Python na máquina de destino):

### No Linux (Gera binário executável nativo)
```bash
pip install pyinstaller
pyinstaller --onefile --add-data "index.html:." --windowed bruno_blockchain_real.py

# Para executar o binário gerado na pasta dist/
cd dist
chmod +x bruno_blockchain_real
./bruno_blockchain_real 6001
```

### No Windows (Gera o arquivo executável .exe)
Abra o Prompt de Comando (CMD) do Windows dentro da pasta do projeto e execute:
```cmd
pip install pyinstaller
pyinstaller --onefile --add-data "index.html;." --windowed bruno_blockchain_real.py
```
O arquivo unificado estará disponível no diretório `dist/bruno_blockchain_real.exe`.
