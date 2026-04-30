"""
Beacon Waste Collection - Integrazione custom per Home Assistant.

Gestisce il conferimento della spazzatura tramite beacon BLE.
Ogni secchio ha un beacon che espone sensori di RSSI, vibrazione,
temperatura, umidità e un pulsante fisico.

Questo modulo è il punto di ingresso dell'integrazione:
- async_setup_entry: crea i coordinator per ogni secchio configurato
  e registra le piattaforme entità (select, binary_sensor, sensor).
- async_unload_entry: rimuove listener e coordinator quando l'integrazione
  viene disabilitata o rimossa.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_BINS,
    CONF_RSSI_THRESHOLD_MIN,
    CONF_RSSI_THRESHOLD_MAX,
    CONF_ZONE_NEAR,
    CONF_ZONE_FAR,
    CONF_TMON_HOME,
    CONF_TMON_PICKUP,
    CONF_TMON_LOST,
)
from .coordinator import BinCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Inizializza l'integrazione a partire da una config entry.

    Per ogni secchio configurato:
    1. Estrae la configurazione globale (soglie RSSI, zone, debounce)
    2. Crea un BinCoordinator che gestisce la macchina a stati
    3. Avvia i listener sui sensori del beacon (RSSI, vibrazione, pulsante)
    4. Registra le piattaforme entità (select, binary_sensor, sensor)
    """
    hass.data.setdefault(DOMAIN, {})

    # Parametri globali condivisi da tutti i secchi:
    # soglie RSSI, mappatura zone, tempi di debounce
    global_config = {
        CONF_RSSI_THRESHOLD_MIN: entry.data[CONF_RSSI_THRESHOLD_MIN],
        CONF_RSSI_THRESHOLD_MAX: entry.data[CONF_RSSI_THRESHOLD_MAX],
        CONF_ZONE_NEAR: entry.data[CONF_ZONE_NEAR],
        CONF_ZONE_FAR: entry.data[CONF_ZONE_FAR],
        CONF_TMON_HOME: entry.data[CONF_TMON_HOME],
        CONF_TMON_PICKUP: entry.data[CONF_TMON_PICKUP],
        CONF_TMON_LOST: entry.data[CONF_TMON_LOST],
    }

    bins_config: list[dict[str, Any]] = entry.data[CONF_BINS]
    coordinators: list[BinCoordinator] = []

    for bin_config in bins_config:
        # Ogni coordinator gestisce un singolo secchio:
        # ascolta RSSI, vibrazione, pulsante e aggiorna gli stati
        coordinator = BinCoordinator(hass, bin_config, global_config, entry.entry_id)
        await coordinator.async_setup()
        coordinators.append(coordinator)

    # Salva i coordinator in hass.data per renderli accessibili
    # alle piattaforme entità (select.py, binary_sensor.py, sensor.py)
    hass.data[DOMAIN][entry.entry_id] = coordinators

    # Registra le piattaforme entità in HA
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rimuovi l'integrazione.

    1. Rimuove le piattaforme entità
    2. Ferma i listener di ogni coordinator (RSSI, vibrazione, pulsante, timer)
    3. Pulisce hass.data
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinators: list[BinCoordinator] = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in coordinators:
            await coordinator.async_teardown()

    return unload_ok
