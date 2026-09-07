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
import timesync
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

# Flag para medición bajo demanda
_measure_requested = False


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def get_timestamp():
    """Timestamp Unix confiable (calibrado por el ACK del servidor), o None."""
    return timesync.get_timestamp()


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
    Envía mensaje de registro al backend via MQTT en CADA arranque/reconexión.
    El backend es idempotente y responde con su hora (ACK) para calibrar el reloj.
    El backend NO valida timestamp en el registro, así que si aún no hay hora
    confiable se firma con 0.
    Topic: devices/{device_id}/register
    """
    timestamp = get_timestamp()
    if timestamp is None:
        timestamp = 0  # registro no valida timestamp; sirve para recibir el ACK con la hora

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
        print("Auto-registro enviado: {} (esperando ACK con hora)".format(topic))
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
    """Callback cuando llega un mensaje del backend (comando o ACK de registro)."""

    global _measure_requested

    try:
        cmd = ujson.loads(payload)
        action = cmd.get("action", "")

        # ACK de registro con la hora del servidor → calibrar reloj
        if action == "time_sync":
            server_time = cmd.get("server_time")
            print("ACK recibido: time_sync server_time={}".format(server_time))
            timesync.set_from_server(server_time)
            return

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

    # Sin hora confiable (aún no llegó el ACK del servidor): NO publicar.
    # El timestamp sería inválido y el backend lo rechazaría. Se omite este ciclo.
    if timestamp is None:
        print("Sin hora calibrada (esperando ACK) → no se publica esta medición")
        return False, readings

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
    timesync.load()  # cargar offset previo si existe (respaldo)

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

    # ── 5. CONECTAR MQTT ──
    mqtt_ok = False
    if wifi_ok:
        mqtt_ok = mqtt_client.connect(DEVICE_ID, MQTT_BROKER, MQTT_PORT)
        if mqtt_ok:
            mqtt_client.set_command_callback(on_command)
            mqtt_client.subscribe_commands(DEVICE_ID)
            mqtt_client.subscribe_register_ack(DEVICE_ID)  # hora del servidor
            # Auto-registro: dispara el ACK con la hora para calibrar el reloj
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
                buffer_count=buffer.count(),
                synced_ts=timesync.get_timestamp()  # None → hora parpadea; con valor → fija (hora servidor)
            )

            # Reconectar (solo si alguna vez conectó)
            if elapsed % 150 == 0:
                if not wifi.is_connected() and wifi_ok:
                    wifi.connect(WIFI_SSID, WIFI_PASSWORD)
                if wifi.is_connected() and not mqtt_client.is_connected():
                    mqtt_ok = mqtt_client.reconnect(DEVICE_ID, MQTT_BROKER, MQTT_PORT)
                    if mqtt_ok:
                        mqtt_client.subscribe_commands(DEVICE_ID)
                        mqtt_client.subscribe_register_ack(DEVICE_ID)
                        # Re-registrar para recibir la hora del servidor y recalibrar
                        do_auto_register()
                # Si estamos conectados pero aún sin hora, re-registrar para pedir el ACK
                elif mqtt_client.is_connected() and not timesync.is_valid():
                    do_auto_register()

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
