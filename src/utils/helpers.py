"""Utility helper functions for the DeeMusic application."""

from typing import Optional

def is_valid_arl_token(arl: Optional[str]) -> bool:
    """Basic check if ARL looks potentially valid (e.g., length)."""
    # ARL tokens are typically 192 hex characters.
    if arl is None:
        return False
    if not isinstance(arl, str):
        return False # Should be a string
    
    # Check for typical length and hex characters
    # Deezer ARLs are 192 characters long and hexadecimal.
    is_hex = all(c in '0123456789abcdefABCDEF' for c in arl)
    return len(arl) == 192 and is_hex 