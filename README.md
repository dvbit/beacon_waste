# Beacon Waste Collection

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/your-username/beacon_waste?style=for-the-badge)](https://github.com/your-username/beacon_waste/releases)
[![License](https://img.shields.io/github/license/your-username/beacon_waste?style=for-the-badge)](LICENSE)

---

## 🇬🇧 English

A custom Home Assistant integration for smart waste bin management using BLE beacons.

Each waste bin has a beacon attached to it that exposes RSSI, vibration, temperature, humidity sensors and a physical button. The integration uses this data to automatically determine each bin's location and operational state.

![Beacon Waste Collection Overview](images/overview.png)

---

### Features

- **Auto-discovery**: automatically detects all ESPHome beacons present in Home Assistant by scanning entity patterns.
- **Zone tracking**: determines whether a bin is in the Home zone, Pickup zone, or Lost, based on RSSI signal strength with configurable anti-flapping debounce.
- **State machine**: automatically manages the Empty, In Use, Awaiting Pickup and Exposable states.
- **Immission counter**: tracks how many times a bin is used between emptying cycles.
- **Automatic exposure window**: calculates when a bin should be put out, starting the evening before the pickup day.
- **Button reset**: the physical button on the beacon resets the bin state after emptying.
- **Generic RSSI thresholds**: the BLE proxy antenna may be closer to the home or pickup zone; the zone-to-signal mapping is fully configurable.
- **Multilingual**: Italian, English, Spanish, French, German.

---

### Requirements

- **Home Assistant** 2024.1.0 or later
- **BLE beacon** with ESPHome firmware exposing the following entities per beacon (where `XXXXXXXXXXXX` is the MAC address without `:`):

| Type | Entity ID pattern | Description |
|------|-------------------|-------------|
| `sensor` | `sensor.*_XXXXXXXXXXXX_rssi` | RSSI signal strength |
| `sensor` | `sensor.*_XXXXXXXXXXXX_name` | Beacon assigned name |
| `sensor` | `sensor.*_XXXXXXXXXXXX_temperature` | Temperature |
| `sensor` | `sensor.*_XXXXXXXXXXXX_humidity` | Humidity |
| `binary_sensor` | `binary_sensor.*_XXXXXXXXXXXX_vibration` | Vibration sensor |
| `binary_sensor` | `binary_sensor.*_XXXXXXXXXXXX_button` | Physical button |

---

### Installation

#### HACS (recommended)

1. Open HACS in Home Assistant.
2. Click the **⋮** menu in the top right → **Custom repositories**.
3. Add the repository URL: `https://github.com/your-username/beacon_waste`
4. Select type: **Integration**.
5. Search for **Beacon Waste Collection** and install it.
6. Restart Home Assistant.

#### Manual

1. Download the latest release from GitHub.
2. Copy the `custom_components/beacon_waste/` folder to the `config/custom_components/` directory of Home Assistant.
3. Restart Home Assistant.

---

### Configuration

After installation, add the integration from the UI:

**Settings → Devices & Services → Add Integration → Beacon Waste Collection**

#### Step 1: Beacon selection and global settings

The integration automatically scans all entities and displays discovered beacons in the format **Name (MAC address)**. You can select which ones to monitor.

On the same screen, configure:

| Parameter | Description | Example |
|-----------|-------------|---------|
| **RSSI threshold min** | Above this value → "near" zone | `-50 dBm` |
| **RSSI threshold max** | Below this value → lost | `-80 dBm` |
| **Strong signal zone** | Zone to assign for strong signal | `Home` or `Pickup` |
| **Medium signal zone** | Zone to assign for medium signal | `Pickup` or `Home` |
| **Home debounce** | Seconds before confirming Home zone | `60` |
| **Pickup debounce** | Seconds before confirming Pickup zone | `60` |
| **Lost debounce** | Seconds before confirming Lost state | `120` |

> **Zone assignment note**: the signal→zone mapping is configurable because the BLE proxy antenna may be physically closer to either the home or the pickup area. Swap the assignments if you move the antenna.

#### Step 2..N: Per-bin configuration

For each selected beacon:

| Parameter | Description |
|-----------|-------------|
| **Waste type name** | E.g. "Paper", "Plastic", "Organic" (pre-filled from beacon) |
| **Pickup scheduling mode** | Choose between **Calendar** or **Boolean entity** |

**Calendar mode** — schedule by day of week and time:

| Parameter | Description |
|-----------|-------------|
| **Pickup days** | Checkbox for each day of the week (Mon–Sun) |
| **Exposure start time** | Time from which the bin can be put out the **evening before** pickup day (e.g. `20:00`) |

The exposure window opens at the configured time on the evening before a pickup day, and lasts until midnight of the pickup day itself.

**Boolean entity mode** — delegate to an external entity:

| Parameter | Description |
|-----------|-------------|
| **Pickup boolean entity** | Select any `binary_sensor` or `input_boolean` — when `on`, the bin is exposable |

This mode lets you integrate any external logic: custom calendars, non-weekly schedules, the [garbage_collection](https://github.com/bruxy70/Garbage-Collection) integration, or automations with arbitrary rules.

---

### Created entities

For each bin, a **device** named `Secchio {Name}` is created with the following entities:

#### Select

| Entity | Description | Values |
|--------|-------------|--------|
| `select.secchio_{name}_zona` | Current bin zone | `casa`, `prelievo`, `non_definita` |

#### Binary Sensor

| Entity | Description |
|--------|-------------|
| `binary_sensor.secchio_{name}_vuoto` | `on` = bin is empty |
| `binary_sensor.secchio_{name}_in_uso` | `on` = bin is being filled |
| `binary_sensor.secchio_{name}_in_attesa_prelievo` | `on` = bin is out, awaiting collection |
| `binary_sensor.secchio_{name}_esponibile` | `on` = bin can be put out (not empty + within time window) |

#### Sensor

| Entity | Description |
|--------|-------------|
| `sensor.secchio_{name}_immissioni` | Usage counter since last emptying |
| `sensor.secchio_{name}_rssi` | Current beacon RSSI value (dBm) |

---

### State logic

#### Zones (RSSI-based with debounce)

The RSSI signal is split into three bands using two configurable thresholds:

```
RSSI ∈ [threshold_min, 0]            → "near" zone  (configurable: home or pickup)
RSSI ∈ [threshold_max, threshold_min) → "far" zone   (configurable: pickup or home)
RSSI < threshold_max                  → lost (undefined)
```

Every zone change requires the signal to remain stable in the new zone for the configured debounce time (tmon) before being confirmed. This prevents spurious state changes caused by vibrations or momentary movements.

#### State machine

```
                 ┌──────────────────────────────┐
                 │                              │
    ┌────────────▼──────────┐    vibration      │
    │        EMPTY          │──────────────┐    │
    │  (home zone,          │              │    │
    │   counter = 0)        │              ▼    │
    └───────────────────────┘    ┌─────────────────┐
                 ▲               │    IN USE        │
                 │               │  (home zone,     │
           button /              │   counter++)     │
           collection            └────────┬────────┘
                 │                        │
                 │               moved to pickup zone
                 │                        │
    ┌────────────┴──────────┐             │
    │  AWAITING PICKUP      │◄────────────┘
    │  (pickup zone)        │
    │                       │──── vibration ──→ EMPTY
    └───────────────────────┘
```

**Exposable** is an independent state calculated as:
- `not empty` **AND** `within the exposure time window`

The exposure window starts the evening before the pickup day (from the configured time) and lasts until the end of the pickup day.

#### Detailed transitions

| Event | Condition | Effect |
|-------|-----------|--------|
| Zone → Home | Not awaiting pickup | Empty = true, counter = 0 |
| Zone → Pickup | Not empty | Awaiting = true, In use = false |
| Vibration | Home zone, empty | Empty = false, In use = true, counter + 1 |
| Vibration | Home zone, in use | Counter + 1 |
| Vibration | Pickup zone, awaiting | Awaiting = false, Empty = true, In use = false, counter = 0 |
| Button | Any | Empty = true, In use = true, Awaiting = false, counter = 0 |

---

### Automation examples

Notify when a bin is ready to be put out:

```yaml
automation:
  - alias: "Notify bin ready for pickup"
    trigger:
      - platform: state
        entity_id: binary_sensor.secchio_carta_esponibile
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Waste collection"
          message: "The paper bin can be put out for tomorrow's collection."
```

Alert if a bin goes missing:

```yaml
automation:
  - alias: "Missing bin alert"
    trigger:
      - platform: state
        entity_id: select.secchio_carta_zona
        to: "non_definita"
        for:
          minutes: 30
    action:
      - service: notify.mobile_app
        data:
          title: "Warning"
          message: "The paper bin has been undetected for 30 minutes!"
```

---

### Troubleshooting

| Problem | Solution |
|---------|----------|
| No beacons found | Verify ESPHome sensors are active and follow the pattern `sensor.*_XXXXXXXXXXXX_rssi` |
| Zone changes too often | Increase debounce values (tmon) |
| Zones assigned backwards | Swap "strong signal zone" and "medium signal zone" in the configuration |
| Exposable never triggers | Verify the bin is not empty and that pickup days/time are correctly set |
| States not updating | Check HA logs: `Logger: custom_components.beacon_waste` |

To enable debug logging:

```yaml
logger:
  logs:
    custom_components.beacon_waste: debug
```

---

### Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss the proposal.

### License

This project is distributed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🇮🇹 Italiano

Integrazione custom per Home Assistant che gestisce il conferimento della spazzatura tramite beacon BLE (Bluetooth Low Energy).

Ogni secchio della spazzatura ha un beacon incollato sopra che espone sensori di RSSI, vibrazione, temperatura, umidità e un pulsante. L'integrazione usa questi dati per determinare automaticamente la posizione dei secchi e il loro stato operativo.

---

### Funzionalità

- **Auto-discovery dei beacon**: rileva automaticamente tutti i beacon ESPHome presenti in Home Assistant tramite il pattern delle entità.
- **Tracciamento zona**: determina se il secchio è in zona Casa, zona Prelievo o Disperso, in base al segnale RSSI con debounce anti-flapping configurabile.
- **Macchina a stati**: gestisce automaticamente gli stati Vuoto, In Uso, In Attesa Prelievo, Esponibile.
- **Contatore immissioni**: conta quante volte viene usato il secchio tra uno svuotamento e l'altro.
- **Esposizione automatica**: calcola quando il secchio può essere esposto la sera prima del giorno di prelievo.
- **Reset con pulsante**: il pulsante sul beacon reinizializza lo stato dopo lo svuotamento.
- **Soglie RSSI generiche**: l'antenna proxy può trovarsi più vicina alla zona casa o a quella di prelievo; la mappatura zona-segnale è configurabile.
- **Multilingua**: italiano, inglese, spagnolo, francese, tedesco.

---

### Requisiti

- **Home Assistant** 2024.1.0 o successivo
- **Beacon BLE** con firmware ESPHome che espone i seguenti sensori per ogni beacon (dove `XXXXXXXXXXXX` è il MAC address senza `:`):

| Tipo | Pattern Entity ID | Descrizione |
|------|-------------------|-------------|
| `sensor` | `sensor.*_XXXXXXXXXXXX_rssi` | Intensità segnale RSSI |
| `sensor` | `sensor.*_XXXXXXXXXXXX_name` | Nome assegnato al beacon |
| `sensor` | `sensor.*_XXXXXXXXXXXX_temperature` | Temperatura |
| `sensor` | `sensor.*_XXXXXXXXXXXX_humidity` | Umidità |
| `binary_sensor` | `binary_sensor.*_XXXXXXXXXXXX_vibration` | Sensore vibrazione |
| `binary_sensor` | `binary_sensor.*_XXXXXXXXXXXX_button` | Pulsante fisico |

---

### Installazione

#### HACS (consigliato)

1. Apri HACS in Home Assistant.
2. Clicca sul menu **⋮** in alto a destra → **Repository personalizzati**.
3. Aggiungi l'URL del repository: `https://github.com/your-username/beacon_waste`
4. Seleziona tipo: **Integrazione**.
5. Cerca **Beacon Waste Collection** e installala.
6. Riavvia Home Assistant.

#### Manuale

1. Scarica l'ultima release da GitHub.
2. Copia la cartella `custom_components/beacon_waste/` nella directory `config/custom_components/` di Home Assistant.
3. Riavvia Home Assistant.

---

### Configurazione

Dopo l'installazione, aggiungi l'integrazione dalla UI:

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Beacon Waste Collection**

#### Step 1: Selezione beacon e parametri globali

L'integrazione scansiona automaticamente tutte le entità e mostra i beacon trovati con il formato **Nome (MAC address)**. Per ciascuno puoi decidere se monitorarlo.

Nella stessa schermata configura:

| Parametro | Descrizione | Esempio |
|-----------|-------------|---------|
| **Soglia RSSI minima** | Sopra questo valore → zona "vicina" | `-50 dBm` |
| **Soglia RSSI massima** | Sotto questo valore → disperso | `-80 dBm` |
| **Zona segnale forte** | Quale zona assegnare al segnale forte | `Casa` o `Prelievo` |
| **Zona segnale medio** | Quale zona assegnare al segnale medio | `Prelievo` o `Casa` |
| **Debounce Casa** | Secondi prima di confermare zona Casa | `60` |
| **Debounce Prelievo** | Secondi prima di confermare zona Prelievo | `60` |
| **Debounce Non Definita** | Secondi prima di confermare disperso | `120` |

> **Nota sulle zone**: la mappatura segnale→zona è configurabile perché l'antenna del proxy BLE può trovarsi più vicina alla zona casa o a quella di prelievo. Scambia le assegnazioni se cambi posizione all'antenna.

#### Step 2..N: Configurazione per ogni secchio

Per ogni beacon selezionato:

| Parametro | Descrizione |
|-----------|-------------|
| **Nome tipologia** | Es. "Carta", "Plastica", "Umido" (preletto dal beacon) |
| **Modalità schedulazione prelievo** | Scegli tra **Calendario** o **Entità booleana** |

**Modalità Calendario** — schedulazione per giorno della settimana e orario:

| Parametro | Descrizione |
|-----------|-------------|
| **Giorni di prelievo** | Checkbox per ogni giorno della settimana (Lun–Dom) |
| **Orario inizio esposizione** | Ora dalla quale il secchio può essere esposto la sera **prima** del giorno di prelievo (es. `20:00`) |

La finestra di esposizione si apre all'orario configurato la sera prima del giorno di prelievo e dura fino a mezzanotte del giorno di prelievo stesso.

**Modalità Entità Booleana** — delega a un'entità esterna:

| Parametro | Descrizione |
|-----------|-------------|
| **Entità booleana prelievo** | Seleziona un `binary_sensor` o `input_boolean` qualsiasi — quando è `on`, il secchio è esponibile |

Questa modalità permette di integrare qualsiasi logica esterna: calendari custom, periodicità non settimanale, l'integrazione [garbage_collection](https://github.com/bruxy70/Garbage-Collection), o automazioni con regole arbitrarie.

---

### Entità create

Per ogni secchio viene creato un **dispositivo** `Secchio {Nome}` con le seguenti entità:

#### Select

| Entità | Descrizione | Valori |
|--------|-------------|--------|
| `select.secchio_{nome}_zona` | Zona corrente del secchio | `casa`, `prelievo`, `non_definita` |

#### Binary Sensor

| Entità | Descrizione |
|--------|-------------|
| `binary_sensor.secchio_{nome}_vuoto` | `on` = secchio vuoto |
| `binary_sensor.secchio_{nome}_in_uso` | `on` = secchio in fase di caricamento |
| `binary_sensor.secchio_{nome}_in_attesa_prelievo` | `on` = secchio esposto, in attesa del ritiro |
| `binary_sensor.secchio_{nome}_esponibile` | `on` = il secchio può essere esposto (non vuoto + nella finestra temporale) |

#### Sensor

| Entità | Descrizione |
|--------|-------------|
| `sensor.secchio_{nome}_immissioni` | Contatore utilizzi dall'ultimo svuotamento |
| `sensor.secchio_{nome}_rssi` | Valore RSSI corrente del beacon (dBm) |

---

### Logica degli stati

#### Zone (basate su RSSI con debounce)

Il segnale RSSI viene suddiviso in tre fasce tramite due soglie configurabili:

```
RSSI ∈ [soglia_min, 0]          → zona "vicina" (configurabile: casa o prelievo)
RSSI ∈ [soglia_max, soglia_min) → zona "lontana" (configurabile: prelievo o casa)
RSSI < soglia_max               → disperso (non definita)
```

Ogni cambio zona richiede che il segnale resti stabile per il tempo di debounce configurato (tmon) prima di essere confermato. Questo previene cambi di stato causati da vibrazioni o spostamenti momentanei.

#### Macchina a stati

```
                 ┌──────────────────────────────┐
                 │                              │
    ┌────────────▼──────────┐    vibrazione     │
    │       VUOTO           │──────────────┐    │
    │  (zona casa,          │              │    │
    │   contatore = 0)      │              ▼    │
    └───────────────────────┘    ┌─────────────────┐
                 ▲               │    IN USO        │
                 │               │  (zona casa,     │
          pulsante /             │   contatore++)   │
          prelievo               └────────┬────────┘
                 │                        │
                 │               spostamento in
                 │               zona prelievo
                 │                        │
    ┌────────────┴──────────┐             │
    │  IN ATTESA PRELIEVO   │◄────────────┘
    │  (zona prelievo)      │
    │                       │──── vibrazione ──→ VUOTO
    └───────────────────────┘
```

**Esponibile** è uno stato indipendente calcolato come:
- `non vuoto` **E** `dentro la finestra di esposizione`

La finestra di esposizione inizia la sera prima del giorno di prelievo (dall'orario configurato) e dura fino alla fine del giorno di prelievo.

#### Transizioni dettagliate

| Evento | Condizione | Effetto |
|--------|-----------|---------|
| Zona → Casa | Non in attesa prelievo | Vuoto = true, contatore = 0 |
| Zona → Prelievo | Non vuoto | In attesa = true, In uso = false |
| Vibrazione | Zona casa, vuoto | Vuoto = false, In uso = true, contatore + 1 |
| Vibrazione | Zona casa, in uso | Contatore + 1 |
| Vibrazione | Zona prelievo, in attesa | In attesa = false, Vuoto = true, In uso = false, contatore = 0 |
| Pulsante | Qualsiasi | Vuoto = true, In uso = true, In attesa = false, contatore = 0 |

---

### Esempio di automazione

Notifica quando un secchio è esponibile:

```yaml
automation:
  - alias: "Notifica secchio da esporre"
    trigger:
      - platform: state
        entity_id: binary_sensor.secchio_carta_esponibile
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Spazzatura"
          message: "Il secchio della carta può essere esposto per il prelievo di domani."
```

Notifica se un secchio risulta disperso:

```yaml
automation:
  - alias: "Allarme secchio disperso"
    trigger:
      - platform: state
        entity_id: select.secchio_carta_zona
        to: "non_definita"
        for:
          minutes: 30
    action:
      - service: notify.mobile_app
        data:
          title: "Attenzione"
          message: "Il secchio della carta risulta disperso da 30 minuti!"
```

---

### Risoluzione problemi

| Problema | Soluzione |
|----------|----------|
| Nessun beacon trovato | Verifica che i sensori ESPHome siano attivi e seguano il pattern `sensor.*_XXXXXXXXXXXX_rssi` |
| Cambio zona troppo frequente | Aumenta i valori di debounce (tmon) |
| Zona assegnata al contrario | Scambia le assegnazioni "zona segnale forte" e "zona segnale medio" nella configurazione |
| Esponibile non si attiva | Verifica che il secchio non sia vuoto e che i giorni/orario di prelievo siano corretti |
| Stati non si aggiornano | Controlla nei log di HA: `Logger: custom_components.beacon_waste` |

Per abilitare i log di debug:

```yaml
logger:
  logs:
    custom_components.beacon_waste: debug
```

---

### Contribuire

Le Pull Request sono benvenute. Per modifiche importanti, apri prima una issue per discutere la proposta.

### Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.