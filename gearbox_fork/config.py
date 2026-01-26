"""Contract addresses and configuration"""

import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()


CREDIT_MANAGER_V3 = Web3.to_checksum_address(
    "0xbCd2fFaC58189E57334Bb63253AcbF34D776DE53"
)
CREDIT_FACADE_V3 = Web3.to_checksum_address(
    "0x67bf2a7778edb535A167fF6C959E08d537888118"
)

# Token addresses (checksummed)
USDC = Web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")

# RPC URLs
ANVIL_RPC_URL = os.getenv("ANVIL_RPC_URL", "http://127.0.0.1:8545")
MAINNET_RPC_URL = os.getenv(
    "MAINNET_RPC_URL", "https://ethereum.publicnode.com"
)  # Public endpoint, no API key required (alternative: https://rpc.ankr.com/eth)

# Default fork block number
DEFAULT_FORK_BLOCK = 19000000
