import requests
import json
import pandas as pd
from datetime import timedelta
import logging
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from . import DOMAIN
import pytz


_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="persistence_forecast",
        name="CO2 Intensity Persistence Forecast",
        native_unit_of_measurement="gCO2eq/kWh",
        icon="mdi:leaf"
    ),
    SensorEntityDescription(
        key="mean_forecast",
        name="CO2 Intensity Mean Forecast",
        native_unit_of_measurement="gCO2eq/kWh",
        icon="mdi:leaf"
    ),
    SensorEntityDescription(
        key="median_forecast",
        name="CO2 Intensity Median Forecast",
        native_unit_of_measurement="gCO2eq/kWh",
        icon="mdi:leaf"
    ),
    SensorEntityDescription(
        key="prophet_forecast",
        name="CO2 Intensity Prophet Forecast",
        native_unit_of_measurement="gCO2eq/kWh",
        icon="mdi:leaf"
    ),
    SensorEntityDescription(
        key="arima_forecast",
        name="CO2 Intensity AutoARIMA Forecast",
        native_unit_of_measurement="gCO2eq/kWh",
        icon="mdi:leaf"
    ),
]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    input_sensor = entry.data["input_sensor"]
    update_interval = entry.data["update_interval"]
    sensors = [
        PredictorSensor(hass, input_sensor, update_interval, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(sensors)

class PredictorSensor(SensorEntity):
    def __init__(self, hass: HomeAssistant, input_sensor: str, update_interval: int, description: SensorEntityDescription) -> None:
        super().__init__()
        self.entity_description = description
        self._hass = hass
        self._input_sensor = input_sensor
        self._attr_unique_id = f"{input_sensor}_{description.key}"
        self._attr_should_poll = True
        self._attr_update_interval = timedelta(seconds=update_interval)
        self._state = None
        self._attr_extra_state_attributes = {
            "forecast": [],
            "lower_ci": [],
            "upper_ci": [],
            "forecast_timestamps": []
        }

    async def async_update(self) -> None:
        """Actualiza el sensor."""
        history = await self._hass.async_add_executor_job(self._get_history)
        if not history:
            _LOGGER.warning("No hay datos históricos disponibles para %s", self._input_sensor)
            self._state = None
            return

        try:

            data = pd.DataFrame(history, columns=["ds", "y"])
            data["ds"] = pd.to_datetime(data["ds"]).dt.tz_localize(None)  # <- 🔧 Aquí está la clave
            data["y"] = data["y"].astype(float)


            input_data = {
                "data": [
                    {"ds": row["ds"].isoformat(), "y": row["y"]}
                    for _, row in data[["ds", "y"]].iterrows()
                ],
                "periods": 24,
                "freq": "h"
            }
            _LOGGER.debug("Datos de entrada para el add-on: %s", input_data)

            #URL del add-on
            url = "http://local-predictor-electricity:5000/predict"

            
            # enviar solicitud al add-on
            response = await self._hass.async_add_executor_job(
                lambda: requests.post(url, json=input_data, timeout=30)
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                _LOGGER.error("Error en el add-on: %s", result["error"])
                self._state = None
                return


            forecast_timestamps = [
                (pd.to_datetime(ts) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
                for ts in result.get("dates", [])
            ]

            model_key = self.entity_description.key.replace("_forecast", "")
            

            if model_key in ["prophet", "arima"]:
                expected_keys = [model_key, f"{model_key}_lower", f"{model_key}_upper"]
            else:
                expected_keys = [model_key]


            if not all(key in result for key in expected_keys):
                _LOGGER.error("Faltan claves esperadas en el resultado: %s", expected_keys)
                self._state = None
                return

            self._state = round(result[model_key][0], 2) if result[model_key] else None
            self._attr_extra_state_attributes = {
                "forecast": result.get(model_key, []),
                "lower_ci": result.get(f"{model_key}_lower", []),
                "upper_ci": result.get(f"{model_key}_upper", []),
                "forecast_timestamps": forecast_timestamps
            }
        except requests.RequestException as e:
            _LOGGER.error("Error al llamar al add-on: %s", e)
            self._state = None
        except Exception as e:
            _LOGGER.error("Error durante la predicción: %s", e)
            self._state = None

    def _get_history(self):
        """Retrieve historical data for the input sensor."""
        try:
            from homeassistant.components.recorder.history import get_significant_states
            now = dt_util.now()
            start_time = now - timedelta(days=7)
            history = get_significant_states(
                self._hass,
                start_time,
                now,
                entity_ids=[self._input_sensor]
            )
            data = []
            for entity_id, states in history.items():
                for state in states:
                    try:
                        value = float(state.state)
                        timestamp = state.last_updated
                        data.append([timestamp, value])
                    except (ValueError, TypeError):
                        continue
            if not data:
                _LOGGER.warning("No valid historical data found for %s", self._input_sensor)
            return data
        except Exception as e:
            _LOGGER.error("Error retrieving history: %s", e)
            return []

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state