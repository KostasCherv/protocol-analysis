#!/bin/bash
# start_fork.sh - Start Anvil with mainnet fork
# Usage: ./start_fork.sh [block_number|latest]
# Default: latest (omits --fork-block-number flag)

FORK_BLOCK=${1:-latest}  # Default to latest block if not specified
# Use public RPC endpoint (no API key required)
# Alternatives: https://rpc.ankr.com/eth, https://ethereum.publicnode.com
MAINNET_RPC_URL=${MAINNET_RPC_URL:-"https://ethereum.publicnode.com"}

# If latest or empty, omit --fork-block-number flag (Anvil forks from latest)
if [ "$FORK_BLOCK" = "latest" ] || [ -z "$FORK_BLOCK" ]; then
    echo "Starting Anvil fork from latest block..."
    anvil --fork-url "$MAINNET_RPC_URL"
else
    echo "Starting Anvil fork from block $FORK_BLOCK..."
    anvil --fork-url "$MAINNET_RPC_URL" --fork-block-number "$FORK_BLOCK"
fi
