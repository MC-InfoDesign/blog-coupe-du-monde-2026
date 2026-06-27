# CLAUDE.md — Blog CdM 2026

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

---

## Contexte projet

**Site en ligne :** https://blog-coupe-du-monde-2026.vercel.app
**GitHub :** https://github.com/MC-InfoDesign/blog-coupe-du-monde-2026
**Dossier local :** `C:\Users\Mimix\blog-coupe-du-monde\`

Blog sur la Coupe du Monde 2026 (USA/Canada/Mexique). Contenu généré automatiquement chaque matin à 9h via GitHub Actions + Groq API.

---

## Stack & fichiers

```
index.html          — SPA vanilla JS ES Modules, zéro framework, zéro bundler
articles.json       — Source de vérité des articles (remplacé chaque jour par agent.py)
schedule.json       — Groupes A-L FIFA réels, classements, résultats, huitièmes
agent.py            — Génère les articles via Groq (gratuit) ou Anthropic
daily.bat           — One-click Windows : refresh + git push
sitemap.py          — Génère sitemap.xml (base-url en argument)
vercel.json         — Headers cache uniquement (pas de builds)
.github/workflows/daily-refresh.yml — GitHub Actions : refresh auto à 9h Paris
.env                — GROQ_API_KEY=gsk_... (ne jamais committer)
```

**Fichiers jamais modifiés par GitHub Actions :** index.html, schedule.json, vercel.json, agent.py
**Fichiers modifiés par GitHub Actions chaque jour :** articles.json, sitemap.xml

---

## Règles ABSOLUES

### 1. Jamais de mention IA visible
Le blog doit paraître humain. Aucune référence à Claude, IA, agent, automatique côté utilisateur.
- Auteurs des articles = noms humains tirés au sort : Thomas Leblanc, Sarah Dupont, Marc Fontaine, Julie Bernard, Pierre Martin, Camille Rousseau, Nicolas Petit, Laura Simon, Antoine Morel, Sophie Girard, Julien Lambert, Emma Leroy
- Footer = `© 2026 Blog CdM 2026 · Tous droits réservés`
- Hero = "mis à jour chaque jour" (sans "par IA")

### 2. Toujours fetcher les vraies données sportives
Ne JAMAIS inventer groupes, résultats, classements. Fetcher ces sources AVANT toute modif de schedule.json :

| Source | URL | Contenu |
|---|---|---|
| Classements A-L | `https://www.nbcsports.com/soccer/news/2026-world-cup-group-stage-table-full-standings-for-all-12-groups` | pts, GD, statut par équipe |
| Résultats matchs | `https://www.espn.com/soccer/story/_/id/48939282/2026-fifa-world-cup-fixtures-results-match-schedule-group-stage-knockout-rounds-bracket` | scores par date |
| Huitièmes confirmés | `https://www.si.com/soccer/every-confirmed-round-of-32-match-2026-world-cup` | R32 avec stades |
| Groupes officiels | `https://www.livescore.com/en/football/international/world-cup-2026/standings/` | composition A-L |

### 3. Vrais groupes FIFA 2026 (ne pas réinventer)
- A : Mexique, Afrique du Sud, Corée du Sud, Tchéquie
- B : Suisse, Canada, Bosnie-Herzégovine, Qatar
- C : Brésil, Maroc, Écosse, Haïti
- D : USA, Australie, Paraguay, Turquie
- E : Allemagne, Côte d'Ivoire, Équateur, Curaçao
- F : Pays-Bas, Japon, Suède, Tunisie
- G : Belgique, Égypte, Iran, Nouvelle-Zélande
- H : Espagne, Cap-Vert, Uruguay, Arabie Saoudite
- I : France, Norvège, Sénégal, Irak
- J : Argentine, Autriche, Algérie, Jordanie
- K : Colombie, Portugal, RD Congo, Ouzbékistan
- L : Angleterre, Ghana, Croatie, Panama

---

## Architecture index.html

SPA complète en JS vanilla (`<script type="module">`). Pas de React, pas de Vue.

### Routing hash-based
- `#/` → home (articles grid)
- `#/category/<nom>` → filtre catégorie
- `#/article/<id>` → page détail
- `#/programme` → grille groupes + huitièmes

### State global
```js
allArticles   // tous les articles chargés depuis articles.json
allSchedule   // données schedule.json (lazy-loaded à la 1ère visite Programme)
search        // chaîne de recherche
selectedCat   // catégorie active ('Tout' par défaut)
selectedPhase // phase programme active ('Groupes' par défaut)
```

