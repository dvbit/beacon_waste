"""
Config flow e Options flow per Beacon Waste Collection.

CONFIG FLOW (prima configurazione):
  Step 1 - user:        auto-discovery beacon + parametri globali (soglie, zone, debounce)
  Step 2 - bin:         nome secchio + scelta modalità prelievo
  Step 3a - bin_calendar: giorni prelievo (multi-select) + orario esposizione
  Step 3b - bin_boolean:  selezione entità booleana esterna

OPTIONS FLOW (riconfigurazione):
  Permette di modificare soglie RSSI, zone e debounce senza reinstallare.
  Accessibile da Impostazioni → Dispositivi e servizi → Configura.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
    TimeSelectorConfig,
)

from .const import (
    DOMAIN,
    CONF_BINS,
    CONF_BIN_NAME,
    CONF_BEACON_MAC,
    CONF_PICKUP_DAYS,
    CONF_PICKUP_TIME_START,
    CONF_PICKUP_MODE,
    CONF_PICKUP_BOOLEAN_ENTITY,
    PICKUP_MODE_CALENDAR,
    PICKUP_MODE_BOOLEAN,
    CONF_RSSI_THRESHOLD_MIN,
    CONF_RSSI_THRESHOLD_MAX,
    CONF_ZONE_NEAR,
    CONF_ZONE_FAR,
    CONF_TMON_HOME,
    CONF_TMON_PICKUP,
    CONF_TMON_LOST,
    CONF_SELECTED_BEACONS,
    SUFFIX_NAME,
    DAYS_OF_WEEK,
    ZONE_HOME,
    ZONE_PICKUP,
)

_LOGGER = logging.getLogger(__name__)

# Regex per individuare le entità RSSI dei beacon ESPHome.
# Cattura: gruppo 1 = prefisso, gruppo 2 = MAC a 12 caratteri hex
BEACON_RSSI_PATTERN = re.compile(
    r"^sensor\.(.+)_([0-9a-fA-F]{12})_rssi$"
)

# Opzioni selettore zona
ZONE_OPTIONS = [
    {"value": ZONE_HOME, "label": "Casa"},
    {"value": ZONE_PICKUP, "label": "Prelievo"},
]

# Opzioni modalità schedulazione prelievo
PICKUP_MODE_OPTIONS = [
    {"value": PICKUP_MODE_CALENDAR, "label": "Calendario (giorni + orario)"},
    {"value": PICKUP_MODE_BOOLEAN, "label": "Entità booleana esterna"},
]

# Opzioni multi-select giorni della settimana.
# Ogni opzione ha value = chiave interna, label = nome leggibile.
# Il SelectSelector con multiple=True restituisce una lista di value selezionati.
DAY_OPTIONS = [
    {"value": "mon", "label": "Lunedì"},
    {"value": "tue", "label": "Martedì"},
    {"value": "wed", "label": "Mercoledì"},
    {"value": "thu", "label": "Giovedì"},
    {"value": "fri", "label": "Venerdì"},
    {"value": "sat", "label": "Sabato"},
    {"value": "sun", "label": "Domenica"},
]


def _discover_beacons(hass) -> dict[str, dict[str, str]]:
    """Scansiona tutte le entità sensor per trovare beacon ESPHome.

    Cerca entità che matchano sensor.*_XXXXXXXXXXXX_rssi e per ciascuna
    tenta di leggere il nome dal sensore sensor.*_XXXXXXXXXXXX_name.

    Returns:
        Dict {mac: {prefix, mac, name}} con tutti i beacon trovati.
    """
    beacons: dict[str, dict[str, str]] = {}
    for state in hass.states.async_all("sensor"):
        match = BEACON_RSSI_PATTERN.match(state.entity_id)
        if match:
            prefix = match.group(1)
            mac = match.group(2).lower()
            name_state = hass.states.get(f"sensor.{prefix}_{mac}_{SUFFIX_NAME}")
            beacon_name = (
                name_state.state
                if name_state and name_state.state not in ("unknown", "unavailable", "")
                else mac
            )
            beacons[mac] = {"prefix": prefix, "mac": mac, "name": beacon_name}
    return beacons


def _global_schema(current: dict[str, Any] | None = None) -> vol.Schema:
    """Costruisce lo schema per i parametri globali (usato da config e options flow)."""
    c = current or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_RSSI_THRESHOLD_MIN,
                default=c.get(CONF_RSSI_THRESHOLD_MIN, -50),
            ): NumberSelector(NumberSelectorConfig(
                min=-100, max=0, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="dBm",
            )),
            vol.Required(
                CONF_RSSI_THRESHOLD_MAX,
                default=c.get(CONF_RSSI_THRESHOLD_MAX, -80),
            ): NumberSelector(NumberSelectorConfig(
                min=-100, max=0, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="dBm",
            )),
            vol.Required(
                CONF_ZONE_NEAR,
                default=c.get(CONF_ZONE_NEAR, ZONE_HOME),
            ): SelectSelector(SelectSelectorConfig(
                options=ZONE_OPTIONS, mode=SelectSelectorMode.DROPDOWN,
            )),
            vol.Required(
                CONF_ZONE_FAR,
                default=c.get(CONF_ZONE_FAR, ZONE_PICKUP),
            ): SelectSelector(SelectSelectorConfig(
                options=ZONE_OPTIONS, mode=SelectSelectorMode.DROPDOWN,
            )),
            vol.Required(
                CONF_TMON_HOME,
                default=c.get(CONF_TMON_HOME, 60),
            ): NumberSelector(NumberSelectorConfig(
                min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )),
            vol.Required(
                CONF_TMON_PICKUP,
                default=c.get(CONF_TMON_PICKUP, 60),
            ): NumberSelector(NumberSelectorConfig(
                min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )),
            vol.Required(
                CONF_TMON_LOST,
                default=c.get(CONF_TMON_LOST, 120),
            ): NumberSelector(NumberSelectorConfig(
                min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )),
        }
    )


def _validate_global(user_input: dict[str, Any]) -> dict[str, str]:
    """Valida i parametri globali. Restituisce dict di errori (vuoto = ok)."""
    errors: dict[str, str] = {}
    if not (user_input[CONF_RSSI_THRESHOLD_MIN] > user_input[CONF_RSSI_THRESHOLD_MAX]):
        errors["base"] = "invalid_rssi_thresholds"
    if user_input[CONF_ZONE_NEAR] == user_input[CONF_ZONE_FAR]:
        errors["base"] = "same_zone_assignment"
    return errors


# ---------------------------------------------------------------------------
# Config flow (prima configurazione)
# ---------------------------------------------------------------------------

class BeaconWasteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisce il config flow UI per la prima configurazione dell'integrazione."""

    VERSION = 1

    def __init__(self) -> None:
        """Inizializza le variabili di stato del flow multi-step."""
        self._discovered_beacons: dict[str, dict[str, str]] = {}
        self._selected_macs: list[str] = []
        self._global_config: dict[str, Any] = {}
        self._bins: list[dict[str, Any]] = []
        self._current_bin: int = 0
        # Dati parziali del secchio corrente (nome + modalità), salvati da step bin
        # prima di passare a bin_calendar o bin_boolean
        self._current_bin_partial: dict[str, Any] = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Registra l'options flow per la riconfigurazione dei parametri globali."""
        return BeaconWasteOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: auto-discovery beacon + parametri globali condivisi.

        Mostra:
        - Multi-select con tutti i beacon trovati (Nome + MAC)
        - Soglie RSSI (min/max), assegnazione zone, debounce
        """
        errors: dict[str, str] = {}
        self._discovered_beacons = _discover_beacons(self.hass)

        if not self._discovered_beacons:
            return self.async_abort(reason="no_beacons_found")

        if user_input is not None:
            selected = user_input.get(CONF_SELECTED_BEACONS, [])
            if not selected:
                errors["base"] = "no_beacons_selected"

            errors.update(_validate_global(user_input))

            if not errors:
                self._selected_macs = selected
                self._global_config = {
                    CONF_RSSI_THRESHOLD_MIN: user_input[CONF_RSSI_THRESHOLD_MIN],
                    CONF_RSSI_THRESHOLD_MAX: user_input[CONF_RSSI_THRESHOLD_MAX],
                    CONF_ZONE_NEAR: user_input[CONF_ZONE_NEAR],
                    CONF_ZONE_FAR: user_input[CONF_ZONE_FAR],
                    CONF_TMON_HOME: user_input[CONF_TMON_HOME],
                    CONF_TMON_PICKUP: user_input[CONF_TMON_PICKUP],
                    CONF_TMON_LOST: user_input[CONF_TMON_LOST],
                }
                self._current_bin = 0
                self._bins = []
                return await self.async_step_bin()

        # Multi-select beacon: etichetta = "Nome (mac)"
        beacon_options = [
            {"value": mac, "label": f"{info['name']} ({mac})"}
            for mac, info in self._discovered_beacons.items()
        ]
        all_macs = list(self._discovered_beacons.keys())

        schema = vol.Schema({
            vol.Required(CONF_SELECTED_BEACONS, default=all_macs): SelectSelector(
                SelectSelectorConfig(
                    options=beacon_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            **_global_schema().schema,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "beacon_count": str(len(self._discovered_beacons)),
            },
        )

    async def async_step_bin(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step A: nome tipologia e scelta modalità prelievo."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._current_bin_partial = {
                CONF_BIN_NAME: user_input[CONF_BIN_NAME],
                CONF_PICKUP_MODE: user_input[CONF_PICKUP_MODE],
            }
            if user_input[CONF_PICKUP_MODE] == PICKUP_MODE_CALENDAR:
                return await self.async_step_bin_calendar()
            return await self.async_step_bin_boolean()

        mac = self._selected_macs[self._current_bin]
        info = self._discovered_beacons[mac]

        schema = vol.Schema({
            vol.Required(CONF_BIN_NAME, default=info["name"]): TextSelector(
                TextSelectorConfig(type="text")
            ),
            vol.Required(CONF_PICKUP_MODE, default=PICKUP_MODE_CALENDAR): SelectSelector(
                SelectSelectorConfig(
                    options=PICKUP_MODE_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })

        return self.async_show_form(
            step_id="bin",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "bin_number": str(self._current_bin + 1),
                "beacon_name": info["name"],
                "beacon_mac": mac,
            },
        )

    async def async_step_bin_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step B1: giorni prelievo (multi-select) + orario esposizione."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # CONF_PICKUP_DAYS è ora direttamente la lista restituita dal multi-select
            pickup_days = user_input.get(CONF_PICKUP_DAYS, [])
            if not pickup_days:
                errors["base"] = "no_pickup_days"

            if not errors:
                mac = self._selected_macs[self._current_bin]
                info = self._discovered_beacons[mac]
                self._bins.append({
                    **self._current_bin_partial,
                    CONF_BEACON_MAC: mac,
                    "entity_prefix": info["prefix"],
                    CONF_PICKUP_DAYS: pickup_days,
                    CONF_PICKUP_TIME_START: user_input[CONF_PICKUP_TIME_START],
                    CONF_PICKUP_BOOLEAN_ENTITY: "",
                })
                self._current_bin += 1
                if self._current_bin < len(self._selected_macs):
                    return await self.async_step_bin()
                return self.async_create_entry(
                    title="Beacon Waste Collection",
                    data={**self._global_config, CONF_BINS: self._bins},
                )

        schema = vol.Schema({
            # Multi-select giorni: restituisce direttamente lista di "mon","tue"...
            # Le label sono gestite da strings.json tramite il campo "options"
            vol.Required(CONF_PICKUP_DAYS, default=[]): SelectSelector(
                SelectSelectorConfig(
                    options=DAY_OPTIONS,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_PICKUP_TIME_START, default="20:00"): TimeSelector(
                TimeSelectorConfig()
            ),
        })

        mac = self._selected_macs[self._current_bin]
        info = self._discovered_beacons[mac]

        return self.async_show_form(
            step_id="bin_calendar",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "bin_number": str(self._current_bin + 1),
                "beacon_name": info["name"],
                "beacon_mac": mac,
            },
        )

    async def async_step_bin_boolean(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step B2: selezione entità booleana esterna."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_PICKUP_BOOLEAN_ENTITY):
                errors["base"] = "no_boolean_entity"

            if not errors:
                mac = self._selected_macs[self._current_bin]
                info = self._discovered_beacons[mac]
                self._bins.append({
                    **self._current_bin_partial,
                    CONF_BEACON_MAC: mac,
                    "entity_prefix": info["prefix"],
                    CONF_PICKUP_DAYS: [],
                    CONF_PICKUP_TIME_START: "20:00",
                    CONF_PICKUP_BOOLEAN_ENTITY: user_input[CONF_PICKUP_BOOLEAN_ENTITY],
                })
                self._current_bin += 1
                if self._current_bin < len(self._selected_macs):
                    return await self.async_step_bin()
                return self.async_create_entry(
                    title="Beacon Waste Collection",
                    data={**self._global_config, CONF_BINS: self._bins},
                )

        schema = vol.Schema({
            vol.Required(CONF_PICKUP_BOOLEAN_ENTITY): EntitySelector(
                EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
            ),
        })

        mac = self._selected_macs[self._current_bin]
        info = self._discovered_beacons[mac]

        return self.async_show_form(
            step_id="bin_boolean",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "bin_number": str(self._current_bin + 1),
                "beacon_name": info["name"],
                "beacon_mac": mac,
            },
        )


# ---------------------------------------------------------------------------
# Options flow (riconfigurazione soglie e zone)
# ---------------------------------------------------------------------------

class BeaconWasteOptionsFlow(config_entries.OptionsFlow):
    """Permette di riconfigurare i parametri globali senza reinstallare.

    Accessibile da: Impostazioni → Dispositivi e servizi → [integrazione] → Configura.
    Modifica solo soglie RSSI, zone e debounce; i secchi rimangono invariati.
    Al salvataggio, l'integrazione viene ricaricata automaticamente da HA.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Inizializza con i valori correnti dalla config entry."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Unico step dell'options flow: modifica parametri globali."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_global(user_input)
            if not errors:
                # Salva le opzioni; HA ricarica automaticamente l'integrazione
                return self.async_create_entry(title="", data=user_input)

        # Pre-popola con i valori correnti (da options se già modificati, altrimenti da data)
        current = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_global_schema(current),
            errors=errors,
        )
