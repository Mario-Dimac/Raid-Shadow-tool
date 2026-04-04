# CB Forge su un Altro PC

Guida pratica per clonare il progetto su un altro computer e usarlo con un account diverso di Raid: Shadow Legends.

## Obiettivo

Questa guida serve per:

- clonare il progetto da Git
- installare le dipendenze minime
- collegare un altro account
- costruire il database locale
- avviare la web UI
- opzionalmente attivare il primo layer AI

## Requisiti

Consigliati:

- Windows 10 o 11
- Python 3.11 o piu recente
- Git
- accesso locale ai file del client di Raid se vuoi usare probe e recorder

## 1. Clonazione repo

```bash
git clone <URL-DEL-REPO> cb-forge
cd cb-forge
```

## 2. Ambiente virtuale

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 3. Installazione dipendenze base

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se vuoi eseguire i test:

```bash
pip install -r requirements-dev.txt
```

Se vuoi usare il primo layer AI:

```bash
pip install -r requirements-ai.txt
```

## 4. Collegare un altro account

CB Forge non usa il DB interno del gioco come database applicativo. Il punto di ingresso canonico e':

- `input/normalized_account.json`

Per usare un altro account hai due strade.

### Strada A - Hai gia' un `normalized_account.json`

Copia il file qui:

- `input/normalized_account.json`

Opzionale:

- `input/raw_account.json`

### Strada B - Vuoi generare i file dal client locale

Se stai lavorando sul PC dove gira Raid, puoi usare i probe locali gia' presenti nel progetto per raccogliere dati raw e poi normalizzarli nel flusso locale che usi abitualmente.

Nota pratica:

- il progetto oggi considera canonico `normalized_account.json`
- se il file non c'e', la parte roster/build/ui non ha abbastanza dati per partire

## 5. Bootstrap del database

Questo comando crea o aggiorna `data/cbforge.sqlite3`:

```bash
python build_databases.py
```

## 6. Enrichment skill

Consigliato dopo il bootstrap:

```bash
python hellhades_enrich.py --provider auto
```

Provider order attuale:

1. `local_registry`
2. `ayumilove`
3. `hellhades`

## 7. Avvio web UI

```bash
python cbforge_web.py
```

Su Windows il modo consigliato e' usare il launcher del progetto, cosi' il server e le dipendenze AI usano sempre lo stesso interprete:

```powershell
.\start_cbforge_web.ps1
```

Esiste anche il wrapper da doppio click:

- `start_cbforge_web.bat`

Se vuoi forzare un interprete specifico:

```powershell
$env:CBFORGE_PYTHON="C:\Program Files\Python311\python.exe"
.\start_cbforge_web.ps1
```

Poi apri:

- roster: `http://127.0.0.1:8765/`
- gear: `http://127.0.0.1:8765/gear`
- build: `http://127.0.0.1:8765/build`
- optimizer: `http://127.0.0.1:8765/optimizer`
- clan boss simulator: `http://127.0.0.1:8765/clan-boss`
- AI Lab: `http://127.0.0.1:8765/ai-lab`
- runs: `http://127.0.0.1:8765/runs`

Se vuoi evitare il refresh iniziale automatico:

```bash
python cbforge_web.py --skip-startup-refresh
```

## 8. Run recorder e probe

Se vuoi importare run reali dal PC locale:

- `client_run_probe.py`
- `deep_battle_probe.py`
- `live_storage_probe.py`
- `run_history_importer.py`

Il punto importante e' questo:

- le run importate finiscono nelle tabelle `run_history_*`
- queste tabelle servono sia per analisi storica sia per il futuro layer AI

## 9. Primo layer AI

Il primo layer AI consigliato nel progetto non e' una rete neurale pesante. E' una baseline tabellare spiegabile basata su:

- composizione team
- stats dei campioni
- contesto encounter
- output reali delle run

Per prepararlo da web:

- apri `http://127.0.0.1:8765/ai-lab`
- scegli l'encounter
- controlla che ci siano almeno 3 run con `total_damage`
- premi `Allena Modello`

Per prepararlo da terminale:

```bash
pip install -r requirements-ai.txt
python ml_team_baseline.py --encounter demon_lord_ultra_nightmare --output models/demon_lord_ultra_nightmare_team_baseline_v1.joblib
```

Questo produce:

- un dataset featureizzato dalle run storiche
- un modello baseline salvato in `models/`

## 10. Verifica rapida

Test:

```bash
pytest -q
```

Controlli minimi utili:

1. `input/normalized_account.json` esiste
2. `python build_databases.py` finisce senza errori
3. `python cbforge_web.py` apre la UI
4. le pagine roster e optimizer mostrano dati reali del nuovo account

Nota pratica:

- se sul PC ci sono piu' Python installati, preferisci `start_cbforge_web.ps1` invece di `python cbforge_web.py`
- il launcher controlla anche le dipendenze di `requirements.txt` e `requirements-ai.txt` sullo stesso interprete che usera' per il server

## Percorsi importanti

- database runtime: `data/cbforge.sqlite3`
- input account canonico: `input/normalized_account.json`
- dump raw opzionale: `input/raw_account.json`
- sorgenti locali skill: `data_sources/`
- frontend: `web/`
- modelli AI baseline: `models/`

## Cosa cambia quando usi un altro account

Cambiano soprattutto:

- roster posseduto
- gear
- bonus account
- run history

Non cambiano:

- schema DB
- web app
- planner
- optimizer
- simulatore Clan Boss
- pipeline AI baseline

## Suggerimento operativo

Per un altro account la sequenza piu pulita e':

1. clonare repo
2. installare requirements
3. mettere `input/normalized_account.json`
4. lanciare `python build_databases.py`
5. lanciare `python hellhades_enrich.py --provider auto`
6. lanciare `python cbforge_web.py`
7. quando hai run sufficienti, allenare `ml_team_baseline.py`