### Fonctions clés
```js
makeThumb(article)        // visuel inline par catégorie (scoreboard, drapeau, etc.)
parseMatchTitle(title)    // extrait équipes + score depuis le titre
FLAGS                     // map 48 équipes → emoji drapeau
renderHeader(page)        // sticky header avec nav Articles/Programme
renderCard(article)       // carte avec visuel généré
renderProgramme(schedule) // groupes A-L avec classements + matchs
renderDetail(article)     // page article complète
renderApp()               // recompose toute la page selon le hash
```

### Visuels des cartes (makeThumb)
- **Résultats** : scoreboard avec drapeaux + score (parsé depuis le titre)
- **Équipes** : grand drapeau centré + nom équipe
- **Transferts** : `flag → 💸 MERCATO` + titre
- **Analyse tactique** : terrain SVG en filigrane + dots formation

### Catégories & couleurs
| Catégorie | Icône | Couleur |
|---|---|---|
| Résultats | ⚽ | `#16a34a` |
| Équipes | 🏆 | `#3b82f6` |
| Transferts | 💸 | `#f59e0b` |
| Analyse tactique | 📊 | `#a855f7` |

### Mobile (breakpoint 660px)
- Header à 2 lignes : logo+search ligne 1, nav Articles/Programme ligne 2
- `#filterbar` sticky à `top: 92px` (compense header 2 lignes)
- Grilles en 1 colonne
- Tableaux standings compacts (pos, flag+équipe, buts, pts)

---

## Agent (agent.py)

### Provider auto-détecté
1. `GROQ_API_KEY` → Groq Llama 3.3 70B (gratuit, prioritaire)
2. `ANTHROPIC_API_KEY` → Claude Sonnet (payant, fallback)

### Commandes
```bash
python agent.py --refresh          # remplace tout articles.json (12 articles J-1)
python agent.py --refresh --count 8
python agent.py --add --count 3    # ajoute sans remplacer
python agent.py --list
python agent.py --dry-run --refresh
```

### Logique --refresh
1. Fetch NewsAPI `from=J-1` (ou sujets de secours si pas de NEWS_API_KEY)
2. `categorize()` → `generate_article()` via LLM
3. Auteur = nom humain aléatoire (random.choice(AUTHORS))
4. Remplace entièrement articles.json

---

## Déploiement

### Vercel (production)
```powershell
cd C:\Users\Mimix\blog-coupe-du-monde
vercel --prod   # déploie les fichiers locaux directement, ~6 secondes
```
**Attention :** Vercel est configuré sur branche `master` (pas `main`).
Si `git push` ne déclenche pas Vercel, toujours utiliser `vercel --prod`.

### Git workflow
```powershell
git add <fichiers>
git commit -m "message"
git push
```

Si conflit (GitHub Actions a pushé entre temps) :
```powershell
git fetch origin
git checkout origin/master -- articles.json   # prendre leur version
# ré-appliquer les changements locaux si besoin
git add -A && git commit -m "message" && git push --force
```

### GitHub Actions (daily-refresh.yml)
- Tourne chaque jour à **9h heure de Paris** (7h UTC)
- Secrets requis dans GitHub Settings → Secrets : `GROQ_API_KEY`
- Optionnel : `NEWS_API_KEY`, `ANTHROPIC_API_KEY`
- Permissions : `contents: write` + `token: GITHUB_TOKEN` dans checkout
- Modifie uniquement : `articles.json`, `sitemap.xml`

---

## SEO & Analytics

- **Google Search Console** : fichier de vérif `googlea193c6b3babdcb7b.html` à la racine
- **Sitemap** : `python sitemap.py --base-url https://blog-coupe-du-monde-2026.vercel.app`
- **Vercel Analytics** : `/_vercel/insights/script.js` (dans `<head>` index.html)
- **Vercel Speed Insights** : `/_vercel/speed-insights/script.js` (dans `<head>` index.html)
- Meta og:, twitter:, JSON-LD NewsArticle mis à jour dynamiquement à chaque navigation

---

## Lancer en local

```powershell
cd C:\Users\Mimix\blog-coupe-du-monde
python -m http.server 8000
# → http://localhost:8000

# Dépendances Python
pip install requests groq anthropic python-dotenv
```
