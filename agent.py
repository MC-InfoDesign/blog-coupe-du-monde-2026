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
import time
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
    {"title": "Analyse : les tactiques qui ont fait la différence hier",       "hint": "Analyse tactique"},
    {"title": "L'équipe surprise du jour : qui a impressionné ?",              "hint": "Équipes"},
    {"title": "Mercato : les rumeurs de transfert nées des performances J-1",  "hint": "Transferts"},
    {"title": "Portrait : le joueur révélation de la journée",                 "hint": "Équipes"},
    {"title": "Décryptage tactique : le meilleur système observé hier",        "hint": "Analyse tactique"},
    {"title": "Blessures et absences : l'infirmerie après la journée",         "hint": "Équipes"},
    {"title": "Transferts chauds : les agents à l'oeuvre après les matchs",   "hint": "Transferts"},
    {"title": "Les tops et flops de la journée au Mondial 2026",               "hint": "Résultats"},
    {"title": "5-4-1 ou 4-3-3 : quel bloc défensif a mieux résisté hier ?",   "hint": "Analyse tactique"},
    {"title": "Classement des groupes mis à jour après la journée d'hier",    "hint": "Résultats"},
]

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "schedule.json")

# Mapping noms ESPN (anglais) → noms schedule.json (français)
TEAM_NAME_MAP = {
    "Mexico": "Mexique", "South Africa": "Afrique du Sud", "South Korea": "Corée du Sud",
    "Czech Republic": "Tchéquie", "Czechia": "Tchéquie",
    "Switzerland": "Suisse", "Canada": "Canada", "Bosnia and Herzegovina": "Bosnie-Herzégovine",
    "Qatar": "Qatar", "Brazil": "Brésil", "Morocco": "Maroc", "Scotland": "Écosse",
    "Haiti": "Haïti", "USA": "USA", "United States": "USA", "Australia": "Australie",
    "Paraguay": "Paraguay", "Turkey": "Turquie", "Germany": "Allemagne",
    "Ivory Coast": "Côte d'Ivoire", "Ecuador": "Équateur", "Curacao": "Curaçao",
    "Netherlands": "Pays-Bas", "Japan": "Japon", "Sweden": "Suède", "Tunisia": "Tunisie",
    "Belgium": "Belgique", "Egypt": "Égypte", "Iran": "Iran", "New Zealand": "Nouvelle-Zélande",
    "Spain": "Espagne", "Cape Verde": "Cap-Vert", "Uruguay": "Uruguay",
    "Saudi Arabia": "Arabie Saoudite", "France": "France", "Norway": "Norvège",
    "Senegal": "Sénégal", "Iraq": "Irak", "Argentina": "Argentine", "Austria": "Autriche",
    "Algeria": "Algérie", "Jordan": "Jordanie", "Colombia": "Colombie", "Portugal": "Portugal",
    "DR Congo": "RD Congo", "Congo DR": "RD Congo", "Uzbekistan": "Ouzbékistan", "England": "Angleterre",
    "Ghana": "Ghana", "Croatia": "Croatie", "Panama": "Panama",
}

def normalize_team(name):
    """Convertit un nom d'équipe ESPN en nom français du schedule."""
    return TEAM_NAME_MAP.get(name, name)

def fetch_espn_scores(date):
    """Fetch les scores du jour depuis l'API JSON ESPN (gratuite, sans clé)."""
    date_str = date.replace("-", "")  # 20260627
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_str}"
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.json()
    results = []
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status not in ("STATUS_FINAL", "STATUS_FULL_TIME"):
            continue
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        results.append({
            "home": normalize_team(home.get("team", {}).get("displayName", "")),
            "away": normalize_team(away.get("team", {}).get("displayName", "")),
            "homeScore": int(home.get("score", 0)),
            "awayScore": int(away.get("score", 0)),
        })
    return results

