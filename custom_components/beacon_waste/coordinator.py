"""
Coordinator per Beacon Waste Collection.

Gestisce la macchina a stati di un singolo secchio della spazzatura.
Ogni istanza di BinCoordinator:

1. Ascolta i cambiamenti del sensore RSSI del beacon per determinare
   la zona (casa, prelievo, disperso) con debounce anti-flapping.

2. Ascolta il sensore di vibrazione per rilevare l'uso del secchio
   (immissione rifiuti) o la raccolta da parte dell'operatore.

3. Ascolta il pulsante fisico per il reset dello stato dopo lo svuotamento.

4. Esegue un check periodico (ogni 10s) per:
   - Completare le transizioni di zona dopo il debounce
   - Aggiornare lo stato "esponibile" in base all'orario

Schema delle zone RSSI:
    ┌─────────────────────────────────────────────────┐
    │  RSSI                                            │
    │  ◄── debole (-100)         forte (0) ──►         │
    │                                                  │
    │  [disperso] | [zona lontana] | [zona vicina]     │
    │         soglia_max      soglia_min               │
    └─────────────────────────────────────────────────┘

    zona_vicina e zona_lontana sono mappate a casa/prelievo
    dall'utente in fase di configurazione.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
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
    SUFFIX_RSSI,
    SUFFIX_TEMPERATURE,
    SUFFIX_HUMIDITY,
    SUFFIX_VIBRATION,
    SUFFIX_BUTTON,
    ZONE_HOME,
    ZONE_PICKUP,
    ZONE_UNDEFINED,
)

_LOGGER = logging.getLogger(__name__)

# Mappatura giorno abbreviato -> weekday() di Python (0=lunedì, 6=domenica)
DAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _build_entity_id(prefix: str, mac: str, suffix: str, domain: str) -> str:
    """Costruisce un entity_id dal pattern dei beacon ESPHome.

    Args:
        prefix: prefisso dell'entità (es. "ble_proxy")
        mac: MAC address a 12 caratteri hex (es. "aabbccddeeff")
        suffix: suffisso del sensore (es. "rssi", "vibration")
        domain: dominio HA (es. "sensor", "binary_sensor")

    Returns:
        Entity ID completo, es. "sensor.ble_proxy_aabbccddeeff_rssi"
    """
    return f"{domain}.{prefix}_{mac}_{suffix}"


class BinCoordinator:
    """Macchina a stati per un singolo secchio della spazzatura.

    Gestisce:
    - Zona corrente (casa / prelievo / non_definita) con debounce
    - Stati funzionali (vuoto, in_uso, in_attesa_prelievo, esponibile)
    - Contatore immissioni (quante volte si usa il secchio)

    Le entità HA registrano callback su questo coordinator per
    ricevere notifiche quando lo stato cambia.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        bin_config: dict[str, Any],
        global_config: dict[str, Any],
        entry_id: str,
    ) -> None:
        """Inizializza il coordinator per un secchio.

        Args:
            hass: istanza Home Assistant
            bin_config: configurazione specifica del secchio (nome, MAC, giorni, orario)
            global_config: configurazione globale (soglie, zone, debounce)
            entry_id: ID della config entry (usato per unique_id delle entità)
        """
        self.hass = hass
        self._config = bin_config
        self._global_config = global_config
        self._entry_id = entry_id

        # Dati identificativi del secchio
        self.name: str = bin_config[CONF_BIN_NAME]
        self._mac: str = bin_config[CONF_BEACON_MAC]
        self._prefix: str = bin_config["entity_prefix"]

        # --- Costruzione automatica degli entity_id ---
        # Dal pattern ESPHome: {domain}.{prefix}_{mac}_{suffix}
        self._rssi_entity = _build_entity_id(
            self._prefix, self._mac, SUFFIX_RSSI, "sensor"
        )
        self._temperature_entity = _build_entity_id(
            self._prefix, self._mac, SUFFIX_TEMPERATURE, "sensor"
        )
        self._humidity_entity = _build_entity_id(
            self._prefix, self._mac, SUFFIX_HUMIDITY, "sensor"
        )
        self._vibration_entity = _build_entity_id(
            self._prefix, self._mac, SUFFIX_VIBRATION, "binary_sensor"
        )
        self._button_entity = _build_entity_id(
            self._prefix, self._mac, SUFFIX_BUTTON, "binary_sensor"
        )

        # --- Stato zona ---
        # Zona corrente confermata dopo il debounce
        self.zone: str = ZONE_UNDEFINED
        # Zona candidata in attesa di conferma debounce
        self._pending_zone: str | None = None
        # Timestamp di inizio del debounce per la zona candidata
        self._pending_zone_since: datetime | None = None

        # --- Stati funzionali ---
        self.is_empty: bool = True           # Secchio vuoto
        self.is_in_use: bool = False         # Secchio in fase di riempimento
        self.is_awaiting_pickup: bool = False # Secchio esposto, attende ritiro
        self.is_exposable: bool = False      # Secchio può essere portato fuori

        # Contatore: quante volte il secchio è stato usato dall'ultimo svuotamento
        self.immission_count: int = 0

        # Ultimo valore RSSI letto dal beacon (None se mai ricevuto)
        self.rssi_value: float | None = None

        # --- Callback e listener ---
        # Le entità HA si registrano qui per ricevere notifiche di aggiornamento
        self._update_callbacks: list[callback] = []
        # Riferimenti ai listener per poterli rimuovere in teardown
        self._unsub_listeners: list[Any] = []

        # --- Soglie RSSI (globali, condivise da tutti i secchi) ---
        # threshold_min: più vicino a 0 = segnale forte = beacon vicino
        # threshold_max: più negativo = segnale debole = beacon lontano
        self._threshold_min: float = float(global_config[CONF_RSSI_THRESHOLD_MIN])
        self._threshold_max: float = float(global_config[CONF_RSSI_THRESHOLD_MAX])

        # Mappatura zone: l'utente sceglie quale zona fisica corrisponde
        # al segnale forte (vicino all'antenna) e quale al segnale medio
        self._zone_near: str = global_config[CONF_ZONE_NEAR]
        self._zone_far: str = global_config[CONF_ZONE_FAR]

        # Tempi di debounce in secondi per ogni zona
        self._tmon_home: float = float(global_config[CONF_TMON_HOME])
        self._tmon_pickup: float = float(global_config[CONF_TMON_PICKUP])
        self._tmon_lost: float = float(global_config[CONF_TMON_LOST])

        # --- Schedulazione prelievo (per-secchio) ---
        # Lista dei weekday() in cui avviene il prelievo
        self._pickup_days: list[int] = [
            DAY_MAP[d] for d in bin_config[CONF_PICKUP_DAYS]
        ]
        # Orario HH:MM a partire dal quale il secchio è esponibile
        # (la sera PRIMA del giorno di prelievo)
        self._pickup_time_start: str = bin_config[CONF_PICKUP_TIME_START]

    # --- Proprietà pubbliche per le entità ---

    @property
    def mac(self) -> str:
        """MAC address del beacon."""
        return self._mac

    @property
    def rssi_entity(self) -> str:
        """Entity ID del sensore RSSI."""
        return self._rssi_entity

    @property
    def temperature_entity(self) -> str:
        """Entity ID del sensore temperatura."""
        return self._temperature_entity

    @property
    def humidity_entity(self) -> str:
        """Entity ID del sensore umidità."""
        return self._humidity_entity

    # --- Gestione callback ---

    def register_callback(self, cb: callback) -> None:
        """Registra un callback che verrà chiamato ad ogni cambio di stato."""
        self._update_callbacks.append(cb)

    def unregister_callback(self, cb: callback) -> None:
        """Rimuovi un callback registrato."""
        if cb in self._update_callbacks:
            self._update_callbacks.remove(cb)

    def _notify_update(self) -> None:
        """Notifica tutte le entità registrate che lo stato è cambiato.

        Ogni entità chiamerà async_write_ha_state() per aggiornare HA.
        """
        for cb in self._update_callbacks:
            cb()

    # --- Setup e teardown ---

    async def async_setup(self) -> None:
        """Avvia i listener sui sensori del beacon.

        Registra:
        - Listener su RSSI per il tracciamento zona
        - Listener su vibrazione per rilevare uso e raccolta
        - Listener su pulsante per il reset stato
        - Timer periodico (10s) per debounce e stato esponibile
        """
        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass, [self._rssi_entity], self._handle_rssi_change
            )
        )

        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass, [self._vibration_entity], self._handle_vibration
            )
        )

        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass, [self._button_entity], self._handle_button
            )
        )

        # Check periodico ogni 10 secondi per:
        # 1. Verificare se il debounce zona è completato
        # 2. Aggiornare lo stato "esponibile" in base all'orario
        self._unsub_listeners.append(
            async_track_time_interval(
                self.hass, self._periodic_check, timedelta(seconds=10)
            )
        )

        _LOGGER.debug(
            "BinCoordinator '%s' (MAC: %s) setup complete", self.name, self._mac
        )

    async def async_teardown(self) -> None:
        """Ferma tutti i listener e libera le risorse."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # --- Logica zone RSSI ---

    def _get_rssi_zone(self, rssi: float) -> str:
        """Determina la zona dal valore RSSI.

        Fasce di segnale (threshold_min > threshold_max, entrambi negativi):
        - [threshold_min, 0]           → zone_near (segnale forte, vicino)
        - [threshold_max, threshold_min) → zone_far  (segnale medio, lontano)
        - sotto threshold_max           → ZONE_UNDEFINED (disperso)

        Args:
            rssi: valore RSSI in dBm (negativo, più vicino a 0 = più forte)

        Returns:
            Nome della zona: casa, prelievo, o non_definita
        """
        if rssi >= self._threshold_min:
            return self._zone_near
        if rssi >= self._threshold_max:
            return self._zone_far
        return ZONE_UNDEFINED

    def _get_tmon_for_zone(self, zone: str) -> float:
        """Restituisce il tempo di debounce in secondi per una data zona."""
        if zone == ZONE_HOME:
            return self._tmon_home
        if zone == ZONE_PICKUP:
            return self._tmon_pickup
        return self._tmon_lost

    # --- Handler eventi sensori ---

    @callback
    def _handle_rssi_change(self, event: Event) -> None:
        """Gestisce il cambio del sensore RSSI.

        NON cambia la zona immediatamente: avvia un debounce.
        Il cambio effettivo avviene in _periodic_check quando il segnale
        resta stabile nella nuova zona per il tempo tmon configurato.

        Questo previene cambi di stato dovuti a:
        - Fluttuazioni momentanee del segnale BLE
        - Vibrazioni durante lo spostamento del secchio
        - Interferenze temporanee
        """
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            rssi = float(new_state.state)
        except (ValueError, TypeError):
            return

        # Aggiorna il valore RSSI corrente e notifica le entità
        self.rssi_value = rssi
        self._notify_update()

        detected_zone = self._get_rssi_zone(rssi)

        if detected_zone != self.zone:
            # Il segnale indica una zona diversa da quella attuale
            if self._pending_zone == detected_zone:
                # Già in debounce per questa zona, attendi il completamento
                return
            # Inizia un nuovo debounce per la zona rilevata
            self._pending_zone = detected_zone
            self._pending_zone_since = dt_util.utcnow()
        else:
            # Il segnale è tornato nella zona attuale: annulla il debounce
            self._pending_zone = None
            self._pending_zone_since = None

    @callback
    def _handle_vibration(self, event: Event) -> None:
        """Gestisce l'evento di vibrazione del secchio.

        Comportamento in base alla zona corrente:

        ZONA CASA:
        - Se il secchio è vuoto: lo segna come "non vuoto" e "in uso"
        - Incrementa sempre il contatore immissioni

        ZONA PRELIEVO:
        - Se il secchio è in attesa di prelievo: lo segna come raccolto
          (vuoto, contatore reset) — la vibrazione indica che l'operatore
          ha svuotato il secchio.

        Reagisce solo alla transizione off→on del binary_sensor.
        """
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        # Reagisci solo alla transizione da off a on
        if new_state.state != "on":
            return
        old_state = event.data.get("old_state")
        if old_state is not None and old_state.state == "on":
            return

        _LOGGER.debug("Vibration detected for bin '%s'", self.name)

        if self.zone == ZONE_HOME:
            # --- Vibrazione in zona casa = uso del secchio ---
            if self.is_empty:
                # Prima immissione: il secchio non è più vuoto
                self.is_empty = False
                self.is_in_use = True
                _LOGGER.debug("Bin '%s': empty->false, in_use->true", self.name)

            # Conta ogni immissione
            self.immission_count += 1
            _LOGGER.debug(
                "Bin '%s': immission_count=%d", self.name, self.immission_count
            )

        elif self.zone == ZONE_PICKUP:
            # --- Vibrazione in zona prelievo = raccolta operatore ---
            if self.is_awaiting_pickup:
                self.is_awaiting_pickup = False
                self.is_empty = True
                self.is_in_use = False
                self.immission_count = 0
                _LOGGER.debug(
                    "Bin '%s': awaiting_pickup->false, empty->true, "
                    "in_use->false, counter reset (collected)",
                    self.name,
                )

        self._notify_update()

    @callback
    def _handle_button(self, event: Event) -> None:
        """Gestisce la pressione del pulsante fisico sul beacon.

        Il pulsante serve per reinizializzare lo stato del secchio
        dopo che è stato riportato in casa e svuotato manualmente.

        Effetto: vuoto=true, in_uso=true, in_attesa=false, contatore=0
        (pronto per un nuovo ciclo di riempimento)
        """
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        if new_state.state != "on":
            return
        old_state = event.data.get("old_state")
        if old_state is not None and old_state.state == "on":
            return

        _LOGGER.debug("Button pressed for bin '%s' - resetting state", self.name)

        self.is_empty = True
        self.is_in_use = True
        self.is_awaiting_pickup = False
        self.immission_count = 0

        self._notify_update()

    # --- Check periodico ---

    @callback
    def _periodic_check(self, now: datetime) -> None:
        """Check periodico eseguito ogni 10 secondi.

        Due compiti:
        1. Verifica se il debounce zona è completato (il segnale RSSI
           è rimasto stabile nella nuova zona per il tempo tmon).
        2. Aggiorna lo stato "esponibile" in base all'orario corrente
           e al giorno della settimana.
        """
        changed = False

        # --- 1. Debounce zona ---
        if (
            self._pending_zone is not None
            and self._pending_zone_since is not None
        ):
            tmon = self._get_tmon_for_zone(self._pending_zone)
            elapsed = (dt_util.utcnow() - self._pending_zone_since).total_seconds()

            if elapsed >= tmon:
                # Debounce completato: conferma il cambio zona
                old_zone = self.zone
                new_zone = self._pending_zone
                self.zone = new_zone
                self._pending_zone = None
                self._pending_zone_since = None
                changed = True

                _LOGGER.debug(
                    "Bin '%s': zone %s -> %s", self.name, old_zone, new_zone
                )
                # Applica gli effetti collaterali del cambio zona
                self._on_zone_change(old_zone, new_zone)

        # --- 2. Stato esponibile ---
        old_exposable = self.is_exposable
        self.is_exposable = self._check_exposable()
        if self.is_exposable != old_exposable:
            changed = True

        if changed:
            self._notify_update()

    # --- Logica transizioni ---

    def _on_zone_change(self, old_zone: str, new_zone: str) -> None:
        """Gestisce gli effetti collaterali di un cambio zona confermato.

        TRANSIZIONE → CASA:
        Se il secchio arriva in zona casa senza essere in attesa prelievo,
        significa che è stato riportato in casa (probabilmente svuotato).
        → Segna come vuoto e resetta il contatore.

        TRANSIZIONE → PRELIEVO:
        Se il secchio arriva in zona prelievo e non è vuoto,
        significa che è stato portato fuori per il ritiro.
        → Segna come "in attesa prelievo" e disattiva "in uso".
        """
        if new_zone == ZONE_HOME:
            if not self.is_awaiting_pickup:
                self.is_empty = True
                self.immission_count = 0
                _LOGGER.debug(
                    "Bin '%s': zone->home, empty->true, counter reset",
                    self.name,
                )

        elif new_zone == ZONE_PICKUP:
            if not self.is_empty:
                self.is_awaiting_pickup = True
                self.is_in_use = False
                _LOGGER.debug(
                    "Bin '%s': zone->pickup, awaiting_pickup->true, in_use->false",
                    self.name,
                )

    def _check_exposable(self) -> bool:
        """Verifica se il secchio è esponibile.

        Condizioni (entrambe devono essere vere):
        1. Il secchio NON è vuoto (c'è qualcosa da raccogliere)
        2. Siamo nella finestra temporale di esposizione
        """
        if self.is_empty:
            return False
        return self._is_in_pickup_window()

    def _is_in_pickup_window(self) -> bool:
        """Verifica se siamo nella finestra di esposizione.

        L'esposizione inizia la SERA PRIMA del giorno di prelievo
        all'orario configurato, e dura fino alla fine del giorno di prelievo.

        Esempio: prelievo lunedì, orario 20:00
        → esponibile da domenica 20:00 fino a lunedì 23:59

        Questo permette di portare fuori il secchio la sera prima,
        come richiesto dalla maggior parte dei servizi di raccolta.
        """
        now = dt_util.now()

        # Parsing dell'orario di inizio esposizione (HH:MM)
        try:
            start_parts = self._pickup_time_start.split(":")
            exposure_hour = int(start_parts[0])
            exposure_minute = int(start_parts[1])
        except (ValueError, IndexError):
            _LOGGER.error(
                "Invalid time format for bin '%s': %s",
                self.name,
                self._pickup_time_start,
            )
            return False

        # Caso 1: oggi è la sera prima di un giorno di prelievo
        # Controlliamo se DOMANI è giorno di prelievo
        tomorrow = (now.weekday() + 1) % 7
        if tomorrow in self._pickup_days:
            exposure_start = now.replace(
                hour=exposure_hour,
                minute=exposure_minute,
                second=0,
                microsecond=0,
            )
            if now >= exposure_start:
                return True

        # Caso 2: oggi È il giorno di prelievo (tutto il giorno)
        if now.weekday() in self._pickup_days:
            return True

        return False
