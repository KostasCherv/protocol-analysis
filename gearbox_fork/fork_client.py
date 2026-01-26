"""Web3 client setup for forked chain"""

from web3 import Web3
from typing import Optional
import os

from .config import ANVIL_RPC_URL


class ForkClient:
    """Client for interacting with Anvil fork"""

    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or ANVIL_RPC_URL
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        # Anvil doesn't need PoA middleware

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {self.rpc_url}")

    def advance_time(self, seconds: int) -> dict:
        """Advance time by specified seconds"""
        return self.w3.provider.make_request("evm_increaseTime", [seconds])

    def mine_blocks(self, count: int = 1, interval_seconds: int = 12) -> dict:
        """Mine specified number of blocks. Uses anvil_mine so multiple blocks
        are actually mined (evm_mine only mines 1). interval_seconds sets
        timestamp delta between blocks for interest accrual."""
        if count <= 0:
            return {}
        # anvil_mine(blocks, interval): both as decimals
        return self.w3.provider.make_request("anvil_mine", [count, interval_seconds])

    def advance_time_and_mine(self, days: float) -> dict:
        """Advance chain by mining blocks over ~days (12s per block). Use this
        for interest accrual; Gearbox accrues per block."""
        seconds = int(days * 24 * 60 * 60)
        blocks = max(1, seconds // 12)
        return self.mine_blocks(blocks, interval_seconds=12)

    def set_balance(self, address: str, balance_wei: int) -> dict:
        """Set balance for an address using anvil_setBalance"""
        return self.w3.provider.make_request(
            "anvil_setBalance", [address, hex(balance_wei)]
        )

    def get_block_number(self) -> int:
        """Get current block number"""
        return self.w3.eth.block_number

    def get_balance(self, address: str) -> int:
        """Get ETH balance for an address"""
        return self.w3.eth.get_balance(address)
