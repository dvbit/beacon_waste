# Beacon Waste Collection

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/your-username/beacon_waste?style=for-the-badge)](https://github.com/your-username/beacon_waste/releases)
[![License](https://img.shields.io/github/license/your-username/beacon_waste?style=for-the-badge)](LICENSE)

Integrazione custom per Home Assistant che gestisce il conferimento della spazzatura tramite beacon BLE (Bluetooth Low Energy).

Ogni secchio della spazzatura ha un beacon incollato sopra che espone sensori di RSSI, vibrazione, temperatura, umidità e un pulsante. L'integrazione usa questi dati per determinare automaticamente la posizione dei secchi e il loro stato operativo.

Per i Beacon e il relativo gateway vedere la sottodirectory ESPHOME ed il readme

![Beacon Waste Collection Overview](images/overview.png)

---

## Funzionalità

- **Auto-discovery dei beacon**: rileva automaticamente tutti i beacon ESPHome presenti in Home Assistant tramite il pattern delle entità.
- **Tracciamento zona**: determina se il secchio è in zona Casa, zona Prelievo o Disperso, in base al segnale RSSI con debounce anti-flapping configurabile.
- **Macchina a stati**: gestisce automaticamente gli stati Vuoto, In Uso, In Attesa Prelievo, Esponibile.
- **Contatore immissioni**: conta quante volte viene usato il secchio tra uno svuotamento e l'altro.
- **Esposizione automatica**: calcola quando il secchio può essere esposto la sera prima del giorno di prelievo.
- **Reset con pulsante**: il pulsante sul beacon reinizializza lo stato dopo lo svuotamento.
- **Soglie RSSI generiche**: l'antenna proxy può trovarsi più vicina alla zona casa o a quella di prelievo; la mappatura zona-segnale è configurabile.
- **Multilingua**: italiano, inglese, spagnolo, francese, tedesco.

---

## Requisiti

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

## Installazione

### HACS (consigliato)

1. Apri HACS in Home Assistant.
2. Clicca sul menu **⋮** in alto a destra → **Repository personalizzati**.
3. Aggiungi l'URL del repository: `https://github.com/your-username/beacon_waste`
4. Seleziona tipo: **Integrazione**.
5. Cerca **Beacon Waste Collection** e installala.
6. Riavvia Home Assistant.

### Manuale

1. Scarica l'ultima release da GitHub.
2. Copia la cartella `custom_components/beacon_waste/` nella directory `config/custom_components/` di Home Assistant.
3. Riavvia Home Assistant.

---

## Configurazione

Dopo l'installazione, aggiungi l'integrazione dalla UI:

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Beacon Waste Collection**

### Step 1: Selezione beacon e parametri globali

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

### Step 2..N: Configurazione per ogni secchio

Per ogni beacon selezionato:

| Parametro | Descrizione |
|-----------|-------------|
| **Nome tipologia** | Es. "Carta", "Plastica", "Umido" (preletto dal beacon) |
| **Giorni di prelievo** | Checkbox per ogni giorno della settimana |
| **Orario inizio esposizione** | Ora dalla quale il secchio può essere esposto la sera **prima** del giorno di prelievo |

---

## Entità create

Per ogni secchio viene creato un **dispositivo** `Secchio {Nome}` con le seguenti entità:

### Select

| Entità | Descrizione | Valori |
|--------|-------------|--------|
| `select.secchio_{nome}_zona` | Zona corrente del secchio | `casa`, `prelievo`, `non_definita` |

### Binary Sensor

| Entità | Descrizione |
|--------|-------------|
| `binary_sensor.secchio_{nome}_vuoto` | `on` = secchio vuoto |
| `binary_sensor.secchio_{nome}_in_uso` | `on` = secchio in fase di caricamento |
| `binary_sensor.secchio_{nome}_in_attesa_prelievo` | `on` = secchio esposto, in attesa del ritiro |
| `binary_sensor.secchio_{nome}_esponibile` | `on` = il secchio può essere esposto (non vuoto + nella finestra temporale) |

### Sensor

| Entità | Descrizione |
|--------|-------------|
| `sensor.secchio_{nome}_immissioni` | Contatore utilizzi dall'ultimo svuotamento |

---

## Logica degli stati

### Zone (basate su RSSI con debounce)

Il segnale RSSI viene suddiviso in tre fasce tramite due soglie configurabili:

```
RSSI ∈ [soglia_min, 0]          → zona "vicina" (configurabile: casa o prelievo)
RSSI ∈ [soglia_max, soglia_min) → zona "lontana" (configurabile: prelievo o casa)
RSSI < soglia_max               → disperso (non definita)
```

Ogni cambio zona richiede che il segnale resti stabile per il tempo di debounce configurato (tmon) prima di essere confermato. Questo previene cambi di stato causati da vibrazioni o spostamenti momentanei.

### Macchina a stati

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

### Transizioni dettagliate

| Evento | Condizione | Effetto |
|--------|-----------|---------|
| Zona → Casa | Non in attesa prelievo | Vuoto = true, contatore = 0 |
| Zona → Prelievo | Non vuoto | In attesa = true, In uso = false |
| Vibrazione | Zona casa, vuoto | Vuoto = false, In uso = true, contatore + 1 |
| Vibrazione | Zona casa, in uso | Contatore + 1 |
| Vibrazione | Zona prelievo, in attesa | In attesa = false, Vuoto = true, In uso = false, contatore = 0 |
| Pulsante | Qualsiasi | Vuoto = true, In uso = true, In attesa = false, contatore = 0 |

---

## Esempio di automazione

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

## Risoluzione problemi

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

## Contribuire

Le Pull Request sono benvenute. Per modifiche importanti, apri prima una issue per discutere la proposta.

## Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.
