# CB Forge

CB Forge e' un toolkit locale per analizzare un account di Raid: Shadow Legends a partire da un dump normalizzato, salvarlo in un database SQLite relazionale e costruire strumenti pratici sopra quei dati.

L'obiettivo del progetto non e' usare i JSON come database applicativo, ma avere una base dati pulita su cui fare analisi roster, valutazione equip, proposte di build e, piu' avanti, ragionamenti specifici per Clan Boss.

## Cosa fa oggi

- importa `input/normalized_account.json` dentro `data/cbforge.sqlite3`
- mantiene catalogo campioni, roster account, skill, gear, bonus account e set in tabelle relazionali
- ricalcola le stats reali dei campioni a runtime invece di fidarsi delle `total_stats` del dump
- distingue tra stats importate e stats derivate, con metadata sulla completezza del calcolo
- espone una web UI locale per:
  - roster account
  - dettaglio campione
  - inventario gear
  - dettaglio pezzo
  - build planner
- integra enrichment HellHades per skill, cooldown e metadata dei campioni target
- include un gear advisor che aiuta a decidere se un pezzo va:
  - spinto a `+12`
  - spinto a `+16`
  - tenuto
  - rivisto
  - venduto
- include un primo build planner con profili come:
  - `arena_speed_lead`
  - `debuffer_acc_spd`
  - `support_tank`
  - `arena_nuker`

## Flusso principale

1. acquisire o aggiornare `input/normalized_account.json`
2. costruire o aggiornare il database SQLite
3. opzionalmente arricchire i campioni target tramite HellHades
4. aprire la web UI locale per consultare roster, gear e proposte di build

## Comandi utili

Bootstrap database:

```bash
python build_databases.py
```

Enrichment HellHades:

```bash
python hellhades_enrich.py
```

Export registry skill locale:

```bash
python build_local_skill_registry.py
```

Avvio web UI locale:

```bash
python cbforge_web.py
```

Test:

```bash
pytest -q
```

Pagine principali:

- roster: `http://127.0.0.1:8765/`
- gear: `http://127.0.0.1:8765/gear`
- build planner: `http://127.0.0.1:8765/build`

## Struttura del progetto

- `build_databases.py`: bootstrap del DB
- `forge_db.py`: schema e import dati principali
- `account_stats.py`: calcolo stats account runtime
- `hellhades_enrich.py`: enrichment skill e metadata da HellHades
- `build_local_skill_registry.py`: export del registry skill locale a partire dal DB
- `gear_advisor.py`: logica decisionale sui pezzi gear
- `build_planner.py`: generazione proposte build per campioni
- `cbforge_web.py`: server HTTP locale e API
- `web/`: frontend statico per roster, gear e build planner
- `data_sources/`: sorgenti locali versionabili, incluso il registry skill
- `test_*.py`: suite test

## Stato del progetto

La base architetturale e' pronta:

- database relazionale locale
- import account
- calcolo stats
- enrichment esterno
- UI consultabile
- advisor gear
- planner build

Questo significa che il progetto e' gia' utile per analisi pratiche del roster e dell'inventario, ma e' ancora in una fase di consolidamento dei dati e delle regole.

## Da fare

Priorita' attuali:

- riallineare e stabilizzare il database runtime rispetto agli ultimi enrichment eseguiti
- verificare la copertura reale dei campioni target HellHades nel DB corrente
- ridurre la dipendenza da HellHades fino a poter lavorare anche senza quella sorgente esterna
- ampliare la modellazione dei set speciali ancora trattati come parziali nel motore stats
- migliorare il planner build con piu' profili, vincoli e criteri di scoring
- aggiungere una vista piu' operativa per gli upgrade gear realmente perseguibili
- consolidare la sell queue e il flusso di refresh da sorgente live

Roadmap dedicata:

- vedi `HELLHADES_DECOUPLING_PLAN.md`

Roadmap successiva:

- registry campioni e skill completamente affidabile
- selettore candidati Clan Boss
- builder loadout piu' avanzato
- simulatore turn order
- analisi sinergie team e recommendation engine

## Note

- `data/` contiene il database runtime locale e non dovrebbe essere trattato come sorgente canonica del codice
- `input/` puo' contenere dump sensibili o voluminosi, quindi conviene gestirlo fuori dalla repo
- `old/` e' un archivio locale del codice precedente e resta fuori dalla repo Git
- il progetto e' pensato per lavorare in locale, con iterazioni rapide su dati reali dell'account
