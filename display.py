"""
display.py - Pantalla OLED I2C 1.3" (SH1106 128x64)

Estados de pantalla:
    1. Logo de inicio (animado)
    2. Mensajes de estado por cada acción (WiFi, NTP, MQTT, etc.)
    3. Pantalla de medición activa
    4. Mensajes por acción MQTT (publicar, recibir comando, etc.)
    5. Modo reposo (pantalla atenuada con info mínima)

Conexión I2C:
    SDA → GPIO16
    SCL → GPIO17
    VCC → 3.3V
    GND → GND
"""

from machine import Pin, I2C
from sh1106 import SH1106_I2C
from time import sleep_ms, ticks_ms, ticks_diff


# I2C en GPIO16 (SDA) y GPIO17 (SCL)
_i2c = I2C(0, sda=Pin(16), scl=Pin(17), freq=400000)
_oled = None
_sleep_mode = False
_last_activity = 0
SLEEP_TIMEOUT_MS = 30000  # 30 segundos sin actividad → reposo


def init():
    """Inicializa la pantalla OLED. Retorna True si se detectó."""
    global _oled, _last_activity

    devices = _i2c.scan()

    if not devices:
        print("OLED no detectada")
        return False

    addr = devices[0]
    print("OLED detectada en 0x{:02X}".format(addr))

    _oled = SH1106_I2C(128, 64, _i2c, addr)
    _oled.fill(0)
    _oled.show()
    _last_activity = ticks_ms()
    return True


def is_available():
    """Retorna True si la pantalla está inicializada."""
    return _oled is not None


# ============================================================
# 1. LOGO DE INICIO
# ============================================================

def show_logo():
    """Muestra logo de inicio animado."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    # Marco exterior
    _oled.rect(0, 0, 128, 64, 1)
    _oled.rect(2, 2, 124, 60, 1)

    # Icono de señal/antena (centro superior)
    # Arcos simulados
    _oled.hline(56, 14, 16, 1)
    _oled.hline(52, 18, 24, 1)
    _oled.hline(48, 22, 32, 1)
    _oled.pixel(64, 26, 1)
    _oled.pixel(63, 26, 1)
    _oled.pixel(65, 26, 1)

    # Texto principal
    _oled.text("IoT Sensor", 24, 32)
    _oled.text("Network", 36, 42)

    # Versión
    _oled.text("v1.0 MQTT", 28, 54)

    _oled.show()
    sleep_ms(800)

    # Animación de carga
    for i in range(10):
        x = 14 + (i * 10)
        _oled.fill_rect(14, 54, 100, 8, 0)
        _oled.fill_rect(14, 54, (i + 1) * 10, 8, 1)
        _oled.show()
        sleep_ms(150)

    sleep_ms(300)


# ============================================================
# 2. MENSAJES DE ESTADO (durante arranque y acciones)
# ============================================================

def show_status(title, message, icon=""):
    """
    Muestra un mensaje de estado con título e icono.
    Usado para cada paso del arranque y cada acción MQTT.
    """
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    # Header con título
    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text(title[:16], 2, 2, 0)  # Texto invertido

    # Icono (si hay)
    if icon:
        _oled.text(icon, 4, 28)
        _oled.text(message[:14], 20, 28)
    else:
        _oled.text(message[:16], 4, 28)

    _oled.show()


def show_progress(title, message, step, total):
    """Muestra progreso con barra."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    # Header
    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text(title[:16], 2, 2, 0)

    # Mensaje
    _oled.text(message[:16], 4, 24)

    # Barra de progreso
    bar_width = 100
    bar_x = 14
    bar_y = 40
    progress = int((step / total) * bar_width)

    _oled.rect(bar_x, bar_y, bar_width, 10, 1)
    _oled.fill_rect(bar_x + 1, bar_y + 1, progress, 8, 1)

    # Porcentaje
    pct = int((step / total) * 100)
    _oled.text("{}%".format(pct), 54, 54)

    _oled.show()


# ============================================================
# 3. MENSAJES MQTT (por cada interacción)
# ============================================================

def show_mqtt_publish(device_id, value, seq):
    """Muestra que se está publicando telemetría."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT PUBLISH", 2, 2, 0)

    _oled.text("Topic:", 0, 16)
    _oled.text("  .../telemetry", 0, 26)
    _oled.text("Val: {}V".format(value), 0, 38)
    _oled.text("Seq: {}".format(seq), 0, 48)

    # Indicador de envío
    _oled.text(">>>", 104, 56)

    _oled.show()


def show_mqtt_published_ok(value, seq):
    """Confirma que la medición se envió correctamente."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("ENVIADO OK", 2, 2, 0)

    _oled.text("Val: {}V".format(value), 0, 20)
    _oled.text("Seq: {}".format(seq), 0, 32)

    # Checkmark grande
    _oled.text("[OK]", 48, 50)

    _oled.show()