def update_schedule(date):
    """Met à jour schedule.json avec les vrais scores ESPN pour la date donnée."""
    print(f"\nMise à jour schedule.json pour le {date}...")
    try:
        scores = fetch_espn_scores(date)
    except Exception as e:
        print(f"  Erreur ESPN : {e}")
        return

    if not scores:
        print("  Aucun match terminé trouvé sur ESPN pour cette date.")
        return

    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            schedule = json.load(f)
    except Exception as e:
        print(f"  Impossible de lire schedule.json : {e}")
        return

    updated = 0
    for match in schedule.get("matches", []):
        if match.get("date") != date:
            continue
        home_fr = match["home"].split(" ", 1)[-1]
        away_fr = match["away"].split(" ", 1)[-1]
        for score in scores:
            if score["home"] == home_fr and score["away"] == away_fr:
                match["homeScore"] = score["homeScore"]
                match["awayScore"] = score["awayScore"]
                match["status"]    = "terminé"
                updated += 1
                print(f"  ✓ {home_fr} {score['homeScore']}-{score['awayScore']} {away_fr}")
                break
            # ESPN retourne parfois home/away inversés
            elif score["home"] == away_fr and score["away"] == home_fr:
                match["homeScore"] = score["awayScore"]
                match["awayScore"] = score["homeScore"]
                match["status"]    = "terminé"
                updated += 1
                print(f"  ✓ {home_fr} {score['awayScore']}-{score['homeScore']} {away_fr}")
                break

    if updated:
        schedule["lastUpdated"] = date
        with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
            json.dump(schedule, f, ensure_ascii=False, indent=2)
        print(f"  {updated} match(s) mis à jour dans schedule.json")
    else:
        print("  Aucun match correspondant trouvé (vérifier les noms d'équipes).")

def get_match_topics(date):
    """Retourne un topic par match terminé à la date donnée, avec score réel."""
    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            schedule = json.load(f)
    except Exception:
        return []

    topics = []
    for m in schedule.get("matches", []):
        if m.get("date") != date or m.get("status") != "terminé":
            continue
        home = m["home"].split(" ", 1)[-1]   # retire l'emoji
        away = m["away"].split(" ", 1)[-1]
        hs   = m.get("homeScore", "?")
        as_  = m.get("awayScore", "?")
        note = m.get("note", "")
        phase = m.get("phase", "Groupes")
        venue = m.get("venue", "")
        topics.append({
            "title": f"{home} {hs}-{as_} {away} : les moments forts",
            "hint": "Résultats",
            "match_context": (
                f"Match : {home} vs {away}, score final {hs}-{as_}. "
                f"Phase : {phase}. Stade : {venue}. "
                f"{('Note : ' + note) if note else ''} "
                f"Date : {date}."
            ),
        })
    return topics


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

def llm_chat(provider, messages, max_tokens=2500, _retry=0):
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
        if resp.status_code == 429 and _retry < 2:
            time.sleep(8)
            return llm_chat(provider, messages, max_tokens, _retry + 1)
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

def get_tournament_context():
    """Résume l'état du tournoi depuis schedule.json pour le LLM."""
    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        return ""

    # Équipes qualifiées par groupe
    qualified = []
    for grp, teams in s.get("standings", {}).items():
        for t in teams:
            if t.get("q"):
                qualified.append(t["team"])

    # Prochains matchs à venir
    upcoming = []
    for m in s.get("matches", []):
        if m.get("status") in ("à venir", "TBD") and m.get("home") != "TBD":
            home = m["home"].split(" ", 1)[-1]
            away = m["away"].split(" ", 1)[-1]
            upcoming.append(f"{m['date']} — {home} vs {away} ({m.get('phase','?')})")
        if len(upcoming) >= 8:
            break

    # Derniers résultats
    recent = []
    for m in reversed(s.get("matches", [])):
        if m.get("status") == "terminé" and m.get("homeScore") is not None:
            home = m["home"].split(" ", 1)[-1]
            away = m["away"].split(" ", 1)[-1]
            recent.append(f"{home} {m['homeScore']}-{m['awayScore']} {away}")
        if len(recent) >= 6:
            break

    ctx = f"Équipes qualifiées : {', '.join(qualified)}.\n"
    if recent:
        ctx += f"Derniers résultats : {' | '.join(recent)}.\n"
    if upcoming:
        ctx += f"Prochains matchs : {' | '.join(upcoming)}.\n"
    return ctx


def generate_pertinent_topics(provider, count):
    """Demande au LLM de suggérer des sujets d'articles pertinents sur le tournoi en cours."""
    context = get_tournament_context()
    prompt = f"""Tu es rédacteur en chef d'un blog sur la Coupe du Monde 2026 (USA/Canada/Mexique, juin-juillet 2026).

Voici l'état actuel du tournoi :
{context}

Propose exactement {count} sujets d'articles PERTINENTS et VARIÉS pour aujourd'hui.
Chaque sujet doit être ancré dans ce qui se passe réellement : équipes qualifiées, chocs à venir, révélations, tactiques observées, histoires humaines des joueurs, enjeux des prochains matchs.
Évite les sujets trop génériques. Mêle : analyse tactique, portrait d'équipe, focus joueur, preview match à venir, bilan de groupe.

Réponds avec du JSON valide uniquement, un tableau de {count} objets :
[
  {{"title": "Titre accrocheur en français", "hint": "Résultats|Équipes|Transferts|Analyse tactique"}},
  ...
]"""
    try:
        raw = llm_chat(provider, [{"role": "user", "content": prompt}], max_tokens=800)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        topics = json.loads(raw)
        return [{"title": t["title"], "hint": t.get("hint", "Équipes")} for t in topics if "title" in t]
    except Exception as e:
        print(f"  Erreur génération sujets pertinents : {e}")
        return []


