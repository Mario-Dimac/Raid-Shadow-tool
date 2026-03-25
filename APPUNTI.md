# Appunti CB Forge

Documento unico di riferimento che consolida tutti gli appunti storici del progetto fino al 2026-03-25.

## Stato corrente verificato il 2026-03-25

- Il database runtime canonico e' `data/cbforge.sqlite3`.
- Il file `forge.db` in root era obsoleto e vuoto; puo' essere rimosso.
- Esiste una pipeline reale `probe session -> run_history_*` tramite `run_history_importer.py`.
- Nel DB runtime e' gia' presente almeno una run importata:
  - `battle_id = 5d46944e-8521-4640-a635-f2d4a609b05f`
  - `encounter_key = demon_lord_ultra_nightmare`
  - `success = 1`
- La cattura delle run e' reale, ma non tutto il flusso e' ancora live/automatico in tempo reale.
- Per `Demon Lord`, il `total_damage` della run e' ora recuperabile dal raw `battleResults` come candidato forte da `s.a.dt >> 32`.
- Il `damage_by_champion` per `Demon Lord` e' ancora solo `candidate`, non `trusted`.
- Il `healing_done` non e' ancora mappato in modo affidabile: il verde finale sembra mescolare cure da skill e sustain da set come `Lifesteal`.
- La roadmap di decoupling da HellHades e' mantenuta in questo file; `HELLHADES_DECOUPLING_PLAN.md` resta solo come rimando per evitare divergenze.

## Decisioni ormai fissate

- Runtime DB: `data/cbforge.sqlite3`
- Sorgente account di import: `input/normalized_account.json`
- I JSON non sono il database applicativo
- Policy registry target: `owned_level_60_only`
- Provider order skill enrichment:
  1. `local_registry`
  2. `ayumilove`
  3. `hellhades`
- Per lo storico run, il DB deve separare:
  - contesto encounter
  - team reale
  - snapshot build/stats
  - metriche run
  - asset raw
  - timeline eventi

## Cronologia sintetica

### 2026-03-18 - Fondazioni del progetto

#### Fatto

- Archiviato il codice precedente in `old/legacy_20260318/`.
- Ripulita la root del progetto.
- Creata la nuova base database in `forge_db.py`.
- Bootstrap database in `build_databases.py`.
- Create tabelle relazionali per:
  - catalogo campioni
  - skill campioni
  - stat base
  - campioni account
  - stat totali account
  - equip
  - substat equip
  - bonus account
  - set
  - combat
- Creato `registry_report.py`.
- Il registry target considera solo i campioni posseduti a livello 60.
- Ultimo refresh salvato in `app_state`.

#### Stato emerso

- Target di enrichment: `114` campioni livello 60 unici.
- Dal dump attuale arrivano bene:
  - roster
  - equip
  - bonus account
  - nomi skill
- Dal dump attuale non arrivano ancora bene:
  - cooldown base strutturati
  - cooldown booked strutturati
  - effetti skill strutturati

#### Scoperta importante

- HellHades espone un endpoint utile:
  - `https://hellhades.com/wp-json/hh-api/v3/raid/skills/{postID}`
- Questo endpoint restituisce almeno:
  - nome skill
  - tipo skill
  - descrizione
  - cooldown base
  - books
- Esempio verificato su Geomancer:
  - `postID = 17837`

#### Comandi utili

- Ricostruire il DB:
  - `python build_databases.py`
- Vedere lo stato del registry:
  - `python registry_report.py`
- Lanciare i test:
  - `pytest -q`

### 2026-03-19 - Enrichment roster, stats e gear UI

#### Risultati chiusi

- Completato l'enrichment HellHades per tutti i target livello 60.
- Popolati nel DB:
  - `hellhades_post_id`
  - `hellhades_url`
  - `last_enriched_at`
  - `skill_type`
  - `description_clean`
  - effetti skill strutturati
- Verificato `114/114` target arricchiti.
- Aggiunta web UI locale per il roster:
  - lista campioni
  - dettaglio campione
  - refresh DB
  - refresh HellHades
- Corretto il problema delle stats account:
  - il dump originale aveva `total_stats` vuote o a zero
  - ora esiste un motore di calcolo serio in `account_stats.py`
- Separate nel DB:
  - stat importate dal dump
  - stat calcolate runtime
- Aggiunta metadata stats per campione:
  - `source`
  - `completeness`
  - `unsupported_sets_json`
  - `applied_sets_json`
  - `computed_at`
- Aggiunta pagina equip dedicata nella web UI:
  - vista tutti i pezzi
  - filtro `equipaggiato / magazzino / tutti`
  - filtri per slot e set
  - dettaglio pezzo con owner, main stat e substat
- Costruito il primo motore decisionale equip in `gear_advisor.py`.

#### Verdict gear esposti in UI

- `push_12`
- `push_16`
- `keep_after_12`
- `sell_now`
- `sell_after_12`
- `review_equipped`
- `keep_16`
- `review_16`

#### Numeri fissati nel checkpoint

