# ESP32 Bluetooth Beacon Proxy

## Hardware

- **ESP32** (esp32dev) con interfaccia Ethernet **LAN8720**
- IP statico: `192.168.2.166`
- Collegamento a Home Assistant via API ESPHome (porta 6053)
- Web server locale su porta 80

---

## Beacons supportati

Cinque beacon **Holyiot/Rensimote nRF52810** con accelerometro, sensore temperatura/umidità e pulsante fisico.

| ID | MAC | Nome beacon |
|----|-----|-------------|
| b1 | `E8:05:97:07:88:2B` | Umido |
| b2 | `EA:9B:FC:16:E6:CB` | Secco |
| b3 | `F3:70:BD:9C:DB:7C` | Carta |
| b4 | `FE:B1:20:9B:BB:D1` | Indifferenziata |
| b5 | `D7:10:4B:97:94:09` | Vetro e Metallo |

I beacon devono essere configurati in modalità **Beacon** (non iBeacon, non Eddystone) tramite l'app iOS.

---

## Protocollo BLE

I beacon trasmettono dati via **BLE advertisement passivo** sul service UUID `0x5242`.

Il payload è di **13 byte**. I byte 0–9 sono fissi (header + MAC address del beacon). I byte 10–12 variano per tipo di pacchetto:

| `byte[10]` | `byte[11]` | `byte[12]` | Significato |
|------------|------------|------------|-------------|
| `0x01` | Temperatura intera | Temperatura decimale | es. `23` + `81/100` = `23.81°C` |
| `0x03` | Umidità intera | Umidità decimale | es. `46` + `89/100` = `46.89%` |
| `0x04` | `0`=fermo, `1`=in movimento | — | Vibrazione/movimento |
| `0x06` | `0`=rilasciato, `1`=premuto | — | Pulsante fisico |

`byte[1]` è sempre la **batteria** in percentuale (es. `0x64` = 100%).

Il nome del beacon (es. "umido") è trasmesso nel **scan response** e letto tramite `on_ble_advertise` → `x.get_name()`.

---

## Entità create in Home Assistant

Per ciascuno dei 5 beacon vengono create le seguenti entità, identificate dal MAC address (senza i due punti):

### Sensori numerici
| Entità | Esempio | Note |
|--------|---------|------|
| `{MAC} RSSI` | `E8059707882B RSSI` | Potenza del segnale BLE in dBm. Media mobile su 10 campioni, aggiornata ogni 5 |
| `{MAC} Battery` | `E8059707882B Battery` | Percentuale batteria. Categoria diagnostica |
| `{MAC} Temperature` | `E8059707882B Temperature` | Temperatura in °C, 2 decimali |
| `{MAC} Humidity` | `E8059707882B Humidity` | Umidità relativa in %, 2 decimali |

### Sensori binari
| Entità | Esempio | Note |
|--------|---------|------|
| `{MAC} Vibration` | `E8059707882B Vibration` | `ON` quando il beacon è in movimento. Si spegne dopo 5 secondi dall'ultimo movimento rilevato |
| `{MAC} Button` | `E8059707882B Button` | `ON` quando il pulsante fisico è premuto. Si spegne dopo 2 secondi |

### Sensori testo
| Entità | Esempio | Note |
|--------|---------|------|
| `{MAC} Name` | `E8059707882B Name` | Nome configurato nel beacon via app iOS. Si aggiorna automaticamente se viene cambiato |

### Sensori di sistema
| Entità | Note |
|--------|------|
| `Uptime` | Tempo di attività dell'ESP32 in secondi |

### Pulsanti di sistema
| Entità | Note |
|--------|------|
| `Safe Mode Boot` | Riavvia in modalità sicura |
| `Factory Reset` | Reset ai valori di fabbrica |

---

## Configurazione

I MAC address dei beacon si modificano **esclusivamente** nella sezione `substitutions` in cima allo script:

```yaml
substitutions:
  b1_mac: "E8:05:97:07:88:2B"
  b1_mac_id: "E8059707882B"
  b2_mac: "EA:9B:FC:16:E6:CB"
  b2_mac_id: "EA9BFC16E6CB"
  b3_mac: "F3:70:BD:9C:DB:7C"
  b3_mac_id: "F370BD9CDB7C"
  b4_mac: "FE:B1:20:9B:BB:D1"
  b4_mac_id: "FEB1209BBBD1"
  b5_mac: "D7:10:4B:97:94:09"
  b5_mac_id: "D7104B979409"
```

Il resto dello script non va modificato. Il `mac_id` è lo stesso MAC senza i due punti, usato come nome delle entità in HA.

---

## Note tecniche

- Il bluetooth proxy (`bluetooth_proxy: active: true`) è abilitato e usa 3 slot di connessione BLE
- La scansione BLE è continua con finestra di 300ms
- Lo smoothing RSSI usa una media mobile su finestra scorrevole di 10 campioni, con pubblicazione ogni 5 campioni (~5 secondi)
- Il nome del beacon viene letto solo quando presente nel scan response (non tutti gli advertisement lo includono)
- Temperature e umidità sono in pacchetti separati (`0x01` e `0x03`) trasmessi in alternanza dal beacon
- Il protocollo `0x5242` è proprietario Holyiot/Rensimote e decodificato tramite analisi empirica dei dati raw + documentazione FCC
