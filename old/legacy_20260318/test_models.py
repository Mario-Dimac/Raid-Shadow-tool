from models import AccountData, Champion, ChampionStats

acc = AccountData()
acc.champions.append(
    Champion(
        champ_id="ch_001",
        name="Maneater",
        rarity="epic",
        affinity="void",
        faction="Ogryn Tribes",
        level=60,
        rank=6,
        ascension=6,
        total_stats=ChampionStats(spd=248, hp=42000, def_=3100, acc=240),
    )
)

print(acc.to_dict())