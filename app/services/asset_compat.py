"""Asset compatibility matrix — which chain+asset combinations are valid."""

# Valid (chain, asset) pairs for auto-pricing option generation.
# Rules:
#   - ETH is native only on ethereum and arbitrum
#   - POL is native only on polygon (upgraded from MATIC on Sep 4, 2024)
#   - USDC and USDT are ERC-20 on all three chains (if contract configured)
#   - ETH on Polygon is invalid (Polygon uses POL as native)
#   - POL on Ethereum is invalid
#   - Both testnet and mainnet variants supported

_VALID_PAIRS: set[tuple[str, str]] = {
    # Ethereum (mainnet + testnet)
    ("ethereum", "ETH"),
    ("ethereum-sepolia", "ETH"),
    ("ethereum", "USDC"),
    ("ethereum-sepolia", "USDC"),
    ("ethereum", "USDT"),
    ("ethereum-sepolia", "USDT"),
    # Arbitrum (mainnet + testnet)
    ("arbitrum", "ETH"),
    ("arbitrum-sepolia", "ETH"),
    ("arbitrum", "USDC"),
    ("arbitrum-sepolia", "USDC"),
    ("arbitrum", "USDT"),
    ("arbitrum-sepolia", "USDT"),
    # Polygon (mainnet + testnet) — POL is native token since Sep 4, 2024
    ("polygon", "POL"),
    ("polygon-amoy", "POL"),
    ("polygon", "USDC"),
    ("polygon-amoy", "USDC"),
    ("polygon", "USDT"),
    ("polygon-amoy", "USDT"),
}


def is_valid_pair(chain: str, asset: str) -> bool:
    """Check if a (chain, asset) combination is valid for auto-pricing.

    Args:
        chain: chain identifier (e.g. "ethereum", "arbitrum", "polygon")
        asset: asset symbol (e.g. "ETH", "USDC", "MATIC")

    Returns:
        True if the combination is valid, False otherwise.
    """
    return (chain.lower(), asset.upper()) in _VALID_PAIRS
