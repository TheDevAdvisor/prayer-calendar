# prayer-calendar

Les horaires de prière de la mosquée Annour d'Ivry-sur-Seine, publiés en calendrier ICS auquel on s'abonne depuis Apple Calendrier (ou Google Agenda, Outlook…).

- S'abonner : `webcal://thedevadvisor.github.io/prayer-calendar/ivry.ics`
- En https : https://thedevadvisor.github.io/prayer-calendar/ivry.ics

## Fonctionnement

Chaque lundi, une GitHub Action lit la page publique Mawaqit de la mosquée, déduit l'année du tableau grâce au passage à l'heure d'été, enregistre le tableau dans `data/<slug>/<année>.json` puis régénère `docs/ivry.ics`, que GitHub Pages sert tel quel.

Le calendrier couvre les 60 derniers jours et tout ce qui est publié après, en piochant dans tous les snapshots. Quand la mosquée publiera l'année suivante, elle s'ajoutera sans couper l'année en cours.

Si Mawaqit est injoignable ou que sa page change de forme, l'Action échoue (GitHub envoie un e-mail) et le dernier calendrier publié reste en ligne. `docs/status.json` résume ce qui est servi : année du tableau, nombre d'événements, période couverte, dates du Ramadan.

## Changer les réglages

Tout se passe dans `config.yaml` : titres, prières affichées (ajouter `shuruq` pour le Chourouq), durée des événements, alertes, Imsak et Iftar pendant le Ramadan, dates officielles du Ramadan (`ramadan.overrides`). On modifie, on pousse sur `main`, et l'Action régénère le calendrier dans la foulée.

## Ajouter une mosquée

Ajouter une entrée sous `mosques` avec l'adresse de sa page Mawaqit :

```yaml
  - slug: autre-mosquee
    url: https://mawaqit.net/fr/autre-mosquee
    output: docs/autre.ics
    calendar_name: "🕌 Prières – Autre mosquée"
```

Son calendrier sera publié à `https://thedevadvisor.github.io/prayer-calendar/autre.ics`, avec les mêmes réglages que les autres.

## En local

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/python -m prayer_calendar.build
```

Les horaires sont ceux que la mosquée publie sur [Mawaqit](https://mawaqit.net/fr/annour-ivry-sur-seine).
