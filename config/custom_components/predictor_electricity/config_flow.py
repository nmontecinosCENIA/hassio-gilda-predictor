from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

DOMAIN = "predictor_electricity"

class PredictorElectricityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Predictor Electricity."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("input_sensor"): str,
                        vol.Optional("update_interval", default=3600): int
                    }
                ),
                description_placeholders={
                    "input_sensor": "e.g., sensor.electricity_maps_co2_intensity_2"
                }
            )

        # Validate the input sensor
        if not self.hass.states.get(user_input["input_sensor"]):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("input_sensor"): str,
                        vol.Optional("update_interval", default=3600): int
                    }
                ),
                errors={"input_sensor": "Sensor not found"}
            )

        # Create the config entry
        return self.async_create_entry(
            title="Electricity Predictor",
            data={
                "input_sensor": user_input["input_sensor"],
                "update_interval": user_input["update_interval"]
            }
        )