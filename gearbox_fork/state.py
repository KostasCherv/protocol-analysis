"""State management and reading for Gearbox Protocol interactions

Provides state tracking, reading, and management for UI integration.
State can be serialized and stored in session (e.g., Streamlit session_state).
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from web3 import Web3

from .contracts import ContractManager
from .config import (
    CREDIT_MANAGER_V3,
    USDC,
)


class StateReader:
    """Read and display on-chain state"""

    def __init__(self, w3: Web3, contract_manager: ContractManager):
        self.w3 = w3
        self.cm = contract_manager
        self.credit_manager = self.cm.get_credit_manager(CREDIT_MANAGER_V3)

    def get_account_summary(self, credit_account: str) -> Dict[str, Any]:
        """
        Get account summary using calcDebtAndCollateral

        Args:
            credit_account: Credit account address

        Returns:
            Dict with debt, collateral USD, weighted collateral USD, health factor, quoted tokens
        """
        credit_account = self.w3.to_checksum_address(credit_account)

        try:
            # Call calcDebtAndCollateral with task 3 (DEBT_AND_COLLATERAL)
            cdd = self.credit_manager.functions.calcDebtAndCollateral(
                credit_account, 3
            ).call()

            # Parse results
            # Based on CollateralDebtData struct:
            # [0] debt, [1] cumulativeIndexNow, [2] cumulativeIndexLastUpdate,
            # [3] cumulativeQuotaInterest, [4] accruedInterest, [5] accruedFees,
            # [6] totalDebtUSD, [7] totalValue, [8] totalValueUSD, [9] twvUSD,
            # [10] enabledTokensMask, [11] quotedTokensMask, [12] quotedTokens, [13] _poolQuotaKeeper
            debt = cdd[0]
            accrued_interest = cdd[4] if len(cdd) > 4 else 0
            accrued_fees = cdd[5] if len(cdd) > 5 else 0
            total_debt_usd = cdd[6] if len(cdd) > 6 else 0
            total_value_usd = cdd[8] if len(cdd) > 8 else 0
            twv_usd = cdd[9] if len(cdd) > 9 else 0
            quoted_tokens = cdd[12] if len(cdd) > 12 else []

            # Calculate total debt (principal + interest + fees) in token units
            total_debt = debt + accrued_interest + accrued_fees

            # Calculate health factor using totalDebtUSD (both in USD with 8 decimals)
            health_factor = None
            if total_debt_usd > 0 and twv_usd > 0:
                health_factor = (twv_usd / total_debt_usd) * 100  # As percentage

            return {
                "success": True,
                "credit_account": credit_account,
                "debt": debt,  # Principal debt
                "accrued_interest": accrued_interest,
                "accrued_fees": accrued_fees,
                "total_debt": total_debt,  # debt + interest + fees
                "collateral_usd": total_value_usd,
                "weighted_collateral_usd": twv_usd,
                "health_factor": health_factor,
                "quoted_tokens": quoted_tokens,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_account_balances(self, account_address: str) -> Dict[str, Any]:
        """Get all balances for an account"""
        usdc_contract = self.cm.get_erc20(USDC)

        return {
            "account": account_address,
            "ETH": self.w3.eth.get_balance(account_address),
            "USDC": usdc_contract.functions.balanceOf(account_address).call(),
        }

    def get_credit_account_balances(self, credit_account: str) -> Dict[str, Any]:
        """Get token balances in a credit account"""
        usdc_contract = self.cm.get_erc20(USDC)

        return {
            "creditAccount": credit_account,
            "USDC": usdc_contract.functions.balanceOf(credit_account).call(),
        }


@dataclass
class AccountState:
    """Represents the state of a credit account"""
    credit_account: str
    account_address: str
    debt: int = 0  # Principal debt
    accrued_interest: int = 0
    accrued_fees: int = 0
    total_debt: int = 0  # debt + interest + fees
    collateral_usd: int = 0
    weighted_collateral_usd: int = 0
    health_factor: Optional[float] = None
    quoted_tokens: list = None
    
    def __post_init__(self):
        if self.quoted_tokens is None:
            self.quoted_tokens = []
        # Calculate total_debt if not set
        if self.total_debt == 0 and (self.debt > 0 or self.accrued_interest > 0 or self.accrued_fees > 0):
            self.total_debt = self.debt + self.accrued_interest + self.accrued_fees
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountState':
        """Create from dictionary"""
        return cls(**data)
    
    def update_from_summary(self, summary: Dict[str, Any]):
        """Update state from account summary"""
        if summary.get("success"):
            self.debt = summary.get("debt", 0)
            self.accrued_interest = summary.get("accrued_interest", 0)
            self.accrued_fees = summary.get("accrued_fees", 0)
            self.total_debt = summary.get("total_debt", 0)
            self.collateral_usd = summary.get("collateral_usd", 0)
            self.weighted_collateral_usd = summary.get("weighted_collateral_usd", 0)
            self.health_factor = summary.get("health_factor")
            self.quoted_tokens = summary.get("quoted_tokens", [])


class StateManager:
    """Manages account state and provides state tracking"""
    
    def __init__(self, w3: Web3, contract_manager: ContractManager):
        self.w3 = w3
        self.cm = contract_manager
        self.state_reader = StateReader(w3, contract_manager)
        self._states: Dict[str, AccountState] = {}
    
    def get_state(
        self,
        credit_account: str,
        account_address: Optional[str] = None,
        refresh: bool = True,
    ) -> AccountState:
        """
        Get current state of a credit account
        
        Args:
            credit_account: Credit account address
            account_address: Owner account address (optional)
            refresh: If True, fetch fresh state from chain
            
        Returns:
            AccountState object
        """
        credit_account = self.w3.to_checksum_address(credit_account)
        
        # Return cached state if exists and not refreshing
        if not refresh and credit_account in self._states:
            return self._states[credit_account]
        
        # Fetch fresh state
        summary = self.state_reader.get_account_summary(credit_account)
        
        if account_address is None:
            # Try to get from cache
            if credit_account in self._states:
                account_address = self._states[credit_account].account_address
            else:
                account_address = credit_account  # Fallback
        
        state = AccountState(
            credit_account=credit_account,
            account_address=account_address,
        )
        state.update_from_summary(summary)
        
        # Cache state
        self._states[credit_account] = state
        
        return state
    
    def update_state(
        self,
        credit_account: str,
        account_address: Optional[str] = None,
    ) -> AccountState:
        """
        Update state from chain (refresh)
        
        Args:
            credit_account: Credit account address
            account_address: Owner account address
            
        Returns:
            Updated AccountState
        """
        return self.get_state(credit_account, account_address, refresh=True)
    
    def set_state(self, state: AccountState):
        """Set state (useful for restoring from session)"""
        self._states[state.credit_account] = state
    
    def get_state_dict(self, credit_account: str) -> Dict[str, Any]:
        """Get state as dictionary (for serialization)"""
        state = self.get_state(credit_account, refresh=False)
        return state.to_dict()
    
    def set_state_dict(self, data: Dict[str, Any]):
        """Set state from dictionary (for deserialization)"""
        state = AccountState.from_dict(data)
        self.set_state(state)
    
    def clear_state(self, credit_account: Optional[str] = None):
        """Clear state cache"""
        if credit_account:
            credit_account = self.w3.to_checksum_address(credit_account)
            if credit_account in self._states:
                del self._states[credit_account]
        else:
            self._states.clear()


class StateStore:
    """Simple state store for UI session management
    
    This can be used with Streamlit session_state or similar.
    """
    
    def __init__(self, session_state=None):
        """
        Initialize state store
        
        Args:
            session_state: Session state object (e.g., st.session_state in Streamlit)
                          If None, uses in-memory dict
        """
        if session_state is None:
            self._store = {}
        else:
            self._store = session_state
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from store"""
        return self._store.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set value in store"""
        self._store[key] = value
    
    def has(self, key: str) -> bool:
        """Check if key exists"""
        return key in self._store
    
    def delete(self, key: str):
        """Delete key from store"""
        if key in self._store:
            del self._store[key]
    
    def get_state(self, credit_account: str) -> Optional[Dict[str, Any]]:
        """Get account state from store"""
        return self.get(f"state_{credit_account}")
    
    def set_state(self, credit_account: str, state: Dict[str, Any]):
        """Save account state to store"""
        self.set(f"state_{credit_account}", state)
    
    def get_credit_account(self, account_address: str) -> Optional[str]:
        """Get credit account for an address"""
        return self.get(f"credit_account_{account_address}")
    
    def set_credit_account(self, account_address: str, credit_account: str):
        """Save credit account for an address"""
        self.set(f"credit_account_{account_address}", credit_account)
