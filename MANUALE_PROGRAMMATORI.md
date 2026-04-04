# Manuale Programmatori CB Forge

Documento tecnico iniziale per orientarsi nel progetto. Non sostituisce il codice, ma serve a rispondere rapidamente a quattro domande:

1. da dove si parte
2. quale modulo usare
3. come richiamarlo
4. cosa produce

## Punto di partenza consigliato

Se devi capire il progetto da zero, il percorso migliore oggi e' questo:

1. `README.md`
   Ti dice cosa fa CB Forge a livello prodotto.
2. `cbforge_web.py`
   Ti mostra il runtime principale: pagine, API, bootstrap del server e punti di integrazione.
3. `forge_db.py`
   Ti dice qual e' il modello dati canonico e come viene popolato `data/cbforge.sqlite3`.
4. `account_stats.py`
   Ti spiega come vengono derivate le stats reali quando il dump non basta.
5. `run_history_importer.py`
   Ti mostra la pipeline piu importante lato recorder: da sessione probe a run storicizzata nel DB.
6. `team_optimizer.py` e `clan_boss_simulator.py`
   Ti fanno vedere dove stiamo andando lato Clan Boss: selezione team e simulazione turn order.

## Architettura pratica

CB Forge oggi e' composto da cinque blocchi:

- ingest account: importa `input/normalized_account.json` nel DB SQLite
- enrichment catalogo: completa skill e metadata campioni con provider esterni o locali
- runtime web: espone UI locale e API JSON
- run recorder pipeline: trasforma sessioni live in storico run interrogabile
- tools decisionali: gear advisor, build planner, optimizer e simulatore Clan Boss

## Convenzioni di progetto

- DB runtime canonico: `data/cbforge.sqlite3`
- sorgente account canonica in input: `input/normalized_account.json`
- i JSON non sono il database applicativo
- la web app locale gira tramite `cbforge_web.py`
- quando possibile i moduli restituiscono `dict[str, Any]` serializzabili in JSON
- i file `test_*.py` sono la specifica eseguibile piu affidabile per i comportamenti stabilizzati

## Moduli core

### `build_databases.py`

Serve a lanciare il bootstrap completo del DB senza passare dalla web UI.

- Quando usarlo: quando hai aggiornato `input/normalized_account.json` e vuoi ricostruire o riallineare il database.
- Come richiamarlo: `python build_databases.py`
- Chi chiama: `forge_db.bootstrap_database()`
- Produce: un summary JSON stampato su stdout con contatori di import e stato finale.

### `forge_db.py`

E' il modulo piu importante sul piano dati. Definisce percorsi base, schema SQLite, import del dump account e vari helper di persistenza.

- Quando usarlo: ogni volta che devi capire dove stanno i dati, come sono modellati e come vengono salvati.
- Come richiamarlo:
  - come script: `python forge_db.py`
  - come libreria: `bootstrap_database()`, `ensure_schema()`, `record_run_history()`
- Produce:
  - tabelle runtime nel DB
  - summary di bootstrap
  - persistenza per roster, gear, bonus account, run history e timeline

### `account_stats.py`

Calcola le stats reali dei campioni quando il dump non contiene `total_stats` affidabili.

- Quando usarlo: quando devi capire da dove arrivano `hp`, `def`, `spd`, `acc`, `res`, `crit_rate`, `crit_dmg` mostrati in UI o usati nei planner.
- Come richiamarlo:
  - come libreria: `build_stat_computation(...)`, `materialize_base_totals(...)`
- Produce:
  - `StatComputationResult`
  - `total_stats`
  - `base_totals`
  - metadata su `source`, `completeness`, `unsupported_sets`, `applied_sets`

### `registry_report.py`

Costruisce il report compatto sullo stato del catalogo e dei target arricchiti.

- Quando usarlo: per audit rapido dopo bootstrap o enrichment.
- Come richiamarlo:
  - script: `python registry_report.py`
  - libreria: `build_registry_report()`
