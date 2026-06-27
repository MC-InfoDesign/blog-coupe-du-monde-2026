#!/usr/bin/env python3
"""
agent.py — Générateur & rafraîchisseur d'articles CdM 2026

Fonctionne avec Groq (GRATUIT, sans CB) ou Anthropic Claude.
Groq est utilisé par défaut si ANTHROPIC_API_KEY est absent.

Modes :
  python agent.py --refresh          # remplace TOUT par les actus J-1 (12 articles)
  python agent.py --refresh --count 8
  python agent.py --add --count 3
  python agent.py --list
  python agent.py --dry-run --refresh
"""
import os
import sys
import json
import random
import argparse
import requests
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ARTICLES_PATH = os.path.join(os.path.dirname(__file__), "articles.json")
CATEGORIES    = ["Résultats", "Équipes", "Transferts", "Analyse tactique"]
YESTERDAY     = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
TODAY         =  datetime.now(timezone.utc).strftime("%Y-%m-%d")

AUTHORS = [
    "Thomas Leblanc", "Sarah Dupont", "Marc Fontaine",
    "Julie Bernard", "Pierre Martin", "Camille Rousseau",
    "Nicolas Petit", "Laura Simon", "Antoine Morel",
    "Sophie Girard", "Julien Lambert", "Emma Leroy",
]

FALLBACK_TOPICS = [
    {"title": "Résultats J-1 : toutes les rencontres de la journée",          "hint": "Résultats"},
    {"title": "Analyse : les tactiques qui ont fait la différence hier",       "hint": "Analyse tactique"},
    {"title": "L'équipe surprise du jour : qui a impressionné ?",              "hint": "Équipes"},
    {"title": "Mercato : les rumeurs de transfert nées des performances J-1",  "hint": "Transferts"},
    {"title": "Buteurs du jour et statistiques clés de la journée",            "hint": "Résultats"},
    {"title": "Portrait : le joueur révélation de la journée",                 "hint": "Équipes"},
    {"title": "Décryptage tactique : le meilleur système observé hier",        "hint": "Analyse tactique"},
    {"title": "Blessures et absences : l'infirmerie après la journée",         "hint": "Équipes"},
    {"title": "Transferts chauds : les agents à l'oeuvre après les matchs",   "hint": "Transferts"},
    {"title": "Les tops et flops de la journée au Mondial 2026",               "hint": "Résultats"},
    {"title": "5-4-1 ou 4-3-3 : quel bloc défensif a mieux résisté hier ?",   "hint": "Analyse tactique"},
    {"title": "Classement des groupes mis à jour après la journée d'hier",    "hint": "Résultats"},
]


# ── Détection du provider ─────────────────────────────────────────────────────

def get_provider():
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    print("❌ Aucune clé API trouvée.")
    print("   → Groq (GRATUIT, sans CB) : https://console.groq.com")
    print("     Ajoute GROQ_API_KEY=gsk_... dans ton fichier .env")
    print("   → Anthropic Claude : https://console.anthropic.com")
    print("     Ajoute ANTHROPIC_API_KEY=sk-ant-... dans ton fichier .env")
    sys.exit(1)


# ── Client LLM unifié ─────────────────────────────────────────────────────────

def llm_chat(provider, messages, max_tokens=2500):
    """Appelle Groq ou Anthropic et retourne le texte de la réponse."""

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    else:  # anthropic
        try:
            import anthropic as _anthropic
        except ImportError:
            print("❌ pip install anthropic")
            sys.exit(1)
        client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        # Séparer system du reste
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs = {"model": "claude-sonnet-4-6", "max_tokens": max_tokens, "messages": user_msgs}
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
        return resp.content[0].text.strip()


# ── I/O articles.json ─────────────────────────────────────────────────────────

def load_articles():
    try:
        with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"articles": []}

def save_articles(data):
    with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ articles.json mis à jour — {len(data['articles'])} articles.")


# ── NewsAPI ───────────────────────────────────────────────────────────────────

def fetch_news(api_key, count=20):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q":        '"Coupe du Monde 2026" OR "World Cup 2026" OR "FIFA 2026"',
        "from":     YESTERDAY, "to": TODAY,
        "sortBy":   "relevancy",
        "pageSize": min(count * 2, 50),
        "language": "fr",
        "apiKey":   api_key,
    }
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    items = r.json().get("articles", [])
    if len(items) < count // 2:
        params["language"] = "en"
        r2 = requests.get(url, params=params, timeout=12)
        if r2.ok:
            items += r2.json().get("articles", [])
    return [
        {"title": a.get("title",""), "description": a.get("description","") or ""}
        for a in items if a.get("title") and "[Removed]" not in a.get("title","")
    ]


# ── Déduplication ─────────────────────────────────────────────────────────────

def is_duplicate(title, existing, threshold=0.62):
    return any(SequenceMatcher(None, title.lower(), a.get("title","").lower()).ratio() > threshold for a in existing)


# ── Génération d'article ──────────────────────────────────────────────────────

def categorize(provider, title, desc):
    prompt = (
        f"Catégorise cet article dans l'une de ces catégories exactement : "
        f"{', '.join(CATEGORIES)}\n\nTitre : {title}\nDescription : {desc}\n\n"
        f"Réponds avec UNIQUEMENT le nom exact de la catégorie."
    )
    result = llm_chat(provider, [{"role": "user", "content": prompt}], max_tokens=30)
    return result.strip() if result.strip() in CATEGORIES else CATEGORIES[0]


