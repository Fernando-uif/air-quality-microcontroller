"""
buffer.py - Buffer local para mediciones offline
"""

import ujson


BUFFER_FILE = "buffer.json"
MAX_BUFFER = 50


def save(readings, timestamp, seq):
    """Guarda medición en buffer local."""

    try:
        buf = _load()

        buf.append({
            "readings": readings,
            "ts": timestamp,
            "seq": seq
        })

        if len(buf) > MAX_BUFFER:
            buf = buf[-MAX_BUFFER:]

        _write(buf)
        print("Buffer: {} pendientes".format(len(buf)))

    except Exception as e:
        print("Error buffer save: {}".format(e))


def flush(send_fn):
    """
    Envía mediciones del buffer.
    send_fn(readings, timestamp, seq) → bool
    """

    buf = _load()

    if not buf:
        return

    print("Enviando {} del buffer...".format(len(buf)))

    remaining = []

    for item in buf:
        success = send_fn(item["readings"], item["ts"], item["seq"])
        if not success:
            remaining.append(item)

    _write(remaining)

    if remaining:
        print("{} siguen pendientes".format(len(remaining)))


def count():
    """Retorna cantidad de mediciones en buffer."""
    return len(_load())


def _load():
    """Carga buffer del archivo."""
    try:
        with open(BUFFER_FILE, "r") as f:
            return ujson.load(f)
    except (OSError, ValueError):
        return []


def _write(buf):
    """Escribe buffer al archivo."""
    with open(BUFFER_FILE, "w") as f:
        ujson.dump(buf, f)
