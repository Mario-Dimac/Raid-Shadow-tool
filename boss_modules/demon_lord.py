from __future__ import annotations


DEMON_LORD_BOSS_MODULE = {
    "boss_key": "demon_lord",
    "label": "Demon Lord",
    "category": "Clan Boss",
    "optimizer_status": "active",
    "implemented_in_optimizer": True,
    "team_size": 5,
    "default_level": "ultra_nightmare",
    "default_affinity": "void",
    "overview": "Boss cooperativo con rotazione AoE1 / AoE2 / Stun. Le build forti vivono su speed tune, uptime difensivi e debuff stabili.",
    "levels": [
        {
            "key": "normal",
            "label": "Normal",
            "stat_targets": [
                {"label": "Speed floor", "value": "150 SPD", "confidence": "medium", "note": "Soglia euristica minima dell'optimizer per mantenere il ciclo."},
                {"label": "Accuracy floor", "value": "140 ACC", "confidence": "medium", "note": "Baseline interna per landing dei debuff utili."},
            ],
            "notes": ["Entrata morbida: punta a Decrease ATK, sustain e danno costante prima delle tune piu rigide."],
        },
        {
            "key": "hard",
            "label": "Hard",
            "stat_targets": [
                {"label": "Speed floor", "value": "160 SPD", "confidence": "medium", "note": "Soglia euristica minima dell'optimizer."},
                {"label": "Accuracy floor", "value": "180 ACC", "confidence": "medium", "note": "Debuff core piu affidabili."},
            ],
            "notes": ["Inizia a premiare team con cleanse, Block Debuffs o Ally Protect affidabili."],
        },
        {
            "key": "brutal",
            "label": "Brutal",
            "stat_targets": [
                {"label": "Speed floor", "value": "170 SPD", "confidence": "medium", "note": "Baseline killable per entrare nel ritmo del boss."},
                {"label": "Accuracy floor", "value": "210 ACC", "confidence": "medium", "note": "Debuff uptime piu consistente."},
            ],
            "notes": ["Da qui in poi le tune iniziano a contare davvero piu del puro score individuale."],
        },
        {
            "key": "nightmare",
            "label": "Nightmare",
            "stat_targets": [
                {"label": "Speed floor", "value": "176 SPD", "confidence": "medium", "note": "Soglia minima euristica attuale di CB Forge."},
                {"label": "Accuracy floor", "value": "230 ACC", "confidence": "medium", "note": "Serve per i debuff boss-centrici piu importanti."},
            ],
            "notes": ["Nightmare e il punto in cui diventa naturale ragionare in 4:3, cleanse timing e stun target."],
        },
        {
            "key": "ultra_nightmare",
            "label": "Ultra-Nightmare",
            "stat_targets": [
                {"label": "Speed floor", "value": "190 SPD", "confidence": "medium", "note": "Soglia minima euristica usata oggi dall'optimizer."},
                {"label": "Accuracy floor", "value": "250 ACC", "confidence": "medium", "note": "Baseline utile per landing affidabili su UNM."},
            ],
            "notes": ["UNM e il target principale dell'optimizer attuale.", "Le tune precise restano da modellare in modo piu rigoroso nel motore."],
        },
    ],
    "affinities": [
        {"key": "void", "label": "Void"},
        {"key": "force", "label": "Force"},
        {"key": "magic", "label": "Magic"},
        {"key": "spirit", "label": "Spirit"},
    ],
    "mechanics": [
        {"label": "Affinity shift", "summary": "Parte Void e sotto il 50% HP puo cambiare affinity nella battaglia successiva."},
        {"label": "Three-step cycle", "summary": "Le tune ruotano su AoE1, AoE2 e Stun; i buff difensivi vanno allineati a questa finestra."},
        {"label": "Stun target", "summary": "Targeting e ratio di HP / DEF influenzano chi prende lo Stun e quindi la stabilita della comp."},
    ],
    "key_roles": [
        {"label": "Decrease ATK", "reason": "Riduce il carico difensivo sui colpi boss."},
        {"label": "Block Debuffs o Cleanse", "reason": "Gestisce debuff e stun nei turni giusti."},
        {"label": "Ally Protect / Shield / Counterattack", "reason": "Le killable migliori trasformano la rotazione del boss in vantaggio."},
        {"label": "Poison / HP Burn / DPS tuned", "reason": "Il danno migliore arriva da output costante dentro una tune stabile."},
    ],
    "watchouts": [
        "Evita masteries, set o skill che alterano Turn Meter o cooldown se stai seguendo una tune stretta.",
        "Controlla l'affinity matchup fuori dal Void: weak hits possono rompere debuff e stun plan.",
        "Un team con score individuali alti ma senza finestra difensiva coerente spesso collassa presto.",
    ],
    "timing_notes": [
        "Le comp 4:3 e le unkillable vanno trattate come archetipi separati.",
        "Block Debuffs, cleanse e cooldown reset vanno letti insieme al ciclo AoE1 / AoE2 / Stun.",
    ],
    "optimizer_gaps": [
        "Il motore Clan Boss e il piu rifinito, ma le tune complete non sono ancora risolte come un calcolatore dedicato stile DeadwoodJedi.",
        "Le speed tune con eccezioni complesse, masteries o passivi fuori standard richiedono ancora verifica manuale.",
    ],
    "sources": [
        {
            "label": "Plarium - Guide: Demon Lord",
            "url": "https://raid-support.plarium.com/hc/en-us/articles/360014645900-Guide-Demon-Lord",
            "kind": "official",
            "confidence": "high",
            "checked_at": "2026-04-04",
            "note": "Difficolta, reset giornaliero e affinity shift.",
        },
        {
            "label": "DeadwoodJedi - What is a Speed Tune?",
            "url": "https://deadwoodjedi.com/what-is-a-speed-tune/",
            "kind": "community",
            "confidence": "high",
            "checked_at": "2026-04-04",
            "note": "Base concettuale per tune Clan Boss.",
        },
        {
            "label": "DeadwoodJedi - Stun Targetting",
            "url": "https://deadwoodjedi.com/stun-targetting/",
            "kind": "community",
            "confidence": "high",
            "checked_at": "2026-04-04",
            "note": "Criteri pratici per lo stun target.",
        },
    ],
}
