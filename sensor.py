"""
sensor.py - Lectura dinámica de sensores

Tipos soportados:
    - temperature (LM35, ADC):  10mV/°C → voltaje * 100 = °C
    - analog (genérico, ADC):   Retorna voltaje crudo 0-3.3V
    - humidity_dht11 (digital): DHT11 en GPIO, protocolo 1-wire

Lee desde la lista de sensores definida en config.json.
"""

from machine import ADC, Pin
from time import sleep_ms
import dht


ADC_VREF = 3.3
ADC_RESOLUTION = 65535

# Cache de objetos por sensor id
_adcs = {}
_dht_sensors = {}


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

        if sensor_type == "humidity_dht11":
            _dht_sensors[sid] = dht.DHT11(Pin(gpio))
            print("Sensor '{}' DHT11 en GPIO{}".format(sid, gpio))
        elif s.get("adc", -1) >= 0:
            _adcs[sid] = ADC(gpio)
            print("Sensor '{}' ({}) en GPIO{} (ADC{})".format(sid, sensor_type, gpio, s["adc"]))


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
    Lee todos los sensores con promediado (ADC) o lectura directa (DHT11).
    Retorna lista de readings.
    """
    readings = []

    for s in sensors_config:
        sid = s["id"]
        sensor_type = s["type"]

        if sensor_type == "humidity_dht11":
            # DHT11: lectura digital
            value = _read_dht11(sid)
            readings.append({
                "sensor_id": sid,
                "value": value,
                "raw_value": int(value * 10)
            })
        elif sid in _adcs:
            # ADC: promediar 10 muestras
            adc = _adcs[sid]
            samples = []
            for _ in range(10):
                samples.append(adc.read_u16())
                sleep_ms(10)

            raw = sum(samples) // len(samples)
            voltage = (raw / ADC_RESOLUTION) * ADC_VREF

            converter = _CONVERTERS.get(sensor_type, _convert_analog)
            value = converter(voltage)

            readings.append({
                "sensor_id": sid,
                "value": value,
                "raw_value": raw
            })

    return readings


def read_all_fast(sensors_config):
    """
    Lectura rápida para pantalla (1 sample ADC, cache DHT11).
    """
    readings = []

    for s in sensors_config:
        sid = s["id"]
        sensor_type = s["type"]

        if sensor_type == "humidity_dht11":
            value = _read_dht11(sid)
            readings.append({
                "sensor_id": sid,
                "value": value,
                "raw_value": int(value * 10)
            })
        elif sid in _adcs:
            adc = _adcs[sid]
            raw = adc.read_u16()
            voltage = (raw / ADC_RESOLUTION) * ADC_VREF

            converter = _CONVERTERS.get(sensor_type, _convert_analog)
            value = converter(voltage)

            readings.append({
                "sensor_id": sid,
                "value": value,
                "raw_value": raw
            })

    return readings


# ============================================================
# DHT11
# ============================================================

_last_dht_humidity = 0.0
_last_dht_read = 0


def _read_dht11(sid):
    """
    Lee DHT11. Solo permite una lectura cada 2 segundos (limitación del sensor).
    Retorna humedad en %.
    """
    global _last_dht_humidity, _last_dht_read
    from time import ticks_ms, ticks_diff

    # DHT11 solo permite lectura cada 2s
    now = ticks_ms()
    if ticks_diff(now, _last_dht_read) < 2000 and _last_dht_read > 0:
        return _last_dht_humidity

    sensor = _dht_sensors.get(sid)
    if not sensor:
        return 0.0

    try:
        sensor.measure()
        _last_dht_humidity = sensor.humidity()
        _last_dht_read = now
        return _last_dht_humidity
    except Exception as e:
        print("DHT11 error: {}".format(e))
        return _last_dht_humidity
