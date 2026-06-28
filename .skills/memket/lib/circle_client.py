"""
circle_client.py — Circle Gateway client for the Lepton Agents Hackathon.

Production-ready Python client for Circle Gateway's unified USDC balance API.
Implements:
  - Client initialization from environment variables.
  - Authentication via EIP-712 signing of burn intents.
  - USDC balance retrieval (unified balance across chains).
  - Transfer creation, signing, attestation fetching, and on-chain minting.
  - Deposit (approve + deposit) to fund the unified balance.
  - Transaction status checking via eth_getTransactionReceipt.
  - Robust error handling and structured logging.

Reference: https://developers.circle.com/gateway/references/technical-guide
Base URLs:
  - Testnet: https://gateway-api-testnet.circle.com/v1
  - Mainnet: https://gateway-api.circle.com/v1

Required environment variables:
  - EVM_PRIVATE_KEY                 : hex private key (no 0x prefix required)
  - GATEWAY_API_KEY                 : (optional) Bearer token for higher rate limits
  - CIRCLE_ENV                      : "TESTNET" (default) or "MAINNET"
  - GATEWAY_RPC_URL                 : JSON-RPC endpoint for the destination chain
  - SOURCE_CHAIN_RPC_URL            : JSON-RPC endpoint for the source chain (deposits)
  - GATEWAY_DEPOSITOR_ADDRESS       : (optional) depositor EOA; defaults to derived address

USDC has 6 decimals throughout. All amounts are integers in micro-units.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_typing import HexStr
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import Web3Exception, ContractLogicError


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("circle_client")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
logger.setLevel(os.getenv("CIRCLE_CLIENT_LOG_LEVEL", "INFO").upper())


# ---------------------------------------------------------------------------
# Configuration constants (sourced from Circle Gateway docs)
# ---------------------------------------------------------------------------

#: Testnet Gateway API base URL.
TESTNET_API_BASE = "https://gateway-api-testnet.circle.com/v1"
#: Mainnet Gateway API base URL.
MAINNET_API_BASE = "https://gateway-api.circle.com/v1"

#: Canonical EVM Gateway Wallet contract (same address on every EVM chain).
EVM_GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"  # testnet
EVM_GATEWAY_WALLET_MAINNET = "0x77777777Dcc4d5A8B6E418Fd04D8997ef11000eE"
#: Canonical EVM Gateway Minter contract (same address on every EVM chain).
EVM_GATEWAY_MINTER = "0x0022222ABE238Cc2C7Bb1f21003F0a260052475B"  # testnet
EVM_GATEWAY_MINTER_MAINNET = "0x2222222d7164433c4C09B0b0D809a9b52C04C205"

#: USDC always has 6 decimals.
USDC_DECIMALS = 6

#: Default timeout for REST + RPC calls (seconds).
DEFAULT_TIMEOUT = 30

#: Number of times to poll a transaction receipt before giving up.
RECEIPT_POLL_ATTEMPTS = 60
RECEIPT_POLL_INTERVAL = 2.0  # seconds


# ---------------------------------------------------------------------------
# Supported domains
# ---------------------------------------------------------------------------


class ChainDomain(int, Enum):
    """Gateway numeric domain identifiers (per Circle docs)."""

    ETHEREUM = 0
    AVALANCHE = 1
    OPTIMISM = 2
    ARBITRUM = 3
    SOLANA = 5  # special-cased for Ed25519; not supported by this client
    BASE = 6
    POLYGON = 7
    UNICHAIN = 10
    SONIC = 13
    WORLD_CHAIN = 14
    SEI = 16
    HYPEREVM = 19
    ARC_TESTNET = 26

    @classmethod
    def from_name(cls, name: str) -> "ChainDomain":
        lookup = {
            "ethereum": cls.ETHEREUM,
            "sepolia": cls.ETHEREUM,
            "avalanche": cls.AVALANCHE,
            "fuji": cls.AVALANCHE,
            "optimism": cls.OPTIMISM,
            "op": cls.OPTIMISM,
            "arbitrum": cls.ARBITRUM,
            "base": cls.BASE,
            "polygon": cls.POLYGON,
            "amoy": cls.POLYGON,
            "unichain": cls.UNICHAIN,
            "sonic": cls.SONIC,
            "worldchain": cls.WORLD_CHAIN,
            "sei": cls.SEI,
            "hyperevm": cls.HYPEREVM,
            "arc": cls.ARC_TESTNET,
            "arctestnet": cls.ARC_TESTNET,
        }
        key = name.lower().replace(" ", "").replace("_", "")
        if key not in lookup:
            raise ValueError(f"Unknown chain name: {name!r}")
        return lookup[key]


# Common testnet USDC addresses (extend as needed).
USDC_ADDRESSES: dict[ChainDomain, str] = {
    ChainDomain.ETHEREUM: "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",   # Sepolia
    ChainDomain.AVALANCHE: "0x5425890298aed601595a70AB815c96711a31Bc65",  # Fuji
    ChainDomain.OPTIMISM: "0x5fd84259d66Cd46123540766Be93DFE6D43130D7",   # OP Sepolia
    ChainDomain.ARBITRUM: "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",    # Arbitrum Sepolia
    ChainDomain.BASE: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",        # Base Sepolia
    ChainDomain.POLYGON: "0x41E94Eb019C0762f9Bfcf59Fb1C4CB81581839cf",    # Polygon Amoy
    ChainDomain.UNICHAIN: "0x31d0220469e10c4E71834a79b1f276d740d37608",   # Unichain Sepolia
    ChainDomain.SONIC: "0xA4879Fed32EcbefCd99bd5C7D891e9C2Df19c06c",       # Sonic Testnet
    ChainDomain.WORLD_CHAIN: "0x66145f38cBac35Ca6F1Dfb2084b594C42D3C6F8E",  # World Sepolia
    ChainDomain.SEI: "0x4fCF1784B31630811181f670Aea7A7bEF803eaED",        # Sei Atlantic
    ChainDomain.HYPEREVM: "0x2B3370aE73D6b96E7A4EaA05ce95D18c34F4FadF",   # HyperEVM Testnet
    ChainDomain.ARC_TESTNET: "0x3600000000000000000000000000000000000000",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CircleClientError(Exception):
    """Base error for the Circle client."""


class ConfigurationError(CircleClientError):
    """Raised when required configuration is missing or invalid."""


class APIError(CircleClientError):
    """Raised when the Gateway REST API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class TransferError(CircleClientError):
    """Raised when a transfer cannot be created, signed, or minted."""


