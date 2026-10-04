"""
sensor.py - Lectura dinámica de sensores

Tipos soportados:
    - temperature (LM35, ADC):   10mV/°C → voltaje * 100 = °C
    - analog (genérico, ADC):    Retorna voltaje crudo 0-3.3V
    - humidity_dht11 (digital):  Humedad del DHT11 en GPIO, protocolo 1-wire
    - temperature_dht11 (digital): Temperatura del mismo DHT11 (misma lectura)

Lee desde la lista de sensores definida en config.json.
"""

from machine import ADC, Pin
from time import sleep_ms
import dht


ADC_VREF = 3.3
ADC_RESOLUTION = 65535

# ── Robustez de temperatura (ADC) ──
# Se toman 10 muestras. Una muestra es "anómala" si se desvía más de
# TEMP_SPREAD_C °C respecto a la MEDIANA de las 10 (robusta a outliers).
# Si hay TEMP_MAX_ANOMALIES o más anómalas → sensor en fallo (pin flotante/roto).
# Si hay menos → se descartan las anómalas y se promedia el resto (tolera glitches).
TEMP_SPREAD_C = 15.0
TEMP_MAX_ANOMALIES = 2  # 2 o más de 10 → fallo (tolera 1 glitch puntual)

# Señal de fallo hacia el backend (sin flag nuevo, sin tocar DTO ni firma):
FAULT_VALUE = 0
FAULT_RAW = 0

# Cache de objetos por sensor id
_adcs = {}
# DHT11 se indexa por GPIO (no por sensor id): temperature_dht11 y humidity_dht11
# pueden apuntar al mismo chip físico y deben compartir una sola instancia.
_dht_sensors = {}
_DHT_TYPES = ("humidity_dht11", "temperature_dht11")


def init(sensors_config):
    """
    Inicializa sensores según la config.
    """
    global _adcs, _dht_sensors
    _adcs = {}
    _dht_sensors = {}

    for s in sensors_config:
        sid = s["id"]
        gpio = s["gpio"]
        sensor_type = s["type"]

        if sensor_type in _DHT_TYPES:
            if gpio in _dht_sensors:
                continue  # ya inicializado por otro sensor_id en el mismo GPIO
            try:
                _dht_sensors[gpio] = dht.DHT11(Pin(gpio))
                print("Sensor '{}' DHT11 en GPIO{}".format(sid, gpio))
                # Health-check: una lectura de prueba (el DHT11 puede fallar la primera)
                try:
                    _dht_sensors[gpio].measure()
                    print("Sensor '{}' DHT11 OK".format(sid))
                except Exception as e:
                    print("Sensor '{}' DHT11 no responde al iniciar: {}".format(sid, e))
            except Exception as e:
                print("Sensor '{}' DHT11 no inicializó: {}".format(sid, e))
        elif s.get("adc", -1) >= 0:
            try:
                _adcs[sid] = ADC(gpio)
                print("Sensor '{}' ({}) en GPIO{} (ADC{})".format(sid, sensor_type, gpio, s["adc"]))
            except Exception as e:
                print("Sensor '{}' ADC no inicializó: {}".format(sid, e))


# ============================================================
# CONVERSIONES
# ============================================================

def _convert_temperature(voltage):
    """LM35: 10mV por °C → voltaje * 100"""
    return round(voltage * 100, 1)


def _convert_analog(voltage):
    """Sensor analógico genérico: retorna voltaje."""
    return round(voltage, 4)


_CONVERTERS = {
    "temperature": _convert_temperature,
    "analog": _convert_analog,
}


# ============================================================
# LECTURA
# ============================================================

def read_all(sensors_config):
    """
    Lee todos los sensores. Cada sensor se aísla en su propio try/except para que
    uno en fallo NO rompa la lectura de los demás.
    Un sensor en fallo se reporta con la señal 0/0 (value=0, raw_value=0); el backend
    la interpreta como "sensor en fallo".
    Retorna SIEMPRE la lista completa de sensores configurados.
    """
    readings = []

    for s in sensors_config:
        sid = s["id"]
        sensor_type = s["type"]

        try:
            if sensor_type in _DHT_TYPES:
                value = _read_dht_field(s["gpio"], sensor_type)
                if value is None:
                    readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})
                else:
                    readings.append({"sensor_id": sid, "value": value, "raw_value": int(value * 10)})

            elif sid in _adcs:
                reading = _read_adc_validated(sid, sensor_type)
                readings.append(reading if reading is not None
                                else {"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})
            else:
                # Sensor configurado pero sin objeto (no inicializó) → fallo
                readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})

        except Exception as e:
            print("Sensor '{}' error: {} → fallo".format(sid, e))
            readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})

    return readings


