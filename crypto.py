"""
crypto.py - HMAC-SHA256 para MicroPython

Formato de firma multi-sensor:
    mensaje = "device_id:val1:val2:...:timestamp:sequence"
"""

import uhashlib
import ubinascii


def hmac_sha256(key, message):
    """HMAC-SHA256 implementado manualmente para MicroPython."""

    block_size = 64

    if len(key) > block_size:
        key = uhashlib.sha256(key).digest()

    key = key + b'\x00' * (block_size - len(key))

    o_key_pad = bytes([k ^ 0x5C for k in key])
    i_key_pad = bytes([k ^ 0x36 for k in key])

    inner = uhashlib.sha256(i_key_pad + message.encode())
    outer = uhashlib.sha256(o_key_pad + inner.digest())

    return ubinascii.hexlify(outer.digest()).decode()


def sign(secret_key, device_id, readings, timestamp, seq):
    """
    Genera firma HMAC-SHA256 para múltiples readings.
    Mensaje: device_id:val1:val2:...:timestamp:sequence

    readings: lista de dicts con "value" key
    """
    parts = [device_id]
    for r in readings:
        parts.append(str(r["value"]))
    parts.append(str(timestamp))
    parts.append(str(seq))

    message = ":".join(parts)
    return hmac_sha256(secret_key, message)
