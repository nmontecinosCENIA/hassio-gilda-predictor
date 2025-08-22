import json
import os
import datetime
import sys

entity_id = sys.argv[1]  # se pasa como argumento al script

filename_map = {
    "sensor.co2_intensity_persistence_forecast": "persistence_forecast_2025.json",
    "sensor.co2_intensity_prophet_forecast": "prophet_forecast_2025.json",
    "sensor.co2_intensity_autoarima_forecast": "autoarima_forecast_2025.json",
}

filename = filename_map.get(entity_id)
if not filename:
    sys.exit(1)

log_path = f"/config/predicciones/{filename}"

# Leer forecast del sensor
import requests

hass_url = "http://localhost:8123/api/states/" + entity_id

#TOKEN DE AUTENTICACIÓN
headers = {
    "Authorization": "Bearer TU_TOKEN_HASS",
    "Content-Type": "application/json",
}

response = requests.get(hass_url, headers=headers)

if response.status_code != 200:
    sys.exit(1)

sensor_data = response.json()
forecast = sensor_data["attributes"].get("forecast")
forecast_timestamps = sensor_data["attributes"].get("forecast_timestamps")

if not forecast or not forecast_timestamps:
    sys.exit(1)

entry = {
    "timestamp": datetime.datetime.now().isoformat(),
    "forecast": forecast,
    "forecast_timestamps": forecast_timestamps,
}

# Cargar o crear archivo
if os.path.exists(log_path):
    with open(log_path, "r") as f:
        try:
            data = json.load(f)
        except:
            data = []
else:
    data = []

data.append(entry)

with open(log_path, "w") as f:
    json.dump(data, f, indent=2)
