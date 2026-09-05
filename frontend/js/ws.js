const listeners = new Set();
let socket = null;
let reconnectDelay = 1000;

function setDot(on) {
  const dot = document.getElementById("ws-dot");
  if (dot) dot.classList.toggle("on", on);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws`);

  socket.onopen = () => {
    setDot(true);
    reconnectDelay = 1000;
  };
  socket.onclose = () => {
    setDot(false);
    socket = null;
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 1.6, 20000);
  };
  socket.onerror = () => {
    try { socket.close(); } catch { /* noop */ }
  };
  socket.onmessage = (evt) => {
    let payload;
    try { payload = JSON.parse(evt.data); } catch { return; }
    for (const fn of listeners) fn(payload);
  };
}

export function startWS() {
  if (!socket) connect();
}

export function stopWS() {
  if (socket) { socket.close(); socket = null; }
  setDot(false);
}

export function onWSMessage(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