- Campioni nel catalogo locale: `495`
- Campioni target account livello 60: `114`
- Target arricchiti HellHades: `114/114`
- Effect rows HellHades scritte: `841`
- Pezzi equip totali nel DB: `2408`
- Pezzi equipaggiati: `1025`
- Pezzi in magazzino: `1383`
- Distribuzione verdict gear:
  - `push_12`: `468`
  - `push_16`: `77`
  - `keep_after_12`: `51`
  - `sell_now`: `648`
  - `sell_after_12`: `65`
  - `keep_16`: `498`
  - `review_16`: `448`
  - `review_equipped`: `153`

#### Stato stats account

- Le `total_stats` del dump non sono affidabili come sorgente primaria.
- Le stats mostrate in UI vengono dal calcolo runtime.
- Stato del ricalcolo:
  - `495` campioni derivati
  - `377` con completezza `derived`
  - `118` con completezza `partial`
- I casi `partial` dipendono da set speciali non ancora quantificati numericamente.
- Esempi di set ancora incompleti:
  - `Feral`
  - `Stone Skin`
  - `Protection`
  - `Sleep Chance`

#### Tabelle importanti a questo punto

- `champion_catalog`
- `champion_roles`
- `champion_base_stats`
- `champion_skills`
- `champion_skill_effects`
- `registry_targets`
- `account_champions`
- `account_champion_imported_total_stats`
- `account_champion_total_stats`
- `account_champion_stat_models`
- `gear_items`
- `gear_substats`
- `account_bonuses`
- `set_definitions`
- `set_definition_stats`
- `app_state`

#### Verifica tecnica

- `pytest -q` -> `12 passed`

### 2026-03-20 - Decoupling da HellHades e provider abstraction

#### Obiettivo

Ridurre la dipendenza da HellHades e spostare CB Forge verso un modello:

- runtime account / gear / operazioni locali
- catalogo skill multi-provider
- registry locale come sorgente canonica letta dal tool

#### Risultati chiusi

- Repo pulita e branch dedicato al decoupling.
- Legacy `old/` fuori dal repo principale.
- UI e report meno HellHades-centrici.
- Introdotto `data_status` provider-neutral.
- `source` skill valorizzato in modo coerente.
- Introdotto layer provider per enrichment skill.
- `hellhades` spostato a provider dedicato.
- Creato `local_registry` provider.
- `auto` ora usa ordine provider-first.

#### Provider order attuale

1. `local_registry`
2. `ayumilove`
3. `hellhades`

#### Nuovi componenti chiave

- `providers/local_registry_provider.py`
- `providers/ayumilove_provider.py`
- `game_data_probe.py`
- `data_sources/local_skill_registry.json`

#### Stato reale verificato nel checkpoint

- Sync reale con:
  - `python hellhades_enrich.py --provider auto`
- Esito osservato:
  - `114/114` target serviti da `local_registry`
  - `0` fallback `hellhades` nell'ultimo sync
- AyumiLove verificato su:
  - `Thea the Tomb Angel`
- Il provider parsea correttamente:
  - `Befoulment`
  - `Hexreaper`
  - `Not of This World`
  - `Cruel Angel`
  - `Aura`
- `game_data_probe.py` ha confermato:
  - client RAID locale presente
  - content version rilevata: `11.30.0`
  - bundle locali disponibili da esplorare
  - registry locale ancora povero di contenuto testuale

#### Punto importante

Il problema principale non e' piu' l'architettura provider.

Il problema vero ora e':

- arricchire `local_skill_registry`
- trovare o costruire una fonte locale piu' ricca per skill text, cooldown ed effetti

#### Dipendenze HellHades residue da tenere monitorate

1. Enrichment skill e metadata
   - file coinvolti: `hellhades_enrich.py`, `registry_report.py`, `cbforge_web.py`
   - uso residuo: match remoto campioni, fetch skill/cooldown, parsing descrizioni
2. Bridge account / inventory
   - file coinvolti: `old/legacy_20260318/cbforge_extractor/hellhades_bridge.py`, `old/legacy_20260318/cbforge_extractor/snapshot.py`, `old/legacy_20260318/extract_local.py`, `cbforge_web.py`
   - uso residuo: roster, artifact e metadata campioni via bridge / API HellHades
3. Live operations
   - file coinvolti: `hellhades_live.py`, `cbforge_web.py`
   - uso residuo: equip/sell live e infrastruttura token/SignalR

#### Base locale gia' disponibile senza HellHades

- lettura file locali del client
- lettura `raid.db` e `raidV2.db`
- analisi di `battleResults`
- osservazione runtime del processo RAID

Questo rende realistico il distacco, ma implica la sostituzione del bridge account e del layer live, non solo del provider skill.

#### Architettura target consolidata

1. Runtime locale
   - responsabilita': leggere client, file/DB locali e runtime process
   - target: `raid_local_runtime.py` oppure package `raid_local/`
2. Importer account locale
   - responsabilita': ricostruire `normalized_account.json` senza bridge HellHades
   - target: `raid_account_import.py`
3. Registry locale campioni / skill
   - responsabilita': catalogo canonico, skill, cooldown, effetti, alias
   - target: `champion_registry.py`, `data_sources/champion_registry.json`, tabelle SQLite dedicate
4. Provider abstraction
   - responsabilita': normalizzare sorgenti locali o esterne in un formato unico
   - target: `enrichment_sources.py`, `providers/hellhades_provider.py`, `providers/local_registry_provider.py`
