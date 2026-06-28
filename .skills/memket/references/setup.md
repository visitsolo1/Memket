# Setup

## 1. Install deps

```bash
pip install requests web3 eth-account hexbytes
```

(Only `arc_rpc.py` needs the stdlib; `circle_client.py` needs the full web3 stack.)

## 2. Configure env

```bash
export EVM_PRIVATE_KEY="0xYOUR_KEY"
export GATEWAY_API_KEY="..."                 # optional
export CIRCLE_ENV="TESTNET"
export GATEWAY_RPC_URL="https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>"
export SOURCE_CHAIN_RPC_URL="$GATEWAY_RPC_URL"
```

## 3. Fund your agent

Send testnet USDC to the address derived from `EVM_PRIVATE_KEY` (printed by `CircleConfig.from_env().account_address`).

Then deposit to Gateway unified balance:

```python
from circle_client import CircleClient
client = CircleClient.from_env()
client.deposit_usdc(amount=1_000_000)  # 1 USDC in micro-units
```

## 4. Verify

```python
from circle_client import CircleClient
c = CircleClient.from_env()
print(c.get_total_usdc_balance())
print(c.get_usdc_token_balance())  # on Arc specifically
```

If `get_total_usdc_balance()` returns your deposit, you're ready to list/buy/sell memes.

## Arc RPC quick checks (no auth needed if you have a token URL)

```python
from arc_rpc import ArcRPC
r = ArcRPC("https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>")
print(r.chain_id(), r.block_number(), r.gas_price())
```

Chain ID should be `5049170` (`0x4cef52`).