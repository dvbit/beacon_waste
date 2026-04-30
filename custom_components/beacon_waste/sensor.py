"""
Piattaforma Sensor per Beacon Waste Collection.

Crea un sensore contatore per ogni secchio che traccia il numero
di immissioni (utilizzi) dall'ultimo svuotamento.

Il contatore:
- Si incrementa ad ogni vibrazione rilevata quando il secchio è in zona casa
- Si resetta a 0 quando il secchio viene svuotato (vuoto → true)
- Si resetta a 0 alla pressione del pulsante

Usa SensorStateClass.TOTAL perché il valore è un contatore cumulativo
che viene resettato periodicamente.

L'entità è raggruppata sotto il dispositivo "Secchio {Nome}".
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import BinCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un sensore contatore immissioni per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities = [
        BinImmissionSensor(coordinator, entry) for coordinator in coordinators
    ]
    async_add_entities(entities)


class BinImmissionSensor(SensorEntity):
    """Sensore contatore che traccia le immissioni nel secchio.

    Con has_entity_name=True, il nome finale in HA sarà:
    "Secchio Carta Immissioni" (device_name + entity_name)
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: BinCoordinator, entry: ConfigEntry
    ) -> None:
        """Inizializza il sensore contatore."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = (
            f"{entry.entry_id}_{coordinator.name}_immissioni"
        )

    @property
    def name(self) -> str:
        """Nome dell'entità (solo suffisso 'Immissioni')."""
        return "Immissioni"

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
    def native_value(self) -> int:
        """Restituisce il conteggio immissioni corrente."""
        return self._coordinator.immission_count

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
