APPUNTO 2026-03-22 - CHECKPOINT RUN CAPTURE E STORICO AI

PUNTO IN CUI SIAMO ARRIVATI
- abbiamo rimesso in piedi una cattura locale delle run senza usare HellHades come ponte
- la sorgente davvero utile oggi e' il client RAID locale, soprattutto:
  - `log.txt`
  - `battle-results/battleResults`
- `workers-serialization` esiste ma non sta dando segnale utile per il dettaglio combat
- cache `Vuplex` e `IndexedDB` non hanno mostrato dati utili nelle prove fatte oggi

COSA RIUSCIAMO A PRENDERE GIA' ADESSO
- `battle_id`
- `stage_id`
- team reale usato
- enemy rows con `type_id`
- start/end della battle
- snapshot raw del `battleResults` ricco prima che torni al placeholder da `11` byte

COSA NON ABBIAMO ANCORA
- vero event log per-hit
- timeline buff/debuff/resist strutturata
- spiegazione tattica fine del tipo "questa skill ha fallito perche' il target aveva questo stato"

PROBE PREPARATI
- `client_run_probe.py`
- `deep_battle_probe.py`
- `battle_results_burst_probe.py`
- `live_storage_probe.py`

STATO ATTUALE PROBE
- a fine sessione i probe sono stati fermati
- nessun processo python lasciato attivo volutamente

RUN HISTORY DB
- e' stata preparata la base in `forge_db.py`
- tabelle nuove:
  - `run_history_runs`
  - `run_history_members`
  - `run_history_member_stats`
  - `run_history_member_metrics`
  - `run_history_assets`
  - `run_history_events`
- esiste gia' il helper `record_run_history(...)`
- al momento i dump delle run sono ancora salvati su disco e NON ancora importati nel DB applicativo

MAPPER ENCOUNTER
- aggiunto `run_mapper.py`
- per `Demon Lord` abbiamo fissato:
  - `stage_id 4019021 -> demon_lord_ultra_nightmare`
  - `encounter_family -> demon_lord`
  - `area_region -> clan_boss`
  - `game_mode -> clan_boss`
  - `difficulty -> ultra_nightmare`
  - `enemy type_id 22296 -> boss_affinity void`

SESSIONI RAW IMPORTANTI SALVATE OGGI
- Dragon / dungeon:
  - `input/live_storage_probe/20260322T110139Z`
  - `input/client_probe/20260322T110139Z`
- Clan Boss preliminare:
  - `input/live_storage_probe/20260322T112527Z`
  - `input/client_probe/20260322T112527Z`
- Clan Boss seconda chiave catturata bene:
  - `input/live_storage_probe/20260322T114745Z`
  - `input/client_probe/20260322T114745Z`

RUN CLAN BOSS PIU' IMPORTANTE DI OGGI
- `battle_id`: `5d46944e-8521-4640-a635-f2d4a609b05f`
- `stage_id`: `4019021`
- encounter confermato: `Demon Lord Ultra-Nightmare`
- affinity derivata: `void`
- team:
  - `Rakka Viletide`
  - `Valkyrie`
  - `Ninja`
  - `Jintoro`
  - `Stag Knight`
- snapshot finale utile:
  - `input/client_probe/20260322T114745Z/snapshots/battle_results/20260322T115640Z_battle_results_12201_5bc98e75ef4f.bin`

RISULTATO A SCHERMO DELLA SECONDA CHIAVE
- totale: `45.62M`
- `Rakka`: `2,076,768`
- `Valkyrie`: `3,635,789`
- `Ninja`: `20,328,973`
- `Jintoro`: `12,762,763`
- `Stag Knight`: `6,817,260`

NOTA CRITICA SUL DECODER
- il `battleResults` viene catturato bene
- il decoder attuale legge correttamente la struttura msgpack/lz4
- pero' il campo strutturato che stiamo usando adesso per `damage_by_champion` NON coincide ancora con i numeri mostrati dalla UI
- quindi:
  - il raw e' affidabile e salvato
  - la normalizzazione del danno per campione e' ancora da correggere prima di importare tutto come dato finale "trusted"

PERCHE' QUESTA BASE E' COMUNQUE GIUSTA
- possiamo gia' costruire uno storico run account-specifico serio
- possiamo gia' legare:
  - encounter
  - difficulty
  - affinity
  - team reale
  - asset raw della run
- questo basta per iniziare a costruire il dataset che in futuro servira' all'AI di ottimizzazione

PROSSIMO PASSO QUANDO RIPRENDIAMO
1. fare un importer `probe session -> run_history_*`
2. importare subito:
   - encounter mapping
   - team
   - asset raw
   - timestamp
   - total damage trusted quando disponibile
3. correggere il decoder `damage_by_champion` del `battleResults`
4. solo dopo marcare i dati run come pienamente affidabili per training

VERIFICA FATTA OGGI
- test suite verde al checkpoint codice:
  - `82 passed`

CONCLUSIONE
- la cattura locale delle run senza HellHades e' reale e funziona
- il progetto e' passato dalla fase "si puo' fare?" alla fase "normalizziamo e importiamo bene"
- il DB per lo storico AI e' pronto
- manca il ponte finale tra dump raw e inserimento strutturato nel DB
