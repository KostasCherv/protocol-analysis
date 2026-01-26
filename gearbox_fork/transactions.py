"""Transaction preparation and execution for Gearbox Protocol

This module provides functions to prepare call data and execute transactions.
Preparation functions are pure (no side effects), while execution functions
handle transaction building, signing, and sending to the blockchain.
"""

import time
from typing import Dict, Any, List, Optional
from web3 import Web3
from eth_account import Account

from .contracts import ContractManager
from .config import CREDIT_FACADE_V3, USDC
from .anvil_accounts import get_private_key

# Constants
MAX_UINT256 = 2**256 - 1


# ============================================================================
# Transaction Preparation Functions (Pure - No Side Effects)
# ============================================================================


def prepare_add_collateral(
    contract_manager: ContractManager,
    token_address: str,
    amount: int,
) -> Dict[str, Any]:
    """
    Prepare call data for adding collateral

    Args:
        contract_manager: ContractManager instance
        token_address: Token address (e.g., USDC)
        amount: Amount to add (in wei)

    Returns:
        Dict with "target" and "callData" keys
    """
    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)
    token_address = Web3.to_checksum_address(token_address)

    call_data = credit_facade.functions.addCollateral(
        token_address, amount
    )._encode_transaction_data()

    return {
        "target": CREDIT_FACADE_V3,
        "callData": call_data,
        "action": "add_collateral",
        "token": token_address,
        "amount": amount,
    }


def prepare_increase_debt(
    contract_manager: ContractManager,
    amount: int,
) -> Dict[str, Any]:
    """
    Prepare call data for increasing debt (borrowing)

    Args:
        contract_manager: ContractManager instance
        amount: Amount to borrow (in wei, underlying token decimals)

    Returns:
        Dict with "target" and "callData" keys
    """
    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)

    call_data = credit_facade.functions.increaseDebt(amount)._encode_transaction_data()

    return {
        "target": CREDIT_FACADE_V3,
        "callData": call_data,
        "action": "increase_debt",
        "amount": amount,
    }


def prepare_decrease_debt(
    contract_manager: ContractManager,
    amount: int,
) -> Dict[str, Any]:
    """
    Prepare call data for decreasing debt (repaying)

    Args:
        contract_manager: ContractManager instance
        amount: Amount to repay (in wei, use MAX_UINT256 for all)

    Returns:
        Dict with "target" and "callData" keys
    """
    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)

    call_data = credit_facade.functions.decreaseDebt(amount)._encode_transaction_data()

    return {
        "target": CREDIT_FACADE_V3,
        "callData": call_data,
        "action": "decrease_debt",
        "amount": amount,
    }


def prepare_withdraw_collateral(
    contract_manager: ContractManager,
    token_address: str,
    amount: int,
    to_address: str,
) -> Dict[str, Any]:
    """
    Prepare call data for withdrawing collateral

    Args:
        contract_manager: ContractManager instance
        token_address: Token address to withdraw
        amount: Amount to withdraw (in wei, use MAX_UINT256 for all)
        to_address: Address to send tokens to

    Returns:
        Dict with "target" and "callData" keys
    """
    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)
    token_address = Web3.to_checksum_address(token_address)
    to_address = Web3.to_checksum_address(to_address)

    call_data = credit_facade.functions.withdrawCollateral(
        token_address, amount, to_address
    )._encode_transaction_data()

    return {
        "target": CREDIT_FACADE_V3,
        "callData": call_data,
        "action": "withdraw_collateral",
        "token": token_address,
        "amount": amount,
        "to": to_address,
    }


def prepare_repay_all_debt(
    contract_manager: ContractManager,
) -> List[Dict[str, Any]]:
    """
    Prepare call data for repaying all debt

    Args:
        contract_manager: ContractManager instance
        credit_manager: CreditManager contract instance (unused, kept for compatibility)
        credit_account: Credit account address (unused, kept for compatibility)

    Returns:
        List with single call dict to repay all debt
    """
    # Repay all debt
    repay_call = prepare_decrease_debt(contract_manager, MAX_UINT256)

    return [repay_call]


# ============================================================================
# Transaction Execution Functions
# ============================================================================


def wait_for_tx(w3: Web3, tx_hash, max_wait: int = 30):
    """Wait for transaction receipt"""
    for i in range(max_wait):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            return receipt
        except:
            time.sleep(1)
    return None