5. Live actions adapter
   - responsabilita': isolare equip / sell e rendere il backend sostituibile
   - target: `live_actions.py`, `providers/hellhades_live_provider.py`, futuro `providers/local_game_bridge.py`

#### Stato delle fasi del decoupling letto alla luce del codice attuale

- Fase 1 `provider-neutral model`: sostanzialmente chiusa
- Fase 2 `provider abstraction`: primo taglio chiuso
- Fase 3 `registry locale persistente`: avviata ma incompleta
- Fase 4 `importer account locale senza bridge`: ancora aperta
- Fase 5 `live actions indipendenti`: ancora aperta e probabilmente opzionale a lungo

#### Criteri di chiusura del decoupling

- il DB si ricostruisce senza chiamate HellHades
- roster e inventory arrivano da sorgenti locali
- skill e cooldown arrivano da registry locale o provider opzionali
- report e UI non assumono HellHades come sorgente primaria
- l'assenza di token/accesso HellHades non blocca il progetto

#### Rischi reali del decoupling

- il bridge account locale puo' richiedere reverse engineering non banale
- i metadata campioni possono restare incompleti senza una fonte esterna iniziale
- alcune live actions potrebbero non essere replicabili facilmente senza tooling esterno

#### Commit principali del checkpoint

- `4d3caf9` Decouple coverage reporting from HellHades
- `777e280` Add HellHades decoupling roadmap
- `aaf2bd4` Add provider abstraction for skill enrichment
- `377f15c` Add local skill registry provider
- `783e6db` Prefer local registry before HellHades fallback
- `5bc23ad` Add local game data audit and readiness metrics
- `91178ec` Add AyumiLove skill provider

#### Verifica tecnica

- `pytest -q` -> `46 passed`

### 2026-03-21 - Pulizia modello gear/build e bonus account

#### Tema

Pulizia del modello gear/build lato account reale, con focus su:

- set gear e loro visibilita'
- coerenza build
- accuratezza delle stat derivate
- bridge live HellHades e fonti bonus account-level

#### Risultati chiusi

- Distinti i set `fixed`, `variable` e `accessory`.
- I set `2-piece` e `4-piece` contano solo artifact.
- I set `variable/accessory` possono contare anche accessori.
- Corretti casi ambigui come `Counterattack Accessory` e `Shield Accessory`.
- Aggiunta pagina `/sets` con registry leggibile, bonus per soglia e operativita'.
- Aggiunta pagina `/set-curation`.
- Possibile:
  - correggere il nome canonico del set
  - dichiarare tipo set
  - incollare bonus stat e bonus speciali
- I bonus speciali vengono tenuti separati dalle stat pure.
- Planner build migliorato per premiare chiusura reale dei set.
- Introdotto `set_coherence`.
- Evitate proposte tank fragili con pezzi singoli forti ma incoerenti.
- UI build aggiornata con indicatore di coerenza.
- Corretto il bridge che tronca gli item equipaggiati.
- Il nono pezzo non viene piu' perso.
- Conteggiato anche `AscendBonus` sugli item.
- Accessori equipaggiati ora assegnati correttamente al campione.
- Mastery statiche applicate al motore stat.
- `Lore of Steel` applicato ai basic set.
- Blessing/awakening statici applicati per rarity e grade.
- Empowerment applicato.
- Il bridge live esporta anche `area_bonuses`.
- Conversione in `account_bonuses` fatta nella pipeline legacy.
- La build page ora ha selettore area/regione.
- Gli area bonus vengono applicati solo se selezionati.

#### Stato verificato

- `pytest -q` -> `68 passed`
- Bonus account-level nel DB reale:
  - `24` bonus `great_hall`
  - `16` bonus `area_bonus`

#### Arbiter verificata

- senza area: `SPD 321.6`
- `Clan Boss`: `SPD 325.6`
- `Hydra`: `SPD 323.6`
- `Doom Tower`: `SPD 321.6`

#### Gap aperti al checkpoint

- `Relic` non ancora completamente tradotti in bonus numerici reali
- possibile manchi ancora qualche layer secondario nelle stat finali rispetto al gioco
- `ignore_def` da area bonus e altre stat non ancora pienamente esposte in UI

### 2026-03-22 - Planner encounter-specifico

#### Tema

Allargare il concetto di build planner oltre i soli Clan Boss / Hydra e costruire una lista ampia dei contenuti da supportare.

Il planner dovra' ragionare per `encounter` reale, non solo per profilo astratto.

#### Tassonomia minima corretta

- `content_family`
- `encounter_id`
- `difficulty`
- `stage_or_floor`
- `affinity_mode`
- `target_affinity` o mappa affinita' nemiche
- `restrictions`

#### Famiglie di run da supportare

