"""
Piattaforma Sensor per Beacon Waste Collection.

Crea quattro sensori per ogni secchio:

1. Contatore immissioni (SensorStateClass.TOTAL)
2. RSSI in dBm     (SensorStateClass.MEASUREMENT, SensorDeviceClass.SIGNAL_STRENGTH)
3. Temperatura °C  (SensorStateClass.MEASUREMENT, SensorDeviceClass.TEMPERATURE)
4. Umidità %       (SensorStateClass.MEASUREMENT, SensorDeviceClass.HUMIDITY)

I valori di RSSI, temperatura e umidità vengono:
- Inizializzati in async_added_to_hass leggendo lo stato corrente dell'entità
  ESPHome originale (evita "unavailable" al primo avvio)
- Aggiornati in tempo reale tramite i listener nel coordinator
- Notificati alle entità HA via callback del coordinator

Tutti i sensori sono raggruppati sotto il dispositivo "Secchio {Nome}".
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
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
    """Crea i 4 sensori per ogni secchio configurato."""
    coordinators: list[BinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for coordinator in coordinators:
        entities.append(BinImmissionSensor(coordinator, entry))
        entities.append(BinRssiSensor(coordinator, entry))
        entities.append(BinTemperatureSensor(coordinator, entry))
        entities.append(BinHumiditySensor(coordinator, entry))
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Classe base per i sensori con seed iniziale dal sensore ESPHome originale
# ---------------------------------------------------------------------------

class _BinSensorBase(SensorEntity):
    """Base per sensori che leggono il valore iniziale dall'entità ESPHome.

    Evita che il sensore parta da 'unavailable' aspettando il primo evento:
    al momento dell'aggiunta a HA legge il valore corrente direttamente
    dallo stato dell'entità ESPHome sorgente.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BinCoordinator,
        entry: ConfigEntry,
        source_entity_getter: str,
        value_attr: str,
    ) -> None:
        """Inizializza il sensore base.

        Args:
            coordinator: coordinator del secchio
            entry: config entry
            source_entity_getter: nome della property del coordinator
              che restituisce l'entity_id sorgente (es. "rssi_entity")
            value_attr: nome dell'attributo del coordinator che contiene
              il valore corrente (es. "rssi_value")
        """
        self._coordinator = coordinator
        self._entry = entry
        self._source_entity_getter = source_entity_getter
        self._value_attr = value_attr

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

    async def async_added_to_hass(self) -> None:
        """Registra callback e legge il valore iniziale dall'entità ESPHome."""
        self._coordinator.register_callback(self._handle_update)

        # Seed del valore iniziale: se il coordinator non ha ancora ricevuto
        # un evento per questo sensore, legge lo stato corrente dall'entità
        # ESPHome originale per evitare "unavailable" al primo avvio.
        if getattr(self._coordinator, self._value_attr) is None:
            source_entity_id = getattr(self._coordinator, self._source_entity_getter)
            state = self.hass.states.get(source_entity_id)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    setattr(
                        self._coordinator,
                        self._value_attr,
                        float(state.state),
                    )
                except (ValueError, TypeError):
                    pass

    async def async_will_remove_from_hass(self) -> None:
        """Rimuovi il callback quando l'entità viene rimossa."""
        self._coordinator.unregister_callback(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        """Aggiorna lo stato in HA quando il coordinator notifica."""
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Sensori concreti
# ---------------------------------------------------------------------------

class BinImmissionSensor(SensorEntity):
    """Sensore contatore immissioni (non usa seed iniziale, parte da 0)."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: BinCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_immissioni"

    @property
    def name(self) -> str:
        return "Immissioni"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._coordinator.name}")},
            name=f"Secchio {self._coordinator.name}",
            manufacturer="Beacon Waste",
            model="Waste Bin Tracker",
        )

    @property
    def native_value(self) -> int:
        return self._coordinator.immission_count

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_callback(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class BinRssiSensor(_BinSensorBase):
    """Sensore RSSI del beacon in dBm."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_icon = "mdi:signal"

    def __init__(self, coordinator: BinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "rssi_entity", "rssi_value")
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_rssi"

    @property
    def name(self) -> str:
        return "RSSI"

    @property
    def native_value(self) -> float | None:
        """Valore RSSI corrente in dBm."""
        return self._coordinator.rssi_value


class BinTemperatureSensor(_BinSensorBase):
    """Sensore temperatura ambiente dal beacon."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: BinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "temperature_entity", "temperature_value")
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_temperatura"

    @property
    def name(self) -> str:
        return "Temperatura"

    @property
    def native_value(self) -> float | None:
        """Temperatura corrente in °C."""
        return self._coordinator.temperature_value


class BinHumiditySensor(_BinSensorBase):
    """Sensore umidità ambiente dal beacon."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: BinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "humidity_entity", "humidity_value")
        self._attr_unique_id = f"{entry.entry_id}_{coordinator.name}_umidita"

    @property
    def name(self) -> str:
        return "Umidità"

    @property
    def native_value(self) -> float | None:
        """Umidità corrente in %."""
        return self._coordinator.humidity_value
