"""
wifi.py - Conexión WiFi (no bloqueante)
"""

from time import sleep
import network


wlan = network.WLAN(network.STA_IF)


def connect(ssid, password):
    """Conecta al WiFi. Un intento con timeout de 10s."""

    wlan.active(True)

    if wlan.isconnected():
        return True

    print("WiFi conectando a {}...".format(ssid))
    wlan.connect(ssid, password)

    timeout = 10
    while not wlan.isconnected() and timeout > 0:
        sleep(1)
        timeout -= 1

    if wlan.isconnected():
        print("WiFi OK - IP: {}".format(wlan.ifconfig()[0]))
        return True

    print("WiFi: sin conexion")
    return False


def is_connected():
    """Verifica si hay conexión WiFi activa."""
    return wlan.isconnected()


def get_ip():
    """Retorna la IP local."""
    return wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
