# Savoir & Réussite — Site Web (Forum Q/R + Critiques + Emails)

Ce projet est un **site web complet** (démo fonctionnelle) pour ta communauté **Savoir & Réussite** :

- Comptes utilisateurs (inscription / connexion)
- Publication de **sujets**
- **Réponses** sous les sujets
- **Critiques / commentaires** sous chaque réponse
- **Suivre un sujet** (abonnement)
- **Notification email (Gmail/SMTP)** quand une nouvelle réponse est postée

Technos : **Flask + SQLite + Flask-Login**.

---

## 1) Lancer le site en local

### A. Pré-requis
- Python 3.10+ recommandé

### B. Installation
```bash
cd savoir-reussite-web
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### C. Démarrer
```bash
python app.py
```

Ouvre : http://127.0.0.1:5000

> La base de données SQLite est créée automatiquement dans `instance/savoir_reussite.sqlite`.

---

## 2) Configurer l'envoi d'emails (Gmail / SMTP)

Par défaut, si SMTP n'est pas configuré, l'app **n'envoie pas d'email** et affiche le contenu en console (mode dev).

### Variables d'environnement
Exemple (Linux/Mac) :
```bash
export APP_BASE_URL="http://127.0.0.1:5000"
export SECRET_KEY="change-moi-en-production"

export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USE_TLS="1"
export SMTP_USER="tonadresse@gmail.com"
export SMTP_PASS="MOT_DE_PASSE_APPLICATION"  # IMPORTANT
export SMTP_FROM_NAME="Savoir & Réussite"
export SMTP_FROM_EMAIL="tonadresse@gmail.com"
```

### Important pour Gmail
Gmail n'accepte pas toujours le mot de passe normal. Il faut souvent utiliser un **mot de passe d'application** (app password) si tu as la vérification en 2 étapes.

---

## 3) Notifications incluses

Quand une nouvelle **réponse** est publiée sur un sujet :

1. L'auteur du sujet reçoit un email (si activé dans ses réglages)
2. Les abonnés (followers) du sujet reçoivent un email (si activé)

### Broadcast (optionnel / dangereux)
Tu peux activer un envoi à **tous les utilisateurs** à chaque réponse (⚠️ spam). Par défaut c'est désactivé.

```bash
export BROADCAST_NEW_REPLIES_TO_ALL="1"
```

---

## 4) Déploiement (production)

Pour mettre en ligne :
- Mettre un vrai `SECRET_KEY`
- Configurer `APP_BASE_URL` avec ton domaine
- Utiliser un serveur WSGI (ex: gunicorn) derrière Nginx
- Passer SQLite -> PostgreSQL si le site devient très grand (phase 2)

---

## 5) Prochaines améliorations (si tu veux un site “géant”)

- Votes + meilleure réponse
- Badges + réputation
- Modération avancée (signalements)
- Email digest hebdo
- Temps réel (websocket)
- API + application mobile


## 6) Docker (optionnel)

```bash
docker compose up --build
```

Puis ouvre : http://localhost:8000

Les données SQLite sont persistées dans le dossier `instance/`.
