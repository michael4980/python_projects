/* Бункер: клиент на Vue 3 (глобальная сборка, без шага сборки). */
const { createApp } = Vue;

const STORAGE_KEY = "bunker.session";

function loadSession() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); } catch (e) { return null; }
}
function saveSession(s) {
  try { if (s) localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); else localStorage.removeItem(STORAGE_KEY); } catch (e) {}
}

createApp({
  data() {
    const params = new URLSearchParams(location.search);
    return {
      cfg: { master_required: false, narrator: false, min_players: 3 },
      form: { name: "", mode: params.get("code") ? "join" : "join", code: (params.get("code") || "").toUpperCase(), master: "" },
      homeError: "",
      busy: false,
      session: loadSession(),
      state: null,
      me: null,
      connected: false,
      ws: null,
      retry: 0,
      toast: "",
      toastTimer: null,
      settings: { seats: 1, reveals_per_round: 1, specials: true },
      specialTarget: "",
      stopped: false,
      connectFailed: false,
    };
  },
  computed: {
    screen() {
      if (!this.session) return "home";
      if (!this.state || !this.me) return "connecting";
      if (this.state.phase === "lobby") return "lobby";
      if (this.state.phase === "finished") return "finished";
      return "game";
    },
    candidates() {
      if (!this.state || !this.state.vote) return [];
      return this.state.players.filter((p) => this.state.vote.candidates.includes(p.id));
    },
    otherAlive() {
      if (!this.state) return [];
      return this.state.players.filter((p) => p.status === "alive" && p.id !== this.me.id);
    },
    needsTarget() {
      return this.me && this.me.special && ["swap", "reveal"].includes(this.me.special.effect);
    },
    verdictClass() {
      const v = this.state.ending.verdict;
      return v.alive === 0 ? "bad" : v.dead === 0 ? "good" : "";
    },
  },
  created() {
    fetch("/api/config").then((r) => r.json()).then((c) => { this.cfg = c; }).catch(() => {});
    if (this.session) this.connect();
  },
  methods: {
    showToast(msg) {
      this.toast = msg;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ""; }, 4000);
    },
    async submitHome() {
      this.homeError = "";
      if (!this.form.name) { this.homeError = "Введите имя"; return; }
      this.busy = true;
      try {
        let r;
        if (this.form.mode === "create") {
          r = await fetch("/api/rooms", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: this.form.name, master_code: this.form.master }) });
        } else {
          if (!this.form.code) { this.homeError = "Введите код комнаты"; return; }
          r = await fetch(`/api/rooms/${encodeURIComponent(this.form.code.toUpperCase())}/join`, { method: "POST",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: this.form.name }) });
        }
        const data = await r.json().catch(() => ({}));
        if (!r.ok) { this.homeError = data.detail || "Не получилось"; return; }
        this.session = { code: data.code, token: data.token, player_id: data.player_id };
        saveSession(this.session);
        history.replaceState(null, "", location.pathname);
        this.connect();
      } catch (e) {
        this.homeError = "Нет связи с сервером";
      } finally {
        this.busy = false;
      }
    },
    connect() {
      if (!this.session) return;
      this.stopped = false;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/${this.session.code}?token=${encodeURIComponent(this.session.token)}`);
      this.ws = ws;
      ws.onopen = () => { this.connected = true; this.retry = 0; this.connectFailed = false; };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") {
          this.state = msg.state;
          this.me = msg.you;
          if (this.state.phase === "lobby" && this.me.is_host) {
            this.settings = { seats: this.state.seats, reveals_per_round: this.state.settings.reveals_per_round, specials: this.state.settings.specials };
          }
        } else if (msg.type === "error") {
          this.showToast(msg.message);
        }
      };
      ws.onclose = (ev) => {
        this.connected = false;
        if (ev.code === 4404) { this.resetSession("Комната не найдена или уже закрыта"); return; }
        if (this.stopped) return;
        this.retry++;
        if (!this.state && this.retry >= 4) this.connectFailed = true;
        const delay = Math.min(10000, 500 * Math.pow(2, this.retry));
        setTimeout(() => this.connect(), delay);
      };
      ws.onerror = () => {};
    },
    send(action) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) { this.showToast("Нет соединения"); return; }
      this.ws.send(JSON.stringify(action));
    },
    applySettings() {
      this.send({ type: "settings", seats: this.settings.seats, reveals_per_round: this.settings.reveals_per_round, specials: this.settings.specials });
    },
    canReveal(cat) {
      return this.state.phase === "reveal" && this.me.status === "alive" && !this.me.cards[cat].revealed && this.me.reveals_left > 0;
    },
    playSpecial() {
      this.send({ type: "special", target_id: this.needsTarget ? this.specialTarget : undefined });
      this.specialTarget = "";
    },
    confirmFinish() {
      if (confirm("Закрыть дверь сейчас? Все, кто в игре, окажутся в бункере, и игра перейдёт к концовке.")) {
        this.send({ type: "finish_now" });
      }
    },
    nameOf(pid) {
      const p = this.state.players.find((x) => x.id === pid);
      return p ? p.name : "?";
    },
    copyLink() {
      const url = `${location.origin}${location.pathname}?code=${this.state.code}`;
      const done = () => this.showToast("Ссылка скопирована: " + url);
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, () => prompt("Скопируйте ссылку", url));
      else prompt("Скопируйте ссылку", url);
    },
    months(m) {
      if (m < 12) return `${m} ${m === 1 ? "месяц" : m < 5 ? "месяца" : "месяцев"}`;
      const y = Math.floor(m / 12), r = m % 12;
      const ys = `${y} ${y % 10 === 1 && y !== 11 ? "год" : y % 10 >= 2 && y % 10 <= 4 && (y < 12 || y > 14) ? "года" : "лет"}`;
      return r ? `${ys} ${this.months(r)}` : ys;
    },
    statusText(s) { return { ok: "закрыто", partial: "частично", fail: "провал" }[s] || s; },
    paragraphs(t) { return (t || "").split(/\n+/).filter((x) => x.trim()); },
    resetSession(msg) {
      this.stopped = true;
      if (this.ws) { try { this.ws.close(); } catch (e) {} }
      this.ws = null; this.session = null; this.state = null; this.me = null; this.connected = false; this.connectFailed = false;
      saveSession(null);
      if (msg) this.homeError = msg;
    },
    leave() {
      if (this.state && this.state.phase !== "finished" && !confirm("Выйти из комнаты? Вернуться в эту партию будет нельзя.")) return;
      this.resetSession("");
    },
    goHome() {
      if (!this.session) return;
      this.leave();
    },
  },
}).mount("#app");
