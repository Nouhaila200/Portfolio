# 🤖 job-alert — Veille automatique d'offres CDI Data en France

> Script Python de veille emploi qui scrape **France Travail**, **Welcome to the Jungle** et **Indeed**, filtre les offres **CDI Data** publiées dans les **dernières 24h**, et envoie des alertes via **Telegram** toutes les **30 minutes**.

---

## 📁 Structure du projet

```
job-alert/
├── config.yaml                   # Configuration (tokens, mots-clés, localisation)
├── main.py                       # Point d'entrée — orchestration & planification
├── requirements.txt              # Dépendances Python
├── README.md                     # Ce fichier
├── job_alert.log                 # Logs générés à l'exécution (auto-créé)
├── sources/
│   ├── __init__.py
│   ├── france_travail.py         # Source : API France Travail v2 (OAuth2)
│   ├── welcome_to_the_jungle.py  # Source : WTTJ via flux RSS
│   └── indeed.py                 # Source : Indeed via flux RSS
├── alerting/
│   ├── __init__.py
│   └── telegram.py               # Envoi de messages Telegram (HTML formaté)
└── storage/
    ├── storage.py                # Gestion JSON des offres déjà vues
    └── seen_jobs.json            # Base de données locale des IDs vus
```

---

## ⚙️ Prérequis

- **Python 3.10+**
- Un compte **France Travail Développeurs** (gratuit) → [francetravail.io](https://francetravail.io)
- Un **bot Telegram** (créé via [@BotFather](https://t.me/BotFather))
- Votre **chat_id** Telegram

---

## 🚀 Installation

### 1. Cloner / télécharger le projet

```bash
git clone <url-du-repo>
cd job-alert
```

### 2. Créer un environnement virtuel

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

---

## 🔑 Configuration

Editez `config.yaml` avec vos identifiants :

```yaml
telegram:
  bot_token: "123456789:ABCDefGhIJKlmNoPQRstuVWxyz"
  chat_id: "987654321"

france_travail:
  client_id: "VOTRE_CLIENT_ID"
  client_secret: "VOTRE_CLIENT_SECRET"

keywords:
  - "Data Engineer"
  - "Data Analyst"
  - "Data Scientist"
  - "Data Architect"
  - "Analytics Engineer"

location:
  country: "France"
  city: ""           # Laisser vide pour toute la France

settings:
  check_interval_minutes: 30
  max_age_hours: 24
  contract_type: "CDI"
  seen_jobs_file: "storage/seen_jobs.json"
  log_level: "INFO"
```

### Obtenir les credentials France Travail

1. Créez un compte sur [francetravail.io](https://francetravail.io/data/api)
2. Créez une application et abonnez-vous à l'API **"Offres d'emploi v2"**
3. Copiez le `client_id` et le `client_secret` dans `config.yaml`

### Créer un bot Telegram

1. Ouvrez Telegram et cherchez **@BotFather**
2. Tapez `/newbot` et suivez les instructions
3. Copiez le **token** fourni dans `config.yaml`
4. Pour obtenir votre `chat_id`, envoyez un message à votre bot puis visitez :
   ```
   https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates
   ```
   Cherchez le champ `"id"` dans `"chat"`.

---

## ▶️ Utilisation

### Lancement en mode continu (planifié toutes les 30 min)

```bash
python main.py
```

### Exécution unique immédiate (pour tester)

```bash
python main.py --once
```

### Mode test sans envoi Telegram (dry-run)

```bash
python main.py --dry-run --once
```

### Fichier de config personnalisé

```bash
python main.py --config chemin/vers/ma_config.yaml
```

---

## 📲 Exemple d'alerte Telegram reçue

```
🚀 Nouvelle offre CDI Data
──────────────────────────────
💼 Poste : Data Engineer
🏢 Entreprise : Société Générale
📍 Lieu : Paris (75)
📝 Contrat : CDI
📅 Publiée : 15/04/2026 09:30
🔗 Source : France Travail
──────────────────────────────
👉 Voir l'offre
```

---

## 🗂️ Fonctionnement interne

```
main.py
  ├── Charge config.yaml
  ├── [toutes les 30 min] run_pass()
  │     ├── collect_all_jobs()
  │     │     ├── france_travail.fetch_jobs()   → API OAuth2
  │     │     ├── welcome_to_the_jungle.fetch_jobs() → RSS feedparser
  │     │     └── indeed.fetch_jobs()           → RSS feedparser
  │     ├── filter_new_jobs()                   → diff avec seen_jobs.json
  │     ├── send_job_alert()  [pour chaque offre]
  │     └── mark_batch_as_seen()                → màj seen_jobs.json
  └── schedule.every(30).minutes
```

---

## 📊 Logs

Les logs sont écrits à la fois dans la console et dans `job_alert.log` :

```
2026-04-15 09:30:00 [INFO    ] main — 🚀 Début de la passe de veille
2026-04-15 09:30:01 [INFO    ] sources.france_travail — France Travail — 'Data Engineer' : 12 offre(s) trouvée(s)
2026-04-15 09:30:03 [INFO    ] sources.indeed — Indeed RSS — 'Data Scientist' : 5 offre(s) éligible(s)
2026-04-15 09:30:05 [INFO    ] main — 🆕 Nouvelles offres après filtre : 8 / 34
2026-04-15 09:30:10 [INFO    ] alerting.telegram — ✅ Alerte envoyée : [France Travail] Data Engineer @ Société Générale
```

---

## 🔒 Sécurité

> **Ne commitez jamais votre `config.yaml` avec de vrais tokens !**

Ajoutez-le à votre `.gitignore` :

```gitignore
config.yaml
*.log
storage/seen_jobs.json
venv/
__pycache__/
```

Ou utilisez des variables d'environnement et adaptez `load_config()` dans `main.py`.

---

## 🤝 Contribution

Les sources sont modulaires : pour ajouter une nouvelle source, créez simplement `sources/ma_source.py` avec une fonction `fetch_jobs(keywords, max_age_hours, location) -> List[Dict]` et importez-la dans `main.py`.

---

## 📄 Licence

MIT — Libre d'utilisation et de modification.
