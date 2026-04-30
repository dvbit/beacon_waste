"""
Config flow per Beacon Waste Collection.

Gestisce la configurazione dell'integrazione tramite UI in due fasi:

Step 1 (async_step_user):
    - Auto-discovery: scansiona tutte le entità sensor.*_XXXXXXXXXXXX_rssi
      per trovare i beacon ESPHome presenti in HA.
    - Mostra un multi-select con i beacon trovati nel formato "Nome (MAC)".
    - Raccoglie i parametri globali: soglie RSSI, mappatura zone, debounce.

Step 2..N (async_step_bin):
    - Per ogni beacon selezionato chiede: nome tipologia spazzatura,
      giorni di prelievo (checkbox L-D), orario inizio esposizione.
    - Il nome è preletto dal sensore _name del beacon.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
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
    BooleanSelector,
)

from .const import (
    DOMAIN,
    CONF_BINS,
    CONF_BIN_NAME,
    CONF_BEACON_MAC,
    CONF_PICKUP_DAYS,
    CONF_PICKUP_TIME_START,
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

# Pattern regex per individuare le entità RSSI dei beacon ESPHome.
# Cattura due gruppi:
#   gruppo 1: prefisso (es. "ble_proxy" in "sensor.ble_proxy_aabbccddeeff_rssi")
#   gruppo 2: MAC address a 12 caratteri hex (es. "aabbccddeeff")
BEACON_RSSI_PATTERN = re.compile(
    r"^sensor\.(.+)_([0-9a-fA-F]{12})_rssi$"
)

# Opzioni per il selettore di zona nel config flow
ZONE_OPTIONS = [
    {"value": ZONE_HOME, "label": "Casa"},
    {"value": ZONE_PICKUP, "label": "Prelievo"},
]


def _discover_beacons(hass) -> dict[str, dict[str, str]]:
    """Scansiona tutte le entità sensor per trovare beacon ESPHome.

    Cerca entità che matchano il pattern sensor.*_XXXXXXXXXXXX_rssi
    dove XXXXXXXXXXXX è un MAC address BLE a 12 caratteri hex.

    Per ogni beacon trovato, tenta di leggere il nome dal sensore
    corrispondente sensor.*_XXXXXXXXXXXX_name.

    Returns:
        Dict con chiave MAC (lowercase) e valore dict con:
        - prefix: prefisso dell'entity_id (es. "ble_proxy")
        - mac: MAC address lowercase
        - name: nome letto dal sensore _name, oppure il MAC come fallback
    """
    beacons: dict[str, dict[str, str]] = {}
    states = hass.states.async_all("sensor")

    for state in states:
        match = BEACON_RSSI_PATTERN.match(state.entity_id)
        if match:
            prefix = match.group(1)
            mac = match.group(2).lower()

            # Tenta di leggere il nome dal sensore *_name del beacon
            name_entity_id = f"sensor.{prefix}_{mac}_{SUFFIX_NAME}"
            name_state = hass.states.get(name_entity_id)
            beacon_name = (
                name_state.state
                if name_state and name_state.state not in ("unknown", "unavailable", "")
                else mac
            )

            beacons[mac] = {
                "prefix": prefix,
                "mac": mac,
                "name": beacon_name,
            }

    return beacons


class BeaconWasteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisce il config flow UI dell'integrazione."""

    VERSION = 1

    def __init__(self) -> None:
        """Inizializza le variabili di stato del flow multi-step."""
        # Beacon trovati dall'auto-discovery {mac: {prefix, mac, name}}
        self._discovered_beacons: dict[str, dict[str, str]] = {}
        # Lista dei MAC selezionati dall'utente
        self._selected_macs: list[str] = []
        # Configurazione globale (soglie, zone, debounce)
        self._global_config: dict[str, Any] = {}
        # Lista delle configurazioni per-secchio accumulate
        self._bins: list[dict[str, Any]] = []
        # Indice del secchio attualmente in configurazione
        self._current_bin: int = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: auto-discovery dei beacon e configurazione globale.

        Mostra:
        - Multi-select con tutti i beacon trovati (Nome + MAC)
        - Soglie RSSI globali (min e max)
        - Assegnazione zone (quale zona per segnale forte/medio)
        - Tempi di debounce per ogni zona
        """
        errors: dict[str, str] = {}

        # Esegui auto-discovery ad ogni visualizzazione dello step
        # (così rileva beacon aggiunti dopo il primo tentativo)
        self._discovered_beacons = _discover_beacons(self.hass)

        if not self._discovered_beacons:
            return self.async_abort(reason="no_beacons_found")

        if user_input is not None:
            # Raccogli i beacon selezionati dal multi-select
            selected = user_input.get(CONF_SELECTED_BEACONS, [])

            if not selected:
                errors["base"] = "no_beacons_selected"

            # Valida le soglie RSSI: min deve essere > max
            # (min è più vicino a 0, quindi segnale più forte)
            t_min = user_input.get(CONF_RSSI_THRESHOLD_MIN, -50)
            t_max = user_input.get(CONF_RSSI_THRESHOLD_MAX, -80)
            if not (t_min > t_max):
                errors["base"] = "invalid_rssi_thresholds"

            # Le due zone devono essere diverse
            zone_near = user_input.get(CONF_ZONE_NEAR, ZONE_HOME)
            zone_far = user_input.get(CONF_ZONE_FAR, ZONE_PICKUP)
            if zone_near == zone_far:
                errors["base"] = "same_zone_assignment"

            if not errors:
                self._selected_macs = selected
                self._global_config = {
                    CONF_RSSI_THRESHOLD_MIN: t_min,
                    CONF_RSSI_THRESHOLD_MAX: t_max,
                    CONF_ZONE_NEAR: zone_near,
                    CONF_ZONE_FAR: zone_far,
                    CONF_TMON_HOME: user_input[CONF_TMON_HOME],
                    CONF_TMON_PICKUP: user_input[CONF_TMON_PICKUP],
                    CONF_TMON_LOST: user_input[CONF_TMON_LOST],
                }
                self._current_bin = 0
                self._bins = []
                return await self.async_step_bin()

        # Costruisci le opzioni per il multi-select:
        # ogni opzione mostra "NomeBeacon (mac_address)"
        beacon_options = [
            {
                "value": mac,
                "label": f"{info['name']} ({mac})",
            }
            for mac, info in self._discovered_beacons.items()
        ]
        # Pre-seleziona tutti i beacon trovati
        all_macs = list(self._discovered_beacons.keys())

        schema = vol.Schema(
            {
                # Multi-select a lista per scegliere i beacon da monitorare
                vol.Required(
                    CONF_SELECTED_BEACONS, default=all_macs
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=beacon_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                # --- Soglie RSSI globali ---
                vol.Required(
                    CONF_RSSI_THRESHOLD_MIN, default=-50
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-100, max=0, step=1, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="dBm",
                    )
                ),
                vol.Required(
                    CONF_RSSI_THRESHOLD_MAX, default=-80
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=-100, max=0, step=1, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="dBm",
                    )
                ),
                # --- Assegnazione zone ---
                vol.Required(
                    CONF_ZONE_NEAR, default=ZONE_HOME
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ZONE_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_ZONE_FAR, default=ZONE_PICKUP
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=ZONE_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                # --- Tempi di debounce (anti-flapping) ---
                vol.Required(CONF_TMON_HOME, default=60): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(CONF_TMON_PICKUP, default=60): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(CONF_TMON_LOST, default=120): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=3600, step=1, mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )

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
        """Step 2..N: configura ogni beacon selezionato.

        Per ogni beacon chiede:
        - Nome tipologia spazzatura (preletto dal sensore _name)
        - Giorni di prelievo (checkbox per ogni giorno)
        - Orario inizio esposizione (sera prima del prelievo)

        Alla fine dell'ultimo beacon salva la config entry completa.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Raccogli i giorni selezionati dalle checkbox
            pickup_days = []
            for day in DAYS_OF_WEEK:
                if user_input.get(f"day_{day}", False):
                    pickup_days.append(day)

            if not pickup_days:
                errors["base"] = "no_pickup_days"

            if not errors:
                mac = self._selected_macs[self._current_bin]
                info = self._discovered_beacons[mac]

                # Salva la configurazione del secchio corrente
                bin_config = {
                    CONF_BIN_NAME: user_input[CONF_BIN_NAME],
                    CONF_BEACON_MAC: mac,
                    # Il prefisso serve per ricostruire gli entity_id
                    # dei sensori del beacon (es. "ble_proxy")
                    "entity_prefix": info["prefix"],
                    CONF_PICKUP_DAYS: pickup_days,
                    CONF_PICKUP_TIME_START: user_input[CONF_PICKUP_TIME_START],
                }
                self._bins.append(bin_config)
                self._current_bin += 1

                # Se ci sono altri beacon da configurare, ripeti lo step
                if self._current_bin < len(self._selected_macs):
                    return await self.async_step_bin()

                # Tutti configurati: salva la config entry con
                # configurazione globale + lista secchi
                return self.async_create_entry(
                    title="Beacon Waste Collection",
                    data={
                        **self._global_config,
                        CONF_BINS: self._bins,
                    },
                )

        # Prepara il form per il secchio corrente
        mac = self._selected_macs[self._current_bin]
        info = self._discovered_beacons[mac]
        default_name = info["name"]
        bin_num = self._current_bin + 1

        schema = vol.Schema(
            {
                # Nome tipologia, preletto dal sensore _name del beacon
                vol.Required(CONF_BIN_NAME, default=default_name): TextSelector(
                    TextSelectorConfig(type="text")
                ),
                # Checkbox giorni di prelievo (L M M G V S D)
                vol.Optional("day_mon", default=False): BooleanSelector(),
                vol.Optional("day_tue", default=False): BooleanSelector(),
                vol.Optional("day_wed", default=False): BooleanSelector(),
                vol.Optional("day_thu", default=False): BooleanSelector(),
                vol.Optional("day_fri", default=False): BooleanSelector(),
                vol.Optional("day_sat", default=False): BooleanSelector(),
                vol.Optional("day_sun", default=False): BooleanSelector(),
                # Orario esposizione: da quest'ora la sera PRIMA del prelievo
                vol.Required(CONF_PICKUP_TIME_START): TimeSelector(
                    TimeSelectorConfig()
                ),
            }
        )

        return self.async_show_form(
            step_id="bin",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "bin_number": str(bin_num),
                "beacon_name": default_name,
                "beacon_mac": mac,
            },
        )