def extract_revert_reason(w3: Web3, tx_hash: str) -> str:
    """
    Extract revert reason from failed transaction using Anvil debug_traceTransaction

    Args:
        w3: Web3 instance
        tx_hash: Transaction hash (hex string)

    Returns:
        Revert reason string or error message
    """
    try:
        # Try to get revert reason using debug_traceTransaction (Anvil specific)
        trace = w3.provider.make_request(
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer", "tracerConfig": {"withLog": True}}],
        )

        if trace and "result" in trace:
            result = trace["result"]
            # Look for revert reason in the trace
            if isinstance(result, dict):
                # Check for error field
                if "error" in result:
                    error = result["error"]
                    if isinstance(error, str):
                        return error
                    elif isinstance(error, dict) and "message" in error:
                        return error["message"]

                # Check for revert in output
                if "output" in result:
                    output = result["output"]
                    if output and output.startswith(
                        "0x08c379a0"
                    ):  # Error(string) selector
                        # Decode error string
                        try:
                            # Skip selector (4 bytes) and offset (32 bytes)
                            error_data = output[10:]  # Skip 0x and selector
                            # Get string length (next 32 bytes)
                            str_len_hex = error_data[64:128]
                            str_len = int(str_len_hex, 16)
                            # Get string data
                            str_data_hex = error_data[128 : 128 + (str_len * 2)]
                            # Convert hex to string
                            error_str = (
                                bytes.fromhex(str_data_hex)
                                .decode("utf-8")
                                .rstrip("\x00")
                            )
                            return error_str
                        except:
                            pass

        # Fallback: try to get error from receipt
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt and receipt.status == 0:
                # Try to call the transaction to get revert reason
                tx = w3.eth.get_transaction(tx_hash)
                try:
                    w3.eth.call(
                        {
                            "to": tx["to"],
                            "data": tx["input"],
                            "from": tx["from"],
                            "gas": tx["gas"],
                            "gasPrice": tx.get("gasPrice", 0),
                            "value": tx.get("value", 0),
                        },
                        tx["blockNumber"] - 1,
                    )
                except Exception as call_error:
                    error_str = str(call_error)
                    # Extract meaningful part
                    if "revert" in error_str.lower():
                        return error_str
        except:
            pass

        return f"Transaction reverted (tx: {tx_hash})"
    except Exception as e:
        return f"Could not extract revert reason: {str(e)}"


def get_base_fee(w3: Web3) -> int:
    """Get base fee from latest block"""
    latest_block = w3.eth.get_block("latest")
    return latest_block.get("baseFeePerGas", 0) if latest_block else 0


def build_transaction(
    w3: Web3,
    account_address: str,
    func_call,
    gas: int = 500000,
) -> Dict[str, Any]:
    """Build transaction with proper gas fees"""
    base_fee = get_base_fee(w3)
    return func_call.build_transaction(
        {
            "from": account_address,
            "gas": gas,
            "maxFeePerGas": max(base_fee, 1000000000),  # 1 gwei minimum
            "maxPriorityFeePerGas": 0,
            "nonce": w3.eth.get_transaction_count(account_address),
        }
    )


def get_account(
    account_index: Optional[int] = None, private_key: Optional[str] = None
) -> Account:
    """Get account from index or private key"""
    from eth_account import Account
    import secrets

    if private_key:
        return Account.from_key(private_key)
    elif account_index is not None:
        return Account.from_key(get_private_key(account_index))
    else:
        # Generate fresh account
        private_key = "0x" + secrets.token_hex(32)
        return Account.from_key(private_key)


