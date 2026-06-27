# CLAUDE.md — Blog CdM 2026

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Architecture

**Stack :** HTML · CSS · JavaScript ES Modules (zéro bundler, zéro framework) · Python 3

### Fichiers principaux

```
index.html        — Blog complet : routing hash, rendu DOM vanilla JS
articles.json     — Source de données des articles (id, title, category, date, author, summary, content, tags)
agent.py          — Agent CLI : NewsAPI → Claude API → articles.json
refresh.bat       — Lance --refresh + ouvre le blog (Windows, double-clic)
refresh.sh        — Lance --refresh + ouvre le blog (Linux/Mac/WSL)
.env.example      — Template ANTHROPIC_API_KEY + NEWS_API_KEY
```

### Flux de données

```
NewsAPI (optionnel)
    │
    ▼
agent.py ──► categorize() via Claude ──► generate_article() via Claude
    │
    ▼
articles.json  ◄──── déduplication (SequenceMatcher > 0.62)
    │
    ▼
index.html fetch('./articles.json') ──► rendu DOM
```

### Structure de index.html

Le fichier est un Single-Page App entièrement en JS vanilla avec ES modules (`<script type="module">`).

**State global :**
- `allArticles` — tableau de tous les articles chargés
- `search` — chaîne de recherche en cours
- `selectedCat` — catégorie active (défaut : `'Tout'`)
- `page` — `'home'` | `'article'`

**Fonctions de rendu (toutes retournent un `HTMLElement`) :**
- `renderHeader()` — barre sticky avec logo + input recherche + badge LIVE
- `renderHero()` — bandeau d'intro (masqué quand recherche active)
- `renderFilterBar()` — 5 boutons catégorie avec compteurs
- `renderCard(article)` — carte cliquable avec thumbnail, badge catégorie, résumé
- `renderDetail(article)` — page article complète avec partage
- `renderGrid()` — applique les filtres et peuple `#main`
- `renderApp()` — recompose toute la page selon le hash courant

**Routing :** hash-based
- `#/` → home, toutes catégories
- `#/category/<nom>` → home filtrée
- `#/article/<id>` → page détail

### Catégories

| Catégorie | Icône | Couleur |
|---|---|---|
| Résultats | ⚽ | `#16a34a` (vert) |
| Équipes | 🏆 | `#3b82f6` (bleu) |
| Transferts | 💸 | `#f59e0b` (or) |
| Analyse tactique | 📊 | `#a855f7` (violet) |

### Format articles.json

```json
{
  "articles": [
    {
      "id": 1,
      "title": "...",
      "category": "Résultats",
      "date": "2026-06-25",
      "author": "...",
      "summary": "2-3 phrases résumé",
      "content": "Texte avec ## Sections\n\nParagraphes séparés par double newline",
      "tags": ["tag1", "tag2"]
    }
  ]
}
```

Le champ `content` utilise `## Titre` pour les sections et `\n\n` entre paragraphes — parsé par `renderDetail()`.

## Lancer le projet

```bash
# Serveur local (obligatoire — fetch() ne fonctionne pas en file://)
python -m http.server 8000
# → http://localhost:8000

# Setup clés API
cp .env.example .env       # renseigner ANTHROPIC_API_KEY (+ optionnel NEWS_API_KEY)
pip install anthropic requests python-dotenv
```

## Agent — commandes principales

```bash
# ★ Rafraîchir TOUT le blog avec les actus J-1 (12 articles, remplace les anciens)
python agent.py --refresh

# Raccourcis one-click
.\refresh.bat              # Windows — refresh + ouvre http://localhost:8000
bash refresh.sh            # Linux/Mac/WSL

# Variantes
python agent.py --refresh --count 8   # 8 articles au lieu de 12
python agent.py --add --count 3       # ajoute 3 articles sans remplacer
python agent.py --dry-run --refresh   # prévisualise sans écrire
python agent.py --list                # liste les articles existants
```

### Logique du mode --refresh

1. Filtre NewsAPI sur `from=J-1&to=today` (ou sujets de secours si pas de clé)
2. Pour chaque sujet : `categorize()` → `generate_article()` via Claude
3. **Remplace** entièrement `articles.json` (IDs réinitialisés à 1)
4. Tous les articles sont datés de J-1

## Commandes graphify

```bash
graphify init .                         # initialiser le graphe (première fois)
graphify update .                       # mise à jour après modification
graphify query "routing hash"           # chercher un concept dans la codebase
graphify explain "renderApp"            # expliquer une fonction
graphify path "agent.py" "articles.json" # relation entre deux fichiers
```

## Points d'attention

- `articles.json` est la **seule source de vérité** — l'agent l'écrit, le blog le lit.
- Les IDs articles sont séquentiels et uniques ; l'agent prend `max(id) + 1`.
- La déduplication dans `agent.py` utilise `SequenceMatcher` avec un seuil de 0.62 — ajuster `threshold` si trop/pas assez strict.
- Le blog utilise `picsum.photos/seed/cdm<id>` pour des thumbnails déterministes par article.
- Pas de build step, pas de node_modules — tout est vanilla.
