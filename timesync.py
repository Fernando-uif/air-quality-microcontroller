"""
timesync.py - Sincronización de tiempo por OFFSET desde el servidor (sin RTC, sin NTP)

El backend responde al registro (topic devices/{id}/register/ack) con su hora Unix
(server_time). El micro calcula:

    offset = server_time - int(time.time())

y a partir de ahí get_timestamp() devuelve int(time.time()) + offset, es decir la hora
Unix del servidor "proyectada" con el reloj local del micro. Esto elimina el problema del
epoch del firmware (2000 vs 1970) porque la referencia la fija el servidor, no el firmware.

El offset se persiste en timeoffset.dat para sobrevivir reinicios (aunque el reloj local
del micro se reinicia al arrancar, así que tras un reinicio conviene re-registrar para
recalibrar; el archivo sirve de respaldo/última referencia conocida).

API:
    timesync.load()                 # cargar offset previo (si existe)
    timesync.set_from_server(ts)    # calibrar con la hora del servidor
    timesync.get_timestamp()        # hora Unix confiable, o None si no calibrado
    timesync.is_valid()             # True si hay hora confiable
"""

import time

_OFFSET_FILE = "timeoffset.dat"

_offset = None        # segundos a sumar a time.time() local
_time_valid = False   # True solo tras una calibración exitosa en esta sesión


def load():
    """Carga el offset persistido (si existe). No marca la hora como válida:
    tras un reinicio el reloj local cambió, así que se recomienda re-registrar."""
    global _offset
    try:
        with open(_OFFSET_FILE, "r") as f:
            _offset = int(f.read().strip())
            print("timesync: offset previo cargado = {}".format(_offset))
    except (OSError, ValueError):
        _offset = None


def set_from_server(server_time):
    """Calibra el reloj con la hora Unix del servidor. Persiste el offset."""
    global _offset, _time_valid
    try:
        server_time = int(server_time)
    except (TypeError, ValueError):
        print("timesync: server_time inválido: {}".format(server_time))
        return False

    _offset = server_time - int(time.time())
    _time_valid = True
    try:
        with open(_OFFSET_FILE, "w") as f:
            f.write(str(_offset))
    except OSError as e:
        print("timesync: no se pudo persistir offset: {}".format(e))

    print("timesync: calibrado. offset={}, ts={}".format(_offset, get_timestamp()))
    return True


def is_valid():
    """True si hay una hora confiable (hubo calibración por ACK en esta sesión)."""
    return _time_valid


def get_timestamp():
    """Timestamp Unix confiable (segundos), o None si aún no se calibró.
    NUNCA devuelve basura: si no hay calibración, devuelve None y el llamador
    debe abstenerse de publicar telemetría."""
    if not _time_valid or _offset is None:
        return None
    return int(time.time()) + _offset
