# Steam × Archipelago Game Picker

Application web self-hosted : tire aléatoirement des jeux compatibles [Archipelago](https://archipelago.gg)
possédés sur Steam par les joueurs choisis (1 à 8), individuellement ou en commun.

```
Profils Steam → Bibliothèques → Mapping Steam ↔ Archipelago → Filtres/exclusions → Tirage individuel ou commun
```

## Architecture

```
Frontend React (nginx) → FastAPI → Services métier → SQLAlchemy → PostgreSQL
```

```
backend/app/
  api/                 routes FastAPI + injection de dépendances
  integrations/steam/  SteamClient (HTTPX), parsing SteamID/URL, erreurs typées
  integrations/archipelago/  sources (protocole ArchipelagoSource) : officielle, wiki (API MediaWiki), Games Library
  services/            SteamService, ArchipelagoService, MappingService, EligibilityService, DrawService, ownership
  models.py schemas.py db.py config.py
backend/alembic/       migrations
frontend/              React + TypeScript + Vite + Tailwind
```

- **Possession** : `GameOwnershipProvider` (`services/ownership.py`) isole le concept de possession ;
  `SteamOwnershipProvider` calcule l'intersection en une requête SQL (`GROUP BY … HAVING COUNT(DISTINCT player) = n`).
  Aucun appel réseau Steam n'a lieu pendant le calcul. Mesuré : 8 joueurs × 4000 jeux ≈ 0,15 s sur PostgreSQL.
- **Sources Archipelago** : tout objet respectant `ArchipelagoSource.fetch_games()` peut être ajouté dans
  `integrations/archipelago/registry.py`. Les jeux sont dédupliqués par slug normalisé (pas par nom brut) ;
  le statut le plus fiable l'emporte (`official` > `community` > `unknown`). Une source en échec conserve ses anciennes données.
- **Mappings** : seuls les mappings **vérifiés** comptent pour l'éligibilité. Un Steam App ID explicite fourni par une source est
  importé comme vérifié ; la correspondance par nom normalisé (dernier recours) crée des mappings `guessed` **non vérifiés**
  (confiance plus faible si ambigu) à valider dans l'administration. Les syncs ne modifient jamais les mappings manuels
  ni l'état « activé ».
- **Modes de filtre** : `official` (jeux officiels), `recommended` (défaut : officiels + communautaires de statut `stable`),
  `extended` (tous les jeux activés ayant un mapping vérifié). Les jeux officiels `deprecated` sont exclus hors `extended`.

## Prérequis

Docker + Docker Compose, et une clé d'API Steam.

## Installation

```bash
cp .env.example .env      # puis renseigner STEAM_API_KEY et POSTGRES_PASSWORD
docker compose up -d
```

L'interface est disponible sur http://localhost:8080 (`FRONTEND_PORT` pour changer).

> Swagger/OpenAPI sont servis par FastAPI sur `/docs` et `/openapi.json` du backend ; le backend n'est pas publié par défaut.
> Pour y accéder, ajoutez `ports: ["8000:8000"]` au service `backend`.

### Configuration (`.env`)

| Variable | Rôle |
| --- | --- |
| `STEAM_API_KEY` | clé Steam Web API (jamais commitée, jamais loggée) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | base PostgreSQL (volume persistant `pgdata`) |
| `DATABASE_URL` | URL SQLAlchemy ; construite par Compose, à définir seulement hors Docker |
| `CORS_ORIGINS` | origines autorisées, séparées par des virgules |
| `LOG_LEVEL` | `INFO` par défaut |
| `STEAM_CACHE_DURATION` | secondes pendant lesquelles une bibliothèque est « fraîche » (défaut 3600) |
| `ARCHIPELAGO_SYNC_ENABLED` | synchronise les sources Archipelago au démarrage du backend |
| `ADMIN_SECRET_KEY` | secret de signature des jetons d'administration (vide : secret aléatoire généré et conservé en base) |

### Obtenir une clé Steam API

Rendez-vous sur https://steamcommunity.com/dev/apikey, connectez-vous et déclarez un domaine (ex. `localhost`).
Les bibliothèques ne sont lisibles que si le profil **et** les « Détails des jeux » sont publics.

## Administration protégée

Identifiants par défaut : **`admin` / `admin`** (une bannière d'avertissement s'affiche tant qu'ils n'ont pas été changés).
Changez-les dans Administration → « Changer le mot de passe » (mot de passe actuel, nouveau, confirmation ; identifiant optionnel).
Seul un hash salé (scrypt) est stocké en base. `POST /api/admin/login` renvoie un jeton signé (HMAC, expiration 12 h) à envoyer dans
l'en-tête HTTP `Authorization` (schéma Bearer) ; changer le mot de passe invalide les anciens jetons. Les échecs de connexion sont ralentis puis
bloqués temporairement (HTTP 429) après 5 essais. Les routes protégées répondent `401 {"error": "UNAUTHORIZED", ...}`.

## Utilisation

1. **Ajouter les joueurs** : SteamID64, URL `steamcommunity.com/profiles/…`, `/id/…` ou vanity URL. La bibliothèque est synchronisée à l'ajout.
2. **Synchroniser Steam** (par joueur ou tous). Les données sont stockées en base ; en cas d'erreur (profil privé, Steam indisponible,
   timeout, rate limit) les dernières données valides sont conservées et l'erreur est affichée. Une bibliothèque inaccessible n'est
   jamais traitée comme vide : un joueur sans bibliothèque valide bloque le calcul (`409 LIBRARY_UNAVAILABLE`).
