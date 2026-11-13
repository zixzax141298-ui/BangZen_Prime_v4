"""Base58 encode/decode for 32-byte Solana keys. No checksum."""

from __future__ import annotations

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    if not raw:
        return ""
    zeros = 0
    for byte in raw:
        if byte == 0:
            zeros += 1
        else:
            break
    number = int.from_bytes(raw, "big")
    chars: list[str] = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_ALPHABET[rem])
    return ("1" * zeros) + "".join(reversed(chars))


def b58decode(text: str) -> bytes:
    if not isinstance(text, str) or not text:
        raise ValueError("base58 value is empty")
    zeros = 0
    for char in text:
        if char == "1":
            zeros += 1
        else:
            break
    number = 0
    for char in text:
        index = _ALPHABET.find(char)
        if index < 0:
            raise ValueError("invalid base58 character")
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return (b"\x00" * zeros) + body
