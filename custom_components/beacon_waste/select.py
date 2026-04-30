"""
Piattaforma Select per Beacon Waste Collection.

Crea un'entità select per ogni secchio che mostra la zona corrente:
- "casa": il secchio è in casa (zona di caricamento)
- "prelievo": il secchio è esposto per il ritiro
- "non_definita": il secchio è fuori portata (disperso)

La zona è determinata automaticamente dal segnale RSSI con debounce,
ma può essere sovrascritta manualmente tramite il selettore.

L'entità è raggruppata sotto il dispositivo "Secchio {Nome}".
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, ZONE_HOME, ZONE_PICKUP, ZONE_UNDEFINED
from .coordinator import BinCoordinator

# Valori possibili per il selettore zona
ZONE_OPTIONS = [ZONE_HOME, ZONE_PICKUP, ZONE_UNDEFINED]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un'entità select zona per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities = [
        BinZoneSelect(coordinator, entry) for coordinator in coordinators
    ]
    async_add_entities(entities)


class BinZoneSelect(SelectEntity):
    """Entità select che rappresenta la zona corrente del secchio.

    Con has_entity_name=True, HA compone il nome come:
    "{device_name} {entity_name}" → "Secchio Carta Zona"
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BinCoordinator, entry: ConfigEntry
    ) -> None:
        """Inizializza l'entità select zona."""
        self._coordinator = coordinator
        self._entry = entry
        # Unique ID composto da entry_id + nome secchio + "zona"
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_zona"
        self._attr_translation_key = "zona"
        self._attr_options = ZONE_OPTIONS
        self._attr_current_option = coordinator.zone

    @property
    def name(self) -> str:
        """Nome dell'entità (solo suffisso, il device name è preposto da HA)."""
        return "Zona"

    @property
    def device_info(self) -> DeviceInfo:
        """Informazioni dispositivo per raggruppare le entità del secchio."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._coordinator.name}")},
            name=f"Secchio {self._coordinator.name}",
            manufacturer="Beacon Waste",
            model="Waste Bin Tracker",
        )

    @property
    def current_option(self) -> str:
        """Restituisce la zona corrente dal coordinator."""
        return self._coordinator.zone

    async def async_select_option(self, option: str) -> None:
        """Override manuale della zona (uso eccezionale)."""
        self._coordinator.zone = option
        self.async_write_ha_state()

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