def categorize(provider, title, desc):
    prompt = (
        f"Catégorise cet article dans l'une de ces catégories exactement : "
        f"{', '.join(CATEGORIES)}\n\nTitre : {title}\nDescription : {desc}\n\n"
        f"Réponds avec UNIQUEMENT le nom exact de la catégorie."
    )
    result = llm_chat(provider, [{"role": "user", "content": prompt}], max_tokens=30)
    return result.strip() if result.strip() in CATEGORIES else CATEGORIES[0]


def generate_article(provider, item, article_id, category, date):
    title_hint    = item.get("title", item.get("hint", "Actualité CdM 2026"))
    desc_hint     = item.get("description", item.get("hint", ""))
    match_context = item.get("match_context", "")

    if match_context:
        extra = f"""
Contexte du match (UTILISE CES DONNÉES RÉELLES) :
{match_context}

L'article doit couvrir : le score final, les moments décisifs, les buteurs ou actions clés, l'ambiance et les conséquences pour la suite du tournoi. Invente des détails plausibles (buteurs, minutes, situations de jeu) cohérents avec le score réel."""
    else:
        extra = ""

    prompt = f"""Tu es journaliste sportif pour un blog sur la Coupe du Monde 2026 (USA / Canada / Mexique, juin-juillet 2026).
La journée dont tu parles est le {date}.

Génère un article complet en français. Réponds avec du JSON valide uniquement (sans balises markdown).

Sujet : {title_hint}
Description : {desc_hint}
Catégorie : {category}
{extra}

JSON attendu (ces clés exactement) :
{{
  "title":         "Titre accrocheur avec le score si c'est un résultat de match, max 90 caractères",
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

    # Topics matchs du jour en priorité absolue
    match_topics = get_match_topics(YESTERDAY)
    if match_topics:
        print(f"  {len(match_topics)} match(s) trouvé(s) dans schedule.json pour le {YESTERDAY}")

    if news_key:
        print("Recuperation NewsAPI...")
        try:
            news_topics = fetch_news(news_key, count=count + 8)
            print(f"  {len(news_topics)} articles trouves")
            if not news_topics:
                raise ValueError("aucun resultat")
        except Exception as e:
            print(f"  NewsAPI erreur ({e}) — sujets pertinents LLM")
            news_topics = []
    else:
        print("Pas de NEWS_API_KEY — sujets pertinents LLM")
        news_topics = []

    # Sujets pertinents générés par le LLM selon l'état du tournoi
    remaining = count - len(match_topics)
    if remaining > 0 and not news_topics:
        print(f"  Génération de {remaining} sujets pertinents via LLM...")
        news_topics = generate_pertinent_topics(provider, remaining)
        print(f"  {len(news_topics)} sujets pertinents générés")

    # Matchs d'abord, puis sujets pertinents, puis fallback si besoin
    topics = match_topics + news_topics
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
            time.sleep(3)  # pause pour éviter le rate limit Groq
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
    parser.add_argument("--refresh",         action="store_true", help="Remplace tout par les actus J-1")
    parser.add_argument("--add",             action="store_true", help="Ajoute des articles")
    parser.add_argument("--list",            action="store_true", help="Liste les articles existants")
    parser.add_argument("--update-schedule", action="store_true", help="Met à jour schedule.json avec scores ESPN")
    parser.add_argument("--count",           type=int, default=12)
    parser.add_argument("--dry-run",         action="store_true")
    args = parser.parse_args()

    if args.list:
        cmd_list(load_articles().get("articles", []))
        return

    if args.update_schedule:
        update_schedule(YESTERDAY)
        return

    if not args.refresh and not args.add:
        args.refresh = True

    provider = get_provider()
    news_key = os.getenv("NEWS_API_KEY")

    if args.refresh:
        # Mise à jour automatique des scores avant de générer les articles
        update_schedule(YESTERDAY)
        run_refresh(provider, news_key, args.count, args.dry_run)
    else:
        run_add(provider, news_key, args.count, args.dry_run)


if __name__ == "__main__":
    main()
