# Appunto 2026-03-22 - Client Telemetry Diretta

## Domanda

Possiamo registrare le run in tempo reale senza usare HellHades come ponte?

## Risposta breve

Si', con buona probabilita'.

Non serve necessariamente intercettare HellHades.
Il client RAID locale espone gia' diversi segnali leggibili direttamente dal filesystem locale:

- log testuale client
- cache battle result
- cache workers serialization
- database sqlite locali del client

## Verifica fatta oggi sul PC locale

Path trovati realmente presenti:

- `C:\Users\acdad\AppData\Local\PlariumPlay\StandAloneApps\raid-shadow-legends\build\log.txt`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\raid.db`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\raidV2.db`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\battle-results\battleResults`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\workers-serialization\serialization`

## Cosa significa davvero

### 1. `log.txt`

E' vivo e contiene eventi di gioco / UI / battle lifecycle.

Esempi osservati:

- `BattleUnloading`
- `BattleView finish Hide`
- `Close view - [View: Battle]`

Questa sorgente e' adatta per:

- capire quando una run parte
- capire quando una run finisce
- riconoscere il contenuto aperto
- costruire un feed live leggero

Ma da sola non basta per ottenere:

- danno finale affidabile
- team completo sempre corretto
- tutte le azioni di combattimento strutturate

### 2. `battle-results/battleResults`

E' il candidato migliore per il risultato finale run.

Nel legacy veniva letto direttamente e decodificato senza bisogno di HellHades:

- parse MessagePack
- tentativo LZ4
- estrazione `total_damage`
- estrazione `damage_by_champion`

Questa sorgente e' adatta per:

- danno totale run
- danno per campione
- eventuali summary strutturati di fine combattimento

Questa e' la parte che piu' somiglia a un "canale affidabile post-battle".

### 3. `workers-serialization/serialization`

Sembra una cache binaria aggiornata dal client.

Potrebbe contenere:

- stato runtime
- comandi serializzati
- snapshot di oggetti client

Va trattata come sorgente sperimentale.
Potrebbe essere utile, ma oggi non e' ancora la via piu' semplice.

### 4. `raid.db` e `raidV2.db`

Esistono, ma nella verifica fatta oggi la tabella `Events` era presente e vuota:

- `raid.db`: `Events = 0 righe`
- `raidV2.db`: `Events = 0 righe`

Quindi:

- il vecchio approccio che faceva polling di `Events` resta interessante
- ma non possiamo assumere che oggi sia sempre popolata
- potrebbe dipendere da modalita' di gioco, timing o versioni client

## Conclusione tecnica

### Quello che penso oggi

Si', c'e' sicuramente comunicazione real time tra client e server.

Pero' per CB Forge non partirei da sniffing di rete.

Partirei da telemetria locale del client, perche':

- e' meno fragile
- non richiede reverse engineering del protocollo remoto
- non dipende da HellHades
- abbiamo gia' una prova concreta che i file locali esistono e si aggiornano

## Strategia consigliata

### Fase 1 - Recorder locale affidabile

Usare solo sorgenti locali:

- `log.txt` per start / end / contesto live
- `battleResults` per risultato finale
- snapshot roster/loadout locale per team e gear usati

Output desiderato:

- una run finale affidabile con:
  - contenuto
  - stage
  - difficolta'
  - team
  - danno
  - turni / durata
  - timestamp

### Fase 2 - Event log opzionale

Se il `log.txt` da' abbastanza segnale, possiamo salvare anche:

- `combat_run_events`

Con eventi tipo:

- `battle_created`
- `battle_state_changed`
- `battle_result_detected`
- `battle_view_closed`

Ma non lo confonderei con un vero action-by-action combat log.

### Fase 3 - Sperimentazione profonda

Solo dopo:

- analisi `workers-serialization`
- nuova verifica di `raid.db` / `raidV2.db`
- eventuale reverse engineering di ulteriori cache locali

## Risposta netta alla domanda

### Possiamo leggere un log real time dal client senza HellHades?

Si'.

### Possiamo avere gia' oggi tutte le mosse strutturate di ogni combattente?

Non ancora dimostrato.

### Possiamo pero' ricostruire bene start, end, team e risultato run senza HellHades?

Si', e questa mi sembra la direzione giusta per rimettere in piedi la registrazione delle run.
