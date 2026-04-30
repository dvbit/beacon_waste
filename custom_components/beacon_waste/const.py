"""
Costanti per l'integrazione Beacon Waste Collection.

Questo modulo centralizza tutte le costanti usate dall'integrazione:
- Chiavi di configurazione per il config flow e il data store
- Suffissi per la costruzione automatica degli entity_id dai beacon
- Nomi delle zone e degli stati della macchina a stati
- Giorni della settimana per la schedulazione del prelievo
"""

# Identificativo univoco dell'integrazione in Home Assistant.
# Usato come domain per entità, servizi e storage.
DOMAIN = "beacon_waste"

# Piattaforme entità che l'integrazione registra in HA.
# Ogni piattaforma corrisponde a un file .py nella cartella dell'integrazione.
PLATFORMS = ["select", "binary_sensor", "sensor", "button"]

# --- Chiavi di configurazione ---
# Usate nel config flow per raccogliere e salvare i dati dell'utente.

# Lista dei secchi configurati (ogni elemento è un dict con i parametri del secchio)
CONF_BINS = "bins"
# Nome assegnato dall'utente alla tipologia di spazzatura (es. "Carta", "Plastica")
CONF_BIN_NAME = "bin_name"
# Indirizzo MAC del beacon (12 caratteri hex, senza ':')
CONF_BEACON_MAC = "beacon_mac"
# Lista dei giorni della settimana in cui avviene il prelievo
CONF_PICKUP_DAYS = "pickup_days"
# Orario (HH:MM) a partire dal quale il secchio può essere esposto
# la sera PRIMA del giorno di prelievo
CONF_PICKUP_TIME_START = "pickup_time_start"
# Modalità di schedulazione del prelievo
CONF_PICKUP_MODE = "pickup_mode"
# Entity ID di un binary_sensor/input_boolean esterno che indica se il secchio
# deve essere esposto (usato in modalità PICKUP_MODE_BOOLEAN)
CONF_PICKUP_BOOLEAN_ENTITY = "pickup_boolean_entity"

# Valori per CONF_PICKUP_MODE
PICKUP_MODE_CALENDAR = "calendar"  # Giorni della settimana + orario
PICKUP_MODE_BOOLEAN = "boolean"    # Entità booleana esterna
# Soglia RSSI "vicina": segnale sopra questo valore = zona vicina all'antenna
# Valore negativo in dBm, più vicino a 0 = segnale più forte (es. -50)
CONF_RSSI_THRESHOLD_MIN = "rssi_threshold_min"
# Soglia RSSI "lontana": segnale sotto questo valore = disperso
# Tra le due soglie = zona lontana dall'antenna (es. -80)
CONF_RSSI_THRESHOLD_MAX = "rssi_threshold_max"
# Zona assegnata quando il beacon è vicino all'antenna (segnale forte)
CONF_ZONE_NEAR = "zone_near"
# Zona assegnata quando il beacon è lontano dall'antenna (segnale medio)
CONF_ZONE_FAR = "zone_far"
# Tempo di debounce (secondi) per confermare la transizione a zona Casa
CONF_TMON_HOME = "tmon_home"
# Tempo di debounce (secondi) per confermare la transizione a zona Prelievo
CONF_TMON_PICKUP = "tmon_pickup"
# Tempo di debounce (secondi) per confermare la transizione a zona Disperso
CONF_TMON_LOST = "tmon_lost"
# Lista dei MAC dei beacon selezionati dall'utente nello step 1 del config flow
CONF_SELECTED_BEACONS = "selected_beacons"

# --- Suffissi entità ESPHome ---
# I beacon ESPHome creano entità con un pattern fisso:
#   {domain}.{prefisso}_{mac}_{suffisso}
# Questi suffissi vengono usati per costruire gli entity_id automaticamente.

SUFFIX_RSSI = "rssi"              # sensor: intensità segnale BLE
SUFFIX_NAME = "name"              # sensor: nome assegnato al beacon
SUFFIX_TEMPERATURE = "temperature" # sensor: temperatura ambiente
SUFFIX_HUMIDITY = "humidity"       # sensor: umidità ambiente
SUFFIX_VIBRATION = "vibration"     # binary_sensor: rileva vibrazioni/movimenti
SUFFIX_BUTTON = "button"           # binary_sensor: pulsante fisico sul beacon

# --- Giorni della settimana ---
# Codici brevi usati internamente e nel config flow.
# L'ordine corrisponde a quello visualizzato nella UI (da lunedì a domenica).
DAYS_OF_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# --- Zone del secchio ---
# Ogni secchio può trovarsi in una di queste tre zone, determinate dal segnale RSSI.
ZONE_HOME = "casa"           # Il secchio è in casa (zona di caricamento)
ZONE_PICKUP = "prelievo"     # Il secchio è esposto per il ritiro
ZONE_UNDEFINED = "non_definita"  # Il secchio è fuori portata (disperso)

# Zone che l'utente può assegnare alle fasce di segnale nel config flow.
# "non_definita" è sempre assegnata automaticamente al segnale più debole.
ZONE_ASSIGNABLE = [ZONE_HOME, ZONE_PICKUP]

# --- Stati funzionali del secchio ---
# Gestiti dalla macchina a stati nel coordinator.
STATE_EMPTY = "vuoto"                      # Il secchio è stato svuotato
STATE_IN_USE = "in_uso"                    # Il secchio è in casa e viene riempito
STATE_AWAITING_PICKUP = "in_attesa_prelievo"  # Il secchio è esposto, attende il ritiro
STATE_EXPOSABLE = "esponibile"             # Il secchio può essere portato fuori
