# HellHades Decoupling Plan

## Obiettivo

Rendere CB Forge utilizzabile senza dipendere da HellHades per:

- import del roster account
- import dell'inventario gear
- registry campioni e skill
- azioni live sul gioco

L'obiettivo finale e' che HellHades, se resta, sia solo un provider opzionale e non un componente necessario al funzionamento del progetto.

## Stato attuale

Oggi la dipendenza da HellHades e' divisa in tre blocchi distinti.

### 1. Enrichment skill e metadata

File coinvolti:

- `hellhades_enrich.py`
- `registry_report.py`
- `cbforge_web.py`

Uso attuale:

- match dei campioni via ricerca remota
- fetch skill e cooldown via endpoint remoti
- parsing descrizioni per estrarre effetti strutturati

### 2. Bridge account / inventory

File coinvolti:

- `old/legacy_20260318/cbforge_extractor/hellhades_bridge.py`
- `old/legacy_20260318/cbforge_extractor/snapshot.py`
- `old/legacy_20260318/extract_local.py`
- `cbforge_web.py` (`refresh_gear_from_game`)

Uso attuale:

- lettura del roster account e degli artifact tramite bridge legato a `hh_reader_bridge`
- fetch di metadata campioni da `raidoptimiser.hellhades.com/api/StaticData/hero_types`

### 3. Live operations

File coinvolti:

- `hellhades_live.py`
- `cbforge_web.py`

Uso attuale:

- vendita artifact via helper live
- equip artifact via helper live
- token e SignalR appoggiati a infrastruttura HellHades

## Cosa possiamo gia' fare senza HellHades

Esiste gia' una base utile lato locale:

- lettura file locali del client
- lettura `raid.db` e `raidV2.db`
- analisi di file `battleResults`
- osservazione runtime del processo RAID

File principali:

- `old/legacy_20260318/cbforge_extractor/snapshot.py`
- `old/legacy_20260318/cbforge_extractor/runtime.py`
- `old/legacy_20260318/cbforge_extractor/memory.py`

Questo significa che l'indipendenza e' realistica, ma richiede di sostituire il bridge account e il layer live, non di inventare tutto da zero.

## Architettura target

CB Forge dovrebbe convergere a questa struttura:

### A. Runtime locale

Responsabilita':

- leggere il client RAID locale
- produrre snapshot raw locali
- leggere file, DB locali e runtime process

Modulo target:

- `raid_local_runtime.py`
- oppure package `raid_local/`

### B. Importer account locale

Responsabilita':

- costruire `normalized_account.json` senza bridge HellHades
- ricavare roster, inventory, bonus e ownership

Modulo target:

- `raid_account_import.py`

### C. Registry locale campioni / skill

Responsabilita':

- mantenere catalogo campioni
- skill canonicali
- cooldown
- effetti strutturati
- aliases e mapping nomi

Moduli / dati target:

- `champion_registry.py`
- `data_sources/champion_registry.json`
- tabelle SQLite dedicate a registry locale

### D. Provider abstraction

Responsabilita':

- permettere piu' sorgenti esterne o locali
- normalizzare output in un formato unico

Moduli target:

- `enrichment_sources.py`
- `providers/hellhades_provider.py`
- `providers/local_registry_provider.py`

### E. Live actions adapter

Responsabilita':

- isolare la logica di equip / sell
- permettere piu' backend

Moduli target:

- `live_actions.py`
- `providers/hellhades_live_provider.py`
- futuro `providers/local_game_bridge.py`

## Piano a fasi

## Fase 1. Disaccoppiare il modello dati dal provider

Stato:

- avviata nel branch `feature/decouple-from-hellhades`

Task:

- usare nel report concetti provider-neutral
- usare in UI concetti come `data_status`
- valorizzare `source` per i dati skill
- smettere di considerare `hellhades_post_id` come criterio centrale di completezza

Esito atteso:

- il progetto sa distinguere dati mancanti, parziali e completi senza parlare in termini di HellHades

## Fase 2. Introdurre il layer provider astratto

Task:

- definire un'interfaccia unica per:
  - resolve_champion
  - fetch_skills
  - normalize_skill_payload
- spostare la logica HellHades dentro un provider dedicato
- fare in modo che `hellhades_enrich.py` non sia piu' il centro del sistema

Esito atteso:

- HellHades diventa un adapter sostituibile

## Fase 3. Creare un registry locale persistente

Task:

- esportare nel registry locale tutti i dati skill gia' presenti nel DB
- introdurre aliases campione
- introdurre una fonte canonicale locale per skill ed effetti
- permettere correzioni manuali locali

Esito atteso:

- il progetto puo' continuare a lavorare anche offline sui dati gia' acquisiti

## Fase 4. Sostituire il bridge account / inventory

Task:

- analizzare quali dati arrivano gia' dai file/DB locali
- ricostruire roster e inventory senza `hh_reader_bridge`
- costruire un importer locale equivalente a `normalize.py`
- eliminare la dipendenza da `raidoptimiser.hellhades.com/api/StaticData/hero_types`

Esito atteso:

- `normalized_account.json` e il DB possono essere rigenerati senza bridge HellHades

## Fase 5. Gestire le live actions

Task:

- isolare l'interfaccia di equip / sell
- decidere se:
  - implementare un bridge locale alternativo
  - oppure rendere queste funzioni opzionali e disattivabili

Esito atteso:

- il progetto non dipende da HellHades per funzionare; al massimo alcune azioni live restano plugin opzionali

## Priorita' pratica

Ordine consigliato:

1. provider abstraction per l'enrichment
2. registry locale skill
3. importer account locale senza bridge HellHades
4. solo dopo: live actions

Motivo:

- enrichment e skill sono piu' facili da sostituire
- il bridge account richiede reverse engineering locale piu' profondo
- le live actions sono il pezzo piu' fragile e possono restare opzionali piu' a lungo

## Criteri di successo

Consideriamo completato il distacco quando:

- il DB si puo' ricostruire senza chiamate HellHades
- roster e inventory arrivano da sorgenti locali
- skill e cooldown arrivano da registry locale o provider opzionali
- il report non usa piu' metriche HellHades-specifiche
- la UI non presuppone HellHades come sorgente primaria
- l'assenza di token/accesso HellHades non blocca il progetto

## Rischi reali

- il bridge account locale potrebbe richiedere reverse engineering non banale
- i metadata campioni potrebbero essere incompleti senza una fonte esterna iniziale
- alcune live actions potrebbero non essere replicabili facilmente senza tooling esterno

Per questo il target corretto e':

- indipendenza funzionale completa per import, DB, analisi e planner
- eventuale live control trattato come modulo opzionale

## Prossimo step concreto

Il prossimo lavoro tecnico consigliato e':

- introdurre un modulo provider astratto per l'enrichment skill

Primo taglio minimo:

- creare `enrichment_sources.py`
- definire una interfaccia provider unica
- spostare la logica attuale di HellHades in un provider dedicato
- far consumare a `cbforge_web.py` e ai job di enrichment solo l'interfaccia astratta
