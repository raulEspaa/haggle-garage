// Haggle Garage client. Vanilla JS, no build step (ADR-0009).
//
// SECURITY RULE: text from the model (or the player) is ALWAYS inserted with textContent,
// never innerHTML. The model's output is untrusted input to the browser (OWASP LLM05).
// A test greps this file to keep it that way.
"use strict";

const $ = (id) => document.getElementById(id);
const usd = (n) => "$" + Number(n).toLocaleString("en-US");
let game = null; // {id, token, carTitle, turnCap}

const store = {
  // sessionStorage can throw (private mode, blocked storage): the game must still work.
  save(g) { try { sessionStorage.setItem("haggle.game", JSON.stringify(g)); } catch (_) {} },
  load() { try { return JSON.parse(sessionStorage.getItem("haggle.game")); } catch (_) { return null; } },
  clear() { try { sessionStorage.removeItem("haggle.game"); } catch (_) {} },
};

async function api(path, { method = "GET", body, token } = {}) {
  const headers = { "Accept": "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["X-Game-Token"] = token;
  const response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // RFC 9457 Problem Details from the server: {title, detail}
    const error = new Error([data.title, data.detail].filter(Boolean).join(": ") || "Request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

function bubble(role, text, meta) {
  const line = document.createElement("div");
  line.className = "bubble " + (role === "buyer" ? "me" : "sam");
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "buyer" ? "You" : "Sam";
  const body = document.createElement("p");
  body.textContent = text; // text only, never parsed as HTML
  line.append(who, body);
  if (meta) {
    const small = document.createElement("small");
    small.textContent = meta;
    line.append(small);
  }
  $("chat").append(line);
  $("chat").scrollTop = $("chat").scrollHeight;
}

function setBusy(busy) {
  for (const id of ["send", "message", "walk"]) $(id).disabled = busy;
  $("send").textContent = busy ? "Sam is thinking…" : "Send";
}

function updateBar(turn, cap, offer) {
  $("game-turns").textContent = `Turn ${turn}/${cap}`;
  $("game-offer").textContent = offer ? `On the table: ${usd(offer)}` : "";
}

function showResult(title, detail) {
  store.clear();
  $("game").hidden = true;
  $("result").hidden = false;
  $("result-title").textContent = title;
  $("result-detail").textContent = detail;
}

function finish(status, deal, floor) {
  if (status === "deal" && deal) {
    showResult(`Sold to you for ${usd(deal.price_usd)}!`,
      `The secret floor was ${usd(floor)}. You captured ${Math.round(deal.discount_captured * 100)}% of the possible discount.`);
  } else if (status === "turn_limit") {
    showResult("Out of turns.", `No deal. The secret floor was ${usd(floor)}.`);
  } else if (status === "expired") {
    showResult("The game expired.", `The secret floor was ${usd(floor)}.`);
  } else {
    showResult("You walked away.", `The secret floor was ${usd(floor)}.`);
  }
}

async function start() {
  $("setup-error").textContent = "";
  const car = document.querySelector("input[name=car]:checked").value;
  const level = Number(document.querySelector("input[name=level]:checked").value);
  $("start").disabled = true;
  try {
    const created = await api("/api/games", { method: "POST", body: { car_id: car, level } });
    game = { id: created.game_id, token: created.game_token, carTitle: created.car.title, turnCap: created.turn_cap, level };
    store.save(game);
    $("setup").hidden = true;
    $("game").hidden = false;
    $("chat").replaceChildren();
    $("game-car").textContent = `${created.car.title} · Level ${level}`;
    updateBar(0, created.turn_cap, created.car.list_price_usd);
    bubble("seller", created.seller_message);
    $("message").focus();
  } catch (error) {
    $("setup-error").textContent = error.message;
  } finally {
    $("start").disabled = false;
  }
}

async function send(event) {
  event.preventDefault();
  const text = $("message").value.trim();
  if (!text || !game) return;
  $("game-error").textContent = "";
  bubble("buyer", text);
  $("message").value = "";
  setBusy(true);
  try {
    const reply = await api(`/api/games/${game.id}/messages`, { method: "POST", body: { text }, token: game.token });
    const meta = reply.offer_on_table_usd ? `${reply.intent} · ${usd(reply.offer_on_table_usd)}` : reply.intent;
    bubble("seller", reply.seller_message, meta);
    updateBar(reply.turn, game.turnCap, reply.offer_on_table_usd);
    if (reply.status !== "open") finish(reply.status, reply.deal, reply.floor_usd);
  } catch (error) {
    if (error.status === 504) {
      // The dealer is slow, not gone: the seller usually finishes the turn anyway.
      $("game-error").textContent = "Sam is taking a while… his answer will appear here.";
      await waitForLateReply();
    } else {
      $("game-error").textContent = error.message;
    }
  } finally {
    setBusy(false);
    $("message").focus();
  }
}

async function waitForLateReply() {
  const before = $("chat").children.length;
  for (let attempt = 0; attempt < 12; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    try {
      const state = await api(`/api/games/${game.id}`, { token: game.token });
      if (state.transcript.length > before) {
        const late = state.transcript[state.transcript.length - 1];
        if (late.role === "seller") bubble("seller", late.content);
        updateBar(state.turn, state.turn_cap, null);
        $("game-error").textContent = "";
        if (state.status !== "open") finish(state.status, state.deal, state.floor_usd);
        return;
      }
    } catch (_) { /* keep waiting */ }
  }
  $("game-error").textContent = "Sam did not answer. Please send your message again.";
}

async function guess(event) {
  event.preventDefault();
  if (!game) return;
  const amount = Number($("guess").value);
  try {
    const result = await api(`/api/games/${game.id}/floor-guess`, { method: "POST", body: { amount_usd: amount }, token: game.token });
    showResult(result.correct ? "You cracked it!" : "Not quite.",
      `You guessed ${usd(amount)}; the secret floor was ${usd(result.floor_usd)} (${result.error_pct}% off).`);
  } catch (error) {
    $("game-error").textContent = error.message;
  }
}

async function walk() {
  if (!game) return;
  try {
    const state = await api(`/api/games/${game.id}/end`, { method: "POST", token: game.token });
    finish(state.status, state.deal, state.floor_usd);
  } catch (error) {
    $("game-error").textContent = error.message;
  }
}

async function resume() {
  // Reloading the page keeps the game (token kept in sessionStorage for this tab only).
  const saved = store.load();
  if (!saved) return;
  try {
    const state = await api(`/api/games/${saved.id}`, { token: saved.token });
    if (state.status !== "open") { store.clear(); return; }
    game = saved;
    $("setup").hidden = true;
    $("game").hidden = false;
    $("game-car").textContent = `${saved.carTitle} · Level ${saved.level}`;
    updateBar(state.turn, state.turn_cap, null);
    for (const line of state.transcript) bubble(line.role, line.content);
  } catch (_) {
    store.clear();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("start").addEventListener("click", start);
  $("message-form").addEventListener("submit", send);
  $("guess-form").addEventListener("submit", guess);
  $("walk").addEventListener("click", walk);
  $("again").addEventListener("click", () => { $("result").hidden = true; $("setup").hidden = false; game = null; });
  resume();
});
