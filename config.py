"""
config.py - Carga de configuración desde /config.json
"""

import ujson


def load_config():
    """Carga configuración desde /config.json."""

    try:
        with open("config.json", "r") as f:
            config = ujson.load(f)

        required = [
            "device_id",
            "secret_key",
            "wifi_ssid",
            "wifi_password",
            "mqtt_broker"
        ]

        for field in required:
            if field not in config:
                print("ERROR: falta '{}' en config.json".format(field))
                return None

        return config

    except OSError:
        print("ERROR: No se encontró /config.json")
        return None
    except ValueError:
        print("ERROR: config.json no es JSON válido")
        return None
