"""
Piattaforma Sensor per Beacon Waste Collection.

Crea due sensori per ogni secchio:

1. Contatore immissioni: traccia il numero di utilizzi dall'ultimo svuotamento.
   - Si incrementa ad ogni vibrazione in zona casa
   - Si resetta a 0 quando il secchio viene svuotato o al reset pulsante
   - Usa SensorStateClass.TOTAL (contatore cumulativo con reset periodico)

2. RSSI: mostra il valore corrente del segnale RSSI del beacon.
   - Permette di monitorare la qualità del segnale direttamente dal device
   - Utile per il debug e la calibrazione delle soglie
   - Usa SensorStateClass.MEASUREMENT (valore istantaneo)
   - Unità di misura: dBm (SensorDeviceClass.SIGNAL_STRENGTH)

Entrambe le entità sono raggruppate sotto il dispositivo "Secchio {Nome}".
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
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
    """Crea i sensori (immissioni + RSSI) per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for coordinator in coordinators:
        entities.append(BinImmissionSensor(coordinator, entry))
        entities.append(BinRssiSensor(coordinator, entry))

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


class BinRssiSensor(SensorEntity):
    """Sensore che mostra il valore RSSI corrente del beacon.

    Espone il segnale RSSI come entità del device del secchio,
    permettendo di monitorare la qualità del segnale BLE e di
    calibrare le soglie direttamente dalla dashboard HA.

    Con has_entity_name=True, il nome finale in HA sarà:
    "Secchio Carta RSSI" (device_name + entity_name)
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_icon = "mdi:signal"

    def __init__(
        self, coordinator: BinCoordinator, entry: ConfigEntry
    ) -> None:
        """Inizializza il sensore RSSI."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = (
            f"{entry.entry_id}_{coordinator.name}_rssi"
        )

    @property
    def name(self) -> str:
        """Nome dell'entità (solo suffisso 'RSSI')."""
        return "RSSI"

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
    def native_value(self) -> float | None:
        """Restituisce l'ultimo valore RSSI letto dal beacon.

        Returns:
            Valore RSSI in dBm, o None se mai ricevuto.
        """
        return self._coordinator.rssi_value

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