def show_mqtt_publish_fail():
    """Muestra fallo de envío MQTT."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("ENVIO FALLIDO", 2, 2, 0)

    _oled.text("Guardando en", 0, 28)
    _oled.text("buffer local...", 0, 40)
    _oled.text("[RETRY]", 40, 54)

    _oled.show()


def show_mqtt_command(action):
    """Muestra que se recibió un comando del backend."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT COMMAND", 2, 2, 0)

    _oled.text("<<<", 0, 16)
    _oled.text("Recibido:", 0, 28)
    _oled.text(action[:16], 0, 40)
    _oled.text("Ejecutando...", 0, 54)

    _oled.show()


def show_mqtt_subscribe(topic):
    """Muestra suscripción a topic."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT SUBSCRIBE", 2, 2, 0)

    _oled.text("Topic:", 0, 24)
    _oled.text(".../command", 0, 36)
    _oled.text("[LISTENING]", 20, 54)

    _oled.show()


def show_buffer_flush(count, sent):
    """Muestra que se está vaciando el buffer."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("FLUSH BUFFER", 2, 2, 0)

    _oled.text("Pendientes: {}".format(count), 0, 24)
    _oled.text("Enviados:   {}".format(sent), 0, 36)

    _oled.show()


# ============================================================
# 4. PANTALLA DE MEDICIÓN (datos actuales)
# ============================================================

