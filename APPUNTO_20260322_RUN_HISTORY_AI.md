APPUNTO 2026-03-22 - RUN HISTORY DB PER AI

OBIETTIVO
Costruire uno storico run che serva subito per analisi pratiche del tuo account e piu' avanti come base dati per un optimizer AI.

PRINCIPIO
Il DB non deve salvare solo "la run e' andata bene o male".
Deve separare:
- contesto encounter
- team reale usato
- stato/build dei membri
- metriche finali osservate
- asset raw collegati
- eventuale timeline eventi

PERCHE' QUESTO SERVE ALL'AI
Per allenare bene un modello, ogni run deve produrre:
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

SCHEMA BASE AGGIUNTO
- run_history_runs
  - una riga per run
  - contiene contesto encounter, risultato e label globali
- run_history_members
  - un membro per slot
  - contiene identita' e snapshot leggero del champ usato
- run_history_member_stats
  - stats numeriche per membro
  - utile per training senza dover parsare JSON
- run_history_member_metrics
  - danno fatto/subito, heal, morti, revive, stato finale
- run_history_assets
  - collega la run ai file raw come battleResults, probe dump, snapshot
- run_history_events
  - timeline opzionale
  - oggi puo' contenere feed sintetici, domani anche eventi piu' granulari

COSA POSSIAMO FARE SUBITO CON QUESTO DB
- ranking dei team reali per encounter
- confronto build per lo stesso contenuto
- suggerimenti basati su storico account-specifico
- dataset supervisionato per stimare:
  - probabilita' di successo
  - tempo run
  - danno atteso
  - contributo medio dei singoli champ

COSA MANCA ANCORA
- per-hit damage esplicito
- buff/debuff timeline strutturata
- reason tracing fine del tipo "perde per mancanza uptime"

QUINDI
Questa base e' gia' sufficiente per una AI di ottimizzazione macro:
- scegliere quali champ usare
- scegliere quali team provare
- preferire build che massimizzano successo/tempo/danno

Non e' ancora sufficiente per una AI tattica micro completa, ma e' il passo giusto da fare adesso.