1. `campaign:<chapter>:<stage>:<difficulty>`
2. `minotaur:<stage>`
3. `arcane_keep:<stage>` / `force_keep:<stage>` / `magic_keep:<stage>` / `spirit_keep:<stage>` / `void_keep:<stage>`
4. `dragons_lair:<stage>` / `ice_golem_cave:<stage>` / `fire_knight_castle:<stage>` / `spider_den:<stage>`
5. `dragons_lair_hard:<stage>` / `ice_golem_cave_hard:<stage>` / `fire_knight_castle_hard:<stage>` / `spider_den_hard:<stage>`
6. `sand_devil:<stage>`
7. `phantom_shogun:<stage>`
8. `iron_twins:<affinity>:<stage>`
9. `demon_lord:<difficulty>:<affinity_state>`
10. `hydra:<difficulty>:<rotation_or_head_set>`
11. `chimera:<difficulty>:<rotation>`
12. `doom_tower_floor:<difficulty>:<floor>` / `doom_tower_boss:<difficulty>:<boss>:<floor>` / `doom_tower_secret_room:<difficulty>:<room>`
13. `faction_wars:<difficulty>:<faction>:<stage>`
14. `cursed_city_stage:<difficulty>:<rotation>:<district>:<node>` e varianti boss
15. `classic_arena:<defense_snapshot_id>`
16. `tag_arena:<defense_snapshot_id>`
17. `live_arena:<draft_snapshot_id>`
18. `siege:<building_type>:<defense_snapshot_id>`
19. `grim_forest:<difficulty>:<rotation>:<node>`

#### Modalita' affinity da supportare nel codice

- `fixed_stage_affinity`
  - minotaur
  - dragon
  - fire_knight
  - ice_golem
  - spider
  - sand_devil
  - phantom_shogun
- `fixed_day_affinity`
  - iron_twins
- `stateful_boss_affinity`
  - demon_lord
- `multi_target_rotation_affinity`
  - hydra
  - chimera
- `dynamic_enemy_affinity`
  - classic_arena
  - tag_arena
  - live_arena
  - siege
  - campaign
- `rotation_map_affinity`
  - doom_tower
  - cursed_city
  - grim_forest

#### Tabelle affinita' stage-based

##### Minotaur

- Spirit: `1 / 5 / 9 / 13`
- Magic: `2 / 6 / 10 / 14`
- Void: `3 / 7 / 11 / 15`
- Force: `4 / 8 / 12`

##### Dragon

- Magic: `1 / 5 / 9 / 13 / 17 / 20 / 22`
- Force: `2 / 6 / 10 / 14 / 18 / 21 / 25`
- Spirit: `3 / 7 / 11 / 15 / 19 / 24`
- Void: `4 / 8 / 12 / 16 / 23`

##### Fire Knight

- Force: `1 / 5 / 9 / 13 / 17 / 20 / 24`
- Spirit: `2 / 6 / 10 / 14 / 18 / 21 / 25`
- Magic: `3 / 7 / 11 / 15 / 19 / 22`
- Void: `4 / 8 / 12 / 16 / 23`

##### Ice Golem

- Spirit: `1 / 5 / 9 / 13 / 17 / 20 / 24`
- Magic: `2 / 6 / 10 / 14 / 18 / 21 / 25`
- Force: `3 / 7 / 11 / 15 / 19 / 23`
- Void: `4 / 8 / 12 / 16 / 22`

##### Spider

- Void: `1 / 5 / 9 / 13 / 17 / 21`
- Magic: `2 / 6 / 10 / 14 / 18 / 22 / 25`
- Force: `3 / 7 / 11 / 15 / 19 / 23`
- Spirit: `4 / 8 / 12 / 16 / 20 / 24`

##### Sand Devil

- Magic: `1 / 5 / 9 / 13 / 17 / 20 / 22`
- Force: `2 / 6 / 10 / 14 / 18 / 21 / 25`
- Spirit: `3 / 7 / 11 / 15 / 19 / 24`
- Void: `4 / 8 / 12 / 16 / 23`

##### Phantom Shogun

Fonte trovata il 2026-03-22 mostrava un'incongruenza:

- Spirit: `3 / 7 / 11 / 15 / 18 / 23`
- Void: `2 / 6 / 10 / 14 / 18 / 22`

Lo stage `18` compare due volte e manca lo stage `19`.

Assunzione operativa ragionevole prima di hardcodare:

- Magic: `1 / 5 / 9 / 13 / 17 / 21 / 25`
- Void: `2 / 6 / 10 / 14 / 18 / 22`
- Spirit: `3 / 7 / 11 / 15 / 19 / 23`
- Force: `4 / 8 / 12 / 16 / 20 / 24`

Da ricontrollare in game o contro una seconda fonte prima di renderla canonica.

#### Conseguenza pratica per CB Forge

Il planner futuro non dovrebbe chiedere solo:

- `profile`
- `region`

Ma qualcosa di questo tipo:

- `content_family`
- `encounter`
- `goal`

Esempi:

- `dragon:20` con goal `safe_farm`
- `fire_knight:25` con goal `turn_attack`
- `demon_lord:ultra_nightmare:void` con goal `max_damage`
- `demon_lord:ultra_nightmare:spirit` con goal `max_damage`
- `hydra:hard:current_rotation` con goal `auto_survival`
- `doom_tower_boss:hard:dark_fae:120` con goal `clear_once`
- `cursed_city_stage:hard:rotation_7:plagueholme:n14` con goal `unlock_path`
- `classic_arena:defense_snapshot_123` con goal `offense_win_rate`

