#!/usr/bin/env python3
"""
Gearbox Protocol Simulator (Borrow Side)
A minimal Python simulator demonstrating Gearbox Protocol borrowing mechanics.

Strategy: Yearn USDC Vault
- Borrow USDC from Gearbox Pool
- Deploy to Yearn USDC Vault for yield
- Monitor health factor and liquidation risk

Required Actions:
- Borrow: Open credit account and borrow funds
- Deploy to Strategy: Move borrowed funds to Yearn
- Close Credit Account: Repay debt and withdraw remaining collateral
- Liquidate: Execute liquidation for accounts with HF < 1.0

Run with: streamlit run gearbox_simulator.py
"""

import streamlit as st
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum


class AccountStatus(Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    LIQUIDATABLE = "liquidatable"


@dataclass
class Oracle:
    """Simple price oracle"""

    prices: Dict[str, float] = field(
        default_factory=lambda: {"USDC": 1.0, "ETH": 3000.0}
    )

    def get_price(self, asset: str) -> float:
        return self.prices.get(asset, 0.0)

    def drop_prices(self, percent: float):
        """Drop all prices by given percentage (for stress testing)"""
        for asset in self.prices:
            self.prices[asset] *= 1 - percent / 100


@dataclass
class Pool:
    """
    Lending pool for a single asset

    Uses Gearbox Protocol's Two-Kink Piecewise Linear Interest Rate Model.
    Reference: https://docs.gearbox.finance/about-gearbox/economics-and-risk/interest-rate-model
    """

    asset: str
    total_liquidity: float = 0.0
    total_borrowed: float = 0.0

    base_rate: float = 0.02
    utilization_kink1: float = 0.60
    utilization_kink2: float = 0.85
    slope1: float = 0.08
    slope2: float = 0.10
    slope3: float = 0.30
    spread_fee: float = 0.05

    def utilization(self) -> float:
        if self.total_liquidity == 0:
            return 0.0
        return min(self.total_borrowed / self.total_liquidity, 1.0)

    def borrow_rate(self) -> float:
        util = self.utilization()
        U1 = self.utilization_kink1
        U2 = self.utilization_kink2

        if util <= U1:
            return self.base_rate + (util / U1) * self.slope1
        elif util <= U2:
            return (
                self.base_rate + self.slope1 + ((util - U1) / (U2 - U1)) * self.slope2
            )
        else:
            return (
                self.base_rate
                + self.slope1
                + self.slope2
                + ((util - U2) / (1 - U2)) * self.slope3
            )

    def effective_borrow_rate(self) -> float:
        return self.borrow_rate() * (1 + self.spread_fee)


@dataclass
class YearnVaultStrategy:
    """Yearn USDC Vault strategy"""

    deposited_amount: float = 0.0  # Amount in USDC
    yield_apy: float = 0.08
    last_update: datetime = field(default_factory=datetime.now)
    rewards: float = 0.0

    def value(self) -> float:
        """Current value in USDC"""
        return self.deposited_amount

    def accrue_yield(self, days: float):
        """Accrue yield over time period"""
        daily_rate = self.yield_apy / 365
        yield_amount = self.deposited_amount * daily_rate * days
        self.deposited_amount += yield_amount
        self.rewards += yield_amount
        self.last_update = datetime.now()

    def deposit(self, amount: float):
        """Deposit USDC into vault"""
        self.deposited_amount += amount

    def withdraw(self) -> float:
        """Withdraw all funds and return to USDC"""
        value = self.deposited_amount
        self.deposited_amount = 0.0
        self.rewards = 0.0  # Reset rewards when withdrawing
        return value

    def claim_rewards(self) -> float:
        """Claim and reset rewards"""
        claimed = self.rewards
        self.rewards = 0.0
        return claimed


@dataclass
class User:
    """Represents a user in the system"""

    address: str
    wallet_balance: Dict[str, float] = field(
        default_factory=lambda: {"USDC": 0.0, "ETH": 0.0}
    )


@dataclass
class CreditAccount:
    """Credit Account for leveraged positions"""

    account_id: str
    owner: str
    collateral: Dict[str, float] = field(default_factory=lambda: {"USDC": 0.0})
    borrowed_amount: float = 0.0
    borrowed_asset: str = "USDC"
    accrued_interest: float = 0.0
    liquidation_threshold: float = 0.95
    opened_at_block: int = 0
    last_update: datetime = field(default_factory=datetime.now)
    strategy: Optional[YearnVaultStrategy] = None
    is_liquidated: bool = False
    available_cash: float = (
        0.0  # Cash returned from strategy (can repay debt or redeploy)
    )

    def collateral_value_usd(self, oracle: Oracle) -> float:
        total = 0.0
        for asset, amount in self.collateral.items():
            total += amount * oracle.get_price(asset)
        return total

    def debt_value_usd(self, oracle: Oracle) -> float:
        total_debt = self.borrowed_amount + self.accrued_interest
        return total_debt * oracle.get_price(self.borrowed_asset)

    def strategy_value_usd(self, oracle: Oracle) -> float:
        if self.strategy is None:
            return 0.0
        return self.strategy.value() * oracle.get_price("USDC")

    def total_position_value(self, oracle: Oracle) -> float:
        """Total value of account: collateral + strategy + available_cash - debt"""
        available_cash_usd = self.available_cash * oracle.get_price("USDC")
        return (
            self.collateral_value_usd(oracle)
            + self.strategy_value_usd(oracle)
            + available_cash_usd
            - self.debt_value_usd(oracle)
        )

    def total_debt(self) -> float:
        return self.borrowed_amount + self.accrued_interest

    def health_factor(self, oracle: Oracle) -> float:
        debt = self.debt_value_usd(oracle)
        if debt == 0:
            return float("inf")
        # Include available_cash as part of collateral (it's USDC that can repay debt)
        available_cash_usd = self.available_cash * oracle.get_price("USDC")
        total_collateral = (
            self.collateral_value_usd(oracle)
            + self.strategy_value_usd(oracle)
            + available_cash_usd
        )
        return (total_collateral * self.liquidation_threshold) / debt

    def status(self, oracle: Oracle) -> AccountStatus:
        hf = self.health_factor(oracle)
        if hf < 1.0:
            return AccountStatus.LIQUIDATABLE
        elif hf < 1.2:
            return AccountStatus.AT_RISK
        else:
            return AccountStatus.HEALTHY


class GearboxSimulator:
    """Main simulator class"""

    def __init__(self):
        self.oracle = Oracle()
        self.pool = Pool(
            asset="USDC",
            total_liquidity=1_000_000.0,
            total_borrowed=200_000.0,
        )
        self.users: Dict[str, User] = {}
        self.credit_accounts: Dict[str, CreditAccount] = {}
        self.account_counter = 0
        self.current_block = 0
        self.blocks_per_year = 2_102_400
        self._init_dummy_accounts()

    def _init_dummy_accounts(self):
        """Create pre-populated dummy accounts"""
        dummy_users = [
            ("Alice", 1.0, 3000.0),
            ("Bob", 1.0, 100000.0),
            ("Charlie", 1.0, 2000.0),
            ("Dave", 1.0, 15000.0),
        ]

        for name, collateral_eth, borrowed_usdc in dummy_users:
            user_address = f"0x{name.lower()}1"
            self.create_user(
                user_address, {"USDC": borrowed_usdc, "ETH": collateral_eth}
            )

            self.account_counter += 1
            account_id = f"CA_{self.account_counter}"

            # Initialize strategy with borrowed amount
            strategy = YearnVaultStrategy(
                deposited_amount=borrowed_usdc,
                rewards=0.0,
            )

            account = CreditAccount(
                account_id=account_id,
                owner=user_address,
                collateral={"ETH": collateral_eth},
                borrowed_amount=borrowed_usdc,
                borrowed_asset="USDC",
                opened_at_block=self.current_block,
                strategy=strategy,
                available_cash=0,
            )
            self.credit_accounts[account_id] = account

    def create_user(self, address: str, initial_balance: Dict[str, float]) -> User:
        user = User(address=address, wallet_balance=initial_balance.copy())
        self.users[address] = user
        return user

    def get_user(self, address: str) -> Optional[User]:
        return self.users.get(address)

    def borrow(
        self,
        user_address: str,
        collateral_amount: float,
        borrow_amount: float,
        collateral_asset: str = "ETH",
    ) -> Dict:
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        user = self.users[user_address]
        if user.wallet_balance.get(collateral_asset, 0.0) < collateral_amount:
            raise ValueError(f"Insufficient {collateral_asset} balance")

        available = self.pool.total_liquidity - self.pool.total_borrowed
        if borrow_amount > available:
            raise ValueError(
                f"Insufficient pool liquidity. Available: {available:,.2f}"
            )

        self.account_counter += 1
        account_id = f"CA_{self.account_counter}"

        leverage = (
            collateral_amount * self.oracle.get_price(collateral_asset) + borrow_amount
        ) / (collateral_amount * self.oracle.get_price(collateral_asset))

        account = CreditAccount(
            account_id=account_id,
            owner=user_address,
            collateral={collateral_asset: collateral_amount},
            borrowed_amount=borrow_amount,
            borrowed_asset="USDC",
            opened_at_block=self.current_block,
            available_cash=borrow_amount,  # Borrowed money is available to deploy
        )

        min_hf = 1.2
        max_safe_leverage = 1.0 + account.liquidation_threshold
        if leverage > max_safe_leverage:
            raise ValueError(
                f"Leverage {leverage:.2f}x too high. Maximum safe leverage: {max_safe_leverage:.2f}x"
            )

        hf = account.health_factor(self.oracle)
        if hf < min_hf:
            raise ValueError(
                f"Health factor too low: {hf:.3f}. Reduce leverage or increase collateral."
            )

        user.wallet_balance[collateral_asset] -= collateral_amount
        self.pool.total_borrowed += borrow_amount
        self.credit_accounts[account_id] = account

        return {
            "action": "borrow",
            "account_id": account_id,
            "collateral": collateral_amount,
            "collateral_asset": collateral_asset,
            "borrowed": borrow_amount,
            "leverage": leverage,
            "health_factor": hf,
        }

    def deploy_to_strategy(self, user_address: str, account_id: str) -> Dict:
        """Deploy all available borrowed funds to strategy"""
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]
        if account.owner != user_address:
            raise ValueError("User does not own this credit account")

        if account.is_liquidated:
            raise ValueError("Cannot deploy to liquidated account")

        if account.strategy is None:
            account.strategy = YearnVaultStrategy()

        available = account.available_cash
        if available <= 0:
            raise ValueError("No funds available to deploy")

        account.strategy.deposit(available)
        account.available_cash = 0

        return {
            "action": "deploy_to_strategy",
            "account_id": account_id,
            "amount_deployed": available,
            "strategy_value": account.strategy.value(),
        }

    def withdraw_from_strategy(self, user_address: str, account_id: str) -> Dict:
        """Withdraw all funds from strategy back to credit account"""
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]
        if account.owner != user_address:
            raise ValueError("User does not own this credit account")

        if account.is_liquidated:
            raise ValueError("Cannot withdraw from liquidated account")

        if account.strategy is None:
            raise ValueError("No strategy to withdraw from")

        if account.strategy.value() <= 0:
            raise ValueError("No funds in strategy to withdraw")

        withdrawn = account.strategy.withdraw()
        account.available_cash += withdrawn

        return {
            "action": "withdraw_from_strategy",
            "account_id": account_id,
            "amount_withdrawn": withdrawn,
            "strategy_value": 0,
        }

    def repay_debt(self, user_address: str, account_id: str) -> Dict:
        """Repay debt (borrowed + interest) from available cash"""
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]
        if account.owner != user_address:
            raise ValueError("User does not own this credit account")

        if account.is_liquidated:
            raise ValueError("Cannot repay on liquidated account")

        total_debt = account.total_debt()
        borrowed_principal = account.borrowed_amount  # Save before resetting

        if account.available_cash < total_debt:
            raise ValueError(
                f"Insufficient funds. Available: ${account.available_cash:,.2f}, Debt: ${total_debt:,.2f}"
            )

        account.available_cash -= total_debt
        account.borrowed_amount = 0
        account.accrued_interest = 0
        # Only reduce pool's total_borrowed by principal, not interest
        self.pool.total_borrowed -= borrowed_principal

        return {
            "action": "repay_debt",
            "account_id": account_id,
            "debt_repaid": total_debt,
            "available_remaining": account.available_cash,
        }

    def add_collateral(
        self, user_address: str, account_id: str, amount: float, asset: str = "ETH"
    ) -> Dict:
        """Add more collateral to existing account"""
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        user = self.users[user_address]
        if user.wallet_balance.get(asset, 0.0) < amount:
            raise ValueError(f"Insufficient {asset} balance")

        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]
        if account.owner != user_address:
            raise ValueError("User does not own this credit account")

        if account.is_liquidated:
            raise ValueError("Cannot add collateral to liquidated account")

        user.wallet_balance[asset] -= amount
        account.collateral[asset] = account.collateral.get(asset, 0.0) + amount

        hf = account.health_factor(self.oracle)

        return {
            "action": "add_collateral",
            "account_id": account_id,
            "amount": amount,
            "asset": asset,
            "new_hf": hf,
        }

    def add_borrow(self, user_address: str, account_id: str, amount: float) -> Dict:
        """Add more borrow to existing account"""
        if user_address not in self.users:
            raise ValueError(f"User {user_address} not found")

        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]
        if account.owner != user_address:
            raise ValueError("User does not own this credit account")

        if account.is_liquidated:
            raise ValueError("Cannot add borrow to liquidated account")

        available = self.pool.total_liquidity - self.pool.total_borrowed
        if amount > available:
            raise ValueError(
                f"Insufficient pool liquidity. Available: {available:,.2f}"
            )

        account.borrowed_amount += amount
        account.available_cash += amount  # Add borrowed funds to available cash
        self.pool.total_borrowed += amount

        hf = account.health_factor(self.oracle)
        if hf < 1.2:
            account.borrowed_amount -= amount
            account.available_cash -= (
                amount  # Revert available cash if health factor check fails
            )
            self.pool.total_borrowed -= amount
            raise ValueError(
                f"Health factor would be too low: {hf:.3f}. Need HF >= 1.2"
            )

        leverage = (
            account.collateral_value_usd(self.oracle) + account.borrowed_amount
        ) / account.collateral_value_usd(self.oracle)

        return {
            "action": "add_borrow",
            "account_id": account_id,
            "amount": amount,
            "new_hf": hf,
            "new_leverage": leverage,
        }

    def liquidate_account(self, account_id: str) -> Dict:
        if account_id not in self.credit_accounts:
            raise ValueError(f"Credit account {account_id} not found")

        account = self.credit_accounts[account_id]

        if account.is_liquidated:
            raise ValueError("Account already liquidated")

        if account.health_factor(self.oracle) >= 1.0:
            raise ValueError("Account is not liquidatable")

        liquidation_penalty = 0.05

        total_debt = account.total_debt()
        strategy_value = account.strategy_value_usd(self.oracle)
        collateral_value = account.collateral_value_usd(self.oracle)
        available_cash_usd = account.available_cash * self.oracle.get_price("USDC")

        self.pool.total_borrowed -= account.borrowed_amount

        if account.strategy:
            account.strategy.withdraw()

        total_available = collateral_value + strategy_value + available_cash_usd
        penalty_amount = total_debt * liquidation_penalty
        remaining_after_penalty = total_available - total_debt - penalty_amount

        account.is_liquidated = True

        return {
            "action": "liquidate",
            "account_id": account_id,
            "owner": account.owner,
            "debt_repaid": total_debt,
            "liquidation_penalty": penalty_amount,
            "collateral_lost": max(0, total_debt - collateral_value - strategy_value),
            "penalty_recipient": "Liquidator",
        }

    def advance_time(self, days: int):
        blocks = int(days * (self.blocks_per_year / 365))
        self.current_block += blocks

        borrow_rate = self.pool.effective_borrow_rate()
        for account in self.credit_accounts.values():
            if account.is_liquidated:
                continue

            interest = account.borrowed_amount * (borrow_rate / 365) * days
            account.accrued_interest += interest

            if account.strategy:
                account.strategy.accrue_yield(days)

            account.last_update = datetime.now()

    def simulate_price_drop(self, percent: float, asset: str = "USDC"):
        """Drop price by given percentage for specific asset"""
        self.oracle.prices[asset] *= 1 - percent / 100

    def revert_price(self, asset: str):
        """Revert asset price to original (USDC=1.0, ETH=3000.0)"""
        original_prices = {"USDC": 1.0, "ETH": 3000.0}
        if asset in original_prices:
            self.oracle.prices[asset] = original_prices[asset]

    def get_all_accounts(self) -> List[Dict]:
        return [
            {
                "account_id": ca.account_id,
                "owner": ca.owner,
                "collateral_value_usd": ca.collateral_value_usd(self.oracle),
                "borrowed_principal": ca.borrowed_amount,
                "total_debt": ca.total_debt(),
                "deposited_amount": ca.strategy.deposited_amount if ca.strategy else 0,
                "strategy_value_usd": ca.strategy_value_usd(self.oracle),
                "rewards": ca.strategy.rewards if ca.strategy else 0,
                "health_factor": ca.health_factor(self.oracle),
                "status": ca.status(self.oracle).value,
                "is_liquidated": ca.is_liquidated,
                "available_cash": ca.available_cash,
            }
            for ca in self.credit_accounts.values()
            if not ca.is_liquidated
        ]

    def get_elapsed_days(self) -> float:
        return (self.current_block / self.blocks_per_year) * 365

    def get_pool_state(self) -> Dict:
        return {
            "asset": self.pool.asset,
            "total_liquidity": self.pool.total_liquidity,
            "total_borrowed": self.pool.total_borrowed,
            "available": self.pool.total_liquidity - self.pool.total_borrowed,
            "utilization": self.pool.utilization(),
            "base_rate_apy": self.pool.borrow_rate(),
            "borrow_rate_apy": self.pool.effective_borrow_rate(),
            "current_block": self.current_block,
            "elapsed_days": self.get_elapsed_days(),
        }


