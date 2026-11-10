# Snap+ Rewardly

Site local de récompenses **Snapchat+ uniquement**. Basé sur l'ancien projet `rewardly`, recentré sur un seul service.

## Structure

```
snap-reward/
├── index.html          # Page d'accueil + formulaire Snap (3 étapes)
├── code.html           # Page d'attente + saisie du code SMS
├── admin.html          # Panel admin (gestion des demandes)
├── css/
│   └── main.css        # Styles (couleurs Snap : jaune/noir)
├── js/
│   ├── config.js
│   ├── api.js
│   ├── app.js          # Logique du formulaire Snap
│   ├── code.js         # Logique de la page code
│   └── admin.js        # Logique du panel admin
├── server.py           # Backend Python (HTTP + notifications Telegram/Discord)
├── data.json           # Base de données locale (générée automatiquement)
├── requirements.txt    # Dépendances Python
├── render.yaml         # Config de déploiement (Render)
└── README.md
```

## Lancer en local

### Prérequis
- Python 3 installé

### Installation

```bash
# Se placer dans le dossier
cd C:\snap-reward

# Installer les dépendances (optionnel, pour Discord/Telegram)
pip install -r requirements.txt

# Lancer le serveur
python server.py
```

Le site sera accessible sur `http://localhost:3000` (ou le port défini par `PORT`).

### Variables d'environnement (optionnel)

| Variable | Description |
|----------|-------------|
| `PORT` | Port du serveur (défaut: 3000) |
| `BOT_TOKEN` | Token du bot Discord (notifications) |
| `CHANNEL_ID` | ID du salon Discord |
| `DISCORD_ENABLED` | Mettre `1` pour activer le bot Discord |
| `TELEGRAM_TOKEN` | Token du bot Telegram |
| `TELEGRAM_CHAT_ID` | ID du chat Telegram |

Le mot de passe admin par défaut est `admin123` (modifiable dans `server.py`, ligne `ADMIN_PASS`).

## Flux utilisateur

1. **index.html** — Choix direct (Snap uniquement) → formulaire en 3 étapes :
   - Étape 1 : Pseudo
   - Étape 2 : Pseudo Snapchat (handle)
   - Étape 3 : Numéro de téléphone (validation 06/07 + opérateur)
2. Soumission → demande envoyée au serveur, statut "en attente"
3. **code.html** — Attente du déclenchement du code SMS par un admin, puis saisie des 4 chiffres
4. **admin.html** — Le modérateur voit la demande, peut envoyer le code, accepter, refuser ou bloquer le numéro

## Personnaliser

- **Couleur Snap** : dans `css/main.css`, `--accent` et `--svc` sont déjà en jaune Snap (`#FFFC00`).
- **Mot de passe admin** : dans `server.py`, modifie `ADMIN_PASS = "admin123"`.
- **Supprimer les notifications Discord/Telegram** : laisse `BOT_TOKEN` et `TELEGRAM_TOKEN` vides, le site fonctionne quand même en local.

## Pusher sur ton dépôt

Une fois prêt, depuis ce dossier :

```bash
git init
git add .
git commit -m "Site Snap+ Rewardly en local"
git remote add origin <TON_DEPOT>
git push -u origin main
```