#### Prossimi step raccomandati emersi

1. Creare `data_sources/run_registry.json`
2. Implementare resolver:
   - `stage_affinity_resolver`
   - `iron_twins_day_resolver`
   - `demon_lord_affinity_state_resolver`
   - `rotation_catalog_resolver`
3. Aggiornare la UI planner con:
   - famiglia contenuto
   - encounter specifico
   - goal
4. Ordine di priorita':
   - Demon Lord
   - Hydra
   - Dragon / Fire Knight / Spider / Ice Golem
   - Sand Devil / Phantom Shogun / Iron Twins
   - Doom Tower Boss
   - Arena
   - Cursed City
   - resto

### 2026-03-22 - Telemetria client diretta e run capture

#### Domanda

Possiamo registrare le run in tempo reale senza usare HellHades come ponte?

#### Risposta emersa

Si', con buona probabilita', usando la telemetria locale del client RAID.

#### Path locali verificati

- `C:\Users\acdad\AppData\Local\PlariumPlay\StandAloneApps\raid-shadow-legends\build\log.txt`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\raid.db`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\raidV2.db`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\battle-results\battleResults`
- `C:\Users\acdad\AppData\LocalLow\Plarium\Raid_ Shadow Legends\workers-serialization\serialization`

#### Valore delle sorgenti locali

##### `log.txt`

Adatto per:

- capire quando una run parte
- capire quando una run finisce
- riconoscere il contenuto aperto
- costruire un feed live leggero

Non basta da solo per:

- danno finale affidabile
- team completo sempre corretto
- tutte le azioni di combattimento strutturate

##### `battle-results/battleResults`

Miglior candidato per il risultato finale run.

Nel legacy veniva letto direttamente e decodificato senza HellHades:

- parse MessagePack
- tentativo LZ4
- estrazione `total_damage`
- estrazione `damage_by_champion`

Adatto per:

- danno totale run
- danno per campione
- eventuali summary strutturati di fine combattimento

##### `workers-serialization/serialization`

Sorgente sperimentale:

- stato runtime
- comandi serializzati
- snapshot di oggetti client

##### `raid.db` e `raidV2.db`

Interessanti, ma nella verifica del 2026-03-22:

- `raid.db`: `Events = 0 righe`
- `raidV2.db`: `Events = 0 righe`

Quindi non si puo' assumere che la tabella `Events` sia sempre popolata.

#### Strategia consigliata emersa

##### Fase 1 - Recorder locale affidabile

Usare:

- `log.txt` per start / end / contesto live
- `battleResults` per risultato finale
- snapshot roster/loadout locale per team e gear usati

Output desiderato:

- contenuto
- stage
- difficolta'
- team
- danno
- turni / durata
- timestamp

##### Fase 2 - Event log opzionale

Salvare eventualmente:

- `combat_run_events`

Con eventi tipo:

- `battle_created`
- `battle_state_changed`
- `battle_result_detected`
- `battle_view_closed`

##### Fase 3 - Sperimentazione profonda

Solo dopo:

- analisi `workers-serialization`
- nuova verifica di `raid.db` / `raidV2.db`
- eventuale reverse engineering di altre cache locali

### 2026-03-22 - Mapping Demon Lord confermato

#### Osservazione confermata

- data osservazione: `2026-03-22`
- client request: `CreateAllianceBossBattle`
- `stage_id` osservato: `4019021`
- `enemy type_id` osservato: `22296`
- screenshot utente: `Demon Lord. Ultra-Nightmare`

#### Mapping fissato

- `4019021 -> demon_lord_ultra_nightmare`
- `encounter_family -> demon_lord`
- `area_region -> clan_boss`
- `game_mode -> clan_boss`
- `difficulty -> ultra_nightmare`

#### Affinita'

- `enemy type_id 22296 = Demon Lord`
- in `hh_hero_types.json` ha `element = 4`
- la mappa affinity del progetto traduce `4 -> void`

#### Conclusione

Per la run osservata:

- `difficulty = ultra_nightmare`
- `boss_affinity = void`

### 2026-03-22 - Run history DB per AI

#### Obiettivo

Costruire uno storico run che serva subito per analisi pratiche dell'account e piu' avanti come base dati per un optimizer AI.

#### Principio

Il DB non deve salvare solo "la run e' andata bene o male".

Deve separare:

- contesto encounter
- team reale usato
- stato/build dei membri
- metriche finali osservate
- asset raw collegati
- eventuale timeline eventi

#### Perche' questo serve all'AI

Ogni run deve produrre:

- features:
  - encounter
  - stage
  - affinity
  - team
  - stats/build dei champ
  - modalita' auto/manual
- labels:
  - success/fail
  - tempo run
  - danno totale
  - danno per campione
  - eventuali metriche future come uptime debuff o morti

#### Schema base aggiunto

- `run_history_runs`
  - una riga per run
  - contiene contesto encounter, risultato e label globali
- `run_history_members`
  - un membro per slot
  - contiene identita' e snapshot leggero del champ usato
- `run_history_member_stats`
  - stats numeriche per membro
  - utile per training senza dover parsare JSON
- `run_history_member_metrics`
  - danno fatto/subito, heal, morti, revive, stato finale
- `run_history_assets`
  - collega la run ai file raw come `battleResults`, probe dump e snapshot
- `run_history_events`
  - timeline opzionale
  - oggi puo' contenere feed sintetici, domani anche eventi piu' granulari

#### Cosa possiamo fare subito con questo DB

- ranking dei team reali per encounter
- confronto build per lo stesso contenuto
- suggerimenti basati su storico account-specifico
- dataset supervisionato per stimare:
  - probabilita' di successo
  - tempo run
  - danno atteso
  - contributo medio dei singoli champ

#### Cosa manca ancora

- per-hit damage esplicito
- buff/debuff timeline strutturata
- reason tracing fine del tipo "perde per mancanza uptime"

#### Conclusione del checkpoint

Questa base e' gia' sufficiente per una AI di ottimizzazione macro:

- scegliere quali champ usare
- scegliere quali team provare
- preferire build che massimizzano successo/tempo/danno

Non e' ancora sufficiente per una AI tattica micro completa.

### 2026-03-22 - Checkpoint run capture e import

#### Punto raggiunto nel checkpoint originario

- Rimessa in piedi una cattura locale delle run senza HellHades come ponte.
- La sorgente piu' utile e' il client RAID locale:
  - `log.txt`
  - `battle-results/battleResults`
- `workers-serialization` non stava dando segnale utile per il dettaglio combat.
- Cache `Vuplex` e `IndexedDB` non hanno mostrato dati utili nelle prove.

#### Dati gia' estraibili

- `battle_id`
- `stage_id`
- team reale usato
- `enemy_rows` con `type_id`
- start/end battle
- snapshot raw del `battleResults` ricco prima del ritorno al placeholder da `11` byte

#### Dati mancanti

- vero event log per-hit
- timeline buff/debuff/resist strutturata
- spiegazione tattica fine dei fallimenti

#### Probe preparati

- `client_run_probe.py`
- `deep_battle_probe.py`
- `battle_results_burst_probe.py`
- `live_storage_probe.py`

#### Sessioni raw importanti salvate

- Dragon / dungeon:
  - `input/live_storage_probe/20260322T110139Z`
  - `input/client_probe/20260322T110139Z`
- Clan Boss preliminare:
  - `input/live_storage_probe/20260322T112527Z`
  - `input/client_probe/20260322T112527Z`
- Clan Boss seconda chiave catturata bene:
  - `input/live_storage_probe/20260322T114745Z`
  - `input/client_probe/20260322T114745Z`

#### Run Clan Boss piu' importante del checkpoint

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

#### Risultato a schermo della seconda chiave

- totale: `45.62M`
- `Rakka`: `2,076,768`
- `Valkyrie`: `3,635,789`
- `Ninja`: `20,328,973`
- `Jintoro`: `12,762,763`
- `Stag Knight`: `6,817,260`

#### Nota critica sul decoder

- Il `battleResults` viene catturato bene.
- Il decoder attuale legge correttamente la struttura `msgpack/lz4`.
- Il campo usato per `damage_by_champion` non coincide ancora con i numeri mostrati dalla UI.
- Quindi:
  - il raw e' affidabile e salvato
  - la normalizzazione del danno per campione va corretta prima di trattarlo come dato finale trusted

#### Stato effettivo aggiornato rispetto al checkpoint

- Il passo `probe session -> run_history_*` oggi esiste davvero tramite `run_history_importer.py`.
- Almeno una run e' gia' stata importata nel DB runtime.
- Questo chiude il gap "solo dump su disco" almeno per le sessioni importate manualmente.
- Resta aperto il gap del live ingest automatico e della normalizzazione danno per campione.

#### Verifica tecnica del checkpoint originario

- `pytest -q` -> `82 passed`

## Fonti consultate negli appunti del 2026-03-22

### Fonti ufficiali Plarium

- Affinita': `https://raid-support.plarium.com/hc/en-us/articles/360017209020-Affinity-What-effects-does-it-have-on-your-Champion-s-Skills`
- Demon Lord: `https://raid-support.plarium.com/hc/en-us/articles/360014645900-Guide-Demon-Lord`
- Hydra: `https://raid-support.plarium.com/hc/en-us/articles/4411876951442-Guide-The-Hydra`
- Chimera: `https://raid-support.plarium.com/hc/en-us/articles/17510611600412-Guide-The-Chimera`
- Doom Tower: `https://raid-support.plarium.com/hc/en-us/articles/360017835959-Doom-Tower`
- Cursed City: `https://raid-support.plarium.com/hc/en-us/articles/11745002129948-Guide-Cursed-City`
- Iron Twins: `https://raid-support.plarium.com/hc/en-us/articles/5875103610140-Iron-Twins-Fortress`
- Classic Arena: `https://raid-support.plarium.com/hc/en-us/articles/360014642780-Classic-Arena`
- Tag Arena: `https://raid-support.plarium.com/hc/it/articles/360014696359-Guida-Arena-a-Squadre`
- Live Arena: `https://raid-support.plarium.com/hc/en-us/articles/11348352472604-Guide-Live-Arena`
- Siege: `https://raid-support.plarium.com/hc/en-us/articles/14888947445660-Guide-Siege`
- Faction Wars: `https://raid-support.plarium.com/hc/en-us/articles/360014709019-Faction-Wars`

