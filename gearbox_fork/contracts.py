"""Contract ABIs and interaction helpers"""

import json
from pathlib import Path
from web3 import Web3
from typing import Dict, Any

# Get the directory where this module is located
_MODULE_DIR = Path(__file__).parent
_ABIS_DIR = _MODULE_DIR / "abis"


def load_abi(filename: str) -> list:
    """Load ABI from JSON file in abis/ directory"""
    abi_path = _ABIS_DIR / filename
    if not abi_path.exists():
        raise FileNotFoundError(
            f"ABI file not found: {abi_path}. "
            f"Please compile core-v3 contracts and extract ABIs."
        )
    with open(abi_path, "r") as f:
        return json.load(f)


def get_contract(w3: Web3, address: str, abi_filename: str):
    """Get contract instance from ABI file"""
    abi = load_abi(abi_filename)
    return w3.eth.contract(address=address, abi=abi)


class ContractManager:
    """Manager for Gearbox Protocol contracts"""

    def __init__(self, w3: Web3):
        self.w3 = w3
        self._contracts: Dict[str, Any] = {}

    def get_credit_facade(self, address: str):
        """Get CreditFacadeV3 contract instance"""
        key = f"credit_facade_{address}"
        if key not in self._contracts:
            self._contracts[key] = get_contract(self.w3, address, "CreditFacadeV3.json")
        return self._contracts[key]

    def get_credit_manager(self, address: str):
        """Get CreditManagerV3 contract instance"""
        key = f"credit_manager_{address}"
        if key not in self._contracts:
            self._contracts[key] = get_contract(
                self.w3, address, "CreditManagerV3.json"
            )
        return self._contracts[key]

    def get_erc20(self, address: str):
        """Get ERC20 token contract instance"""
        key = f"erc20_{address}"
        if key not in self._contracts:
            self._contracts[key] = get_contract(self.w3, address, "ERC20.json")
        return self._contracts[key]
