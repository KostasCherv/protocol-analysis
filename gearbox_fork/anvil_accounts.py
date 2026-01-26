"""Anvil default accounts (0-9) with addresses and private keys"""

ANVIL_ACCOUNTS = {
    0: {
        "address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    },
    1: {
        "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    },
    2: {
        "address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "private_key": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    },
}


def get_account(account_index: int) -> dict:
    """Get account details by index (0-9)"""
    if account_index not in ANVIL_ACCOUNTS:
        raise ValueError(f"Account index must be 0-9, got {account_index}")
    return ANVIL_ACCOUNTS[account_index]


def get_address(account_index: int) -> str:
    """Get account address by index"""
    return get_account(account_index)["address"]


def get_private_key(account_index: int) -> str:
    """Get account private key by index"""
    return get_account(account_index)["private_key"]
