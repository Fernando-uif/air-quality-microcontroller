"""
main.py - Raspberry Pi Pico W - Nodo IoT con MQTT

Firmware modular con comunicación MQTT bidireccional.
- Lee sensores dinámicamente desde config.json
- Publica readings[] en: devices/{device_id}/telemetry
- Escucha comandos en:   devices/{device_id}/command
- Pantalla OLED siempre activa.

Archivos requeridos:
    /main.py, /config.json, /config.py, /wifi.py, /sensor.py,
    /crypto.py, /mqtt_client.py, /buffer.py, /sequence.py,
    /display.py, /sh1106.py
"""

from machine import Pin
from time import sleep, sleep_ms, time

import config as cfg
import wifi
import sensor
import crypto
import mqtt_client
import buffer
import sequence
import display
import ntptime
import ujson


# ============================================================
# CONFIGURACIÓN
# ============================================================

conf = cfg.load_config()

if conf is None:
    display.init()
    display.show_error("No config.json")
    raise SystemExit

DEVICE_ID = conf["device_id"]
SECRET_KEY = conf["secret_key"].encode()
WIFI_SSID = conf["wifi_ssid"]
WIFI_PASSWORD = conf["wifi_password"]
MQTT_BROKER = conf.get("mqtt_broker", "192.168.100.155")
MQTT_PORT = conf.get("mqtt_port", 1883)
INTERVAL = conf.get("interval_seconds", 300)
SENSORS = conf.get("sensors", [])

# LED integrado
led = Pin("LED", Pin.OUT)

# NTP epoch offset (no necesario en MicroPython 1.22+)
EPOCH_OFFSET = 0

# Flag para medición bajo demanda
_measure_requested = False


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def get_timestamp():
    """Obtiene timestamp Unix."""
    return int(time()) + EPOCH_OFFSET


def sync_time():
    """Sincroniza reloj con NTP. Reintenta 3 veces."""
    for attempt in range(3):
        try:
            ntptime.settime()
            print("NTP sincronizado (intento {})".format(attempt + 1))
            return True
        except Exception as e:
            print("NTP intento {} fallo: {}".format(attempt + 1, e))
            sleep(2)
    print("NTP: sin sincronizar")
    return False


def led_blink(times, ms):
    """Parpadea LED."""
    for _ in range(times):
        led.value(1)
        sleep_ms(ms)
        led.value(0)
        sleep_ms(ms)


# ============================================================
# AUTO-REGISTRO
# ============================================================

REGISTERED_FILE = "registered.flag"


def is_registered():
    """Verifica si el dispositivo ya se registró previamente."""
    try:
        with open(REGISTERED_FILE, "r") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def mark_registered():
    """Marca que el dispositivo se registró exitosamente."""
    with open(REGISTERED_FILE, "w") as f:
        f.write("1")


def do_auto_register():
    """
    Envía mensaje de registro al backend via MQTT.
    Solo se ejecuta si el dispositivo no se ha registrado antes.
    Topic: devices/{device_id}/register
    """
    if is_registered():
        print("Ya registrado, omitiendo registro")
        return True

    timestamp = get_timestamp()
    # Firma: HMAC(secret_key, device_id:timestamp)
    message = "{}:{}".format(DEVICE_ID, timestamp)
    signature = crypto.hmac_sha256(SECRET_KEY, message)

    payload = {
        "device_id": DEVICE_ID,
        "country": conf.get("country", ""),
        "state": conf.get("state", ""),
        "municipality": conf.get("municipality", ""),
        "latitude": conf.get("latitude", 0.0),
        "longitude": conf.get("longitude", 0.0),
        "sensors": SENSORS,
        "timestamp": timestamp,
        "signature": signature
    }

    topic = "devices/{}/register".format(DEVICE_ID)
    success = mqtt_client.publish(topic, ujson.dumps(payload))

    if success:
        print("Auto-registro enviado: {}".format(topic))
        mark_registered()
    else:
        print("Error enviando auto-registro")

    return success


# ============================================================
# MQTT - ENVÍO DE MEDICIÓN
# ============================================================

def build_payload(readings, timestamp, seq):
    """Construye payload JSON con firma HMAC multi-sensor."""

    signature = crypto.sign(SECRET_KEY, DEVICE_ID, readings, timestamp, seq)

    payload = {
        "device_id": DEVICE_ID,
        "readings": readings,
        "timestamp": timestamp,
        "sequence": seq,
        "signature": signature
    }

    return ujson.dumps(payload)


def send_measurement(readings, timestamp, seq):
    """Publica medición via MQTT. Retorna True si fue exitoso."""

    payload = build_payload(readings, timestamp, seq)
    success = mqtt_client.publish_telemetry(DEVICE_ID, payload)

    if success:
        print("MQTT OK → {} sensors seq={}".format(len(readings), seq))
        led_blink(1, 200)
    else:
        print("MQTT FAIL")
        led_blink(3, 100)

    return success


