"""
mqtt_client.py - Cliente MQTT para Pico W

Usa umqtt.simple (incluido en MicroPython estándar).
Maneja conexión, publicación de telemetría y suscripción a comandos.
"""

from umqtt.simple import MQTTClient
from time import sleep


_client = None
_command_callback = None


def connect(client_id, broker_host, broker_port=1883, user=None, password=None):
    """
    Conecta al broker MQTT.
    Retorna True si fue exitoso.
    """

    global _client

    try:
        _client = MQTTClient(client_id, broker_host, port=broker_port,
                             user=user, password=password, keepalive=120)
        _client.set_callback(_on_message)
        _client.connect()
        print("MQTT conectado a {}:{}".format(broker_host, broker_port))
        return True

    except Exception as e:
        print("ERROR MQTT connect: {}".format(e))
        _client = None
        return False


def subscribe_commands(device_id):
    """
    Se subscribe al topic de comandos para este dispositivo.
    Topic: devices/{device_id}/command
    """

    if not _client:
        return False

    topic = "devices/{}/command".format(device_id)

    try:
        _client.subscribe(topic.encode())
        print("MQTT subscrito a: {}".format(topic))
        return True
    except Exception as e:
        print("ERROR MQTT subscribe: {}".format(e))
        return False


def subscribe_register_ack(device_id):
    """
    Se subscribe al topic de ACK de registro (hora del servidor para calibrar).
    Topic: devices/{device_id}/register/ack
    """

    if not _client:
        return False

    topic = "devices/{}/register/ack".format(device_id)

    try:
        _client.subscribe(topic.encode())
        print("MQTT subscrito a: {}".format(topic))
        return True
    except Exception as e:
        print("ERROR MQTT subscribe ack: {}".format(e))
        return False


def publish_telemetry(device_id, payload_json):
    """
    Publica medición en el topic de telemetría.
    Topic: devices/{device_id}/telemetry
    """

    if not _client:
        return False

    topic = "devices/{}/telemetry".format(device_id)

    try:
        _client.publish(topic.encode(), payload_json.encode(), qos=0)
        return True
    except Exception as e:
        print("ERROR MQTT publish: {}".format(e))
        return False


def publish(topic, payload_json):
    """
    Publica en un topic arbitrario.
    """

    if not _client:
        return False

    try:
        _client.publish(topic.encode(), payload_json.encode(), qos=0)
        return True
    except Exception as e:
        print("ERROR MQTT publish {}: {}".format(topic, e))
        return False


def set_command_callback(callback):
    """
    Registra callback para cuando llega un comando.
    callback(topic: str, payload: str)
    """

    global _command_callback
    _command_callback = callback


def check_messages():
    """
    Revisa si hay mensajes MQTT pendientes (non-blocking).
    Debe llamarse frecuentemente en el loop.
    """

    if not _client:
        return

    try:
        _client.check_msg()
    except Exception as e:
        print("ERROR MQTT check: {}".format(e))


def is_connected():
    """Retorna True si el cliente MQTT está conectado."""
    return _client is not None


def disconnect():
    """Desconecta del broker MQTT."""

    global _client

    if _client:
        try:
            _client.disconnect()
        except:
            pass
        _client = None


def reconnect(client_id, broker_host, broker_port=1883):
    """Intenta reconectar al broker."""

    disconnect()
    sleep(2)
    return connect(client_id, broker_host, broker_port)


def _on_message(topic, msg):
    """Callback interno cuando llega un mensaje MQTT."""

    topic_str = topic.decode() if isinstance(topic, bytes) else topic
    msg_str = msg.decode() if isinstance(msg, bytes) else msg

    print("MQTT recibido: {} → {}".format(topic_str, msg_str[:100]))

    if _command_callback:
        _command_callback(topic_str, msg_str)