def show_measurement(device_id, readings, sensors_config, wifi_ok, mqtt_ok, buffer_count,
                     synced_ts=None):
    """
    Pantalla principal — siempre visible.
    Header: HORA (izq)          RED barras (der)
    Body: Dinámico según sensores del config
    Footer: ID corto (centrado)

    synced_ts: timestamp Unix confiable (calibrado con la hora del servidor) o None.
      - Si None (aún no sincronizado): la hora PARPADEA (feedback de "sincronizando").
      - Si tiene valor: muestra la hora del servidor de forma fija (deja de parpadear).
    """
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    # -- HEADER: HORA --
    # Solo se muestra la hora cuando está ligada a la del servidor (synced_ts).
    # Antes de sincronizar NO se muestra hora (queda en blanco), no parpadea.
    from time import localtime
    if synced_ts is not None:
        # Hora local de México (UTC-6). Solo visual; los datos/firma van en UTC.
        local_ts = int(synced_ts) - 6 * 3600
        t = localtime(local_ts)
        hour = t[3]
        minute = t[4]
        ampm = "AM" if hour < 12 else "PM"
        hour12 = hour % 12
        if hour12 == 0:
            hour12 = 12
        time_str = "{}:{:02d} {}".format(hour12, minute, ampm)
        _oled.text(time_str, 0, 2)
    else:
        # Sin hora del servidor todavía: indicador discreto (no muestra hora)
        _oled.text("sync..", 0, 2)

    # RED + barras animadas (con espacio entre el texto y las barras)
    _oled.text("RED", 80, 2)
    frame = (ticks_ms() // 300) % 4

    if wifi_ok and mqtt_ok:
        _oled.fill_rect(112, 8, 3, 3, 1)
        _oled.fill_rect(116, 5, 3, 6, 1)
        _oled.fill_rect(120, 2, 3, 9, 1)
    elif wifi_ok:
        _oled.fill_rect(112, 8, 3, 3, 1)
        _oled.fill_rect(116, 5, 3, 6, 1)
        if frame < 2:
            _oled.fill_rect(120, 2, 3, 9, 1)
    else:
        if frame >= 1:
            _oled.fill_rect(112, 8, 3, 3, 1)
        if frame >= 2:
            _oled.fill_rect(116, 5, 3, 6, 1)
        if frame >= 3:
            _oled.fill_rect(120, 2, 3, 9, 1)

    _oled.hline(0, 13, 128, 1)

    # -- BODY: Sensores dinámicos --
    y = 18
    for i, r in enumerate(readings):
        if y > 44:
            break
        # Buscar label del sensor en config
        label = ""
        unit = ""
        for s in sensors_config:
            if s["id"] == r["sensor_id"]:
                label = s.get("label", s["id"])[:4]
                unit = s.get("unit", "")
                break
        line = "{}: {} {}".format(label, r["value"], unit)
        _oled.text(line[:16], 0, y)
        y += 14

    # -- FOOTER (centrado) --
    _oled.hline(0, 52, 128, 1)
    short_id = _format_device_id(device_id)
    x_offset = (128 - len(short_id) * 8) // 2
    _oled.text(short_id, x_offset, 56)

    _oled.show()


def _format_device_id(device_id):
    """Formatea device_id para pantalla."""
    return device_id.upper()[:16]


# ============================================================
# 5. MODO REPOSO
# ============================================================

def show_sleep(device_id, next_in_secs):
    """
    Modo reposo — pantalla mínima con countdown al próximo envío.
    Contraste reducido para ahorrar pantalla.
    """
    if not _oled:
        return

    global _sleep_mode
    _sleep_mode = True

    _oled.fill(0)

    # -- HEADER --
    _oled.text("WiFi:OK", 0, 0)
    _oled.text("MQTT:OK", 72, 0)
    _oled.hline(0, 10, 128, 1)

    # -- BODY: Countdown --
    mins = next_in_secs // 60
    secs = next_in_secs % 60
    _oled.text("zzZ Reposo", 24, 20)
    _oled.text("Prox: {}:{:02d}".format(mins, secs), 20, 34)

    # -- FOOTER --
    _oled.hline(0, 52, 128, 1)
    _oled.text(device_id[:16], 0, 56)

    _oled.show()

    # Reducir contraste
    _oled.contrast(10)


def check_sleep_timeout():
    """Verifica si debe entrar en modo reposo por inactividad."""
    global _last_activity
    if not _oled:
        return False
    return ticks_diff(ticks_ms(), _last_activity) > SLEEP_TIMEOUT_MS


# ============================================================
# UTILIDADES
# ============================================================

def _wake():
    """Despierta la pantalla del modo reposo."""
    global _sleep_mode, _last_activity

    _last_activity = ticks_ms()

    if _sleep_mode and _oled:
        _sleep_mode = False
        _oled.contrast(255)


def show_error(message):
    """Muestra mensaje de error."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("!! ERROR !!", 2, 2, 0)

    _oled.text(message[:16], 0, 28)
    _oled.text(message[16:32], 0, 40)

    _oled.show()


def show_wifi_connecting(ssid):
    """Muestra que se está conectando a WiFi."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("WIFI", 2, 2, 0)

    _oled.text("Conectando...", 0, 24)
    _oled.text(ssid[:16], 0, 38)

    _oled.show()


def show_wifi_ok(ip):
    """Muestra WiFi conectado."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("WIFI OK", 2, 2, 0)

    _oled.text("IP:", 0, 28)
    _oled.text(ip, 0, 40)

    _oled.show()


def show_wifi_fail():
    """Muestra fallo WiFi."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("WIFI FAIL", 2, 2, 0)

    _oled.text("Sin conexion", 0, 28)
    _oled.text("Reintentando...", 0, 40)

    _oled.show()


def show_ntp_sync(success):
    """Muestra resultado de sincronización NTP."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("NTP SYNC", 2, 2, 0)

    if success:
        _oled.text("Hora OK", 0, 28)
    else:
        _oled.text("Hora: sin sync", 0, 28)
        _oled.text("(usando local)", 0, 40)

    _oled.show()


def show_mqtt_connecting(broker):
    """Muestra que se conecta al broker."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT CONNECT", 2, 2, 0)

    _oled.text("Broker:", 0, 24)
    _oled.text(broker[:16], 0, 36)
    _oled.text("Conectando...", 0, 50)

    _oled.show()


def show_mqtt_connected():
    """Muestra MQTT conectado."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT OK", 2, 2, 0)

    _oled.text("Conectado al", 0, 28)
    _oled.text("broker MQTT", 0, 40)
    _oled.text("[READY]", 40, 54)

    _oled.show()


def show_mqtt_fail():
    """Muestra fallo MQTT."""
    if not _oled:
        return

    _wake()
    _oled.fill(0)

    _oled.fill_rect(0, 0, 128, 12, 1)
    _oled.text("MQTT FAIL", 2, 2, 0)

    _oled.text("Sin conexion", 0, 28)
    _oled.text("al broker", 0, 40)

    _oled.show()


def clear():
    """Limpia la pantalla."""
    if not _oled:
        return
    _oled.fill(0)
    _oled.show()


def off():
    """Apaga la pantalla."""
    if not _oled:
        return
    _oled.poweroff()
