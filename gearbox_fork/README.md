# Gearbox Protocol - Forked Mainnet Integration

Python integration that interacts with actual deployed Gearbox Protocol contracts on a locally forked Ethereum mainnet using Anvil and web3.py.

## Overview

This integration allows you to:
- Interact with real Gearbox Protocol contracts on a forked mainnet
- Open credit accounts, add collateral, borrow funds
- Read on-chain state (balances, health factors, debt)
- Advance time to demonstrate interest accrual
- Manage credit accounts through an interactive Streamlit UI

## Prerequisites

1. **Foundry (for Anvil)**
   ```bash
   curl -L https://foundry.paradigm.xyz | bash
   foundryup
   ```

2. **Python 3.8+** with `uv` package manager

## Installation

1. **Install Python dependencies:**
   ```bash
   uv sync
   ```

2. **Contract ABIs:**
   Contract ABIs are included in `gearbox_fork/abis/` (copied from Gearbox Protocol's core-v3 repository). No additional compilation steps are required.

## Quick Start

### 1. Start Anvil Fork

In one terminal, start Anvil with mainnet fork:

```bash
# Using the provided script
./gearbox_fork/start_fork.sh

# Or manually (with specific block number)
anvil --fork-url https://eth.llamarpc.com --fork-block-number 19000000

# Or use latest block
anvil --fork-url https://eth.llamarpc.com
```

**Note:** Using public RPC endpoint (`https://eth.llamarpc.com`) - no API key required.

### 2. Run Streamlit UI

In another terminal:

```bash
streamlit run gearbox_fork/streamlit_app.py
```

The UI will open at `http://localhost:8501`

### 3. Using the UI

1. **Select Account**: Choose Anvil account 0-9 from dropdown (all come pre-funded with 10,000 ETH)
2. **Fund Wallet**: Add USDC tokens using the "Fund Wallet" button
3. **Open Credit Account**: Add collateral and borrow funds
4. **Manage Account**: Add collateral, borrow more, repay debt, withdraw collateral
5. **Advance Time**: Use sidebar to advance days and accrue interest
6. **Close Account**: Repay debt and close the credit account

## Features

### Implemented Actions

- ✅ **Open Credit Account**: Open credit account with collateral and optional borrowing
- ✅ **Add Collateral**: Add collateral to existing credit account
- ✅ **Borrow**: Increase debt (borrow more funds)
- ✅ **Repay Debt**: Repay debt (partial or full)
- ✅ **Withdraw Collateral**: Withdraw collateral from credit account
- ✅ **Close Account**: Close credit account and return collateral

### State Reading

- Credit account balances (collateral, debt)
- Health factor calculations
- Accrued interest tracking
- Token balances in credit accounts
- Account summaries with debt and collateral values

### Time Advancement

- Advance time by days using `evm_increaseTime` and `evm_mine`
- Demonstrate interest accrual over time

## Architecture

```
gearbox_fork/
├── config.py                    # Contract addresses and configuration
├── contracts.py                 # Contract ABIs and interaction helpers
├── fork_client.py              # Web3 client setup for forked chain
├── actions.py                  # User action implementations
├── action_builders.py          # Pure functions for preparing call data
├── executors.py                # Transaction execution functions
├── state_manager.py            # State management and session storage
├── state_reader.py             # On-chain state reading utilities
├── credit_account_controller.py # Main controller (UI-ready)
├── wallet_manager.py           # Wallet funding utilities
├── anvil_accounts.py           # Anvil default accounts (0-9)
├── streamlit_app.py            # Streamlit UI application
└── abis/                        # Contract ABIs (copied from core-v3)
```

## Contract Addresses

All addresses from [dev.gearbox.finance](https://dev.gearbox.finance):

- **CreditFacadeV3**: `0x9ab55e5c894238812295a31bdb415f00f7626792`
- **CreditManagerV3**: `0x3eb95430fdb99439a86d3c6d7d01c3c561393556`
- **PoolV3 USDC**: `0xda00000035fef4082F78dEF6A8903bee419FbF8E`
- **USDC**: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`

## Wallet Funding

Wallets are funded using Anvil's storage manipulation and whale impersonation:

- **ETH**: Accounts come pre-funded with 10,000 ETH each
- **USDC**: Use `fund_from_whale()` to transfer USDC from whale addresses using `anvil_impersonateAccount`

## Limitations & Assumptions

1. **ABIs**: Contract ABIs are included (copied from Gearbox's core-v3 repository)
2. **Credit Account Discovery**: Credit account addresses need to be extracted from transaction events
3. **Storage Slots**: ERC20 balance storage slots assume standard mapping layout
4. **Multicall Encoding**: Multicall structure follows Gearbox V3 patterns
5. **Focus**: Current implementation focuses on USDC-only operations

## Troubleshooting

### Connection Issues

- Ensure Anvil is running: `anvil --fork-url https://eth.llamarpc.com`
- Check RPC URL in config matches Anvil's port (default: 8545)
- If using a specific block number, ensure it's not pruned (use recent blocks or "latest")

### Transaction Failures

- Check account has sufficient ETH for gas
- Verify credit account exists before operations
- Ensure health factor requirements are met (HF >= 1.2 to open)
- Check token approvals are set correctly

### Block Number Issues

- If you get "state is pruned" error, use a more recent block number
- Default is now "latest" which uses the most recent available block
- You can specify a recent block: `anvil --fork-url <rpc> --fork-block-number <recent_block>`

## References

- [Gearbox Documentation](https://docs.gearbox.finance)
- [Deployed Contracts](https://dev.gearbox.finance)
- [Gearbox Core V3](https://github.com/Gearbox-protocol/core-v3)
