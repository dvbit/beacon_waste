"""
Beacon Waste Collection - Integrazione custom per Home Assistant.

Gestisce il conferimento della spazzatura tramite beacon BLE.

Questo modulo:
- async_setup_entry: crea i coordinator, registra piattaforme e il servizio reset_bin
- async_unload_entry: rimuove listener e coordinator
- Il servizio beacon_waste.reset_bin equivale alla pressione del pulsante fisico:
  resetta lo stato del secchio (vuoto, in_uso, attesa=false, contatore=0)
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_BINS,
    CONF_RSSI_THRESHOLD_HIGH,
    CONF_RSSI_THRESHOLD_LOW,
    CONF_ZONE_NEAR,
    CONF_ZONE_FAR,
    CONF_TMON_HOME,
    CONF_TMON_PICKUP,
    CONF_TMON_LOST,
)
from .coordinator import BinCoordinator

_LOGGER = logging.getLogger(__name__)

# Nome del servizio HA per il reset manuale del secchio
SERVICE_RESET_BIN = "reset_bin"
# Attributo del servizio: nome del secchio da resettare
ATTR_BIN_NAME = "bin_name"


def _get_global_config(entry: ConfigEntry) -> dict[str, Any]:
    """Legge la configurazione globale fondendo data e options.

    Le options hanno priorità su data: permettono di sovrascrivere
    le soglie RSSI e le zone tramite l'options flow senza reinstallare.
    """
    return {
        CONF_RSSI_THRESHOLD_HIGH: entry.options.get(
            CONF_RSSI_THRESHOLD_HIGH, entry.data[CONF_RSSI_THRESHOLD_HIGH]
        ),
        CONF_RSSI_THRESHOLD_LOW: entry.options.get(
            CONF_RSSI_THRESHOLD_LOW, entry.data[CONF_RSSI_THRESHOLD_LOW]
        ),
        CONF_ZONE_NEAR: entry.options.get(CONF_ZONE_NEAR, entry.data[CONF_ZONE_NEAR]),
        CONF_ZONE_FAR: entry.options.get(CONF_ZONE_FAR, entry.data[CONF_ZONE_FAR]),
        CONF_TMON_HOME: entry.options.get(CONF_TMON_HOME, entry.data[CONF_TMON_HOME]),
        CONF_TMON_PICKUP: entry.options.get(CONF_TMON_PICKUP, entry.data[CONF_TMON_PICKUP]),
        CONF_TMON_LOST: entry.options.get(CONF_TMON_LOST, entry.data[CONF_TMON_LOST]),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Inizializza l'integrazione a partire da una config entry.

    1. Legge la configurazione globale (fondendo data e options)
    2. Crea un BinCoordinator per ogni secchio
    3. Registra le piattaforme entità
    4. Registra il servizio beacon_waste.reset_bin
    """
    hass.data.setdefault(DOMAIN, {})

    global_config = _get_global_config(entry)
    bins_config: list[dict[str, Any]] = entry.data[CONF_BINS]
    coordinators: list[BinCoordinator] = []

    for bin_config in bins_config:
        coordinator = BinCoordinator(hass, bin_config, global_config, entry.entry_id)
        await coordinator.async_setup()
        coordinators.append(coordinator)

    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Registrazione servizio reset_bin ---
    # Il servizio è equivalente alla pressione del pulsante fisico sul beacon.
    # Può essere chiamato da automazioni, script, o tramite il pulsante nel dispositivo.
    async def handle_reset_bin(call: ServiceCall) -> None:
        """Gestisce il servizio beacon_waste.reset_bin.

        Cerca il coordinator con il nome corrispondente e ne resetta lo stato.
        """
        bin_name = call.data[ATTR_BIN_NAME]
        found = False
        for entry_coordinators in hass.data.get(DOMAIN, {}).values():
            for coordinator in entry_coordinators:
                if coordinator.name == bin_name:
                    coordinator.reset_state()
                    found = True
                    _LOGGER.debug("Service reset_bin called for '%s'", bin_name)

        if not found:
            _LOGGER.warning(
                "beacon_waste.reset_bin: no bin found with name '%s'", bin_name
            )

    # Registra il servizio solo se non già registrato (evita duplicati al reload)
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_BIN):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_BIN,
            handle_reset_bin,
            schema=vol.Schema({vol.Required(ATTR_BIN_NAME): cv.string}),
        )

    # Ascolta le modifiche all'options flow per ricaricare l'integrazione
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ricarica l'integrazione quando le opzioni vengono modificate.

    Chiamato automaticamente da HA quando l'utente salva le modifiche
    nell'options flow (soglie RSSI, zone, debounce).
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rimuove l'integrazione.

    1. Rimuove le piattaforme entità
    2. Ferma i listener di ogni coordinator
    3. Rimuove il servizio se non ci sono altre entry attive
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinators: list[BinCoordinator] = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in coordinators:
            await coordinator.async_teardown()

        # Rimuovi il servizio solo se non ci sono più entry caricate
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_RESET_BIN)

    return unload_ok
