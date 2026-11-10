"use strict";
// Log frontal minimal (optionnel). Envoie des visites au serveur si disponible.
(function() {
  try {
    var API = (window.CONFIG && window.CONFIG.API) ? window.CONFIG.API : window.location.origin;
    fetch(API + "/api/visit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ts: Date.now() }) }).catch(function() {});
  } catch (e) {}
})();
