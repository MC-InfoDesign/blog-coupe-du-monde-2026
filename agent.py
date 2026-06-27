#!/usr/bin/env python3
"""
agent.py — Générateur & rafraîchisseur d'articles CdM 2026

Modes :
  python agent.py --refresh          # ★ remplace TOUT par les actus J-1 (12 articles)
  python agent.py --refresh --count 8  # idem, mais 8 articles
  python agent.py --add              # ajoute N articles sans remplacer les existants
  python agent.py --add --count 3
  python agent.py --list             # liste les articles dans articles.json
  python agent.py --dry-run --refresh  # prévisualise sans écrire
"""
import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    print("❌ Dépendances manquantes. Installez : pip install anthropic requests python-dotenv")
    sys.exit(1)

# ── Constantes ────────────────────────────────────────────────────────────────

ARTICLES_PATH = os.path.join(os.path.dirname(__file__), "articles.json")
CATEGORIES    = ["Résultats", "Équipes", "Transferts", "Analyse tactique"]
MODEL         = "claude-sonnet-4-6"

YESTERDAY = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
TODAY     =  datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Sujets de secours si pas de NEWS_API_KEY
FALLBACK_TOPICS = [
    {"title": "Résultats J-1 : toutes les rencontres de la journée",         "hint": "Résultats"},
    {"title": "Analyse : les tactiques qui ont fait la différence hier",      "hint": "Analyse tactique"},
    {"title": "L'équipe surprise du jour : qui a impressionné ?",             "hint": "Équipes"},
    {"title": "Mercato : les rumeurs de transfert nées des performances J-1", "hint": "Transferts"},
    {"title": "Buteurs du jour et statistiques clés de la journée",           "hint": "Résultats"},
    {"title": "Portrait : le joueur révélation de la journée",                "hint": "Équipes"},
    {"title": "Décryptage tactique : le meilleur système de jeu observé hier","hint": "Analyse tactique"},
    {"title": "Blessures et absences : l'infirmerie après J-1",               "hint": "Équipes"},
    {"title": "Transferts chauds : les agents à l'œuvre après les matchs",    "hint": "Transferts"},
    {"title": "Les tops et flops de la journée au Mondial 2026",              "hint": "Résultats"},
    {"title": "5-4-1 ou 4-3-3 : quel bloc défensif a mieux résisté hier ?",  "hint": "Analyse tactique"},
    {"title": "Classement des groupes mis à jour après la journée d'hier",    "hint": "Résultats"},
]


# ── I/O articles.json ─────────────────────────────────────────────────────────

def load_articles() -> dict:
    try:
        with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"articles": []}


def save_articles(data: dict) -> None:
    with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ articles.json mis à jour — {len(data['articles'])} articles au total.")


# ── NewsAPI ───────────────────────────────────────────────────────────────────

def fetch_news_yesterday(api_key: str, count: int = 20) -> list:
    """Récupère les actus CdM 2026 publiées hier via NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q":          '"Coupe du Monde 2026" OR "World Cup 2026" OR "FIFA 2026"',
        "from":       YESTERDAY,
        "to":         TODAY,
        "sortBy":     "relevancy",
        "pageSize":   min(count * 2, 50),
        "language":   "fr",
        "apiKey":     api_key,
    }
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    items = r.json().get("articles", [])

    # Essai en anglais si pas assez de résultats FR
    if len(items) < count // 2:
        params["language"] = "en"
        r2 = requests.get(url, params=params, timeout=12)
        if r2.ok:
            items += r2.json().get("articles", [])

    return [
        {
            "title":       a.get("title", ""),
            "description": a.get("description", "") or "",
            "source":      a.get("source", {}).get("name", ""),
            "published":   a.get("publishedAt", "")[:10],
        }
        for a in items
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


# ── Déduplication (mode --add uniquement) ─────────────────────────────────────

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_duplicate(title: str, existing: list, threshold: float = 0.62) -> bool:
    return any(similarity(title, a.get("title", "")) > threshold for a in existing)


# ── Claude helpers ────────────────────────────────────────────────────────────

def categorize(client: anthropic.Anthropic, title: str, desc: str) -> str:
    prompt = (
        f"Catégorise cet article dans l'une de ces catégories exactement : "
        f"{', '.join(CATEGORIES)}\n\n"
        f"Titre : {title}\nDescription : {desc}\n\n"
        f"Réponds avec UNIQUEMENT le nom exact de la catégorie."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=30,
        messages=[{"role": "user", "content": prompt}],
    )
    cat = resp.content[0].text.strip()
    return cat if cat in CATEGORIES else CATEGORIES[0]


def generate_article(
    client: anthropic.Anthropic,
    item: dict,
    article_id: int,
    category: str,
    target_date: str,
) -> dict:
    """Génère un article complet en français via Claude, ancré dans target_date."""

    hint = item.get("hint", "")
    prompt = f"""Tu es journaliste sportif pour un blog sur la Coupe du Monde 2026 (USA / Canada / Mexique).
