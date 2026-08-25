# Raspberry Pi Pico W — Nodo IoT con MQTT

Firmware modular con comunicación MQTT bidireccional. Publica mediciones y recibe comandos en tiempo real.

## Diferencias con pico_w (HTTP)

| Aspecto | HTTP (pico_w/) | MQTT (pico-mqtt/) |
|---------|----------------|-------------------|
| Protocolo | HTTP POST cada 5 min | MQTT publish (conexión persistente) |
| Recibe comandos | No | Sí (subscribe a topic) |
| Medición bajo demanda | No | Sí (comando `measure_now`) |
| Loop interval | Duerme 5 min entre mediciones | Loop cada 1s (escucha comandos) |
| Módulo de red | `network_client.py` (HTTP) | `mqtt_client.py` (MQTT) |

## Estructura de archivos

```
pico-mqtt/
├── main.py            ← Loop principal con MQTT
├── config.json        ← Configuración (broker en vez de URL)
├── config.py          ← Carga config.json
├── wifi.py            ← Conexión WiFi
├── sensor.py          ← Lectura ADC (GPIO26)
├── crypto.py          ← HMAC-SHA256
├── mqtt_client.py     ← Cliente MQTT (connect, publish, subscribe)
├── buffer.py          ← Buffer offline
├── sequence.py        ← Sequence number persistente
├── display.py         ← Pantalla OLED (opcional)
└── sh1106.py          ← Driver SH1106
```

## Configuración

```json
{
    "device_id": "pico-mx-000001",
    "secret_key": "tu_clave_secreta",
    "wifi_ssid": "tu_wifi",
    "wifi_password": "tu_password",
    "mqtt_broker": "192.168.1.100",
    "mqtt_port": 1883,
    "interval_seconds": 300
}
```

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| `device_id` | Sí | Identificador único |
| `secret_key` | Sí | Clave HMAC |
| `wifi_ssid` | Sí | Red WiFi |
| `wifi_password` | Sí | Contraseña WiFi |
| `mqtt_broker` | Sí | IP o hostname del broker Mosquitto |
| `mqtt_port` | No | Puerto MQTT (default: 1883) |
| `interval_seconds` | No | Intervalo entre mediciones (default: 300) |

## Topics MQTT

| Topic | Dirección | Uso |
|-------|-----------|-----|
| `devices/pico-mx-000001/telemetry` | Pico → Backend | Publica mediciones |
| `devices/pico-mx-000001/command` | Backend → Pico | Recibe comandos |

## Comandos soportados

| Comando | Acción |
|---------|--------|
| `{"action": "measure_now"}` | Lee sensor y publica medición inmediatamente |

## Flujo de operación

```
1. Conecta WiFi
2. Conecta MQTT broker
3. Subscribe a devices/{id}/command
4. Loop (cada 1 segundo):
   a. Revisa si llegó comando MQTT
   b. Si comando "measure_now" → mide y publica inmediatamente
   c. Si pasaron INTERVAL segundos → mide y publica (periódico)
   d. Actualiza pantalla OLED
   e. Reconecta WiFi/MQTT si se perdió conexión
```

## Conexiones de hardware

### Sensor analógico

| Pin | Pico W |
|-----|--------|
| VCC | 3.3V |
| GND | GND |
| OUT | GPIO26 (ADC0) |

### Pantalla OLED 1.3" (opcional)

| Pin | Pico W |
|-----|--------|
| SDA | GPIO4 |
| SCL | GPIO5 |
| VCC | 3.3V |
| GND | GND |

## Payload publicado en telemetry

```json
{
    "device_id": "pico-mx-000001",
    "value": 23.42,
    "raw_value": 47236,
    "timestamp": 1786812000,
    "sequence": 1234,
    "signature": "a82f3b2c..."
}
```

## Dependencias MicroPython

Solo módulos estándar incluidos en el firmware:
- `umqtt.simple` (cliente MQTT)
- `machine`, `network`, `time`
- `ujson`, `uhashlib`, `ubinascii`
- `ntptime`, `framebuf`

No se requieren librerías externas.