def main():
    st.set_page_config(
        page_title="Gearbox Protocol Simulator", page_icon="⚙️", layout="wide"
    )

    st.title("⚙️ Gearbox Protocol Simulator")
    strategy_apy = YearnVaultStrategy().yield_apy
    st.caption(
        f"Borrow USDC, deploy to Yearn ({strategy_apy*100:.1f}% APY), monitor health factors"
    )

    if "simulator" not in st.session_state:
        st.session_state.simulator = GearboxSimulator()

    sim = st.session_state.simulator
    pool_state = sim.get_pool_state()

    st.sidebar.markdown("### Pool (USDC)")
    st.sidebar.metric("Liquidity", f"${pool_state['total_liquidity']:,.0f}")
    st.sidebar.metric("Utilization", f"{pool_state['utilization']*100:.1f}%")
    st.sidebar.metric("Borrow APY", f"{pool_state['borrow_rate_apy']*100:.2f}%")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Time")
    st.sidebar.metric("Days", f"{sim.get_elapsed_days():.1f}")
    days = st.sidebar.number_input(
        "Advance", min_value=1, max_value=365, value=30, key="days_input"
    )
    if st.sidebar.button("⏭️ Advance"):
        sim.advance_time(days)
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Wallet")

    accounts = sim.get_all_accounts()
    account_ids = [acc["account_id"] for acc in accounts] + ["+ New Account"]
    selected = st.selectbox("Select Account", account_ids, key="select_account")

    if selected == "+ New Account":
        user_addr = "0xuser1"
    else:
        acc = next((a for a in accounts if a["account_id"] == selected), None)
        user_addr = acc["owner"] if acc else "0xuser1"

    if user_addr not in sim.users:
        sim.create_user(user_addr, {"USDC": 50000.0, "ETH": 50.0})
    user = sim.users[user_addr]
    st.sidebar.metric("ETH", f"{user.wallet_balance.get('ETH', 0):.2f}")
    st.sidebar.metric("USDC", f"${user.wallet_balance.get('USDC', 0):,.0f}")

    tab1, tab2, tab3 = st.tabs(["📊 Accounts", "💰 Strategies", "🔥 Liquidations"])

    with tab1:
        st.subheader("Accounts")
        with st.expander("💡 **Credit Accounts Guide** - Click to expand"):
            st.markdown(
                """
            **What are Credit Accounts?**
            
            Open accounts by providing ETH collateral and borrowing USDC. You can then deploy borrowed funds to strategies to earn yield.
            
            **Health Factor Requirements:**
            - **Minimum to Open**: HF ≥ 1.2
            - **Healthy**: HF ≥ 1.2 (safe from liquidation)
            - **At Risk**: HF 1.0-1.2 (monitor closely)
            - **Liquidatable**: HF < 1.0 (can be liquidated)
            
            **Key Terms:**
            - **Collateral**: ETH locked in your account
            - **Borrowed**: USDC principal borrowed from the pool
            - **Debt**: Borrowed amount + accrued interest
            - **Available**: USDC ready to deploy or repay
            
            **Health Factor Formula:**
            ```
            HF = (Total Collateral × 0.95) / Total Debt
            ```
            - **Total Collateral** = Collateral Value + Strategy Value + Available Cash
            - **Total Debt** = Borrowed Principal + Accrued Interest
            - **0.95** = Liquidation threshold
            """
            )

        if selected == "+ New Account":
            st.markdown("### Open New Account")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Collateral**")
                collateral_asset = st.selectbox(
                    "Asset", ["ETH"], disabled=True, key="col_asset"
                )
                collateral_amt = st.number_input(
                    "Amount (ETH)", min_value=0.01, value=5.0, step=0.5, key="col_amt"
                )

            with col2:
                st.markdown("**Borrow**")
                st.text_input("Asset", value="USDC", disabled=True, key="borrow_asset")
                borrow_amt = st.number_input(
                    "Amount (USDC)",
                    min_value=100.0,
                    value=10000.0,
                    step=100.0,
                    key="borrow_amt",
                )

            if collateral_amt > 0 and borrow_amt > 0:
                collateral_usd = collateral_amt * sim.oracle.get_price("ETH")
                leverage = (collateral_usd + borrow_amt) / collateral_usd
                temp_account = CreditAccount(
                    account_id="temp",
                    owner="temp",
                    collateral={"ETH": collateral_amt},
                    borrowed_amount=borrow_amt,
                    borrowed_asset="USDC",
                )
                hf = temp_account.health_factor(sim.oracle)

                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("Leverage", f"{leverage:.2f}x")
                c2.metric("Collateral (USD)", f"${collateral_usd:,.0f}")
                hf_color = "green" if hf >= 1.2 else "red"
                c3.markdown(f"**Health Factor:** :{hf_color}[{hf:.3f}]")

                can_open = hf >= 1.2
                if not can_open:
                    st.warning("⚠️ Health factor must be ≥ 1.2 to open account")

                if st.button(
                    "OPEN ACCOUNT",
                    type="primary",
                    disabled=not can_open,
                    key="btn_open",
                ):
                    user_addr = "0xuser1"
                    if user_addr not in sim.users:
                        sim.create_user(
                            user_addr, {"USDC": 0.0, "ETH": collateral_amt * 2}
                        )
                    try:
                        result = sim.borrow(
                            user_addr, collateral_amt, borrow_amt, "ETH"
                        )
                        st.toast(f"✅ Account {result['account_id']} opened!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
        else:
            acc = next((a for a in accounts if a["account_id"] == selected), None)
            if acc:
                account = sim.credit_accounts[acc["account_id"]]
                st.markdown(f"### {acc['account_id']}")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Collateral", f"${acc['collateral_value_usd']:,.0f}")
                c2.metric("Borrowed", f"${acc['borrowed_principal']:,.0f}")
                c3.metric("Debt", f"${acc['total_debt']:,.0f}")
                c4.metric("HF", f"{acc['health_factor']:.3f}")

                st.markdown("#### Add Collateral")
                cc1, cc2 = st.columns(2)
                cc1.number_input(
                    "ETH Amount",
                    min_value=0.01,
                    value=1.0,
                    step=0.5,
                    key="add_collateral_amt",
                )
                if cc2.button("Add Collateral", key="btn_add_collateral"):
                    user_addr = acc["owner"]
                    if user_addr not in sim.users:
                        sim.create_user(
                            user_addr,
                            {
                                "USDC": 0.0,
                                "ETH": st.session_state.add_collateral_amt * 2,
                            },
                        )
                    try:
                        result = sim.add_collateral(
                            user_addr,
                            acc["account_id"],
                            st.session_state.add_collateral_amt,
                            "ETH",
                        )
                        st.toast(f"✅ Collateral added! HF: {result['new_hf']:.3f}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

                st.markdown("#### Add Borrow")
                cb1, cb2 = st.columns(2)
                cb1.number_input(
                    "USDC Amount",
                    min_value=100.0,
                    value=1000.0,
                    step=100.0,
                    key="add_borrow_amt",
                )
                if cb2.button("Add Borrow", key="btn_add_borrow"):
                    user_addr = acc["owner"]
                    if user_addr not in sim.users:
                        sim.create_user(
                            user_addr,
                            {"USDC": st.session_state.add_borrow_amt * 2, "ETH": 0.0},
                        )
                    try:
                        result = sim.add_borrow(
                            user_addr,
                            acc["account_id"],
                            st.session_state.add_borrow_amt,
                        )
                        st.toast(f"✅ Borrowed! HF: {result['new_hf']:.3f}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

        st.divider()
        st.subheader("All Accounts")

        accounts = sim.get_all_accounts()
        if not accounts:
            st.info("No accounts yet.")
        else:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = st.columns(
                [2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2]
            )
            c1.write("**Account**")
            c2.write("**Collateral**")
            c3.write("**Borrowed**")
            c4.write("**Deposited**")
            c5.write("**Strategy**")
            c6.write("**Available**")
            c7.write("**Rewards**")
            c8.write("**Int.**")
            c9.write("**HF**")
            c10.write("**")
            c11.write("**")

            for acc in accounts:
                account = sim.credit_accounts[acc["account_id"]]
                collateral = acc["collateral_value_usd"]
                borrowed = acc["borrowed_principal"]
                deposited = acc["deposited_amount"]
                strategy_value = acc["strategy_value_usd"]
                available = acc["available_cash"]
                rewards = acc["rewards"]
                accrued_interest = account.accrued_interest

                c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = st.columns(
                    [2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2]
                )
                c1.write(f"**{acc['account_id']}**")
                c2.write(f"${collateral:,.0f}")
                c3.write(f"${borrowed:,.0f}")
                c4.write(f"${deposited:,.0f}")
                c5.write(f"${strategy_value:,.0f}")
                c6.write(f"${available:,.0f}")
                c7.write(f"${rewards:.2f}")
                c8.write(f"${accrued_interest:.2f}")
                c9.write(f"{acc['health_factor']:.2f}")
                if c10.button(
                    "Liquidate",
                    key=f"liq_tbl_{acc['account_id']}",
                    disabled=acc["status"] != "liquidatable",
                ):
                    try:
                        result = sim.liquidate_account(acc["account_id"])
                        st.toast(f"✅ Liquidated")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

    with tab2:
        st.subheader("Strategies")
        with st.expander("💡 **Strategy Management Guide** - Click to expand"):
            st.markdown(
                """
            **Strategy Management**: Deploy borrowed USDC to Yearn Vault (8% APY) to earn yield. Strategy value counts as collateral for Health Factor.
            
            - **Deploy**: Move available cash to Yearn strategy to start earning yield
            - **Withdraw**: Remove funds from strategy back to available cash
            - **Repay**: Use available cash to pay down debt (principal + interest)
            - **Available**: USDC ready to deploy or repay (from borrowing or withdrawing)
            """
            )

        accounts = sim.get_all_accounts()
        if not accounts:
            st.info("No accounts yet. Open one in the first tab.")
        else:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12 = st.columns(12)
            c1.write("**Account**")
            c2.write("**Collateral**")
            c3.write("**Borrowed**")
            c4.write("**Deposited**")
            c5.write("**Strategy**")
            c6.write("**Available**")
            c7.write("**Rewards**")
            c8.write("**Int.**")
            c9.write("**HF**")
            c10.write("**")
            c11.write("**")
            c12.write("**")

            for acc in accounts:
                account = sim.credit_accounts[acc["account_id"]]
                collateral = acc["collateral_value_usd"]
                borrowed = acc["borrowed_principal"]
                deposited = acc["deposited_amount"]
                strategy_value = acc["strategy_value_usd"]
                available = acc["available_cash"]
                rewards = acc["rewards"]
                accrued_interest = account.accrued_interest

                c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12 = st.columns(12)
                c1.write(f"**{acc['account_id']}**")
                c2.write(f"${collateral:,.0f}")
                c3.write(f"${borrowed:,.0f}")
                c4.write(f"${deposited:,.0f}")
                c5.write(f"${strategy_value:,.0f}")
                c6.write(f"${available:,.0f}")
                c7.write(f"${rewards:.2f}")
                c8.write(f"${accrued_interest:.2f}")
                c9.write(f"{acc['health_factor']:.2f}")
                if c10.button(
                    "Deploy",
                    key=f"d_{acc['account_id']}",
                    use_container_width=True,
                    disabled=available <= 0,
                ):
                    try:
                        sim.deploy_to_strategy(acc["owner"], acc["account_id"])
                        st.toast("✅ Deployed to Yearn")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
                total_debt = borrowed + accrued_interest
                if c11.button(
                    "Repay",
                    key=f"r_{acc['account_id']}",
                    use_container_width=True,
                    disabled=acc["borrowed_principal"] == 0 or available < total_debt,
                ):
                    try:
                        result = sim.repay_debt(acc["owner"], acc["account_id"])
                        st.toast(
                            f"✅ Repaid ${result['debt_repaid']:,.0f} | Available: ${result['available_remaining']:,.0f}"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
                if c12.button(
                    "Withdraw",
                    key=f"c_{acc['account_id']}",
                    use_container_width=True,
                    disabled=deposited <= 0 or strategy_value <= 0,
                ):
                    try:
                        result = sim.withdraw_from_strategy(
                            acc["owner"], acc["account_id"]
                        )
                        st.toast(f"✅ ${result['amount_withdrawn']:,.0f}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

            st.markdown("---")
    with tab3:
        st.subheader("Liquidations")
        with st.expander("⚠️ **Liquidation Risk Guide** - Click to expand"):
            st.markdown(
                """
            **Liquidation Risk**: Accounts with Health Factor < 1.0 can be liquidated. Price drops reduce collateral value and increase risk. Monitor **At Risk** accounts (HF 1.0-1.2).
            
            - **Liquidatable** (HF < 1.0): Can be liquidated immediately, 5% penalty applies
            - **At Risk** (HF 1.0-1.2): Close to liquidation threshold, monitor closely
            - **Healthy** (HF ≥ 1.2): Safe from liquidation
            - Use price drop buttons to simulate market stress and test liquidation scenarios
            """
            )

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("📉 DROP 10% USDC"):
            sim.simulate_price_drop(10, "USDC")
            st.rerun()
        if c2.button("↩️ Restore USDC"):
            sim.revert_price("USDC")
            st.rerun()
        if c3.button("📉 DROP 10% ETH"):
            sim.simulate_price_drop(10, "ETH")
            st.rerun()
        if c4.button("↩️ Restore ETH"):
            sim.revert_price("ETH")
            st.rerun()

        st.divider()

        accounts = sim.get_all_accounts()
        liquidatable = [a for a in accounts if a["status"] == "liquidatable"]
        at_risk = [a for a in accounts if a["status"] == "at_risk"]
        healthy = [a for a in accounts if a["status"] == "healthy"]

        st.markdown(
            f"**Accounts:** {len(healthy)} ✅  |  {len(at_risk)} ⚠️  |  {len(liquidatable)} 🔥"
        )

        for acc in liquidatable:
            st.error(
                f"**{acc['account_id']}** | HF: {acc['health_factor']:.3f} | Debt: ${acc['total_debt']:,.0f}"
            )
            if st.button("Liquidate", key=f"liq_{acc['account_id']}"):
                try:
                    result = sim.liquidate_account(acc["account_id"])
                    st.success(
                        f"✅ Liquidated | Penalty: ${result['liquidation_penalty']:,.0f}"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

        for acc in at_risk:
            st.warning(
                f"**{acc['account_id']}** | HF: {acc['health_factor']:.3f} | Debt: ${acc['total_debt']:,.0f}"
            )

        for acc in healthy:
            st.info(
                f"**{acc['account_id']}** | HF: {acc['health_factor']:.3f} | Debt: ${acc['total_debt']:,.0f}"
            )


if __name__ == "__main__":
    main()