La journée dont tu parles est celle du {target_date}.

Génère un article complet en français. Réponds avec du JSON valide uniquement (sans balises markdown).

Sujet / titre indicatif : {item.get('title', hint)}
Description source      : {item.get('description', '')}
Catégorie               : {category}

JSON attendu (ces clés exactement) :
{{
  "title":         "Titre accrocheur, max 90 caractères",
  "summary":       "Résumé percutant de 2 à 3 phrases",
  "content":       "## Section 1\\n\\nParagraphe...\\n\\n## Section 2\\n\\nParagraphe...\\n\\nMinimum 5 paragraphes, 650 mots, style journalistique de qualité.",
  "tags":          ["tag1","tag2","tag3","tag4"],
  "imageKeywords": "2 à 4 mots-clés EN ANGLAIS décrivant l'image idéale pour cet article (ex: 'france,mbappe,football,match' ou 'tactics,whiteboard,coach,football')"
}}

L'article doit être factuel, ancré dans la réalité du tournoi 2026, en français courant. \
Mentionne des stades, des joueurs réels, des scores plausibles pour cette journée."""

    resp = client.messages.create(
        model=MODEL, max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    gen = json.loads(raw)
    return {
        "id":       article_id,
        "title":    gen["title"],
        "category": category,
        "date":     target_date,
        "author":   f"Agent IA · CdM 2026 · {target_date}",
        "summary":  gen["summary"],
        "content":  gen["content"],
        "tags":          gen.get("tags", ["CdM2026", "Football"]),
        "imageKeywords": gen.get("imageKeywords", "football,match,worldcup"),
    }


# ── Commandes ─────────────────────────────────────────────────────────────────

def cmd_list(articles: list) -> None:
    print(f"\n📋 {len(articles)} articles dans articles.json :\n")
    for a in sorted(articles, key=lambda x: x.get("date",""), reverse=True):
        print(f"  [{a['id']:>2}] {a['date']}  [{a['category']:<20}]  {a['title'][:65]}")
    print()


def cmd_refresh(client, api_key_news, count, dry_run):
    """Remplace TOUT le contenu par les actus J-1."""
    print(f"\n🔄  Mode REFRESH — actus du {YESTERDAY}")
    print("━" * 55)

    # 1. Récupérer les sujets
    if api_key_news:
        print("📡  Récupération NewsAPI…")
        try:
            topics = fetch_news_yesterday(api_key_news, count=count + 8)
            print(f"    {len(topics)} articles trouvés ({YESTERDAY})")
            if not topics:
                raise ValueError("Aucun résultat")
        except Exception as e:
            print(f"⚠️   NewsAPI erreur ({e}) — sujets de secours utilisés")
            topics = FALLBACK_TOPICS
    else:
        print("ℹ️   Pas de NEWS_API_KEY — sujets de secours utilisés")
        topics = FALLBACK_TOPICS

    # Compléter avec fallback si pas assez
    if len(topics) < count:
        topics += FALLBACK_TOPICS
    topics = topics[:count + 4]  # marge de sécurité

    # 2. Générer les articles
    new_articles = []
    for i, item in enumerate(topics, start=1):
        if len(new_articles) >= count:
            break
        title = item.get("title", item.get("hint", ""))
        print(f"\n✍️   [{len(new_articles)+1}/{count}] {title[:60]}…")
        try:
            cat     = categorize(client, title, item.get("description", item.get("hint", "")))
            print(f"     📂 {cat}")
            article = generate_article(client, item, i, cat, YESTERDAY)
            print(f"     📝 {article['title'][:65]}")
            new_articles.append(article)
        except json.JSONDecodeError as e:
            print(f"     ❌ JSON invalide : {e} — sujet ignoré")
        except Exception as e:
            print(f"     ❌ Erreur API : {e} — sujet ignoré")

    if not new_articles:
        print("\n❌  Aucun article généré. Vérifiez ANTHROPIC_API_KEY.")
        return

    # 3. Sauvegarder (remplace tout)
    if dry_run:
        print(f"\n[dry-run] {len(new_articles)} articles générés, non sauvegardés.")
        print(json.dumps(new_articles[0], ensure_ascii=False, indent=2)[:500] + "\n  …")
    else:
        save_articles({"articles": new_articles})
        print(f"🗓️   Tous les articles datent du {YESTERDAY}.")


def cmd_add(client, api_key_news, count, dry_run):
    """Ajoute N articles sans toucher aux existants."""
    print(f"\n➕  Mode ADD — {count} article(s) à ajouter")
    print("━" * 55)

    data     = load_articles()
    existing = data.get("articles", [])
    next_id  = max((a["id"] for a in existing), default=0) + 1
    added    = 0

    if api_key_news:
        print("📡  Récupération NewsAPI…")
        try:
            topics = fetch_news_yesterday(api_key_news, count=count + 6)
            print(f"    {len(topics)} articles trouvés")
        except Exception as e:
            print(f"⚠️   NewsAPI erreur ({e}) — sujets de secours")
            topics = FALLBACK_TOPICS
    else:
        print("ℹ️   Pas de NEWS_API_KEY — sujets de secours")
        topics = FALLBACK_TOPICS

    for item in topics:
        if added >= count:
            break
        title = item.get("title", item.get("hint", ""))
        if is_duplicate(title, existing):
            print(f"⏭   Doublon : {title[:55]}…")
            continue
        print(f"\n✍️   [{added+1}/{count}] {title[:60]}…")
        try:
            cat     = categorize(client, title, item.get("description", ""))
            article = generate_article(client, item, next_id, cat, YESTERDAY)
            print(f"     📝 {article['title'][:65]}")
            existing.append(article)
            next_id += 1
            added   += 1
        except Exception as e:
            print(f"     ❌ {e}")

    if dry_run:
        print(f"\n[dry-run] {added} articles générés, non sauvegardés.")
    elif added > 0:
        data["articles"] = existing
        save_articles(data)
    else:
        print("\nℹ️  Aucun nouvel article (doublons ou erreurs).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agent CdM 2026 — rafraîchit ou enrichit articles.json via Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python agent.py --refresh            # remplace tout par les actus J-1
  python agent.py --refresh --count 8  # idem, 8 articles
  python agent.py --add --count 3      # ajoute 3 articles
  python agent.py --dry-run --refresh  # prévisualise sans écrire
  python agent.py --list               # liste les articles existants
        """,
    )
    parser.add_argument("--refresh",  action="store_true", help="Remplace TOUT le contenu par les actus J-1")
    parser.add_argument("--add",      action="store_true", help="Ajoute des articles sans remplacer les existants")
    parser.add_argument("--list",     action="store_true", help="Liste les articles existants et quitte")
    parser.add_argument("--count",    type=int, default=12, help="Nombre d'articles à générer (défaut : 12)")
    parser.add_argument("--dry-run",  action="store_true", help="Génère sans sauvegarder")
    args = parser.parse_args()

    # --list ne nécessite pas de clé API
    if args.list:
        cmd_list(load_articles().get("articles", []))
        return

    # Défaut implicite : --refresh si rien de précisé
    if not args.refresh and not args.add:
        args.refresh = True

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY manquante. Copiez .env.example → .env et renseignez votre clé.")
        sys.exit(1)

    client       = anthropic.Anthropic(api_key=api_key)
    api_key_news = os.getenv("NEWS_API_KEY")

    if args.refresh:
        cmd_refresh(client, api_key_news, args.count, args.dry_run)
    elif args.add:
        cmd_add(client, api_key_news, args.count, args.dry_run)


if __name__ == "__main__":
    main()