- Produce: un report JSON con numeri di catalogo, target e copertura enrichment.

## Web runtime

### `cbforge_web.py`

E' il server HTTP locale. Contiene routing pagine, endpoint API, helper di query e bootstrap runtime.

- Quando usarlo: sempre, se stai lavorando sulla UI o vuoi capire quali funzioni sono gia' esposte come API.
- Come richiamarlo:
  - script: `python cbforge_web.py`
  - launcher Windows consigliato: `.\start_cbforge_web.ps1`
  - wrapper da doppio click: `start_cbforge_web.bat`
  - opzioni utili: `--host`, `--port`, `--db-path`, `--source-path`, `--skip-startup-refresh`
- Produce:
  - server web locale
  - pagine HTML statiche sotto `web/`
  - endpoint JSON per roster, gear, planner, run history, optimizer e Clan Boss simulator

Nota runtime:

- il launcher Windows risolve i casi in cui `python` e `py` puntano a interpreti diversi
- prova prima `Python 3.11`, poi altri interpreti noti, e installa le dipendenze mancanti sullo stesso Python che usera' per il server

Punti da conoscere:

- `prepare_server_runtime(...)`: riallinea il DB all'avvio
- `list_owned_champions(...)`: roster deduplicato per UI
- `champion_detail(...)`: dettaglio campione
- `build_team_optimizer_view(...)`: vista optimizer
- `build_clan_boss_simulator_bootstrap(...)`: bootstrap del simulatore Clan Boss
- `build_ai_training_overview(...)`: overview di training AI e stato modelli
- `train_ai_baseline_model(...)`: training del baseline AI lanciato dalla UI

### `web/`

Qui stanno le pagine statiche e il frontend puro.

- Quando usarlo: quando lavori sulla UX o sui flussi utente.
- Come richiamarlo: non direttamente; viene servito da `cbforge_web.py`
- Produce: HTML, CSS e JS per le pagine locali.

Pagine principali oggi:

- `/` roster
- `/gear`
- `/build`
- `/optimizer`
- `/clan-boss`
- `/ai-lab`
- `/runs`
- `/sets`

## Enrichment skill e provider

### `enrichment_sources.py`

Definisce il contratto comune dei provider di enrichment skill.

- Quando usarlo: se devi aggiungere un provider nuovo o cambiare il provider order.
- Come richiamarlo: come libreria tramite `register_skill_enrichment_provider(...)` e `get_skill_enrichment_provider(...)`
- Produce:
  - registry in memoria dei provider
  - protocollo `SkillEnrichmentProvider`
  - dataclass `ChampionSkillMatch`

### `hellhades_enrich.py`

Esegue enrichment dei campioni target e scrive skill/cooldown/metadata nel DB usando il provider selezionato.

- Quando usarlo: per popolare o riallineare il catalogo skill.
- Come richiamarlo:
  - `python hellhades_enrich.py`
  - `python hellhades_enrich.py --provider auto`
- Produce:
  - update di `champion_catalog`
  - righe in `champion_skills`
  - righe in `champion_skill_effects` quando il provider le sa estrarre
  - summary di enrichment

### `build_local_skill_registry.py`

Esporta un registry locale versionabile a partire dal DB arricchito.

- Quando usarlo: dopo un enrichment riuscito, per congelare una base locale riusabile.
- Come richiamarlo: `python build_local_skill_registry.py`
- Produce: `data_sources/local_skill_registry.json`

### `game_data_probe.py`

Fa audit delle sorgenti locali e della copertura registry.

- Quando usarlo: quando vuoi verificare se il client RAID locale e i bundle disponibili possono essere sfruttati meglio.
- Come richiamarlo: `python game_data_probe.py`
- Produce: un report JSON su presenza client, bundle, versioni e copertura.

### `hellhades_live.py`

Contiene integrazione live con HellHades e helper usati dal runtime o da automazioni locali.