### Fonti di riferimento per tabelle stage / affinity

- Minotaur: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-minotaurs-labyrinth/`
- Dragon: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-dragons-lair/`
- Fire Knight: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-fire-knights-castle/`
- Ice Golem: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-ice-golems-peak/`
- Spider: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-spiders-den/`
- Sand Devil: `https://ayumilove.net/raid-shadow-legends-champion-ranking-for-sand-devils-necropolis/`
- Phantom Shogun: `https://ayumilove.net/raid-shadow-legends-champion-ranking-for-phantom-shogun-grove/`
- Magic Keep: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-magic-keep/`
- Spirit Keep: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-spirit-keep/`
- Void Keep: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-void-keep/`
- Force Keep: `https://ayumilove.net/raid-shadow-legends-champion-ranking-in-force-keep/`
- Guida generale / indice modalita': `https://ayumilove.net/raid-shadow-legends-guide/`

## Backlog consolidato

### Dati e provider

- Arricchire meglio `local_skill_registry`
- Ridurre ancora la dipendenza contenutistica da provider esterni

### Stats e build

- Tradurre meglio `Relic` e altri layer secondari in bonus numerici
- Esportare meglio metriche come `ignore_def` in UI
- Continuare la validazione sentinella su campioni reali dopo il fix accessori:
  - `Maneater`
  - `Ninja`
  - almeno altri 2-3 campioni con screenshot in-game di confronto