3. **Sélectionner 1 à 8 joueurs** (un neuvième est impossible côté UI et refusé par l'API).
4. Le mode **Individuel** est sélectionné par défaut : chaque joueur reçoit un jeu compatible qu'il possède. Les jeux sont distincts
   entre joueurs ; le serveur calcule une affectation complète avant de l'enregistrer. Si un joueur n'a aucun candidat, l'API renvoie
   `409 NO_COMPATIBLE_GAMES`. Si les candidats existent mais ne permettent pas une affectation sans doublon, elle renvoie
   `409 DUPLICATES_UNAVOIDABLE` sans enregistrer de tirage. Chaque résultat individuel apparaît dans l'historique pour son joueur.
5. Le mode **Commun** conserve le tirage d'un seul jeu possédé par tous : **🎲 Tirer un jeu commun**. Aucun jeu commun :
   `409 {"error": "NO_COMMON_GAMES", ...}`. « Ne pas proposer les jeux déjà tirés » exclut les jeux de l'historique (l'API accepte aussi
   `exclude_last_n` et `excluded_game_ids`).

### Synchronisation Archipelago et mappings

Onglet **Administration** : « Synchroniser les sources Archipelago », liste des jeux (source, statut, App IDs, activation),
section **Mappings à vérifier**, création/suppression/validation de mappings, et rapprochement par nom.
Un jeu sans mapping Steam vérifié n'est jamais éligible. DLC et bundles ne sont jamais déduits d'un jeu principal :
seul l'App ID exact présent dans la bibliothèque compte.

### API

Principales routes (`/api/…`) : `health`, `players` (+ `/{id}`, `/{id}/sync`, `/sync`), `archipelago/games|sources|sync`,
`mappings` (+ `/{id}`, `/auto-match`), `selection/common-games`, `selection/player-games`, `draw` (commun, rétrocompatible),
`draw/per-player` (un résultat par joueur, unicité activée par défaut), `draws` (`DELETE /api/draws` vide l'historique), `admin/login|logout|session|password`. L'historique commun reste un élément avec tous ses joueurs ;
les tirages individuels sont enregistrés comme un élément par joueur. Erreurs métier : `{"error": CODE, "message": …}`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
cd ../frontend && npm ci && npm run build
```

Les tests utilisent SQLite en mémoire et des mocks : aucun appel à Steam ou Archipelago. Un test applique les migrations Alembic.

## Limitations connues

- Les formats HTML de `archipelago.gg/games` et de la Games Library n'ont pas pu être vérifiés depuis l'environnement de
  développement (sans accès à ces domaines). Les parseurs sont tolérants mais « best effort » et couverts par des fixtures ;
  le wiki utilise l'API MediaWiki structurée. En cas de changement de format, la source passe en erreur sans affecter les autres
  et les anciennes données sont conservées — adaptez alors le parseur concerné.
- La page **Administration** et les routes d'administration de l'API (`/api/archipelago/*`, `/api/mappings/*`) sont protégées par un
  identifiant/mot de passe, mais le tirage, les joueurs et l'historique (y compris « Vider l'historique ») restent publics ;
  à n'exposer que sur un réseau de confiance.
- Le tirage uniforme n'a pas de pondération.

## Dépannage

- `STEAM_API_KEY_MISSING` : renseignez la clé dans `.env` puis `docker compose up -d`.
- Bibliothèque « privée » : le joueur doit rendre profil et détails des jeux publics.
- Peu de jeux compatibles : vérifiez les mappings (section « à vérifier »), le mode de filtre (`extended`) et les sources.
- Logs : `docker compose logs -f backend`. Réinitialiser la base : `docker compose down -v` (supprime le volume).
- Migrations manuelles : `docker compose exec backend alembic upgrade head` (exécutées automatiquement au démarrage).