- Quando usarlo: quando devi recuperare o sincronizzare dati HellHades in un flusso operativo e non solo di enrichment catalogo.
- Come richiamarlo: come libreria dai moduli runtime.
- Produce: payload intermedi e operativi legati al bridge HellHades.

### `providers/local_registry_provider.py`

Provider primario. Legge `data_sources/local_skill_registry.json`.

- Quando usarlo: per avere enrichment deterministico e offline-friendly.
- Come richiamarlo: viene registrato automaticamente quando il modulo viene importato.
- Produce:
  - match campione dal registry locale
  - skill list strutturata per il campione richiesto

### `providers/ayumilove_provider.py`

Provider HTML scraper da AyumiLove.

- Quando usarlo: come fallback quando il registry locale non copre il campione.
- Come richiamarlo: via provider order in `hellhades_enrich.py`
- Produce:
  - match campione da URL/search
  - skill parseate da pagina guida

### `providers/hellhades_provider.py`

Provider API-driven da HellHades.

- Quando usarlo: come fallback esterno quando i provider precedenti non bastano.
- Come richiamarlo: via provider order in `hellhades_enrich.py`
- Produce:
  - match campione da search endpoint
  - payload skill da endpoint HH skills

## Planner e motori decisionali

### `gear_advisor.py`

Valuta un singolo pezzo gear e assegna un verdetto operativo.

- Quando usarlo: per sorting inventario, sell queue e priorita upgrade.
- Come richiamarlo: `evaluate_gear_item(item, substats)`
- Produce:
  - `verdict`
  - score intermedi
  - reasons leggibili

### `build_planner.py`

Genera proposte build per un campione in un contesto specifico.

- Quando usarlo: quando vuoi passare da "questo campione esiste" a "come dovrebbe essere buildato".
- Come richiamarlo: `build_champion_plan(champion_name, profile_key=..., area_region=...)`
- Produce:
  - build corrente
  - lista di proposte
  - score, swap count, scope e coerenza set

### `team_optimizer.py`

Sceglie un team candidato per un boss, oggi soprattutto `Demon Lord`.

- Quando usarlo: quando vuoi una proposta team-level prima del simulatore.
- Come richiamarlo:
  - libreria: `build_team_optimizer_report(...)`
  - supporto UI: `list_team_optimizer_targets()`
- Produce:
  - target effettivo
  - `selected_team`
  - copertura ruoli
  - rischi e panchina utile

### `local_game_bridge.py`

Trasforma un loadout team in un piano manuale di equip piu leggibile.

- Quando usarlo: quando il risultato dell'optimizer deve diventare una sequenza di azioni.
- Come richiamarlo: `build_team_equip_plan(team_loadout)`
- Produce:
  - lista `steps`
  - `member_blocks`
  - summary di swap, free equip e conflitti

### `damage_model.py`

Modello matematico piccolo e isolato per stimare danni diretti.

- Quando usarlo: quando vuoi fare esperimenti di formula senza toccare il simulatore globale.
- Come richiamarlo: `estimate_direct_skill_damage(...)`
- Produce: un valore numerico di danno stimato post mitigazione.

### `set_curation.py`

Gestisce la curation locale dei set, soprattutto per normalizzare nomi, alias e scelte di esposizione.

- Quando usarlo: quando devi correggere come i set vengono presentati o interpretati.
- Come richiamarlo: funzioni come `load_local_set_entries()` e `save_local_set_entry()`
- Produce:
  - registry locale dei set curati
  - salvataggi usati da UI e motori di calcolo

## Clan Boss

### `clan_boss_simulator.py`

Prima implementazione del simulatore Clan Boss turno per turno.

- Quando usarlo: dopo il `team_optimizer`, per capire se la tune regge davvero nella finestra osservata.
- Come richiamarlo:
  - come libreria: `simulate_clan_boss_battle(payload)`
  - via API: `POST /api/clan-boss-simulate`
