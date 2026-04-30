"""
Piattaforma Button per Beacon Waste Collection.

Crea un pulsante per ogni secchio che esegue il reset dello stato,
equivalente alla pressione del pulsante fisico sul beacon o alla
chiamata del servizio beacon_waste.reset_bin.

Con has_entity_name=True il nome finale in HA sarà:
"Secchio Carta Reset" (device_name + entity_name)
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import BinCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un pulsante reset per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BinResetButton(coordinator, entry) for coordinator in coordinators
    )


class BinResetButton(ButtonEntity):
    """Pulsante che resetta lo stato del secchio dopo lo svuotamento.

    Premere questo pulsante equivale a:
    - Premere il pulsante fisico sul beacon
    - Chiamare il servizio beacon_waste.reset_bin

    Utile per resettare lo stato manualmente dalla dashboard HA quando
    il pulsante fisico non è stato premuto o il segnale non è arrivato.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:delete-restore"

    def __init__(
        self, coordinator: BinCoordinator, entry: ConfigEntry
    ) -> None:
        """Inizializza il pulsante reset."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_reset"

    @property
    def name(self) -> str:
        """Nome dell'entità (solo suffisso, device name è preposto da HA)."""
        return "Reset"

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

    async def async_press(self) -> None:
        """Esegui il reset dello stato del secchio."""
        self._coordinator.reset_state()