def _median(values):
    """Mediana de una lista (copia ordenada)."""
    n = len(values)
    if n == 0:
        return 0.0
    ordered = sorted(values)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _read_adc_validated(sid, sensor_type):
    """
    Lee 10 muestras del ADC, valida coherencia por mediana y devuelve el reading
    válido, o None si el sensor está en fallo (ruido de pin flotante).
    """
    adc = _adcs[sid]
    converter = _CONVERTERS.get(sensor_type, _convert_analog)

    # 10 muestras crudas → convertidas a la magnitud (°C para temperatura)
    values = []
    raws = []
    for _ in range(10):
        raw = adc.read_u16()
        raws.append(raw)
        voltage = (raw / ADC_RESOLUTION) * ADC_VREF
        values.append(converter(voltage))
        sleep_ms(10)

    # Detección de fallo solo para temperatura (coherencia entre muestras)
    if sensor_type == "temperature":
        med = _median(values)
        anomalies = sum(1 for v in values if abs(v - med) > TEMP_SPREAD_C)
        if anomalies >= TEMP_MAX_ANOMALIES:
            print("Sensor '{}' temp en fallo: {}/{} muestras anómalas (med={})".format(
                sid, anomalies, len(values), med))
            return None  # → señal 0/0 en el llamador
        # Promediar solo las muestras buenas (tolera 1 glitch puntual)
        good = [v for v in values if abs(v - med) <= TEMP_SPREAD_C]
        good_raws = [raws[i] for i in range(len(values)) if abs(values[i] - med) <= TEMP_SPREAD_C]
        value = round(sum(good) / len(good), 1)
        raw = sum(good_raws) // len(good_raws)
        return {"sensor_id": sid, "value": value, "raw_value": raw}

    # Otros tipos analógicos: promedio simple sin validación de coherencia
    raw = sum(raws) // len(raws)
    voltage = (raw / ADC_RESOLUTION) * ADC_VREF
    return {"sensor_id": sid, "value": converter(voltage), "raw_value": raw}


def read_all_fast(sensors_config):
    """
    Lectura rápida para pantalla (1 sample ADC, cache DHT11).
    """
    readings = []

    for s in sensors_config:
        sid = s["id"]
        sensor_type = s["type"]

        try:
            if sensor_type in _DHT_TYPES:
                value = _read_dht_field(s["gpio"], sensor_type)
                if value is None:
                    readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})
                else:
                    readings.append({"sensor_id": sid, "value": value, "raw_value": int(value * 10)})
            elif sid in _adcs:
                adc = _adcs[sid]
                raw = adc.read_u16()
                voltage = (raw / ADC_RESOLUTION) * ADC_VREF
                converter = _CONVERTERS.get(sensor_type, _convert_analog)
                value = converter(voltage)
                readings.append({"sensor_id": sid, "value": value, "raw_value": raw})
            else:
                readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})
        except Exception as e:
            print("read_all_fast '{}' error: {}".format(sid, e))
            readings.append({"sensor_id": sid, "value": FAULT_VALUE, "raw_value": FAULT_RAW})

    return readings


# ============================================================
# DHT11
# ============================================================
# Un DHT11 físico entrega temperatura y humedad en la misma lectura.
# Se cachea por GPIO para no violar el mínimo de 2s entre lecturas del sensor
# y para que temperature_dht11 y humidity_dht11 compartan una sola medición.

_dht_cache = {}  # gpio -> {"t": float, "h": float, "ts": ticks_ms}


def _read_dht_combined(gpio):
    """
    Mide el DHT11 en `gpio` (o reutiliza la lectura de los últimos 2s).
    Retorna {"t": temperatura, "h": humedad} o None si el sensor falló.
    """
    from time import ticks_ms, ticks_diff

    now = ticks_ms()
    cached = _dht_cache.get(gpio)
    if cached and ticks_diff(now, cached["ts"]) < 2000:
        return cached

    sensor = _dht_sensors.get(gpio)
    if not sensor:
        return None

    try:
        sensor.measure()
        reading = {"t": sensor.temperature(), "h": sensor.humidity(), "ts": now}
        _dht_cache[gpio] = reading
        return reading
    except Exception as e:
        print("DHT11 en GPIO{} error: {} → fallo".format(gpio, e))
        # No devolver una lectura vieja como si fuera real: señalar fallo
        _dht_cache.pop(gpio, None)
        return None


def _read_dht_field(gpio, sensor_type):
    """Retorna el campo pedido ('t' o 'h') de la lectura combinada del DHT11."""
    reading = _read_dht_combined(gpio)
    if reading is None:
        return None
    return reading["h"] if sensor_type == "humidity_dht11" else reading["t"]