- Produce:
  - `summary`
  - `warnings`
  - `boss_turns`
  - `timeline`
  - `team_state`

Modella oggi:

- speed race deterministica
- speed aura
- cycle boss `AoE 1 / AoE 2 / Stun`
- `Decrease ATK`
- `Decrease DEF`
- `Weaken`
- `Poison`
- `HP Burn`
- `Block Debuffs`
- `Increase DEF`
- `Ally Protect`
- `Counterattack`
- `Increase SPD`
- `Shield`
- `Unkillable`
- `Strengthen`
- `Cleanse`
- `Turn Meter Fill`

Non modella ancora:

- AI avanzata reale del gioco
- targeting affinity preciso
- danno finale realistico
- mastery e set in combattimento

### `ml_team_baseline.py`

Prima baseline AI del progetto. Non e' una rete neurale: e' un modello supervisionato tabellare addestrato sulle run storiche.

- Quando usarlo: quando hai gia' raccolto run reali in `run_history_*` e vuoi un primo scorer data-driven dei team.
- Come richiamarlo:
  - script: `python ml_team_baseline.py --encounter demon_lord_ultra_nightmare --output models/demon_lord_ultra_nightmare_team_baseline_v1.joblib`
  - libreria: `build_supervised_rows(...)`, `train_team_baseline(...)`, `train_from_database(...)`
- Produce:
  - righe featureizzate per training
  - modello `.joblib`
  - metriche base di training o holdout
  - top feature importances del regressore

Feature v1:

- contesto encounter
- team signature
- presenza campioni
- conteggi ruoli/tag
- conteggi set
- stats aggregate team-level
- booked ratio
- medie di rank, level, awakening, empowerment

Target v1:

- `total_damage` come regressione
- `success` come classificazione quando il dataset ha almeno due classi

### `web/ai-lab.html` e `web/ailab.js`

UI web per allenare il baseline AI senza passare dalla console.

- Quando usarlo: quando vuoi allenare o ri-allenare il modello dal browser.
- Come richiamarlo: aprendo `/ai-lab`
- Produce:
  - overview degli encounter allenabili
  - stato dei modelli in `models/`
  - training on-demand del baseline
  - metriche e feature importances dell'ultimo training

## Pipeline run recorder

### `live_storage_probe.py`

Watcher su storage live per catturare materiale utile dal client.

- Quando usarlo: quando vuoi raccogliere sessioni raw da importare dopo.
- Come richiamarlo: `python live_storage_probe.py`
- Produce: sessioni sotto `input/live_storage_probe/...`

### `client_run_probe.py`

Probe piu basso livello per eventi e payload dal client, compresi helper di decode binario.

- Quando usarlo: quando devi capire il formato dei file o fare reverse engineering di payload compressi.
- Come richiamarlo: `python client_run_probe.py`
- Produce:
  - sessioni probe
  - helper come `decode_msgpack_best_effort(...)`
  - helper come `try_decompress_lz4_block_array(...)`

### `deep_battle_probe.py`

Watcher/collector orientato alla battaglia, piu ricco del probe base.

- Quando usarlo: quando vuoi sessioni piu complete per analisi di run.
- Come richiamarlo: `python deep_battle_probe.py`
- Produce: sessioni di osservazione battle-centriche.

### `battle_results_burst_probe.py`

Collector specializzato per burst di `battleResults`.

- Quando usarlo: quando serve intercettare e salvare rapidamente i burst relativi ai risultati battaglia.
- Come richiamarlo: `python battle_results_burst_probe.py`
- Produce: dump session-based orientati ai file risultato.

### `run_mapper.py`

Ricostruisce il contesto encounter a partire da battle context, stage id e type metadata.

- Quando usarlo: quando una run va classificata in `encounter_key`, famiglia, affinity e difficulty.
- Come richiamarlo: `derive_run_mapping(battle_context, sqlite_row=...)`
- Produce:
  - `encounter_key`
  - `encounter_name`
  - `encounter_family`
  - `game_mode`
  - `difficulty`
  - `boss_affinity`
  - `mapping_confidence`