### Planner

- Passare da planner per `profile/region` a planner encounter-specifico
- Introdurre catalogo run versionabile
- Aggiungere resolver di affinita' e rotazione
- Mantenere in UI i pezzi `excluded/suspicious` invece di farli sparire, cosi' il confronto col gioco resta leggibile

### Run capture / AI

- Priorita' alta alla prossima ripresa:
  - trovare il vero `total_damage` e il vero `damage_by_champion` dentro il payload raw `battleResults`
  - il dato danno resta essenziale e ancora non e' stato mappato correttamente ai numeri UI
  - lavorare partendo da run note con valore a schermo conosciuto, confrontando i campi numerici del raw fino a identificare la corrispondenza corretta
- Chiudere il live ingest automatico nel DB
- Correggere il decoder `damage_by_champion`
- Importare metriche finali trusted quando disponibili
- Espandere eventualmente timeline eventi e reason tracing

### Modello danno diretto

- Importato come riferimento il foglio `Delta89_CalcoloDanno_RSL.xlsx` fornito dall'utente.
- Il workbook e' stato verificato staticamente:
  - nessuna macro
  - nessun external link
  - nessuna connection
  - un solo foglio `Danno D89`
- Il foglio e' utile come modello teorico del danno diretto da skill:
  - stat offensiva scalata da base, gear, libri, maestrie e bonus account
  - crit damage e buff offensivi
  - mitigazione sulla difesa finale del bersaglio
- Il foglio non basta invece per derivare il danno finale UI di una run:
  - non modella tick ritardati da `Poison` o `HP Burn`
  - non modella attributi temporali come uptime scudi, `Ally Protect`, `Leech`, `Lifesteal`
  - non sostituisce il mapping trusted del raw `battleResults`
- Dal foglio ricaviamo pero' una base riusabile per:
  - stimare il danno atteso delle skill dirette
  - confrontare la plausibilita' dei numeri manuali
  - costruire piu' avanti un simulatore encounter-aware per Clan Boss

### Decoder eventi raw

- Nei `battleResults` esiste anche un log eventi raw in `root.r.c`.
- Per i membri del team giocatore:
  - `event.s.p.h` segue lo slot sorgente del campione
  - `event.s.s` contiene un codice che mappa alla skill usata
- Pattern verificato:
  - `event_code // 100 == champion_type_id // 10`
  - `event_code % 100 == skill_order`
- Esempio reale verificato su una run Dragon:
  - `62002` = Ninja `A2`
  - `69003` = Yumeko `A3`
  - `58301` = Jintoro `A1`
  - `21604` = Valkyrie `A4`
- Questo non risolve ancora il `damage_by_champion`, ma apre una strada forte:
  - contare quante volte ogni skill viene usata
  - confrontare il danno diretto teorico atteso con i log della run
  - separare meglio contributi diretti e indiretti

## 2026-03-25 - Demon Lord: totale run chiuso, heal ancora aperto

### Confermato

- Sessione probe `20260325T173527Z` con due run `Demon Lord. Ultra-Nightmare` spirit:
  - `afad85e9-4c1c-4fd0-a8fe-fc5aa7bf6368`
  - `fbbbae7e-58d1-461e-8660-7c86297796c8`
- Il `total_damage` della run e' recuperabile dal raw `battleResults` in `s.a.dt` come fixed-point:
  - decoder pratico: `s.a.dt >> 32`
  - status salvato: `candidate_demon_lord_s_a_dt_high32`
- Confronto run 2:
  - screen: `41,949,623`
  - raw: `41,949,610`
  - differenza: `13`
- Confronto run 1:
  - cumulativo utente dopo run 1 + run 2: `85,470,000`
  - run 1 inferita da differenza: `43,520,377`
  - raw run 1: `43,522,952`
  - differenza: `2,575`
