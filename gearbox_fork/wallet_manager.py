"""Simple wallet funding using Anvil"""

import time
from web3 import Web3

from .fork_client import ForkClient
from .anvil_accounts import get_address, get_private_key
from .config import USDC
from .contracts import ContractManager
from .transactions import build_transaction, wait_for_tx
from eth_account import Account

# Constants
MAX_UINT256 = 2**256 - 1

# Whale addresses for funding
USDC_WHALES = [
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance hot wallet
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",  # Binance 2
    "0x7713974908Be4BEd47172370115e8b121146F513",  # Another large holder
    "0x55FE002aefF02F77364de339a1292923A15844B8",  # Circle
]


def wait_for_tx(w3: Web3, tx_hash, max_wait: int = 30):
    """Wait for transaction receipt"""
    for i in range(max_wait):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            return receipt
        except:
            time.sleep(1)
    return None


class WalletManager:
    """Simple wallet funding - set balances directly"""

    def __init__(self, fork_client: ForkClient):
        self.fork_client = fork_client
        self.w3 = fork_client.w3
        self.cm = ContractManager(self.w3)

    def fund_wallet(
        self,
        account_index: int,
        eth_amount: int = 0,
        usdc_amount: int = 0,
    ) -> dict:
        """
        Fund Anvil account with ETH and USDC

        Args:
            account_index: Anvil account index (0-9)
            eth_amount: Amount of ETH to fund (in wei)
            usdc_amount: Amount of USDC to fund (in wei, 6 decimals)
        """
        from .anvil_accounts import get_private_key
        from eth_account import Account

        account_address = get_address(account_index)
        account = Account.from_key(get_private_key(account_index))

        # Ensure we have enough ETH for gas
        if eth_amount > 0:
            self.fork_client.set_balance(account_address, eth_amount)

        return {
            "account": account_address,
            "ETH": self.fork_client.get_balance(account_address),
            "USDC": self._get_usdc_balance(account_address),
        }

    def get_wallet_balances(self, account_index: int) -> dict:
        """Get all balances (ETH, USDC) for an account"""
        account_address = get_address(account_index)

        return {
            "account": account_address,
            "ETH": self.fork_client.get_balance(account_address),
            "USDC": self._get_usdc_balance(account_address),
        }

    def _get_usdc_balance(self, account_address: str) -> int:
        """Get USDC balance"""
        usdc_contract = self.w3.eth.contract(
            address=USDC,
            abi=[
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                }
            ],
        )
        return usdc_contract.functions.balanceOf(account_address).call()

    def fund_from_whale(
        self, account_address: str, token_address: str, amount: int
    ) -> dict:
        """
        Fund account from whale using impersonateAccount

        Args:
            account_address: Address to fund
            token_address: Token address (e.g., USDC)
            amount: Amount to transfer (in token's smallest unit)

        Returns:
            Dict with success status, tx_hash, balance, and whale_address
        """
        token_address = self.w3.to_checksum_address(token_address)
        account_address = self.w3.to_checksum_address(account_address)
        token_contract = self.cm.get_erc20(token_address)

        # Find whale with sufficient balance
        whale_address = None
        for addr in USDC_WHALES:
            addr_checksum = self.w3.to_checksum_address(addr)
            balance = token_contract.functions.balanceOf(addr_checksum).call()
            if balance >= amount:
                whale_address = addr_checksum
                break

        if not whale_address:
            return {
                "success": False,
                "error": f"No whale found with sufficient balance (need {amount})",
            }

        try:
            # Impersonate the whale account
            self.w3.provider.make_request("anvil_impersonateAccount", [whale_address])

            # Transfer tokens from whale to account
            transfer_tx = token_contract.functions.transfer(
                account_address, amount
            ).build_transaction(
                {
                    "from": whale_address,
                    "gas": 100000,
                    "nonce": self.w3.eth.get_transaction_count(whale_address),
                }
            )
            tx_hash = self.w3.eth.send_transaction(transfer_tx)
            receipt = wait_for_tx(self.w3, tx_hash)

            # Stop impersonating
            self.w3.provider.make_request(
                "anvil_stopImpersonatingAccount", [whale_address]
            )

            if not receipt or receipt.status == 0:
                return {"success": False, "error": f"Transfer failed: {tx_hash.hex()}"}

            # Verify balance
            balance = token_contract.functions.balanceOf(account_address).call()
            return {
                "success": True,
                "tx_hash": tx_hash.hex(),
                "balance": balance,
                "whale_address": whale_address,
            }
        except Exception as e:
            # Stop impersonating on error
            try:
                self.w3.provider.make_request(
                    "anvil_stopImpersonatingAccount", [whale_address]
                )
            except:
                pass
            return {"success": False, "error": str(e)}

    def approve_token(
        self,
        account_index: int,
        token_address: str,
        spender: str,
        amount: int,
    ) -> dict:
        """
        Approve token spending

        Args:
            account_index: Anvil account index (0-9)
            token_address: Token address to approve
            spender: Address to approve (e.g., CreditManager)
            amount: Amount to approve (use MAX_UINT256 for max approval)

        Returns:
            Dict with success status and tx_hash
        """
        account_address = get_address(account_index)
        account = Account.from_key(get_private_key(account_index))
        token_address = self.w3.to_checksum_address(token_address)
        spender = self.w3.to_checksum_address(spender)

        token_contract = self.cm.get_erc20(token_address)

        # Check current allowance
        current_allowance = token_contract.functions.allowance(
            account_address, spender
        ).call()
        if current_allowance >= amount:
            return {"success": True, "already_approved": True}

        # Approve with max amount
        max_approval = MAX_UINT256
        try:
            tx = build_transaction(
                self.w3,
                account_address,
                token_contract.functions.approve(spender, max_approval),
                gas=100000,
            )

            signed_tx = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = wait_for_tx(self.w3, tx_hash)

            if not receipt or receipt.status == 0:
                return {
                    "success": False,
                    "error": f"Approval transaction reverted: {tx_hash.hex()}",
                }

            return {"success": True, "tx_hash": tx_hash.hex()}
        except Exception as e:
            return {"success": False, "error": str(e)}
