from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "predictor_electricity"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """configurar Predictor Electricity a partir de una configuración analizada"""
    hass.data.setdefault(DOMAIN, {})
# reenviar la configuración a la plataforma del sensor
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """descargar una entrada de configuración."""
    await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True
