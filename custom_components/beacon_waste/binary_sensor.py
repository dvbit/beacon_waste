"""
Piattaforma Binary Sensor per Beacon Waste Collection.

Crea 4 binary sensor per ogni secchio, uno per ogni stato funzionale:

- Vuoto: il secchio è stato svuotato e non contiene rifiuti
- In uso: il secchio è in casa e sta venendo riempito
- In attesa prelievo: il secchio è esposto e attende il ritiro
- Esponibile: il secchio può essere portato fuori (non vuoto + orario giusto)

Ogni entità è raggruppata sotto il dispositivo "Secchio {Nome}".
Con has_entity_name=True, i nomi sono solo i suffissi (es. "Vuoto"),
e HA li compone con il device name: "Secchio Carta Vuoto".
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    STATE_EMPTY,
    STATE_IN_USE,
    STATE_AWAITING_PICKUP,
    STATE_EXPOSABLE,
)
from .coordinator import BinCoordinator

# Label leggibili per gli stati, usati come nome entità nella UI
STATE_LABELS = {
    STATE_EMPTY: "Vuoto",
    STATE_IN_USE: "In uso",
    STATE_AWAITING_PICKUP: "In attesa prelievo",
    STATE_EXPOSABLE: "Esponibile",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea i 4 binary sensor per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinStateBinarySensor] = []

    for coordinator in coordinators:
        entities.extend(
            [
                BinStateBinarySensor(
                    coordinator, entry, STATE_EMPTY, "mdi:delete-empty"
                ),
                BinStateBinarySensor(
                    coordinator, entry, STATE_IN_USE, "mdi:delete"
                ),
                BinStateBinarySensor(
                    coordinator, entry, STATE_AWAITING_PICKUP, "mdi:truck"
                ),
                BinStateBinarySensor(
                    coordinator, entry, STATE_EXPOSABLE, "mdi:calendar-check"
                ),
            ]
        )

    async_add_entities(entities)


class BinStateBinarySensor(BinarySensorEntity):
    """Binary sensor per uno stato funzionale del secchio.

    Ogni istanza rappresenta uno dei 4 stati possibili e legge
    il valore booleano corrispondente dal coordinator.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BinCoordinator,
        entry: ConfigEntry,
        state_key: str,
        icon: str,
    ) -> None:
        """Inizializza il binary sensor.

        Args:
            coordinator: coordinator del secchio
            entry: config entry dell'integrazione
            state_key: chiave dello stato (es. STATE_EMPTY)
            icon: icona MDI da mostrare nella UI
        """
        self._coordinator = coordinator
        self._entry = entry
        self._state_key = state_key
        self._attr_unique_id = (
            f"{entry.entry_id}_{coordinator.name}_{state_key}"
        )
        self._attr_icon = icon

    @property
    def name(self) -> str:
        """Nome dell'entità (solo suffisso, es. 'Vuoto', 'Esponibile')."""
        return STATE_LABELS.get(self._state_key, self._state_key)

    @property
    def device_info(self) -> DeviceInfo:
        """Informazioni dispositivo per raggruppare le entità del secchio."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._entry.entry_id}_{self._coordinator.name}")
            },
            name=f"Secchio {self._coordinator.name}",
            manufacturer="Beacon Waste",
            model="Waste Bin Tracker",
        )

    @property
    def is_on(self) -> bool:
        """Legge lo stato booleano dal coordinator in base a state_key."""
        if self._state_key == STATE_EMPTY:
            return self._coordinator.is_empty
        if self._state_key == STATE_IN_USE:
            return self._coordinator.is_in_use
        if self._state_key == STATE_AWAITING_PICKUP:
            return self._coordinator.is_awaiting_pickup
        if self._state_key == STATE_EXPOSABLE:
            return self._coordinator.is_exposable
        return False

    async def async_added_to_hass(self) -> None:
        """Registra il callback per ricevere aggiornamenti dal coordinator."""
        self._coordinator.register_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Rimuovi il callback quando l'entità viene rimossa."""
        self._coordinator.unregister_callback(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        """Aggiorna lo stato dell'entità in HA quando il coordinator notifica."""
        self.async_write_ha_state()
