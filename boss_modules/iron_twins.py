from __future__ import annotations


IRON_TWINS_BOSS_MODULE = {
    "boss_key": "iron_twins",
    "label": "Iron Twins Fortress",
    "category": "Dungeon / Boss PvE",
    "optimizer_status": "active",
    "implemented_in_optimizer": True,
    "team_size": 5,
    "default_level": "stage_15",
    "default_affinity": "void",
    "overview": "Dungeon daily a affinity variabile. Le comp forti qui ruotano su controllo fine, sustain e gestione del pattern punitivo del boss.",
    "levels": [
        {
            "key": "stage_6",
            "label": "Stage 6+",
            "stat_targets": [
                {"label": "Speed floor", "value": "180 SPD", "confidence": "medium", "note": "Baseline progression per far girare support e utility."},
                {"label": "Accuracy floor", "value": "180 ACC", "confidence": "medium", "note": "Serve a far passare Decrease SPD e debuff core."},
                {"label": "Survival lane", "value": "alta priorita", "confidence": "medium", "note": "Scudi, cleanse e sustain pesano gia molto."},
            ],
            "notes": ["Dalle stage medie in poi la semplice nuke comp vale sempre meno."],
        },
        {
            "key": "stage_12",
            "label": "Stage 12+",
            "stat_targets": [
                {"label": "Speed floor", "value": "220 SPD", "confidence": "medium", "note": "Cleanse e buff timing diventano la struttura del run."},
                {"label": "Accuracy floor", "value": "280 ACC", "confidence": "medium", "note": "Decrease SPD e debuff utility devono essere piu stabili."},
                {"label": "Resistance lane", "value": "300 RES", "confidence": "medium", "note": "Le comp resist-based iniziano a diventare interessanti."},
            ],
            "notes": ["Qui conviene distinguere progressione generica da comp dedicate."],
        },
        {
            "key": "stage_15",
            "label": "Stage 15",
            "stat_targets": [
                {"label": "Speed floor", "value": "240 SPD", "confidence": "medium", "note": "Supporti lenti collassano nelle finestre punitive del boss."},
                {"label": "Accuracy floor", "value": "360 ACC", "confidence": "medium", "note": "Per debuff chiave come Decrease SPD e setup utili al team."},
                {"label": "Resistance lane", "value": "450 RES", "confidence": "medium", "note": "Le comp resist-based e alcuni support stage 15 ne beneficiano molto."},
            ],
            "notes": ["Stage 15 merita comp dedicate, non un semplice riuso del team dungeon standard."],
        },
    ],
    "affinities": [
        {"key": "spirit", "label": "Spirit"},
        {"key": "force", "label": "Force"},
        {"key": "magic", "label": "Magic"},
        {"key": "void", "label": "Void"},
    ],
    "mechanics": [
        {"label": "Daily affinity rotation", "summary": "L'affinity cambia in base al giorno e conviene adattare roster e matchup."},
        {"label": "Progression per affinity", "summary": "Ogni affinity ha progressione stage separata."},
        {"label": "Punishing boss windows", "summary": "Le comp forti ruotano su support timing, sustain e gestione di finestre pericolose."},
        {"label": "Dedicated comps", "summary": "Nelle stage alte si vedono spesso comp specializzate con Geomancer, cleanse, shields o Revive on Death."},
    ],
    "key_roles": [
        {"label": "Decrease SPD", "reason": "Aiuta a controllare meglio il ritmo del boss."},
        {"label": "Cleanse / Block Debuffs", "reason": "Riduce il peso delle finestre punitive e dei debuff."},
        {"label": "Shield / Ally Protect / Sustain", "reason": "Le late stages premiano difese stabili."},
        {"label": "Single-target pressure", "reason": "Serve danno consistente su boss senza perdere il controllo del run."},
    ],
    "watchouts": [
        "L'affinity del giorno cambia davvero il valore dei campioni; il matchup va considerato prima dello score puro.",
        "Le stage alte spesso richiedono comp dedicate, non semplici varianti del team dungeon generico.",
        "Le soglie esatte ACC / RES per stage e affinity vanno ancora calibrate meglio dentro CB Forge.",
    ],
    "timing_notes": [
        "Per Iron Twins il prossimo salto utile sara modellare finestre punitive, cleanse timing e archetipi Revive on Death.",
    ],
    "optimizer_gaps": [
        "Lo scoring Iron Twins e attivo, ma non simula ancora il pattern del boss turno per turno.",
        "Le comp Revive on Death e resist-based sono riconosciute come archetipi, ma non ancora verificate da simulatore dedicato.",
    ],
    "sources": [
        {
            "label": "Plarium - Iron Twins Fortress",
            "url": "https://raid-support.plarium.com/hc/en-us/articles/5875103610140-Iron-Twins-Fortress",
            "kind": "official",
            "confidence": "high",
            "checked_at": "2026-04-04",
            "note": "Schedule, progressione per affinity e struttura del contenuto.",
        },
        {
            "label": "HellHades - Iron Twins Fortress Guide",
            "url": "https://hellhades.com/iron-twins-fortress-guide/",
            "kind": "community",
            "confidence": "medium",
            "checked_at": "2026-04-04",
            "note": "Approcci progression e comp dedicate per stage alte.",
        },
        {
            "label": "AyumiLove - Iron Twins 15 Void Example Team",
            "url": "https://ayumilove.net/rsl-guide-iron-twins-15-void-mithrala-duchess-krisk-champfort-geomancer/",
            "kind": "community",
            "confidence": "low",
            "checked_at": "2026-04-04",
            "note": "Esempio concreto di comp stage 15 Void, utile come riferimento archetipale.",
        },
    ],
}