### `run_damage_decoder.py`

Decodifica metriche principali da `battleResults`.

- Quando usarlo: quando hai un file raw `battleResults` e vuoi estrarre total damage, candidate member metrics e struttura base.
- Come richiamarlo:
  - script: `python run_damage_decoder.py ...`
  - libreria: `extract_damage_summary(path)`, `extract_member_result_rows(path)`
- Produce:
  - summary danni
  - member rows
  - stato `trusted` o `candidate` delle metriche

Nota importante:

- per Clan Boss il `total_damage` e' il candidato piu forte
- il blu `damage_taken` Clan Boss oggi resta candidato, non trusted

### `battle_event_decoder.py`

Estrae segnali evento-level dalla stessa raw run.

- Quando usarlo: quando non basta il totale e vuoi sapere skill usage o chi e' stato targettato.
- Come richiamarlo:
  - `extract_skill_usage_counts(path)`
  - `extract_incoming_target_counts(path)`
- Produce:
  - conteggi skill per membro
  - conteggi incoming target per membro

### `run_effect_timeline.py`

Genera una timeline buff/debuff candidata a partire da `battleResults`.

- Quando usarlo: quando vuoi una vista temporale degli effetti e non solo metriche aggregate.
- Come richiamarlo:
  - script: `python run_effect_timeline.py --raw <file>`
  - libreria: `extract_effect_timeline(...)`
- Produce: righe timeline effetto-oriented, salvabili anche nel DB.

### `run_history_importer.py`

Trasforma una sessione probe in record storici persistiti nel DB.

- Quando usarlo: e' il punto di ingresso principale della pipeline run recorder.
- Come richiamarlo:
  - script: `python run_history_importer.py`
  - libreria: `import_probe_session(...)`, `import_probe_sessions(...)`
- Produce:
  - record in `run_history_runs`
  - membri run
  - metriche aggregate
  - snapshot build/stats
  - effect timeline

## Moduli di supporto

### `battle_event_decoder.py`, `run_damage_decoder.py`, `run_effect_timeline.py`

Questi tre moduli lavorano bene insieme:

- `run_damage_decoder.py` risponde a "quanto e' successo"
- `battle_event_decoder.py` risponde a "chi ha fatto cosa"
- `run_effect_timeline.py` risponde a "quando si sono visti gli effetti"

### `enrichment_sources.py` + `providers/`

Questo e' il nucleo dell'astrazione provider-first. Se cambi ordine provider o aggiungi una sorgente nuova, parti da qui.

## Test

### `test_*.py`

Ogni modulo importante ha il suo test file dedicato. La convenzione e' diretta:

- `test_forge_db.py` per bootstrap/schema/import
- `test_cbforge_web.py` per API/helper web
- `test_team_optimizer.py` per optimizer
- `test_run_history_importer.py` per pipeline run history
- `test_run_damage_decoder.py` per decode metriche
- `test_clan_boss_simulator.py` per il nuovo simulatore

Quando aggiungi un modulo nuovo, la regola pratica e' aggiungere anche un `test_<modulo>.py`.

## Comandi consigliati per sviluppatori

Bootstrap DB:

```bash
python build_databases.py
```

Enrichment provider-first:

```bash
python hellhades_enrich.py --provider auto
```

Avvio web:

```bash
python cbforge_web.py
```

Import run recorder:

```bash
python run_history_importer.py
```

Test rapidi:

```bash
pytest -q
```

## Stato del manuale

Questo e' il primo passaggio del manuale. La struttura c'e' gia', ma nei prossimi aggiornamenti va approfondita almeno in tre direzioni:

- schema DB e tabelle principali con relazioni
- contratti JSON delle API web piu usate
- walkthrough completi per i flussi:
  - bootstrap account
  - enrichment
  - import run
  - optimizer
  - simulatore Clan Boss