def execute_multicall(
    w3: Web3,
    contract_manager: ContractManager,
    account_index: Optional[int] = None,
    private_key: Optional[str] = None,
    credit_account: str = None,
    calls: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a multicall on an existing credit account

    Args:
        w3: Web3 instance
        contract_manager: ContractManager instance
        account_index: Account index (0-9)
        private_key: Private key string
        credit_account: Credit account address (required)
        calls: List of prepared calls (required)

    Returns:
        Dict with success, tx_hash, receipt
    """
    if not credit_account or not calls:
        return {"success": False, "error": "credit_account and calls are required"}

    account = get_account(account_index, private_key)
    account_address = account.address
    credit_account = w3.to_checksum_address(credit_account)

    # Extract just target and callData for multicall
    # _encode_transaction_data() returns bytes, but web3.py expects hex strings for tuple encoding
    multicall_calls = []
    for call in calls:
        call_data = call["callData"]
        # Ensure callData is bytes (from _encode_transaction_data)
        if isinstance(call_data, str):
            # If it's a hex string, convert to bytes first, then back to hex for web3
            if call_data.startswith("0x"):
                call_data_bytes = bytes.fromhex(call_data[2:])
            else:
                call_data_bytes = bytes.fromhex(call_data)
            call_data = call_data_bytes

        # Web3.py expects hex strings for tuple encoding in .call()
        call_data_hex = (
            "0x" + call_data.hex() if isinstance(call_data, bytes) else call_data
        )

        multicall_calls.append(
            {
                "target": w3.to_checksum_address(call["target"]),
                "callData": call_data_hex,
            }
        )

    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)

    try:
        tx = build_transaction(
            w3,
            account_address,
            credit_facade.functions.multicall(credit_account, multicall_calls),
            gas=500000,
        )

        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = wait_for_tx(w3, tx_hash)

        if not receipt or receipt.status == 0:
            revert_reason = extract_revert_reason(w3, tx_hash.hex())
            return {"success": False, "error": revert_reason, "tx_hash": tx_hash.hex()}

        return {
            "success": True,
            "tx_hash": tx_hash.hex(),
            "receipt": receipt,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_open_account(
    w3: Web3,
    contract_manager: ContractManager,
    account_index: Optional[int] = None,
    private_key: Optional[str] = None,
    on_behalf_of: str = None,
    calls: List[Dict[str, Any]] = None,
    referral_code: int = 0,
) -> Dict[str, Any]:
    """
    Execute openCreditAccount transaction

    Args:
        w3: Web3 instance
        contract_manager: ContractManager instance
        account_index: Account index (0-9)
        private_key: Private key string
        on_behalf_of: Address to open account for (defaults to account address)
        calls: List of prepared calls for multicall
        referral_code: Referral code (default: 0)

    Returns:
        Dict with success, tx_hash, receipt, credit_account
    """
    account = get_account(account_index, private_key)
    account_address = account.address

    if on_behalf_of is None:
        on_behalf_of = account_address
    else:
        on_behalf_of = w3.to_checksum_address(on_behalf_of)

    # Extract just target and callData for multicall
    multicall_calls = [
        {"target": call["target"], "callData": call["callData"]}
        for call in (calls or [])
    ]

    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)

    try:
        tx = build_transaction(
            w3,
            account_address,
            credit_facade.functions.openCreditAccount(
                on_behalf_of, multicall_calls, referral_code
            ),
            gas=3000000,
        )

        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = wait_for_tx(w3, tx_hash)

        if not receipt or receipt.status == 0:
            revert_reason = extract_revert_reason(w3, tx_hash.hex())
            return {"success": False, "error": revert_reason, "tx_hash": tx_hash.hex()}

        # Extract credit account from event
        event_sig = w3.keccak(text="OpenCreditAccount(address,address,address,uint256)")
        credit_account = None
        for log in receipt.logs:
            if len(log.topics) > 0 and log.topics[0] == event_sig:
                credit_account = w3.to_checksum_address(
                    "0x" + log.topics[1].hex()[-40:]
                )
                break

        if not credit_account:
            return {
                "success": False,
                "error": "Could not extract credit account from event",
            }

        return {
            "success": True,
            "tx_hash": tx_hash.hex(),
            "receipt": receipt,
            "credit_account": credit_account,
            "account_address": account_address,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def simulate_multicall(
    w3: Web3,
    contract_manager: ContractManager,
    account_address: str,
    credit_account: str,
    calls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Simulate a multicall without executing it

    Args:
        w3: Web3 instance
        contract_manager: ContractManager instance
        account_address: Account address
        credit_account: Credit account address
        calls: List of prepared calls

    Returns:
        Dict with success and simulation result
    """
    credit_account = w3.to_checksum_address(credit_account)

    # Extract just target and callData
    multicall_calls = [
        {"target": call["target"], "callData": call["callData"]} for call in calls
    ]

    credit_facade = contract_manager.get_credit_facade(CREDIT_FACADE_V3)

    try:
        result = credit_facade.functions.multicall(
            credit_account, multicall_calls
        ).call({"from": account_address})

        return {
            "success": True,
            "result": result,
        }
    except Exception as e:
        # Extract error message more carefully
        error_msg = str(e)
        error_details = {}

        # Handle tuple errors (sometimes web3 returns tuples)
        if isinstance(e, tuple):
            error_msg = ", ".join(str(item) for item in e)
            # Try to extract selector from tuple
            for item in e:
                if isinstance(item, str) and item.startswith("0x") and len(item) == 10:
                    error_details["selector"] = item
        elif hasattr(e, "args") and e.args:
            if len(e.args) == 1:
                error_msg = str(e.args[0])
                if (
                    isinstance(e.args[0], str)
                    and e.args[0].startswith("0x")
                    and len(e.args[0]) == 10
                ):
                    error_details["selector"] = e.args[0]
            else:
                error_msg = ", ".join(str(arg) for arg in e.args)
                # Check if any arg is a selector
                for arg in e.args:
                    if isinstance(arg, str) and arg.startswith("0x") and len(arg) == 10:
                        error_details["selector"] = arg

        # Try to extract error selector if it's a custom error
        if "execution reverted" in error_msg.lower() or "selector" not in error_details:
            import re

            # Pattern: "0x" followed by 8 hex characters (4 bytes)
            selector_match = re.search(r"0x([0-9a-fA-F]{8})", error_msg)
            if selector_match:
                error_details["selector"] = selector_match.group(0)

        # Map known selectors to error names
        if "selector" in error_details:
            selector = error_details["selector"]
            error_map = {
                "0x16dd0ffb": "UnknownMethodException (selector not recognized)",
                "0xce167994": "BorrowAmountOutOfLimitsException",
                "0x20328066": "UpdateQuotaOnZeroDebtAccountException",
                "0xba04a99a": "QuotaIsOutOfBoundsException",
                "0x51bb745d": "DebtToZeroWithActiveQuotasException",
                "0xf4059071": "ERC20 transfer/approve error",
                "0x675f1a56": "BorrowedBlockLimitException",
                "0x9abfd950": "CreditManagerCantBorrowException",
            }
            error_name = error_map.get(selector, f"Custom error {selector}")
            error_msg = f"{error_name}: {error_msg}"
            error_details["error_name"] = error_name

        return {
            "success": False,
            "error": error_msg,
            **error_details,
        }
