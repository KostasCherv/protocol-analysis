# Gearbox Protocol Analysis & Simulator

This repository contains a comprehensive analysis of Gearbox Protocol (Borrow/Lending Side) and a minimal Python simulator demonstrating credit account mechanics, leveraged Yearn strategy deployment, and liquidation risk.

## Protocol Selection

**Selected Protocol:** Gearbox Protocol (Borrow/Lending Side)  
**Website:** https://app.gearbox.finance/lending

## Contents

- **`PROTOCOL_ANALYSIS.md`**: Complete written analysis covering:
  - Protocol explanation and mechanics
  - Main contracts for yield farmers
  - Dependencies and second-order exposure analysis
  - Assumptions and limitations
  - AI usage self-assessment

- **`gearbox_simulator.py`**: Minimal Streamlit simulator

## Quick Start

### Prerequisites

- Python 3.8 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Install dependencies using uv
uv sync

# Or if you prefer pip (requirements.txt is also provided)
# pip install -r requirements.txt
```

### Run the Simulator

```bash
# Run with uv
uv run streamlit run gearbox_simulator.py
```

The application will open automatically in your browser at `http://localhost:8501`

## Mini Guide

**Your First Position:**

1. Go to **Accounts** tab → select "+ New Account"
2. Enter ETH collateral (e.g., 5 ETH) and USDC borrow amount (e.g., $10,000)
3. Click **OPEN ACCOUNT** (HF must be ≥ 1.2)
4. Go to **Strategies** tab
5. Click **DEPLOY** to send borrowed USDC to Yearn strategy
6. Use sidebar to **Advance Time** (e.g., 30 days) and earn yield
7. Click **WITHDRAW** to close strategy and return funds
8. Click **REPAY** to pay off debt and keep profits

**Try Liquidation:**
- Use buttons in **Liquidations** tab to drop prices
- Watch accounts approach HF < 1.0
- Liquidate risky accounts

## Simulator Features

The simulator demonstrates the following actions:

1. **Open Account**: Provide ETH collateral and borrow USDC with leverage
2. **Deploy**: Move borrowed USDC to Yearn strategy to earn yield (8% APY)
3. **Withdraw**: Remove funds from strategy back to available balance
4. **Repay**: Pay off debt (principal + interest) using available balance
5. **Harvest**: Claim accrued rewards from Yearn strategy
6. **Liquidate**: Liquidate accounts with HF < 1.0 (5% penalty)

### Key Features

- Credit account management with health factor tracking
- Yearn vault strategy simulation with yield accrual
- Deploy/withdraw/repay workflow for leveraged positions
- Dynamic interest rates based on pool utilization
- Price drop simulation for liquidation testing
- Interactive Streamlit interface

## How to Use

1. **Open Account**: Provide ETH collateral and borrow USDC
2. **Deploy**: Send borrowed USDC to Yearn strategy for yield
3. **Advance Time**: Accrue yield and interest over time
4. **Withdraw**: Close strategy, return funds to available balance
5. **Repay**: Pay off debt, keep any profit
6. **Harvest**: Claim rewards from strategy
7. **Monitor Health Factor**: Watch for liquidation risk

## Assumptions & Limitations

### Simplifications Made

1. **Interest Rate Model**: Simplified piecewise linear model (real protocol uses more complex curves)
2. **Strategy**: Simulates Yearn USDC vault with fixed 8% APY (simplified from actual vault mechanics)
3. **Rewards**: Linear reward accrual (simplified from actual gauge mechanics)
4. **Health Factor**: Simplified calculation (real protocol includes quota factors)
5. **Oracle**: Static prices (no price volatility except via manual price drop)
6. **Gas Costs**: Not included
7. **Slippage**: Not modeled
8. **Single Pool**: One USDC pool (real protocol has multiple pools per asset)
9. **Supply Side**: Not included (no LP tokens, focuses on borrowing/leveraging)


## Disclaimer

This simulator is for **educational purposes only**. It is a simplified model and does not include all protocol features. Do not use this code for production DeFi operations.
