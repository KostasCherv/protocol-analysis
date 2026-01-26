"""
Credit Account Controller - Simple API for managing Gearbox credit accounts

This controller provides a clean interface for:
- Opening credit accounts
- Preparing actions (add collateral, borrow, repay, etc.)
- Executing multicalls
- Simulating transactions
- Getting account state
"""

from typing import Dict, Any, List, Optional
from web3 import Web3

from .contracts import ContractManager
from .transactions import (
    prepare_add_collateral,
    prepare_increase_debt,
    prepare_decrease_debt,
    prepare_withdraw_collateral,
    prepare_repay_all_debt,
    execute_multicall,
    execute_open_account,
    simulate_multicall,
    get_account,
    build_transaction,
    wait_for_tx,
    extract_revert_reason,
)
from .state import StateManager, StateStore
from .config import USDC, CREDIT_MANAGER_V3, CREDIT_FACADE_V3


class CreditAccountController:
    """
    Simple controller for managing Gearbox Protocol credit accounts.

    This is the main interface you'll use to interact with credit accounts.
    It handles preparing actions, executing transactions, and managing state.
    """

    def __init__(
        self,
        w3: Web3,
        contract_manager: ContractManager,
        fork_client=None,
        state_store=None,
    ):
        """
        Initialize the controller.

        Args:
            w3: Web3 instance
            contract_manager: ContractManager instance
            fork_client: Optional ForkClient for time manipulation
            state_store: Optional StateStore for session persistence
        """
        self.w3 = w3
        self.cm = contract_manager
        self.fork_client = fork_client
        self.state_manager = StateManager(w3, contract_manager)
        self.state_store = state_store or StateStore()

    def prepare_action(self, action_type: str, **kwargs) -> Dict[str, Any]:
        """
        Prepare a single action (returns call data, doesn't execute).

        Args:
            action_type: Type of action:
                - "add_collateral" - Add collateral token
                - "increase_debt" - Borrow funds
                - "decrease_debt" - Repay debt
                - "withdraw_collateral" - Withdraw collateral
            **kwargs: Action-specific parameters

        Returns:
            Dict with "target" and "callData" keys
        """
        if action_type == "add_collateral":
            return prepare_add_collateral(
                self.cm,
                kwargs.get("token", USDC),
                kwargs["amount"],
            )
        elif action_type == "increase_debt":
            return prepare_increase_debt(self.cm, kwargs["amount"])
        elif action_type == "decrease_debt":
            return prepare_decrease_debt(self.cm, kwargs["amount"])
        elif action_type == "withdraw_collateral":
            return prepare_withdraw_collateral(
                self.cm,
                kwargs.get("token", USDC),
                kwargs["amount"],
                kwargs["to"],
            )
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def execute_multicall(
        self,
        credit_account: str,
        calls: List[Dict[str, Any]],
        account_index: Optional[int] = None,
        private_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a multicall on an existing credit account.

        Automatically simulates before executing and updates state on success.

        Args:
            credit_account: Credit account address
            calls: List of prepared calls (from prepare_action)
            account_index: Account index (0-9) or private_key
            private_key: Private key string

        Returns:
            Dict with success, tx_hash, receipt, error
        """
        # Resolve special actions (like repay_all_debt)
        resolved_calls = []
        for call in calls:
            if call.get("action") == "repay_all_debt":
                credit_manager = self.cm.get_credit_manager(CREDIT_MANAGER_V3)
                repay_calls = prepare_repay_all_debt(
                    self.cm,
                    credit_manager,
                    credit_account,
                )
                resolved_calls.extend(repay_calls)
            else:
                resolved_calls.append(call)

        # Simulate before executing
        account = get_account(account_index, private_key)
        account_address = account.address
        sim_result = simulate_multicall(
            self.w3,
            self.cm,
            account_address,
            credit_account,
            resolved_calls,
        )

        if not sim_result.get("success"):
            return {
                "success": False,
                "error": f"Simulation failed: {sim_result.get('error', 'Unknown error')}",
                "simulation_error": sim_result.get("error"),
            }

        # Execute if simulation succeeds
        result = execute_multicall(
            self.w3,
            self.cm,
            account_index=account_index,
            private_key=private_key,
            credit_account=credit_account,
            calls=resolved_calls,
        )

        # Update state on success
        if result.get("success") and self.state_store:
            account = get_account(account_index, private_key)
            self.state_manager.update_state(
                credit_account,
                account_address=account.address,
            )
            state = self.state_manager.get_state(credit_account, refresh=False)
            self.state_store.set_state(credit_account, state.to_dict())

        return result

    def execute_open_account(
        self,
        account_index: Optional[int] = None,
        private_key: Optional[str] = None,
        calls: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Open a new credit account.

        Args:
            account_index: Account index (0-9) or private_key
            private_key: Private key string
            calls: Optional list of prepared calls for initial setup

        Returns:
            Dict with success, tx_hash, credit_account, error
        """
        result = execute_open_account(
            self.w3,
            self.cm,
            account_index=account_index,
            private_key=private_key,
            calls=calls or [],
        )

        # Update state on success
        if result.get("success") and self.state_store:
            credit_account = result["credit_account"]
            account_address = result["account_address"]

            self.state_manager.update_state(
                credit_account,
                account_address=account_address,
            )

            state = self.state_manager.get_state(credit_account, refresh=False)
            self.state_store.set_state(credit_account, state.to_dict())
            self.state_store.set_credit_account(account_address, credit_account)

        return result

    def get_state(
        self,
        credit_account: str,
        refresh: bool = False,
    ):
        """
        Get account state.

        Args:
            credit_account: Credit account address
            refresh: If True, fetch fresh state from chain

        Returns:
            AccountState object
        """
        return self.state_manager.get_state(credit_account, refresh=refresh)

    def close_credit_account(
        self,
        credit_account: str,
        account_index: Optional[int] = None,
        private_key: Optional[str] = None,
        calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Close a credit account.

        Args:
            credit_account: Credit account address (required)
            account_index: Account index (0-9) or private_key
            private_key: Private key string
            calls: Optional multicall operations before closing

        Returns:
            Dict with success, tx_hash, receipt, error
        """
        if not credit_account:
            return {"success": False, "error": "credit_account is required"}

        account = get_account(account_index, private_key)
        account_address = account.address
        credit_account = self.w3.to_checksum_address(credit_account)

        multicall_calls = calls or []
        credit_facade = self.cm.get_credit_facade(CREDIT_FACADE_V3)

        try:
            tx = build_transaction(
                self.w3,
                account_address,
                credit_facade.functions.closeCreditAccount(
                    credit_account, multicall_calls
                ),
                gas=2000000,
            )

            signed_tx = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = wait_for_tx(self.w3, tx_hash)

            if not receipt or receipt.status == 0:
                revert_reason = extract_revert_reason(self.w3, tx_hash.hex())
                return {
                    "success": False,
                    "error": revert_reason,
                    "tx_hash": tx_hash.hex(),
                }

            # Update state on success
            if self.state_store:
                self.state_manager.clear_state(credit_account)
                self.state_store.delete(f"state_{credit_account}")

            return {
                "success": True,
                "tx_hash": tx_hash.hex(),
                "receipt": receipt,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