class TransactionTimeoutError(CircleClientError):
    """Raised when waiting for a transaction receipt exceeds the polling budget."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_bytes32(address: str) -> bytes:
    """Pad an EVM address to 32 bytes (left-pad with zeros)."""
    if not Web3.is_address(address):
        raise ValueError(f"Invalid EVM address: {address!r}")
    return Web3.to_bytes(hexstr="0x" + "0" * 24 + address.lower().replace("0x", ""))[:32]


def _address_from_bytes32(b: bytes) -> str:
    """Extract an EVM address from the low 20 bytes of a 32-byte word."""
    return Web3.to_checksum_address("0x" + b[-20:].hex())


def parse_units(value: str | int | float | Decimal, decimals: int = USDC_DECIMALS) -> int:
    """Convert a human-readable amount into the integer micro-unit representation.

    Examples:
        parse_units("1.5")           -> 1_500_000
        parse_units(Decimal("0.01")) -> 10_000
    """
    d = Decimal(str(value))
    if d < 0:
        raise ValueError("Amount cannot be negative")
    scaled = d * (Decimal(10) ** decimals)
    if scaled != int(scaled):
        raise ValueError(
            f"Amount {value!r} has more than {decimals} decimal places of precision"
        )
    return int(scaled)


def format_units(value: int | str, decimals: int = USDC_DECIMALS) -> str:
    """Format an integer micro-unit amount into a human-readable string."""
    return str(Decimal(str(value)) / (Decimal(10) ** decimals))


# ---------------------------------------------------------------------------
# EIP-712 typed-data for the Gateway burn intent
# ---------------------------------------------------------------------------

# Per Circle docs: do NOT modify these field names, types, or ordering.
EIP712_TYPED_DATA: dict[str, Any] = {
    "domain": {"name": "GatewayWallet", "version": "1"},
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
        ],
        "TransferSpec": [
            {"name": "version", "type": "uint32"},
            {"name": "sourceDomain", "type": "uint32"},
            {"name": "destinationDomain", "type": "uint32"},
            {"name": "sourceContract", "type": "bytes32"},
            {"name": "destinationContract", "type": "bytes32"},
            {"name": "sourceToken", "type": "bytes32"},
            {"name": "destinationToken", "type": "bytes32"},
            {"name": "sourceDepositor", "type": "bytes32"},
            {"name": "destinationRecipient", "type": "bytes32"},
            {"name": "sourceSigner", "type": "bytes32"},
            {"name": "destinationCaller", "type": "bytes32"},
            {"name": "value", "type": "uint256"},
            {"name": "salt", "type": "bytes32"},
            {"name": "hookData", "type": "bytes"},
        ],
        "BurnIntent": [
            {"name": "maxBlockHeight", "type": "uint256"},
            {"name": "maxFee", "type": "uint256"},
            {"name": "spec", "type": "TransferSpec"},
        ],
    },
    "primaryType": "BurnIntent",
}


# ---------------------------------------------------------------------------
# ABIs (minimal subsets)
# ---------------------------------------------------------------------------

GATEWAY_WALLET_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "deposit",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
]

GATEWAY_MINTER_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "gatewayMint",
        "inputs": [
            {"name": "attestationPayload", "type": "bytes"},
            {"name": "signature", "type": "bytes"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
]

ERC20_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "approve",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "allowance",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CircleConfig:
    """Validated client configuration."""

    env: str
    api_base: str
    api_key: str | None
    private_key: str
    account_address: str
    gateway_rpc_url: str
    source_chain_rpc_url: str
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, env: str | None = None) -> "CircleConfig":
        """Build a config from environment variables. Raises ConfigurationError if invalid."""
        resolved_env = (env or os.getenv("CIRCLE_ENV", "TESTNET")).upper()
        if resolved_env not in {"TESTNET", "MAINNET"}:
            raise ConfigurationError(
                f"CIRCLE_ENV must be 'TESTNET' or 'MAINNET', got {resolved_env!r}"
            )

        api_base = MAINNET_API_BASE if resolved_env == "MAINNET" else TESTNET_API_BASE

        private_key = os.getenv("EVM_PRIVATE_KEY", "").strip()
        if not private_key:
            raise ConfigurationError("EVM_PRIVATE_KEY environment variable is required")

        # Accept keys with or without 0x prefix.
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key

        try:
            account = Account.from_key(private_key)
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(f"EVM_PRIVATE_KEY is not a valid private key: {exc}") from exc

        gateway_rpc_url = os.getenv("GATEWAY_RPC_URL", "").strip()
        if not gateway_rpc_url:
            raise ConfigurationError("GATEWAY_RPC_URL environment variable is required")

        source_chain_rpc_url = (
            os.getenv("SOURCE_CHAIN_RPC_URL", "").strip() or gateway_rpc_url
        )

        return cls(
            env=resolved_env,
            api_base=api_base,
            api_key=os.getenv("GATEWAY_API_KEY", "").strip() or None,
            private_key=private_key,
            account_address=account.address,
            gateway_rpc_url=gateway_rpc_url,
            source_chain_rpc_url=source_chain_rpc_url,
            timeout=int(os.getenv("CIRCLE_CLIENT_TIMEOUT", str(DEFAULT_TIMEOUT))),
        )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


@dataclass
class CircleClient:
    """High-level client for Circle Gateway."""

    config: CircleConfig
    session: requests.Session = field(default_factory=requests.Session)

    # ----- Construction -----------------------------------------------------

    @classmethod
    def from_env(cls, env: str | None = None) -> "CircleClient":
        """Build a client from environment variables."""
        cfg = CircleConfig.from_env(env=env)
        return cls(config=cfg)

    def __post_init__(self) -> None:
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "circle_client.py/1.0 (Lepton hackathon)",
            }
        )
        if self.config.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.config.api_key}"

    # ----- Internal helpers ------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.config.api_base}{path}"
        logger.debug("HTTP %s %s", method, url)
        try:
            resp = self.session.request(
                method,
                url,
                json=json_body,
                params=params,
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise APIError(0, f"Network error: {exc}") from exc

        if resp.status_code >= 400:
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            logger.error("Gateway API error: HTTP %s body=%s", resp.status_code, body)
            raise APIError(resp.status_code, resp.reason or "API error", body)

        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def _web3(self, rpc_url: str | None = None) -> Web3:
        url = rpc_url or self.config.gateway_rpc_url
        return Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": self.config.timeout}))

    @staticmethod
    def _random_salt() -> bytes:
        return secrets.token_bytes(32)

    # ----- USDC balance retrieval -----------------------------------------

    def get_balances(
        self,
        sources: Iterable[tuple[int | ChainDomain, str]] | None = None,
        token: str = "USDC",
    ) -> list[dict[str, Any]]:
        """Fetch the unified Gateway balance for one or more (domain, depositor) sources.

        Args:
            sources: iterable of (domain, depositor_address) tuples. If None, queries
                the configured account on Ethereum Sepolia (testnet) or Ethereum mainnet.
            token: token symbol; defaults to USDC (the only token supported by Gateway).

        Returns:
            List of {domain, depositor, balance} dicts. `balance` is a decimal string
            in human-readable USDC units (6 decimals).
        """
        if sources is None:
            default_domain = 0  # Ethereum / Sepolia
            sources = [(default_domain, self.config.account_address)]

        body = {
            "token": token,
            "sources": [
                {"domain": int(domain), "depositor": Web3.to_checksum_address(depositor)}
                for domain, depositor in sources
            ],
        }
        result = self._request("POST", "/balances", json_body=body)
        balances = result.get("balances", []) if isinstance(result, dict) else []
        logger.info(
            "Fetched %d balance entries for %s", len(balances), [s[0] for s in sources]
        )
        return balances

    def get_total_usdc_balance(
        self, sources: Iterable[tuple[int | ChainDomain, str]] | None = None
    ) -> Decimal:
        """Return the sum of balances across all provided sources, as a Decimal."""
        balances = self.get_balances(sources=sources)
        total = Decimal("0")
        for entry in balances:
            total += Decimal(entry.get("balance", "0"))
        return total

    def get_usdc_token_balance(
        self, chain: ChainDomain | int, holder: str | None = None
    ) -> int:
        """Read the raw ERC-20 USDC balance for `holder` on `chain` (in micro-units)."""
        domain = int(chain)
        usdc_addr = USDC_ADDRESSES.get(ChainDomain(domain))
        if usdc_addr is None:
            raise ConfigurationError(f"No USDC address configured for domain {domain}")

        w3 = self._web3()
        if not w3.is_connected():
            raise CircleClientError(
                f"Could not connect to RPC: {self.config.gateway_rpc_url}"
            )

        erc20 = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_addr), abi=ERC20_ABI
        )
        owner = holder or self.config.account_address
        return int(erc20.functions.balanceOf(Web3.to_checksum_address(owner)).call())

    # ----- Transfer creation & signing -----------------------------------

    def _build_transfer_spec(
        self,
        *,
        source_domain: int | ChainDomain,
        destination_domain: int | ChainDomain,
        depositor: str,
        recipient: str,
        amount_micro: int,
        source_token: str | None = None,
        destination_token: str | None = None,
        destination_caller: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        src_domain = int(source_domain)
        dst_domain = int(destination_domain)

        src_usdc = source_token or USDC_ADDRESSES.get(ChainDomain(src_domain))
        dst_usdc = destination_token or USDC_ADDRESSES.get(ChainDomain(dst_domain))
        if not src_usdc:
            raise ConfigurationError(f"No USDC address configured for source domain {src_domain}")
        if not dst_usdc:
            raise ConfigurationError(
                f"No USDC address configured for destination domain {dst_domain}"
            )

        # Pick the right Gateway contract addresses for the environment.
        if self.config.env == "MAINNET":
            source_contract = EVM_GATEWAY_WALLET_MAINNET
            destination_contract = EVM_GATEWAY_MINTER_MAINNET
        else:
            source_contract = EVM_GATEWAY_WALLET
            destination_contract = EVM_GATEWAY_MINTER

        return {
            "version": 1,
            "sourceDomain": src_domain,
            "destinationDomain": dst_domain,
            "sourceContract": _to_bytes32(source_contract).hex(),
            "destinationContract": _to_bytes32(destination_contract).hex(),
            "sourceToken": _to_bytes32(src_usdc).hex(),
            "destinationToken": _to_bytes32(dst_usdc).hex(),
            "sourceDepositor": _to_bytes32(depositor).hex(),
            "destinationRecipient": _to_bytes32(recipient).hex(),
            "sourceSigner": _to_bytes32(depositor).hex(),
            "destinationCaller": _to_bytes32(destination_caller).hex(),
            "value": int(amount_micro),
            "salt": "0x" + self._random_salt().hex(),
            "hookData": "0x",
        }

    def _sign_burn_intent(
        self, spec: dict[str, Any], max_block_height: int, max_fee_micro: int
    ) -> str:
        """EIP-712 sign a BurnIntent and return a 0x-prefixed hex signature."""
        message = {
            "maxBlockHeight": int(max_block_height),
            "maxFee": int(max_fee_micro),
            "spec": spec,
        }
        typed_data = {
            "domain": EIP712_TYPED_DATA["domain"],
            "types": EIP712_TYPED_DATA["types"],
            "primaryType": EIP712_TYPED_DATA["primaryType"],
            "message": message,
        }
        signable = encode_typed_data(full_message=typed_data)
        signed = Account.sign_message(signable, private_key=self.config.private_key)
        return "0x" + signed.signature.hex()

    # ----- Transaction submission ----------------------------------------

    def create_transfer(
        self,
        *,
        source_domain: int | ChainDomain,
        destination_domain: int | ChainDomain,
        amount: str | int | Decimal,
        recipient: str | None = None,
        depositor: str | None = None,
        max_fee: str | int | Decimal = "2.01",
        max_block_height: int | None = None,
        source_token: str | None = None,
        destination_token: str | None = None,
        destination_caller: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        """Create, sign, and submit a single-source Gateway transfer.

        Args:
            source_domain: Gateway domain ID to burn from.
            destination_domain: Gateway domain ID to mint on.
            amount: human-readable USDC amount, e.g. "1.5" or Decimal("1.5").
            recipient: destination recipient address (defaults to depositor).
            depositor: source depositor address (defaults to the configured account).
            max_fee: max fee in USDC; default 2.01 USDC.
            max_block_height: deadline for burn inclusion; default = current head + 1000.
            source_token / destination_token: optional USDC overrides.
            destination_caller: zero address by default (permissionless mint).

        Returns:
            Parsed API response: {"attestation": "0x...", "signature": "0x..."}.
        """
        depositor = depositor or self.config.account_address
        recipient = recipient or depositor

        amount_micro = parse_units(amount)
        max_fee_micro = parse_units(max_fee)

        # Compute max_block_height via the source RPC if not provided.
        if max_block_height is None:
            w3 = self._web3(self.config.source_chain_rpc_url)
            if not w3.is_connected():
                raise CircleClientError(
                    "Could not connect to source chain RPC to fetch block height"
                )
            current = w3.eth.block_number
            max_block_height = int(current) + 1000

        spec = self._build_transfer_spec(
            source_domain=source_domain,
            destination_domain=destination_domain,
            depositor=depositor,
            recipient=recipient,
            amount_micro=amount_micro,
            source_token=source_token,
            destination_token=destination_token,
            destination_caller=destination_caller,
        )

        signature = self._sign_burn_intent(spec, max_block_height, max_fee_micro)

        request_body = [
            {
                "burnIntent": {
                    "maxBlockHeight": int(max_block_height),
                    "maxFee": int(max_fee_micro),
                    "spec": spec,
                },
                "signature": signature,
            }
        ]

        logger.info(
            "Submitting transfer: %s USDC, source_domain=%s, dest_domain=%s, depositor=%s",
            format_units(amount_micro),
            int(source_domain),
            int(destination_domain),
            depositor,
        )

        result = self._request("POST", "/transfer", json_body=request_body)
        if not isinstance(result, dict) or "attestation" not in result:
            raise TransferError(
                f"Unexpected /transfer response shape: {result!r}"
            )

        logger.info(
            "Transfer attestation received: %s…", result["attestation"][:18]
        )
        return result

    # ----- On-chain minting ----------------------------------------------

    def mint_on_destination(
        self,
        attestation: str,
        signature: str,
        *,
        rpc_url: str | None = None,
        destination_minter: str | None = None,
        gas: int | None = None,
    ) -> str:
        """Call gatewayMint on the destination chain and return the tx hash.

        Args:
            attestation: 0x-prefixed attestation payload from /transfer.
            signature: 0x-prefixed operator signature from /transfer.
            rpc_url: destination chain RPC (defaults to GATEWAY_RPC_URL).
            destination_minter: override the minter contract address.
            gas: optional explicit gas limit.

        Returns:
            Transaction hash (0x-hex string).
        """
        w3 = self._web3(rpc_url)
        if not w3.is_connected():
            raise CircleClientError(
                f"Could not connect to destination chain RPC: {rpc_url or self.config.gateway_rpc_url}"
            )

        if self.config.env == "MAINNET":
            default_minter = EVM_GATEWAY_MINTER_MAINNET
        else:
            default_minter = EVM_GATEWAY_MINTER
        minter_addr = Web3.to_checksum_address(destination_minter or default_minter)

        minter = w3.eth.contract(address=minter_addr, abi=GATEWAY_MINTER_ABI)
        account = Account.from_key(self.config.private_key)

        tx = minter.functions.gatewayMint(
            HexBytes(attestation), HexBytes(signature)
        ).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": gas or 500_000,
                # Let web3 fill in the latest gas price strategy.
            }
        )
        try:
            tx = minter.functions.gatewayMint(
                HexBytes(attestation), HexBytes(signature)
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": w3.eth.get_transaction_count(account.address),
                    "gas": gas or 500_000,
                    "maxFeePerGas": w3.eth.gas_price,
                    "maxPriorityFeePerGas": 0,
                    "chainId": w3.eth.chain_id,
                }
            )
        except Web3Exception as exc:
            raise TransferError(f"Failed to build gatewayMint transaction: {exc}") from exc

        signed = account.sign_transaction(tx)
        try:
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        except Web3Exception as exc:
            raise TransferError(f"Failed to send gatewayMint transaction: {exc}") from exc

        tx_hash_hex = tx_hash.hex()
        logger.info("gatewayMint submitted: %s", tx_hash_hex)
        return tx_hash_hex

    # ----- Transaction status checking -----------------------------------

    def wait_for_receipt(
        self,
        tx_hash: str,
        *,
        rpc_url: str | None = None,
        timeout: float | None = None,
        poll_interval: float = RECEIPT_POLL_INTERVAL,
        confirmations: int = 1,
    ) -> dict[str, Any]:
        """Poll for a transaction receipt and wait for N confirmations.

        Raises:
            TransactionTimeoutError: if no receipt is found within the budget.
        """
        w3 = self._web3(rpc_url)
        if not w3.is_connected():
            raise CircleClientError(
                f"Could not connect to RPC: {rpc_url or self.config.gateway_rpc_url}"
            )

        attempts = (
            int(timeout / poll_interval) if timeout else RECEIPT_POLL_ATTEMPTS
        )
        h = HexBytes(tx_hash)

        for i in range(attempts):
            try:
                receipt = w3.eth.get_transaction_receipt(h)
            except Web3Exception as exc:
                # Pending or RPC error — keep polling.
                logger.debug("Receipt poll #%d: %s", i + 1, exc)
                receipt = None

            if receipt is not None:
                # Wait for confirmations.
                if confirmations > 1:
                    head = w3.eth.block_number
                    while receipt["blockNumber"] + confirmations > head:
                        time.sleep(poll_interval)
                        head = w3.eth.block_number
                logger.info(
                    "Receipt for %s: block=%s status=%s",
                    tx_hash,
                    receipt["blockNumber"],
                    receipt["status"],
                )
                if receipt["status"] != 1:
                    raise TransferError(
                        f"Transaction {tx_hash} reverted on-chain "
                        f"(block {receipt['blockNumber']})"
                    )
                return dict(receipt)

            time.sleep(poll_interval)

        raise TransactionTimeoutError(
            f"No receipt for {tx_hash} after {attempts} polls "
            f"({attempts * poll_interval:.0f}s)"
        )

    def get_transaction_status(
        self,
        tx_hash: str,
        *,
        rpc_url: str | None = None,
    ) -> dict[str, Any]:
        """Return a normalized status dict for a transaction.

        Returns one of:
            {"status": "not_found",    "tx_hash": "0x..."}
            {"status": "pending",      "tx_hash": "0x..."}
            {"status": "confirmed",    "tx_hash": "...", "block": int, "confirmations": int}
            {"status": "reverted",     "tx_hash": "...", "block": int}
        """
        w3 = self._web3(rpc_url)
        if not w3.is_connected():
            raise CircleClientError(
                f"Could not connect to RPC: {rpc_url or self.config.gateway_rpc_url}"
            )
        h = HexBytes(tx_hash)
        try:
            receipt = w3.eth.get_transaction_receipt(h)
        except Web3Exception:
            try:
                tx = w3.eth.get_transaction(h)
            except Web3Exception:
                return {"status": "not_found", "tx_hash": tx_hash}
            return {"status": "pending", "tx_hash": tx_hash, "from": tx["from"], "to": tx["to"]}

        if receipt["status"] != 1:
            return {
                "status": "reverted",
                "tx_hash": tx_hash,
                "block": int(receipt["blockNumber"]),
            }

        head = w3.eth.block_number
        return {
            "status": "confirmed",
            "tx_hash": tx_hash,
            "block": int(receipt["blockNumber"]),
            "confirmations": max(0, int(head - receipt["blockNumber"]) + 1),
            "gas_used": int(receipt["gasUsed"]),
        }

    # ----- Deposits -------------------------------------------------------

    def deposit_usdc(
        self,
        *,
        chain: int | ChainDomain,
        amount: str | int | Decimal,
        rpc_url: str | None = None,
        wait: bool = True,
    ) -> str:
        """Approve and deposit USDC into the Gateway Wallet on `chain`.

        Returns the deposit transaction hash.
        """
        amount_micro = parse_units(amount)
        domain = int(chain)
        usdc_addr = USDC_ADDRESSES.get(ChainDomain(domain))
        if usdc_addr is None:
            raise ConfigurationError(f"No USDC address configured for domain {domain}")

        if self.config.env == "MAINNET":
            wallet_addr = EVM_GATEWAY_WALLET_MAINNET
        else:
            wallet_addr = EVM_GATEWAY_WALLET

        w3 = self._web3(rpc_url or self.config.source_chain_rpc_url)
        if not w3.is_connected():
            raise CircleClientError("Could not connect to source chain RPC for deposit")

        account = Account.from_key(self.config.private_key)
        usdc = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_addr), abi=ERC20_ABI
        )
        gateway = w3.eth.contract(
            address=Web3.to_checksum_address(wallet_addr), abi=GATEWAY_WALLET_ABI
        )

        chain_id = w3.eth.chain_id
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price

        # 1) Approve.
        approve_tx = usdc.functions.approve(
            Web3.to_checksum_address(wallet_addr), int(amount_micro)
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": 100_000,
                "maxFeePerGas": gas_price,
                "maxPriorityFeePerGas": 0,
                "chainId": chain_id,
            }
        )
        signed = account.sign_transaction(approve_tx)
        approve_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("USDC approve submitted: %s", approve_hash.hex())
        if wait:
            self.wait_for_receipt(approve_hash.hex(), rpc_url=rpc_url)

        # 2) Deposit.
        nonce = w3.eth.get_transaction_count(account.address)
        deposit_tx = gateway.functions.deposit(
            Web3.to_checksum_address(usdc_addr), int(amount_micro)
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": 200_000,
                "maxFeePerGas": gas_price,
                "maxPriorityFeePerGas": 0,
                "chainId": chain_id,
            }
        )
        signed = account.sign_transaction(deposit_tx)
        deposit_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("Gateway deposit submitted: %s", deposit_hash.hex())
        if wait:
            self.wait_for_receipt(deposit_hash.hex(), rpc_url=rpc_url)
        return deposit_hash.hex()

    # ----- End-to-end convenience ----------------------------------------

    def transfer_usdc(
        self,
        *,
        source_domain: int | ChainDomain,
        destination_domain: int | ChainDomain,
        amount: str | int | Decimal,
        recipient: str | None = None,
        depositor: str | None = None,
        max_fee: str | int | Decimal = "2.01",
        wait_for_mint: bool = True,
        destination_rpc_url: str | None = None,
        source_token: str | None = None,
        destination_token: str | None = None,
    ) -> dict[str, Any]:
        """End-to-end Gateway transfer: attest, mint, and (optionally) wait for receipt.

        Returns:
            {
                "attestation": "0x...",
                "operator_signature": "0x...",
                "mint_tx_hash": "0x..." or None,
                "receipt": {...} or None,
            }
        """
        api_result = self.create_transfer(
            source_domain=source_domain,
            destination_domain=destination_domain,
            amount=amount,
            recipient=recipient,
            depositor=depositor,
            max_fee=max_fee,
            source_token=source_token,
            destination_token=destination_token,
        )

        mint_tx_hash = self.mint_on_destination(
            attestation=api_result["attestation"],
            signature=api_result["signature"],
            rpc_url=destination_rpc_url,
        )

        receipt = None
        if wait_for_mint:
            receipt = self.wait_for_receipt(
                mint_tx_hash, rpc_url=destination_rpc_url
            )

        return {
            "attestation": api_result["attestation"],
            "operator_signature": api_result["signature"],
            "mint_tx_hash": mint_tx_hash,
            "receipt": receipt,
        }


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def _cli() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    parser: Any  # avoid importing argparse at module scope for cleanliness
    import argparse

    parser = argparse.ArgumentParser(
        description="Circle Gateway client (Lepton hackathon)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="Print the configured account address and env")

    bal = sub.add_parser("balances", help="Query unified Gateway balances")
    bal.add_argument("--domain", type=int, action="append", default=[])
    bal.add_argument("--depositor", action="append", default=[])

    dep = sub.add_parser("deposit", help="Deposit USDC into the Gateway Wallet")
    dep.add_argument("--chain-domain", type=int, required=True)
    dep.add_argument("--amount", required=True, help="USDC amount, e.g. 5 or 1.5")

    xfer = sub.add_parser("transfer", help="Burn on source + mint on destination")
    xfer.add_argument("--source-domain", type=int, required=True)
    xfer.add_argument("--destination-domain", type=int, required=True)
    xfer.add_argument("--amount", required=True)
    xfer.add_argument("--recipient", default=None)
    xfer.add_argument("--max-fee", default="2.01")

    args = parser.parse_args()
    client = CircleClient.from_env()

    if args.cmd == "whoami":
        print(json.dumps(
            {
                "env": client.config.env,
                "account": client.config.account_address,
                "api_base": client.config.api_base,
                "gateway_rpc_url": client.config.gateway_rpc_url,
            },
            indent=2,
        ))
        return 0

    if args.cmd == "balances":
        sources: list[tuple[int, str]] = []
        if args.domain and args.depositor:
            for d, a in zip(args.domain, args.depositor):
                sources.append((d, a))
        else:
            sources = [(0, client.config.account_address)]
        balances = client.get_balances(sources=sources)
        print(json.dumps(balances, indent=2))
        return 0

    if args.cmd == "deposit":
        tx_hash = client.deposit_usdc(chain=args.chain_domain, amount=args.amount)
        print(json.dumps({"deposit_tx_hash": tx_hash}, indent=2))
        return 0

    if args.cmd == "transfer":
        result = client.transfer_usdc(
            source_domain=args.source_domain,
            destination_domain=args.destination_domain,
            amount=args.amount,
            recipient=args.recipient,
            max_fee=args.max_fee,
        )
        print(json.dumps(
            {k: (v.hex() if hasattr(v, "hex") else v) for k, v in result.items()},
            indent=2,
            default=str,
        ))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(_cli())