def generate_article(provider, item, article_id, category, date):
    title_hint = item.get("title", item.get("hint", "Actualité CdM 2026"))
    desc_hint  = item.get("description", item.get("hint", ""))

    prompt = f"""Tu es journaliste sportif pour un blog sur la Coupe du Monde 2026 (USA / Canada / Mexique, juin-juillet 2026).
La journée dont tu parles est le {date}.

Génère un article complet en français. Réponds avec du JSON valide uniquement (sans balises markdown).

Sujet : {title_hint}
Description : {desc_hint}
Catégorie : {category}

JSON attendu (ces clés exactement) :
{{
  "title":         "Titre accrocheur, max 90 caractères",
  "summary":       "Résumé de 2 à 3 phrases percutantes",
  "content":       "## Section 1\\n\\nParagraphe...\\n\\n## Section 2\\n\\nContenu... (min 5 paragraphes, 650 mots)",
  "tags":          ["tag1","tag2","tag3","tag4"],
  "imageKeywords": "2-4 mots EN ANGLAIS pour l'image (ex: france,football,match,goal)"
}}

Article factuel, ancré dans le Mondial 2026, style journalistique de qualité, en français courant."""

    raw = llm_chat(provider, [{"role": "user", "content": prompt}], max_tokens=2500)
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    gen = json.loads(raw)

    return {
        "id":            article_id,
        "title":         gen["title"],
        "category":      category,
        "date":          date,
        "author":        random.choice(AUTHORS),
        "summary":       gen["summary"],
        "content":       gen["content"],
        "tags":          gen.get("tags", ["CdM2026", "Football"]),
        "imageKeywords": gen.get("imageKeywords", "football,worldcup,match"),
    }


# ── Commandes ─────────────────────────────────────────────────────────────────

def cmd_list(articles):
    print(f"\n{len(articles)} articles dans articles.json :\n")
    for a in sorted(articles, key=lambda x: x.get("date",""), reverse=True):
        print(f"  [{a['id']:>2}] {a['date']}  [{a['category']:<20}]  {a['title'][:65]}")
    print()


def run_refresh(provider, news_key, count, dry_run):
    print(f"\nMode REFRESH — actus du {YESTERDAY}")
    print(f"Provider : {'Groq (Llama 3.3 70B)' if provider=='groq' else 'Anthropic Claude'}")
    print("─" * 50)

    if news_key:
        print("Recuperation NewsAPI...")
        try:
            topics = fetch_news(news_key, count=count + 8)
            print(f"  {len(topics)} articles trouves")
            if not topics:
                raise ValueError("aucun resultat")
        except Exception as e:
            print(f"  NewsAPI erreur ({e}) — sujets de secours")
            topics = FALLBACK_TOPICS
    else:
        print("Pas de NEWS_API_KEY — sujets de secours utilises")
        topics = FALLBACK_TOPICS

    if len(topics) < count:
        topics += FALLBACK_TOPICS
    topics = topics[:count + 4]

    new_articles = []
    for item in topics:
        if len(new_articles) >= count:
            break
        title = item.get("title", item.get("hint", ""))
        print(f"\n  [{len(new_articles)+1}/{count}] {title[:60]}...")
        try:
            cat     = categorize(provider, title, item.get("description", item.get("hint","")))
            article = generate_article(provider, item, len(new_articles)+1, cat, YESTERDAY)
            print(f"  OK : {article['title'][:65]}")
            new_articles.append(article)
        except json.JSONDecodeError as e:
            print(f"  JSON invalide, sujet ignore : {e}")
        except Exception as e:
            print(f"  Erreur : {e}")

    if not new_articles:
        print("\nAucun article genere. Verifiez votre cle API.")
        return

    if dry_run:
        print(f"\n[dry-run] {len(new_articles)} articles generes, non sauvegardes.")
    else:
        save_articles({"articles": new_articles})


def run_add(provider, news_key, count, dry_run):
    print(f"\nMode ADD — {count} article(s) a ajouter")
    print("─" * 50)

    data     = load_articles()
    existing = data.get("articles", [])
    next_id  = max((a["id"] for a in existing), default=0) + 1
    added    = 0

    if news_key:
        try:
            topics = fetch_news(news_key, count=count + 6)
        except Exception as e:
            print(f"NewsAPI erreur ({e}) — sujets de secours")
            topics = FALLBACK_TOPICS
    else:
        topics = FALLBACK_TOPICS

    for item in topics:
        if added >= count:
            break
        title = item.get("title", item.get("hint",""))
        if is_duplicate(title, existing):
            continue
        try:
            cat     = categorize(provider, title, item.get("description",""))
            article = generate_article(provider, item, next_id, cat, YESTERDAY)
            existing.append(article)
            next_id += 1
            added   += 1
            print(f"  OK : {article['title'][:65]}")
        except Exception as e:
            print(f"  Erreur : {e}")

    if not dry_run and added > 0:
        data["articles"] = existing
        save_articles(data)
    elif added == 0:
        print("Aucun nouvel article (doublons ou erreurs).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent CdM 2026 — Groq (gratuit) ou Anthropic")
    parser.add_argument("--refresh",  action="store_true", help="Remplace tout par les actus J-1")
    parser.add_argument("--add",      action="store_true", help="Ajoute des articles")
    parser.add_argument("--list",     action="store_true", help="Liste les articles existants")
    parser.add_argument("--count",    type=int, default=12)
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    if args.list:
        cmd_list(load_articles().get("articles", []))
        return

    if not args.refresh and not args.add:
        args.refresh = True

    provider     = get_provider()
    news_key     = os.getenv("NEWS_API_KEY")

    if args.refresh:
        run_refresh(provider, news_key, args.count, args.dry_run)
    else:
        run_add(provider, news_key, args.count, args.dry_run)


if __name__ == "__main__":
    main()
