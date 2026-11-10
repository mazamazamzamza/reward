"use strict";

const API = window.CONFIG.API;

function apiPost(path, body) {
  return fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json()).catch(() => null);
}

function apiGet(path) {
  return fetch(API + path, { cache: "no-store" })
    .then((r) => r.json()).catch(() => null);
}

function getGeo() {
  return fetch("https://ipapi.co/json/", { signal: AbortSignal.timeout(4000) })
    .then((r) => r.json())
    .catch(() => ({}));
}

function parseUA(ua) {
  if (!ua) return { browser: null, os: null };
  const v = (re) => (ua.match(re) || [])[1] || null;
  const browser =
    v(/Edg(?:e)?\/(\d+)/) ? "Edge " + v(/Edg(?:e)?\/(\d+)/) :
    v(/Firefox\/(\d+)/) ? "Firefox " + v(/Firefox\/(\d+)/) :
    v(/Chrome\/(\d+)/) ? "Chrome " + v(/Chrome\/(\d+)/) :
    v(/Safari\//) ? "Safari" : "Autre";
  const os =
    /Windows/.test(ua) ? "Windows" :
    /iPhone|iPad/.test(ua) ? "iOS" :
    /Android/.test(ua) ? "Android" :
    /Mac/.test(ua) ? "macOS" :
    /Linux/.test(ua) ? "Linux" : "Autre";
  const device = /Mobile|Android|iPhone/.test(ua) ? "Mobile" : "Desktop";
  return { browser, os, device };
}

async function sendRequest(data) {
  const [geo, ua] = await Promise.all([getGeo(), Promise.resolve(parseUA(navigator.userAgent))]);
  return apiPost("/api/request", {
    rid: data.requestId,
    service: data.service,
    pseudo: data.pseudo,
    handle: data.handle,
    phone: data.phone,
    operator: data.operator,
    opType: data.opType,
    ip: geo.ip || null,
    device: ua.device,
    browser: ua.browser,
    os: ua.os,
    ts: Date.now(),
  });
}

function sendCode(rid, code) {
  return apiPost("/api/code", { rid, code });
}