# ============================================================
# MQTT - RECEPCIÓN DE COMANDOS
# ============================================================

def on_command(topic, payload):
    """Callback cuando llega un comando del backend."""

    global _measure_requested

    try:
        cmd = ujson.loads(payload)
        action = cmd.get("action", "")

        display.show_mqtt_command(action)
        sleep_ms(800)

        if action == "measure_now":
            print("Comando recibido: measure_now")
            _measure_requested = True

    except Exception as e:
        print("Error parsing command: {}".format(e))


# ============================================================
# LECTURA Y ENVÍO
# ============================================================

def do_measure_and_send():
    """Lee sensores, firma y envía via MQTT. Retorna (success, readings)."""

    readings = sensor.read_all(SENSORS)
    timestamp = get_timestamp()
    seq = sequence.next()

    print("\n[seq={}] readings={} ts={}".format(seq, len(readings), timestamp))
    for r in readings:
        print("  {}: {} (raw={})".format(r["sensor_id"], r["value"], r["raw_value"]))

    if mqtt_client.is_connected():
        success = send_measurement(readings, timestamp, seq)
        if not success:
            buffer.save(readings, timestamp, seq)
    else:
        buffer.save(readings, timestamp, seq)
        success = False

    return success, readings


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():
    """Ciclo principal del sensor IoT con MQTT."""

    global _measure_requested

    print("=" * 40)
    print("IoT Sensor Node (MQTT)")
    print("Device: {}".format(DEVICE_ID))
    print("Broker: {}:{}".format(MQTT_BROKER, MQTT_PORT))
    print("Sensors: {}".format(len(SENSORS)))
    print("Intervalo: {}s".format(INTERVAL))
    print("=" * 40)

    # ── 1. PANTALLA + LOGO ──
    display.init()
    display.show_logo()
    sleep(3)

    # ── 2. INICIALIZAR SENSORES ──
    sensor.init(SENSORS)
    sequence.load()

    # ── 3. LEER SENSOR Y MOSTRAR INMEDIATAMENTE ──
    readings = sensor.read_all_fast(SENSORS)

    display.show_measurement(
        device_id=DEVICE_ID,
        readings=readings,
        sensors_config=SENSORS,
        wifi_ok=False,
        mqtt_ok=False,
        buffer_count=0
    )
    sleep(1)

    # ── 4. CONECTAR WiFi ──
    wifi_ok = wifi.connect(WIFI_SSID, WIFI_PASSWORD)
    if wifi_ok:
        sync_time()

    # ── 5. CONECTAR MQTT ──
    mqtt_ok = False
    if wifi_ok:
        mqtt_ok = mqtt_client.connect(DEVICE_ID, MQTT_BROKER, MQTT_PORT)
        if mqtt_ok:
            mqtt_client.set_command_callback(on_command)
            mqtt_client.subscribe_commands(DEVICE_ID)
            # Auto-registro: el backend me registra automáticamente
            do_auto_register()

    # LED inicio
    led.value(1)
    sleep(1)
    led.value(0)

    # Timers
    elapsed = INTERVAL * 5  # Forzar primer envío
    LOOP_MS = 200
    INTERVAL_TICKS = INTERVAL * (1000 // LOOP_MS)

    while True:
        try:
            # Revisar mensajes MQTT
            if mqtt_client.is_connected():
                mqtt_client.check_messages()

            # ¿Medición bajo demanda?
            if _measure_requested:
                _measure_requested = False
                success, readings = do_measure_and_send()
                elapsed = 0

            # ¿Medición periódica?
            if elapsed >= INTERVAL_TICKS:
                elapsed = 0

                # Flush buffer
                if mqtt_client.is_connected() and buffer.count() > 0:
                    buffer.flush(lambda r, t, s: send_measurement(r, t, s))

                # Medir y enviar
                success, readings = do_measure_and_send()

            # Refrescar pantalla con lectura rápida
            readings = sensor.read_all_fast(SENSORS)

            display.show_measurement(
                device_id=DEVICE_ID,
                readings=readings,
                sensors_config=SENSORS,
                wifi_ok=wifi.is_connected(),
                mqtt_ok=mqtt_client.is_connected(),
                buffer_count=buffer.count()
            )

            # Reconectar (solo si alguna vez conectó)
            if elapsed % 150 == 0:
                if not wifi.is_connected() and wifi_ok:
                    wifi.connect(WIFI_SSID, WIFI_PASSWORD)
                if wifi.is_connected() and not mqtt_client.is_connected():
                    mqtt_ok = mqtt_client.reconnect(DEVICE_ID, MQTT_BROKER, MQTT_PORT)
                    if mqtt_ok:
                        mqtt_client.subscribe_commands(DEVICE_ID)

        except Exception as e:
            print("Error: {}".format(e))
            display.show_error(str(e)[:32])

        sleep_ms(LOOP_MS)
        elapsed += 1


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
