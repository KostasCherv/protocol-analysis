"""
Streamlit UI for Gearbox Protocol Credit Account Management

Provides a user-friendly interface for:
- Opening credit accounts
- Adding collateral
- Borrowing (increasing debt)
- Repaying debt
- Closing accounts
"""

import streamlit as st
from datetime import datetime
from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gearbox_fork.fork_client import ForkClient
from gearbox_fork.contracts import ContractManager
from gearbox_fork.credit_account_controller import CreditAccountController
from gearbox_fork.state import StateStore, StateReader
from gearbox_fork.wallet_manager import WalletManager
from gearbox_fork.config import USDC, CREDIT_MANAGER_V3
from gearbox_fork.anvil_accounts import get_address
from gearbox_fork.transactions import prepare_repay_all_debt

# Constants
MAX_UINT256 = 2**256 - 1

# Page config
st.set_page_config(
    page_title="Gearbox Protocol - Credit Account Manager",
    page_icon="⚙️",
    layout="wide",
)

st.markdown(
    """
<style>
    .rightPanel {
        position: fixed;
        right: 0;
        top: 0;
        width: 300px;
        height: 100vh;
        overflow-y: auto;
        background-color: var(--secondary-background-color);
        border-left: 1px solid var(--border-color);
        padding: 1rem;
        z-index: 100;
    }
    .main .block-container {
        padding-right: 320px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "controller" not in st.session_state:
    try:
        fork_client = ForkClient()
        w3 = fork_client.w3
        cm = ContractManager(w3)
        state_store = StateStore(st.session_state)
        st.session_state.controller = CreditAccountController(
            w3, cm, fork_client, state_store
        )
        st.session_state.wallet_manager = WalletManager(fork_client)
        st.session_state.state_reader = StateReader(w3, cm)
        st.session_state.account_index = 0
        st.session_state.credit_account = None
        st.session_state.transaction_log = []
        if "expander_add_collateral_open" not in st.session_state:
            st.session_state.expander_add_collateral_open = False
    except Exception as e:
        st.error(f"Failed to initialize: {str(e)}")
        st.stop()

# Get components from session state
controller = st.session_state.controller
wallet_manager = st.session_state.wallet_manager
state_reader = st.session_state.state_reader
fork_client = controller.fork_client


def log_transaction(action_name: str, result: Dict[str, Any], success: bool = None):
    """Log transaction to session state"""
    if success is None:
        success = result.get("success", False)

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action_name,
        "success": success,
        "tx_hash": result.get("tx_hash"),
        "error": result.get("error"),
    }

    if "transaction_log" not in st.session_state:
        st.session_state.transaction_log = []

    st.session_state.transaction_log.insert(0, log_entry)  # Add to beginning
    # Keep only last 20 entries
    if len(st.session_state.transaction_log) > 20:
        st.session_state.transaction_log = st.session_state.transaction_log[:20]


def set_flash_success(msg: str, tx_hash: Optional[str] = None) -> None:
    """Store success message to display after rerun (survives st.rerun())."""
    st.session_state.flash_success = {"msg": msg, "tx_hash": tx_hash}


def set_flash_error(msg: str) -> None:
    """Store error message to display next to Actions after rerun."""
    st.session_state.flash_error = {"msg": msg}


def display_account_summary(credit_account: str):
    """Display formatted account summary"""
    if not credit_account:
        return

    try:
        state = controller.get_state(credit_account, refresh=True)
        summary = state_reader.get_account_summary(credit_account)
        balances = state_reader.get_credit_account_balances(credit_account)

        if not summary.get("success"):
            st.error(f"Error getting summary: {summary.get('error')}")
            return

        # Account info card
        with st.container():
            st.subheader("📊 Account Summary")

            col1, col2, col3 = st.columns(3)

            with col1:
                # Debt breakdown
                total_debt = summary.get("total_debt", summary.get("debt", 0))
                principal_debt = summary.get("debt", 0)
                accrued_interest = summary.get("accrued_interest", 0)
                accrued_fees = summary.get("accrued_fees", 0)

                st.metric("Total Debt", f"{total_debt / 10**6:.2f} USDC")
                if principal_debt > 0:
                    st.caption(f"Principal: {principal_debt / 10**6:.2f} USDC")
                if accrued_interest > 0:
                    st.caption(f"Interest: {accrued_interest / 10**6:.4f} USDC")
                if accrued_fees > 0:
                    st.caption(f"Fees: {accrued_fees / 10**6:.4f} USDC")

                st.metric(
                    "Collateral USD", f"{summary['collateral_usd'] / 10**8:.2f} USD"
                )

            with col2:
                st.metric(
                    "Weighted Collateral USD",
                    f"{summary['weighted_collateral_usd'] / 10**8:.2f} USD",
                )

                # Health factor with color coding
                health_factor = summary.get("health_factor")
                if health_factor:
                    if health_factor >= 100:
                        color = "🟢"
                    elif health_factor >= 50:
                        color = "🟡"
                    else:
                        color = "🔴"
                    st.metric("Health Factor", f"{color} {health_factor:.2f}%")
                else:
                    st.metric("Health Factor", "N/A")

            with col3:
                st.metric("USDC Balance", f"{balances['USDC'] / 10**6:.2f} USDC")

            # Credit account address
            st.caption(f"Credit Account: `{credit_account}`")

    except Exception as e:
        st.error(f"Error displaying summary: {str(e)}")


def get_account_address(account_index: int) -> str:
    """Get account address from index"""
    try:
        return get_address(account_index)
    except:
        return f"Account {account_index}"


# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")

    # Account selection
    account_index = st.selectbox(
        "Account Index",
        options=list(range(10)),
        index=st.session_state.account_index,
        help="Select Anvil account (0-9)",
    )
    st.session_state.account_index = account_index
    account_address = get_account_address(account_index)
    st.caption(f"Address: `{account_address}`")

    st.divider()

    # Funding section
    st.subheader("💰 Fund Account")

    # Fund ETH
    if st.button("Fund ETH (for gas)", use_container_width=True, key="fund_eth_btn"):
        try:
            with st.spinner("Funding ETH..."):
                fork_client.set_balance(account_address, 10 * 10**18)
                eth_balance = controller.w3.eth.get_balance(account_address)
                st.success(f"Funded! Balance: {eth_balance / 10**18:.2f} ETH")
                log_transaction(
                    "Fund ETH",
                    {"success": True, "tx_hash": "N/A (balance set)"},
                    success=True,
                )
        except Exception as e:
            st.error(f"Failed to fund ETH: {str(e)}")
            log_transaction(
                "Fund ETH", {"success": False, "error": str(e)}, success=False
            )

    # Fund USDC
    usdc_amount = st.number_input(
        "USDC Amount", min_value=0.0, value=10000.0, step=1000.0
    )
    if st.button("Fund USDC", use_container_width=True, key="fund_usdc_btn"):
        try:
            with st.spinner(f"Funding {usdc_amount} USDC..."):
                amount_wei = int(usdc_amount * 10**6)
                result = wallet_manager.fund_from_whale(
                    account_address, USDC, amount_wei
                )
                if result.get("success"):
                    st.success(f"Funded! Balance: {result['balance'] / 10**6:.2f} USDC")
                    log_transaction("Fund USDC", result, success=True)
                else:
                    st.error(f"Failed: {result.get('error')}")
                    log_transaction("Fund USDC", result, success=False)
        except Exception as e:
            st.error(f"Failed to fund USDC: {str(e)}")
            log_transaction(
                "Fund USDC", {"success": False, "error": str(e)}, success=False
            )

    st.divider()

    # Current account info
    st.subheader("📋 Current Account")
    if st.session_state.credit_account:
        st.success("✅ Credit Account Active")
        st.caption(f"`{st.session_state.credit_account}`")
    else:
        st.info("No credit account opened")

    # Display balances
    try:
        balances = state_reader.get_account_balances(account_address)
        st.caption(f"ETH: {balances['ETH'] / 10**18:.4f}")
        st.caption(f"USDC: {balances['USDC'] / 10**6:.2f}")
    except:
        pass

    st.divider()

    # Advance blocks section
    st.subheader("⏰ Advance Blocks")
    if st.session_state.credit_account:
        # Show current block number
        try:
            current_block = fork_client.get_block_number()
            st.caption(f"Current Block: {current_block}")
        except:
            pass

        advance_blocks = st.number_input(
            "Blocks",
            min_value=1,
            value=100,
            step=10,
            key="advance_blocks",
            help="Mine blocks (~12s each) so interest/fees accrue. Borrow first to see accrual.",
        )

        if st.button(
            "Advance Blocks", use_container_width=True, key="advance_blocks_btn"
        ):
            try:
                with st.spinner(f"Mining {advance_blocks} blocks..."):
                    summary_before = state_reader.get_account_summary(
                        st.session_state.credit_account
                    )
                    fees_before = summary_before.get(
                        "accrued_fees", 0
                    ) + summary_before.get("accrued_interest", 0)

                    fork_client.mine_blocks(advance_blocks)

                    summary_after = state_reader.get_account_summary(
                        st.session_state.credit_account
                    )
                    fees_after = summary_after.get(
                        "accrued_fees", 0
                    ) + summary_after.get("accrued_interest", 0)
                    fees_increase = fees_after - fees_before

                    log_transaction(
                        "Advance Blocks",
                        {
                            "success": True,
                            "blocks": advance_blocks,
                            "fees_increase": fees_increase,
                        },
                        success=True,
                    )
                    set_flash_success(
                        f"✅ Mined {advance_blocks} blocks! Fees increased by {fees_increase / 10**6:.4f} USDC"
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to advance blocks: {str(e)}")
                log_transaction(
                    "Advance Blocks", {"success": False, "error": str(e)}, success=False
                )
    else:
        st.info("Open a credit account to advance blocks and track fees")

# Main area
st.title("⚙️ Gearbox Protocol - Credit Account Manager")

# Display account summary if exists
if st.session_state.credit_account:
    display_account_summary(st.session_state.credit_account)
    st.divider()

# Action buttons section
st.header("🎯 Actions")

# Flash success message from previous run (survives st.rerun)
if st.session_state.get("flash_success"):
    data = st.session_state.flash_success
    st.success(data["msg"])
    if data.get("tx_hash"):
        st.info(f"📝 Transaction Hash: `{data['tx_hash']}`")
    del st.session_state.flash_success

# Flash error message from previous run (show next to Actions)
if st.session_state.get("flash_error"):
    data = st.session_state.flash_error
    st.error(data["msg"])
    del st.session_state.flash_error

# Open Account
with st.expander(
    "📝 Open Credit Account", expanded=not st.session_state.credit_account
):
    if st.session_state.credit_account:
        st.warning("⚠️ Credit account already exists. Close it first to open a new one.")
    else:
        if st.button(
            "Open Account",
            type="primary",
            use_container_width=True,
            key="open_account_btn",
        ):
            try:
                with st.spinner("Opening credit account..."):
                    # Fund ETH if needed
                    eth_balance = controller.w3.eth.get_balance(account_address)
                    if eth_balance < 10 * 10**18:
                        fork_client.set_balance(account_address, 10 * 10**18)

                    # Open account with empty multicall
                    result = controller.execute_open_account(
                        account_index=account_index,
                        calls=[],
                    )

                    if result.get("success"):
                        st.session_state.credit_account = result["credit_account"]
                        log_transaction("Open Account", result, success=True)
                        fork_client.mine_blocks(
                            1
                        )  # Advance one block after successful action
                        set_flash_success(
                            f"✅ Account opened! Credit Account: `{result['credit_account']}`",
                            tx_hash=result.get("tx_hash"),
                        )
                        st.rerun()
                    else:
                        log_transaction("Open Account", result, success=False)
                        set_flash_error(
                            f"❌ Failed: {result.get('error', 'Unknown error')}"
                        )
                        st.rerun()
            except Exception as e:
                log_transaction(
                    "Open Account", {"success": False, "error": str(e)}, success=False
                )
                set_flash_error(f"❌ Error: {str(e)}")
                st.rerun()

with st.expander(
    "💎 Add Collateral",
    expanded=st.session_state.get("expander_add_collateral_open", False),
):
    if not st.session_state.credit_account:
        st.warning("⚠️ Please open a credit account first.")
    else:
        # Get account address for this section
        account_address = get_account_address(st.session_state.account_index)

        collateral_amount = st.number_input(
            "Amount (USDC)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            key="collateral_amount",
        )

        token_address = USDC
        token_decimals = 6
        amount_wei = int(collateral_amount * (10**token_decimals))

        if st.button(
            "Add Collateral",
            use_container_width=True,
            type="primary",
            key="add_collateral_btn",
        ):
            try:
                with st.spinner(f"Adding {collateral_amount} USDC as collateral..."):
                    # Step 1: Fund from whale if needed
                    token_contract = controller.cm.get_erc20(token_address)
                    balance = token_contract.functions.balanceOf(account_address).call()
                    if balance < amount_wei:
                        st.info(f"💰 Funding {collateral_amount} USDC...")
                        fund_result = wallet_manager.fund_from_whale(
                            account_address, token_address, amount_wei
                        )
                        if not fund_result.get("success"):
                            log_transaction(
                                "Add Collateral", fund_result, success=False
                            )
                            set_flash_error(
                                f"❌ Failed to fund: {fund_result.get('error', 'Unknown error')}"
                            )
                            st.session_state.expander_add_collateral_open = True
                            st.rerun()
                        st.success(
                            f"✅ Funded {fund_result['balance'] / (10**token_decimals):.2f} USDC"
                        )

                    # Step 2: Automatically approve Credit Manager if needed
                    allowance = token_contract.functions.allowance(
                        account_address, CREDIT_MANAGER_V3
                    ).call()
                    if allowance < amount_wei:
                        st.info(
                            f"🔐 Approving Credit Manager to spend {collateral_amount} USDC..."
                        )
                        approve_result = wallet_manager.approve_token(
                            account_index, token_address, CREDIT_MANAGER_V3, amount_wei
                        )
                        if not approve_result.get("success"):
                            log_transaction(
                                "Add Collateral", approve_result, success=False
                            )
                            set_flash_error(
                                f"❌ Failed to approve: {approve_result.get('error', 'Unknown error')}"
                            )
                            st.session_state.expander_add_collateral_open = True
                            st.rerun()
                        st.success("✅ Approval successful")

                    # Prepare calls
                    calls = []
                    call = controller.prepare_action(
                        "add_collateral", token=token_address, amount=amount_wei
                    )
                    calls.append(call)

                    # Execute (simulation happens automatically in execute_multicall)
                    result = controller.execute_multicall(
                        st.session_state.credit_account,
                        calls,
                        account_index=account_index,
                    )

                    if result.get("success"):
                        log_transaction("Add Collateral", result, success=True)
                        fork_client.mine_blocks(
                            1
                        )  # Advance one block after successful action
                        set_flash_success(
                            f"🎉 **Success!** Added {collateral_amount} USDC as collateral!",
                            tx_hash=result.get("tx_hash"),
                        )
                        st.session_state.expander_add_collateral_open = True
                        st.rerun()
                    else:
                        err = result.get("simulation_error") or result.get(
                            "error", "Unknown error"
                        )
                        log_transaction("Add Collateral", result, success=False)
                        set_flash_error(f"❌ {err}")
                        st.session_state.expander_add_collateral_open = True
                        st.rerun()
            except Exception as e:
                log_transaction(
                    "Add Collateral",
                    {"success": False, "error": str(e)},
                    success=False,
                )
                set_flash_error(f"❌ Error: {str(e)}")
                st.session_state.expander_add_collateral_open = True
                st.rerun()

with st.expander("📈 Increase Debt (Borrow)"):
    if not st.session_state.credit_account:
        st.warning("⚠️ Please open a credit account first.")
    else:
        # Get account address for this section
        account_address = get_account_address(st.session_state.account_index)

        borrow_amount = st.number_input(
            "Borrow Amount (USDC)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            key="borrow_amount",
        )
        amount_wei = int(borrow_amount * 10**6)

        if st.button("Borrow", use_container_width=True, key="borrow_btn"):
            try:
                with st.spinner(f"Borrowing {borrow_amount} USDC..."):
                    call = controller.prepare_action("increase_debt", amount=amount_wei)
                    result = controller.execute_multicall(
                        st.session_state.credit_account,
                        [call],
                        account_index=account_index,
                    )

                    if result.get("success"):
                        log_transaction("Increase Debt", result, success=True)
                        fork_client.mine_blocks(
                            1
                        )  # Advance one block after successful action
                        set_flash_success(
                            f"🎉 **Success!** Borrowed {borrow_amount} USDC!",
                            tx_hash=result.get("tx_hash"),
                        )
                        st.rerun()
                    else:
                        log_transaction("Increase Debt", result, success=False)
                        set_flash_error(
                            f"❌ Failed: {result.get('error', 'Unknown error')}"
                        )
                        st.rerun()
            except Exception as e:
                log_transaction(
                    "Increase Debt", {"success": False, "error": str(e)}, success=False
                )
                set_flash_error(f"❌ Error: {str(e)}")
                st.rerun()

with st.expander("💳 Repay Debt"):
    if not st.session_state.credit_account:
        st.warning("⚠️ Please open a credit account first.")
    else:
        # Get account address for this section
        account_address = get_account_address(st.session_state.account_index)

        repay_amount = st.number_input(
            "Repay Amount (USDC)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            key="repay_amount",
        )
        amount_wei = int(repay_amount * 10**6)

        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "Repay Debt",
                use_container_width=True,
                type="primary",
                key="repay_debt_btn",
            ):
                try:
                    with st.spinner(f"Repaying {repay_amount} USDC..."):
                        call = controller.prepare_action(
                            "decrease_debt", amount=amount_wei
                        )
                        result = controller.execute_multicall(
                            st.session_state.credit_account,
                            [call],
                            account_index=account_index,
                        )

                        if result.get("success"):
                            log_transaction("Repay Debt", result, success=True)
                            fork_client.mine_blocks(
                                1
                            )  # Advance one block after successful action
                            set_flash_success(
                                f"🎉 **Success!** Repaid {repay_amount} USDC!",
                                tx_hash=result.get("tx_hash"),
                            )
                            st.rerun()
                        else:
                            log_transaction("Repay Debt", result, success=False)
                            set_flash_error(
                                f"❌ Failed: {result.get('error', 'Unknown error')}"
                            )
                            st.rerun()
                except Exception as e:
                    log_transaction(
                        "Repay Debt", {"success": False, "error": str(e)}, success=False
                    )
                    set_flash_error(f"❌ Error: {str(e)}")
                    st.rerun()
        with col2:
            if st.button(
                "Repay All Debt", use_container_width=True, key="repay_all_debt_btn"
            ):
                try:
                    with st.spinner("Repaying all debt..."):
                        # Use prepare_repay_all_debt to repay all debt
                        credit_manager = controller.cm.get_credit_manager(
                            CREDIT_MANAGER_V3
                        )
                        calls = prepare_repay_all_debt(controller.cm)
                        result = controller.execute_multicall(
                            st.session_state.credit_account,
                            calls,
                            account_index=account_index,
                        )

                        if result.get("success"):
                            log_transaction("Repay All Debt", result, success=True)
                            fork_client.mine_blocks(
                                1
                            )  # Advance one block after successful action
                            set_flash_success(
                                "🎉 **Success!** All debt repaid!",
                                tx_hash=result.get("tx_hash"),
                            )
                            st.rerun()
                        else:
                            log_transaction("Repay All Debt", result, success=False)
                            set_flash_error(
                                f"❌ Failed: {result.get('error', 'Unknown error')}"
                            )
                            st.rerun()
                except Exception as e:
                    log_transaction(
                        "Repay All Debt",
                        {"success": False, "error": str(e)},
                        success=False,
                    )
                    set_flash_error(f"❌ Error: {str(e)}")
                    st.rerun()

with st.expander("💸 Withdraw Collateral"):
    if not st.session_state.credit_account:
        st.warning("⚠️ Please open a credit account first.")
    else:
        # Get account address for this section
        account_address = get_account_address(st.session_state.account_index)

        withdraw_amount = st.number_input(
            "Amount (USDC)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            key="withdraw_amount",
        )

        token_address = USDC
        token_decimals = 6
        amount_wei = int(withdraw_amount * (10**token_decimals))

        col_exec1, col_exec2 = st.columns(2)

        with col_exec1:
            if st.button(
                "Withdraw Collateral",
                key="withdraw_exec",
                use_container_width=True,
                type="primary",
            ):
                try:
                    with st.spinner(f"Withdrawing {withdraw_amount} USDC..."):
                        call = controller.prepare_action(
                            "withdraw_collateral",
                            token=token_address,
                            amount=amount_wei,
                            to=account_address,
                        )
                        result = controller.execute_multicall(
                            st.session_state.credit_account,
                            [call],
                            account_index=account_index,
                        )

                        if result.get("success"):
                            log_transaction("Withdraw Collateral", result, success=True)
                            fork_client.mine_blocks(
                                1
                            )  # Advance one block after successful action
                            set_flash_success(
                                f"🎉 **Success!** Withdrew {withdraw_amount} USDC!",
                                tx_hash=result.get("tx_hash"),
                            )
                            st.rerun()
                        else:
                            err = result.get("simulation_error") or result.get(
                                "error", "Unknown error"
                            )
                            log_transaction(
                                "Withdraw Collateral", result, success=False
                            )
                            set_flash_error(f"❌ {err}")
                            st.rerun()
                except Exception as e:
                    log_transaction(
                        "Withdraw Collateral",
                        {"success": False, "error": str(e)},
                        success=False,
                    )
                    set_flash_error(f"❌ Error: {str(e)}")
                    st.rerun()

        with col_exec2:
            if st.button(
                "Withdraw All Collateral",
                key="withdraw_all_exec",
                use_container_width=True,
            ):
                try:
                    with st.spinner(f"Withdrawing all USDC..."):
                        call = controller.prepare_action(
                            "withdraw_collateral",
                            token=token_address,
                            amount=MAX_UINT256,
                            to=account_address,
                        )
                        result = controller.execute_multicall(
                            st.session_state.credit_account,
                            [call],
                            account_index=account_index,
                        )

                        if result.get("success"):
                            log_transaction(
                                "Withdraw All Collateral", result, success=True
                            )
                            fork_client.mine_blocks(
                                1
                            )  # Advance one block after successful action
                            set_flash_success(
                                f"🎉 **Success!** Withdrew all USDC!",
                                tx_hash=result.get("tx_hash"),
                            )
                            st.rerun()
                        else:
                            err = result.get("simulation_error") or result.get(
                                "error", "Unknown error"
                            )
                            log_transaction(
                                "Withdraw All Collateral", result, success=False
                            )
                            set_flash_error(f"❌ {err}")
                            st.rerun()
                except Exception as e:
                    log_transaction(
                        "Withdraw All Collateral",
                        {"success": False, "error": str(e)},
                        success=False,
                    )
                    set_flash_error(f"❌ Error: {str(e)}")
                    st.rerun()

# Close Account
with st.expander("🔒 Close Credit Account"):
    if not st.session_state.credit_account:
        st.warning("⚠️ No credit account to close.")
    else:
        # Check debt
        try:
            state = controller.get_state(st.session_state.credit_account, refresh=True)
            if state.debt > 0:
                st.warning(
                    f"⚠️ Account has debt: {state.debt / 10**6:.2f} USDC. Repay debt before closing."
                )
        except:
            pass

        if st.button(
            "Close Account",
            type="secondary",
            use_container_width=True,
            key="close_account_btn",
        ):
            try:
                with st.spinner("Closing credit account..."):
                    result = controller.close_credit_account(
                        credit_account=st.session_state.credit_account,
                        account_index=account_index,
                    )

                    if result.get("success"):
                        st.session_state.credit_account = None
                        log_transaction("Close Account", result, success=True)
                        fork_client.mine_blocks(
                            1
                        )  # Advance one block after successful action
                        set_flash_success(
                            "🎉 **Success!** Credit account closed!",
                            tx_hash=result.get("tx_hash"),
                        )
                        st.rerun()
                    else:
                        log_transaction("Close Account", result, success=False)
                        set_flash_error(
                            f"❌ Failed: {result.get('error', 'Unknown error')}"
                        )
                        st.rerun()
            except Exception as e:
                log_transaction(
                    "Close Account", {"success": False, "error": str(e)}, success=False
                )
                set_flash_error(f"❌ Error: {str(e)}")
                st.rerun()

# Transaction log
st.divider()
with st.expander("📜 Transaction Log", expanded=False):
    if st.session_state.transaction_log:
        for log in st.session_state.transaction_log:
            timestamp = log.get("timestamp", "N/A")
            action = log.get("action", "Unknown")
            success = log.get("success", False)
            tx_hash = log.get("tx_hash")
            error = log.get("error")

            if success:
                st.success(f"✅ [{timestamp}] {action}")
                if tx_hash:
                    st.caption(f"TX: `{tx_hash}`")
            else:
                st.error(f"❌ [{timestamp}] {action}")
                if error:
                    st.caption(f"Error: {error}")
    else:
        st.info("No transactions yet")

# Footer
st.divider()
st.caption("Make sure Anvil fork is running: `./start_fork.sh`")