- `damage_taken` per campione resta affidabile da `member.dt >> 32` e coincide con la linea blu della schermata risultato.

### Stato del danno per campione

- Per il team Demon Lord noto e' stato cablato un `damage_done` per campione come `candidate`, non `trusted`.
- La stima attuale usa pesi specifici per campione normalizzati sul `total_damage` della run.
- Status salvato: `candidate_demon_lord_manual_fit_normalized_total`
- Questo e' utile in UI e DB come diagnostica, ma non va ancora trattato come valore canonicale generale.
- Se cambia team, il mapping attuale non va applicato alla cieca.

### Stato delle cure

- Il `healing_done` non ha ancora un mapping trusted nel payload `battleResults`.
- Punto importante verificato con l'utente:
  - il numero verde finale include sia cure da skill sia sustain da set, per esempio `Lifesteal` su `Ninja` e `Jintoro`
- I campi raw sembrano distribuire il sustain su bucket multipli, non su una singola chiave pulita analoga a `dt`.
- Quindi oggi non va importato nessun `healing_done` candidato come se fosse affidabile.

### Prossimo focus operativo

- Analizzare buff/debuff nel raw con timeline strutturata per turno.
- Obiettivi principali:
  - chi applica cosa
  - su quale target
  - `placed`, `extended`, `resisted`, `blocked`
  - uptime per buff/debuff chiave
- Per Clan Boss interessano in particolare:
  - `Decrease DEF`
  - `Weaken`
  - `Increase DEF`
  - `Counterattack`
  - `Block Debuffs`
  - eventuali effetti tipo `Ally Protect`

## Roadmap operativa 2026-03-24

### Done

- Documento unico consolidato in `APPUNTI.md`
- Roadmap HellHades unificata e resa non divergente
- Provider abstraction introdotta
- `local_registry` e `ayumilove` gia' integrati nel flusso skill
- Pipeline `probe session -> run_history_*` esistente
- Cattura locale delle run funzionante con asset raw salvati
- Primo foglio manuale per danno per campione creato in `data_sources/manual_battle_damage_notes.md`
- Pagina optimizer con boss/affinita'/livello, team proposto, coverage, rischi e build planner collegato
- Pagina run ripulita con segnali leggibili per campione e raw spostato in debug
- Persistenza `skill_usage` da `battleResults` nel DB e in UI
- Persistenza `total_damage` candidato Demon Lord da `s.a.dt >> 32` nel DB
- Modello teorico del danno diretto derivato dal foglio `Delta89`
- Correzione pipeline gear/accessori del 24 marzo 2026:
  - confermato che nel dump HH `Kind 8 = amulet` e `Kind 9 = banner`
  - corretto il bridge legacy, il normalizer e il repair DB
  - separato il mapping dei `Kind` stat per gli accessori dal mapping artifact normale
  - rigenerati `input/raw_account.json` e `input/normalized_account.json`
  - ricostruito il DB
  - caso sentinella `Maneater` riallineato:
    - item `25944` ora e' `amulet`
    - `main_stat = crit_dmg 40`
    - `substats = atk 19 / def 81 / acc 21 / hp 522`
  - caso sentinella `27391` riallineato:
    - item `27391` ora e' `banner`
    - `main_stat = acc 96`
    - `substats = hp% 6 / def 40 / spd 16 / atk% 7`
  - il planner ora esclude e segnala i pezzi con decode impossibile invece di mostrarli come validi

### Next

- Trovare il mapping trusted tra payload raw `battleResults` e danni UI per campione
- Tenere il `damage_done` Demon Lord attuale come `candidate`, non come verita' canonica
- Formalizzare un piccolo dataset di run note con:
  - `battle_id`
  - danni manuali per campione
  - path del miglior snapshot raw
- Formalizzare anche un dataset manuale con `damage_taken` e `healing_done` da schermata quando disponibili
- Trovare il mapping trusted del `healing_done`, tenendo conto che il verde finale include sia skill sia set come `Lifesteal`
- Costruire timeline buff/debuff strutturata da `root.r.c`
- Quando il mapping torna, importare `member_damage` e `healing_done` trusted nel DB e nella UI run
- Ricontrollare i totali build/stats reali su un piccolo set sentinella dopo il fix accessori
- Estendere la diagnostica gear sospetto anche alla pagina gear/account, non solo optimizer

### Later

- Chiudere il live ingest automatico nel DB senza import manuale
- Portare avanti `run_registry.json` e resolver encounter/affinity
- Rafforzare il registry locale skill fino a ridurre davvero il bisogno di fallback esterni
- Affrontare l'import account locale senza bridge HellHades
- Tenere le live actions come modulo opzionale finche' non c'e' una strada locale stabile

## Nota finale

Il progetto e' passato da:

- base dati minima
- enrichment roster e gear
- decoupling provider
- build/stat piu' affidabili
- modellazione encounter-specifica
- cattura reale delle run locali
- primo inserimento run storico nel DB

La direzione corretta ormai e':

- consolidare il catalogo encounter
- migliorare la qualita' del dato run
- usare lo storico account-specifico per planner e AI di ottimizzazione
