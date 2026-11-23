# prayer-calendar

Les horaires de prière publiés en calendrier ICS auquel on s'abonne depuis Apple Calendrier (ou Google Agenda, Outlook…). Les horaires viennent de la page Mawaqit de la Grande Mosquée de Paris.

- S'abonner : `webcal://thedevadvisor.github.io/prayer-calendar/prieres.ics`
- En https : https://thedevadvisor.github.io/prayer-calendar/prieres.ics
- Page à partager : https://thedevadvisor.github.io/prayer-calendar/ (horaires du jour, abonnement Apple, Google ou Outlook, mode d'emploi)

## Fonctionnement

Chaque nuit, une GitHub Action lit la page publique Mawaqit de la mosquée, déduit l'année du tableau grâce au passage à l'heure d'été, enregistre le tableau dans `data/<slug>/<année>.json` puis régénère `docs/prieres.ics`, que GitHub Pages sert tel quel.

Le calendrier remonte à 9 semaines avant le lundi courant (au moins 60 jours) et va jusqu'au bout de ce qui est publié, en piochant dans tous les snapshots. Tout est calé sur le lundi : sans correction de la mosquée, les fichiers ne changent qu'une fois par semaine, et les autres nuits l'Action ne commite rien. GitHub retarde ou saute parfois un run planifié (c'est arrivé le lundi 23/11/2026), et la nuit suivante rattrape. Quand la mosquée publiera l'année suivante, elle s'ajoutera sans couper l'année en cours. Si au 1er janvier la mosquée affiche encore le tableau de l'an dernier, l'année en cours est servie en provisoire (`"provisional": true` dans `status.json`) : chaque horaire est reporté au même instant UTC, donc le changement d'heure tombe au bon jour. Rien n'est enregistré dans `data/`, et le vrai tableau prend la place dès sa publication. Le vendredi, Dhuhr s'affiche comme Jumu'a (même horaire), et pendant le Ramadan on ajoute l'Imsak et l'Iftar.

Si Mawaqit est injoignable, que sa page change de forme ou que le tableau paraît incohérent (horaires dans le désordre, ou un horaire qui bouge de plus de 30 min d'un jour à l'autre, changements d'heure exclus), l'Action échoue (GitHub envoie un e-mail) et le dernier calendrier publié reste en ligne. `docs/status.json` résume ce qui est servi : année du tableau, nombre d'événements, période couverte, dates du Ramadan.

## Changer les réglages

Tout se passe dans `config.yaml` : titres, prières affichées (ajouter `shuruq` pour le Chourouq), Jumu'a le vendredi (`friday_jumua`), durée des événements, alertes, Imsak et Iftar pendant le Ramadan, dates officielles du Ramadan (`ramadan.overrides`), message en bas de la page (`page_message`). La page vient de `prayer_calendar/templates/`. On modifie, on pousse sur `main`, et l'Action régénère le calendrier dans la foulée.

## Changer de mosquée ou en ajouter une

Pour changer de source, il suffit de remplacer `slug`, `url` et `source_name` sous `mosques` par ceux d'une autre page Mawaqit. `source_name` n'apparaît que sur la page : le calendrier, lui, ne nomme aucune mosquée. L'adresse d'abonnement et les UID (`uid_prefix`) ne bougent pas, donc les abonnés n'ont rien à refaire.

Pour publier un deuxième calendrier, on ajoute une entrée :

```yaml
  - slug: autre-mosquee
    url: https://mawaqit.net/fr/autre-mosquee
    output: docs/autre.ics
    calendar_name: "🕌 Prières (autre)"
    uid_prefix: autre
```

Il sera publié à `https://thedevadvisor.github.io/prayer-calendar/autre.ics`, avec les mêmes réglages que le premier.

## En local

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/python -m prayer_calendar.build
```
