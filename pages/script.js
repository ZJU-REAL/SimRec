const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Reveal on scroll */
const revealer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("in");
      revealer.unobserve(entry.target);
      entry.target.dispatchEvent(new Event("sr:in"));
    });
  },
  { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
);
document.querySelectorAll(".reveal").forEach((el) => revealer.observe(el));

/* Active section in navigation */
const navLinks = [...document.querySelectorAll('.sr-nav nav a[href^="#"]')];
const spy = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${entry.target.id}`));
    });
  },
  { rootMargin: "-45% 0px -50% 0px" },
);
["method", "how", "results", "takeaways"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) spy.observe(el);
});

/* Hero: the example conversation arrives message by message */
(() => {
  const thread = document.querySelector("[data-sr-thread]");
  if (!thread || reduceMotion) return;
  const items = [...thread.children];
  const typing = document.createElement("div");
  typing.className = "sr-typing";
  typing.innerHTML = "<i></i><i></i><i></i>";
  thread.classList.add("live");
  let visible = true;
  new IntersectionObserver(([e]) => (visible = e.isIntersecting)).observe(thread);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const side = (el) => (el.classList.contains("user") ? "user" : "rec");
  async function loop() {
    for (;;) {
      items.forEach((el) => el.classList.remove("on"));
      for (const el of items) {
        while (!visible) await wait(400);
        const bubble = el.classList.contains("sr-b");
        if (bubble) {
          typing.className = `sr-typing on ${side(el)}`;
          thread.insertBefore(typing, el);
          await wait(side(el) === "user" ? 900 : 700);
          typing.remove();
        }
        el.classList.add("on");
        await wait(bubble ? 900 : 700);
      }
      await wait(4200);
    }
  }
  loop();
})();

/* Segmented control helper */
function segmented(group, onChange) {
  const buttons = [...group.querySelectorAll("button")];
  buttons.forEach((button) =>
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      onChange(button.dataset.v);
    }),
  );
}

/* ------------------------------ Results ------------------------------ */
(() => {
  // Aggregate results reported in the paper (README).
  const results = {
    esci: [
      ["Qwen3-4B Base", "", [32.23, 72.03, 21.2]],
      ["ChatCRS", "", [34.36, 76.8, 22.31]],
      ["SimRec-4B", "external simulator", [35.42, 77.91, 24.08], "me"],
      ["SimRec-4B + self-play", "", [34.72, 75.81, 22.42], "var"],
      ["SimRec-4B + BM25", "BM25 retrieval", [24.02, 65.37, 14.76], "var"],
    ],
    c4: [
      ["Qwen3-4B Base", "", [22.94, 56.21, 8.3]],
      ["ChatCRS", "", [22.12, 57.96, 7.61]],
      ["SimRec-4B", "external simulator", [24.72, 59.18, 9.75], "me"],
      ["SimRec-4B + self-play", "", [19.77, 49.54, 7.14], "var"],
      ["SimRec-4B + BM25", "BM25 retrieval", [15.88, 40.77, 5.75], "var"],
    ],
  };
  const names = { esci: "ESCI", c4: "Amazon C4" };
  const metrics = ["NDCG@100", "Recall@100", "Hit@1"];
  const extra = {
    "c4-0": " SimRec-4B has the highest aggregate Amazon C4 NDCG@100 among all methods reported in the paper.",
    "c4-1": " In the paper’s full comparison, BLAIR-LARGE has the highest Amazon C4 Recall@100 (63.01).",
  };
  const bars = document.querySelector("[data-sr-bars]");
  const note = document.querySelector("[data-sr-res-note]");
  const table = document.querySelector("[data-sr-table]");
  if (!bars) return;
  let dataset = "esci";
  let metric = 0;
  let shown = false;

  bars.innerHTML = results.esci
    .map(
      ([name, sub, , kind]) => `
      <div class="sr-bar ${kind || ""}">
        <span class="lbl">${name}${sub ? `<small>${sub}</small>` : ""}</span>
        <span class="track"><i></i></span>
        <output></output>
      </div>`,
    )
    .join("");
  table.innerHTML = Object.entries(results)
    .flatMap(([key, rows]) =>
      rows.map(
        ([name, , v, kind]) =>
          `<tr class="${kind === "me" ? "me" : ""}"><td>${names[key]}</td><td>${name}</td>${v
            .map((x) => `<td>${x.toFixed(2)}</td>`)
            .join("")}</tr>`,
      ),
    )
    .join("");

  const tiles = [...document.querySelectorAll("[data-sr-metric] button")];
  function render() {
    const rows = results[dataset];
    tiles.forEach((tile, k) => {
      const ours = rows[2][2][k];
      const delta = ours - rows[0][2][k];
      tile.querySelector("[data-tile-val]").textContent = ours.toFixed(2);
      tile.querySelector("[data-tile-delta]").textContent = `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)} vs. base`;
    });
    const max = Math.ceil((Math.max(...rows.map((r) => r[2][metric])) * 1.15) / 10) * 10;
    [...bars.children].forEach((el, i) => {
      const v = rows[i][2][metric];
      el.querySelector("i").style.setProperty("--w", shown ? (v / max) * 100 : 0);
      el.querySelector("output").textContent = v.toFixed(2);
    });
    const base = rows[0][2][metric];
    const ours = rows[2][2][metric];
    const delta = (ours - base).toFixed(2);
    note.innerHTML =
      `<b>${names[dataset]} ${metrics[metric]}:</b> SimRec-4B ${ours.toFixed(2)} vs. ${base.toFixed(2)} for the ` +
      `Qwen3-4B base (+${delta}). Axis from 0 to ${max}.` +
      (extra[`${dataset}-${metric}`] || "");
  }
  segmented(document.querySelector("[data-sr-dataset]"), (v) => {
    dataset = v;
    render();
  });
  segmented(document.querySelector("[data-sr-metric]"), (v) => {
    metric = Number(v);
    render();
  });
  render();
  const card = bars.closest(".reveal");
  const show = () => {
    shown = true;
    requestAnimationFrame(render);
  };
  if (card.classList.contains("in")) show();
  else card.addEventListener("sr:in", show, { once: true });
})();

/* Component ablations (Amazon C4) */
(() => {
  const host = document.querySelector("[data-sr-abl]");
  if (!host) return;
  const rows = [
    ["Full SimRec", 24.72, 9.75],
    ["w/o preference tool", 21.17, 7.65],
    ["w/o item-detail tool", 23.42, 6.04],
    ["w/o multi-turn feedback", 22.14, 8.06],
  ];
  const cols = [
    ["NDCG@100", 1, 30],
    ["Hit@1", 2, 12],
  ];
  host.innerHTML = cols
    .map(
      ([label, k, max]) => `
      <div>
        <h4>${label} <span>(axis 0–${max})</span></h4>
        ${rows
          .map((r, i) => {
            const d = r[k] - rows[0][k];
            return `<div class="sr-bar ${i === 0 ? "me" : "var"}">
              <span class="lbl">${r[0]}</span>
              <span class="track"><i data-w="${(r[k] / max) * 100}"></i></span>
              <output>${r[k].toFixed(2)}${i ? `<small>(${d.toFixed(2).replace("-", "−")})</small>` : ""}</output>
            </div>`;
          })
          .join("")}
      </div>`,
    )
    .join("");
  const card = host.closest(".reveal");
  const show = () =>
    requestAnimationFrame(() => host.querySelectorAll("i[data-w]").forEach((i) => i.style.setProperty("--w", i.dataset.w)));
  if (card.classList.contains("in")) show();
  else card.addEventListener("sr:in", show, { once: true });
})();

/* ------------------- Method figure: search, ask, learn ------------------- */
(() => {
  const fig = document.querySelector("[data-sr]");
  if (!fig) return;
  const stage = fig.querySelector("[data-sr-stage]");
  const svg = fig.querySelector("[data-sr-wires]");
  const tabs = [...fig.querySelectorAll("[data-sr-phase]")];
  const playButton = fig.querySelector("[data-sr-play]");
  const panels = [...fig.querySelectorAll("[data-sr-panel]")];
  const ep = fig.querySelector(".sr-ep");
  const tools = fig.querySelector(".sr-tools");
  const rl = fig.querySelector(".sr-rl");
  const anchor = (key) => fig.querySelector(`[data-sr-a="${key}"]`);
  const NS = "http://www.w3.org/2000/svg";
  const types = ["user", "rec", "obs", "hit"];
  const typeOf = (el) => types.find((t) => el.classList.contains(t));

  /* Token strip: one token block per message, revealed with its message */
  const strip = fig.querySelector("[data-sr-strip]");
  const msgs = [...fig.querySelectorAll(".sr-msg")];
  const stripTypes = [];
  msgs.forEach((m) => {
    const type = typeOf(m);
    for (let k = 0; k < Number(m.dataset.n || 2); k++) {
      const t = document.createElement("i");
      t.className = `sr-tk ${type}`;
      t.dataset.p = m.dataset.p;
      t.dataset.s = m.dataset.s;
      strip.append(t);
      stripTypes.push(type);
    }
  });

  /* Rollouts: the first is the episode above; the others are illustrative */
  const expand = (spec) => spec.flatMap(([type, n]) => Array(n).fill(type));
  const rollouts = [
    ["τ1", stripTypes],
    ["τ2", expand([["user", 4], ["rec", 3], ["obs", 5], ["rec", 2], ["obs", 3], ["hit", 2]])],
    ["τ3", expand([["user", 4], ["rec", 2], ["user", 2], ["rec", 3], ["obs", 5], ["hit", 2], ["user", 3], ["rec", 3], ["obs", 4], ["hit", 2]])],
    null,
    ["τ8", expand([["user", 4], ["rec", 3], ["obs", 5], ["rec", 2], ["obs", 4], ["rec", 2], ["obs", 3], ["hit", 2]])],
  ];
  const rowsHost = fig.querySelector("[data-sr-rows]");
  rollouts.forEach((row) => {
    const el = document.createElement("div");
    if (!row) {
      el.className = "sr-row more";
      el.dataset.p = "3";
      el.dataset.s = "1";
      el.textContent = "⋮";
      rowsHost.append(el);
      return;
    }
    const [label, seq] = row;
    el.className = "sr-row";
    el.innerHTML = `<span class="rl">${label}</span><span class="sr-tkline"></span><span class="r" data-p="3" data-s="6">r<sub>${label.slice(1)}</sub></span>`;
    const line = el.querySelector(".sr-tkline");
    seq.forEach((type, i) => {
      const t = document.createElement("i");
      t.className = `sr-tk ${type}`;
      t.dataset.p = "3";
      t.dataset.s = "1";
      t.style.transitionDelay = `${Math.min(i, 40) * 12}ms`;
      line.append(t);
    });
    rowsHost.append(el);
  });

  /* Token masking toggle */
  const maskButtons = [...fig.querySelectorAll("[data-sr-mask]")];
  function setMask(mode) {
    rl.dataset.mask = mode;
    maskButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.srMask === mode)));
  }
  maskButtons.forEach((b) =>
    b.addEventListener("click", (event) => {
      event.stopPropagation();
      setMask(b.dataset.srMask);
    }),
  );

  /* ---------- Wires routed between live element boxes ---------- */
  let wires = {};
  const shown = (el) => el && el.getClientRects().length > 0 && el.closest(".sr-panel").getClientRects().length > 0;
  function box(el) {
    const r = el.getBoundingClientRect();
    const s = stage.getBoundingClientRect();
    const l = r.left - s.left;
    const t = r.top - s.top;
    return { l, t, r: l + r.width, b: t + r.height, cx: l + r.width / 2, cy: t + r.height / 2 };
  }
  const colors = { call: "var(--rec)", ret: "var(--obs)", rl: "var(--rl)" };
  function routes() {
    const out = {};
    const gut = parseFloat(getComputedStyle(fig).getPropertyValue("--gut")) || 30;
    const e = box(ep);
    if (shown(tools)) {
      const t0 = box(tools);
      const side = t0.l > e.r - 2;
      ["search", "detail", "pref"].forEach((key) => {
        const call = fig.querySelector(`[data-tool="${key}"]`);
        const ret = fig.querySelector(`[data-ret="${key}"]`);
        const tool = box(fig.querySelector(`[data-sr-tool="${key}"]`));
        const c = box(call);
        const o = box(ret);
        if (side) {
          const x1 = e.r + (t0.l - e.r) * 0.32;
          const x2 = e.r + (t0.l - e.r) * 0.68;
          out[`call-${key}`] = [1, "call", [[c.r, c.cy], [x1, c.cy], [x1, tool.cy - 6], [tool.l, tool.cy - 6]]];
          out[`ret-${key}`] = [1, "ret", [[tool.l, tool.cy + 6], [x2, tool.cy + 6], [x2, o.cy], [o.r, o.cy]]];
        } else {
          const x1 = e.r + gut * 0.32;
          const x2 = e.r + gut * 0.68;
          out[`call-${key}`] = [1, "call", [[c.r, c.cy], [x1, c.cy], [x1, tool.cy - 6], [tool.r, tool.cy - 6]]];
          out[`ret-${key}`] = [1, "ret", [[tool.r, tool.cy + 6], [x2, tool.cy + 6], [x2, o.cy], [o.r, o.cy]]];
        }
      });
    }
    if (shown(rl)) {
      const roll = box(anchor("rollouts"));
      const rew = box(anchor("reward"));
      const upd = box(anchor("update"));
      const r = box(rl);
      const sideBySide = rew.l > roll.r;
      if (sideBySide) {
        out["rl-reward"] = [3, "rl", [[roll.r, roll.cy], [rew.l, roll.cy]]];
        out["rl-update"] = [3, "rl", [[rew.r, roll.cy], [upd.l, roll.cy]]];
      } else {
        out["rl-reward"] = [3, "rl", [[roll.cx, roll.b], [rew.cx, rew.t]]];
        out["rl-update"] = [3, "rl", [[rew.cx, rew.b], [upd.cx, upd.t]]];
      }
      if (shown(ep)) {
        const s = box(anchor("strip"));
        const mid = (e.b + r.t) / 2;
        out["strip-rl"] = [3, "rl", [[s.cx, s.b], [s.cx, mid], [roll.cx, mid], [roll.cx, roll.t]]];
        const pol = box(anchor("policy"));
        const rec = box(anchor("rec"));
        const xl = e.l - gut * 0.5;
        const yb = r.b + 16;
        const yt = e.t - 12;
        out["loop"] = [3, "rl", [[pol.cx, pol.b], [pol.cx, yb], [xl, yb], [xl, yt], [rec.cx, yt], [rec.cx, rec.t]]];
      }
    }
    return out;
  }
  function pathData(pts, radius = 12) {
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i - 1];
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[i + 1];
      const l1 = Math.hypot(x1 - x0, y1 - y0) || 1;
      const l2 = Math.hypot(x2 - x1, y2 - y1) || 1;
      const k = Math.min(radius, l1 / 2, l2 / 2);
      d += ` L${x1 + ((x0 - x1) / l1) * k},${y1 + ((y0 - y1) / l1) * k}`;
      d += ` Q${x1},${y1} ${x1 + ((x2 - x1) / l2) * k},${y1 + ((y2 - y1) / l2) * k}`;
    }
    const [lx, ly] = pts[pts.length - 1];
    return `${d} L${lx},${ly}`;
  }
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
  };
  function drawWires() {
    const keep = Object.fromEntries(Object.entries(wires).map(([id, w]) => [id, w.g.getAttribute("class")]));
    svg.replaceChildren();
    const defs = make("defs", {});
    Object.entries(colors).forEach(([kind, color]) => {
      const marker = make("marker", {
        id: `sr-arrow-${kind}`,
        markerWidth: 9,
        markerHeight: 9,
        refX: 8,
        refY: 4.5,
        orient: "auto",
        markerUnits: "userSpaceOnUse",
      });
      marker.append(make("path", { d: "M0,0.5 L9,4.5 L0,8.5 z", style: `fill: ${color}` }));
      defs.append(marker);
    });
    svg.append(defs);
    wires = {};
    Object.entries(routes()).forEach(([id, [phase, kind, pts]]) => {
      const d = pathData(pts);
      const g = make("g", { style: `--wc: ${colors[kind]}` });
      const base = make("path", { class: "base", d, "marker-end": `url(#sr-arrow-${kind})` });
      const flow = make("path", { class: "flow", d });
      const dot = make("circle", { class: "dot", r: 4.5, cx: pts[0][0], cy: pts[0][1] });
      g.append(base, flow, dot);
      svg.append(g);
      const len = flow.getTotalLength();
      flow.style.strokeDasharray = `${len} ${len}`;
      flow.style.strokeDashoffset = keep[id]?.includes("done") ? 0 : len;
      if (keep[id]) g.setAttribute("class", keep[id]);
      wires[id] = { g, flow, dot, len, phase };
    });
    markWires();
  }
  function markWires() {
    Object.values(wires).forEach((w) => w.g.classList.toggle("on", w.phase === phase));
  }
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  function flow(id, ms) {
    const run = token;
    const start = performance.now();
    return new Promise((resolve) => {
      function frame(now) {
        const w = wires[id];
        if (run !== token || !w) return resolve();
        const t = Math.min(1, (now - start) / ms);
        const at = w.len * ease(t);
        const p = w.flow.getPointAtLength(at);
        w.flow.style.strokeDashoffset = w.len - at;
        w.dot.setAttribute("cx", p.x);
        w.dot.setAttribute("cy", p.y);
        w.g.classList.add("live");
        if (t < 1) return requestAnimationFrame(frame);
        w.g.classList.remove("live");
        w.g.classList.add("done");
        resolve();
      }
      requestAnimationFrame(frame);
    });
  }
  function clearWires() {
    Object.values(wires).forEach((w) => {
      w.g.classList.remove("live", "done");
      w.flow.style.strokeDashoffset = w.len;
    });
  }

  /* ---------- Effects ---------- */
  const lit = (p, s) => fig.querySelectorAll(`[data-p="${p}"][data-s="${s}"]`).forEach((el) => el.classList.add("lit"));
  function hot(el) {
    fig.querySelectorAll(".sr-msg.hot, .sr-tool.hot").forEach((h) => h !== el && h.classList.remove("hot"));
    if (el) el.classList.add("hot");
  }
  function bump(el) {
    if (!el) return;
    el.classList.remove("bump");
    void el.offsetWidth;
    el.classList.add("bump");
  }
  const msg = (p, s) => fig.querySelector(`.sr-msg[data-p="${p}"][data-s="${s}"]`);
  const tool = (key) => fig.querySelector(`[data-sr-tool="${key}"]`);
  function say(p, s) {
    lit(p, s);
    hot(msg(p, s));
  }
  function toolCall(p, s, key) {
    return [
      [600, () => say(p, s)],
      [750, (ms) => {
        hot(tool(key));
        flow(`call-${key}`, ms);
      }],
      [650, (ms) => flow(`ret-${key}`, ms)],
      [700, () => say(p, s + 1)],
    ];
  }

  /* ---------- Sequences: [duration ms, action] ---------- */
  const sequences = {
    1: [
      [700, () => {
        say(1, 1);
        bump(anchor("user"));
      }],
      ...toolCall(1, 2, "search"),
      ...toolCall(1, 4, "detail"),
      ...toolCall(1, 6, "pref"),
      [1500, () => {}],
    ],
    2: [
      [800, () => say(2, 1)],
      [900, () => {
        say(2, 2);
        bump(anchor("user"));
      }],
      [1000, () => say(2, 3)],
      [1100, () => {
        say(2, 4);
        bump(anchor("user"));
      }],
      [1000, () => say(2, 5)],
      [900, () => say(2, 6)],
      [1800, () => bump(anchor("final"))],
    ],
    3: [
      [900, (ms) => {
        hot(null);
        flow("strip-rl", ms);
      }],
      [900, () => lit(3, 1)],
      [1000, () => setMask("external")],
      [1300, () => setMask("selfplay")],
      [800, () => setMask("external")],
      [800, (ms) => flow("rl-reward", ms)],
      [1100, () => lit(3, 5)],
      [900, () => lit(3, 6)],
      [800, (ms) => flow("rl-update", ms)],
      [900, () => lit(3, 7)],
      [1300, (ms) => flow("loop", ms)],
      [1600, () => bump(anchor("rec"))],
    ],
  };

  /* ---------- Player ---------- */
  let token = 0;
  let phase = 1;
  let playing = !reduceMotion;
  let inView = false;
  let running = false;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  function setActive(p, dim) {
    phase = p;
    fig.dataset.active = String(p);
    fig.toggleAttribute("data-dim", dim);
    panels.forEach((panel) => panel.classList.toggle("on", panel.dataset.srPanel.split(" ").includes(String(p))));
    tabs.forEach((tab) => tab.setAttribute("aria-pressed", String(Number(tab.dataset.srPhase) === p)));
    markWires();
  }
  function settle() {
    fig.classList.remove("sr-run");
    fig.querySelectorAll("[data-p]").forEach((el) => el.classList.add("lit"));
    hot(null);
    clearWires();
    tabs.forEach((tab) => tab.style.setProperty("--t", 0));
  }
  function stop() {
    token++;
    running = false;
    settle();
  }
  async function run(p) {
    const my = ++token;
    running = true;
    tabs.forEach((tab) => tab.style.setProperty("--t", 0));
    setActive(p, true);
    fig.classList.add("sr-run");
    fig.querySelectorAll("[data-p]").forEach((el) => el.classList.toggle("lit", Number(el.dataset.p) < p));
    hot(null);
    drawWires();
    clearWires();
    const steps = sequences[p];
    const total = steps.reduce((sum, [ms]) => sum + ms, 0);
    const tab = tabs[p - 1];
    const start = performance.now();
    (function progressFrame(now) {
      if (my !== token) return;
      tab.style.setProperty("--t", Math.min(1, (now - start) / total));
      requestAnimationFrame(progressFrame);
    })(start);
    for (const [ms, action] of steps) {
      action(ms);
      await wait(ms);
      if (my !== token) return;
    }
    if (playing && inView) run((p % 3) + 1);
    else stop();
  }
  function select(p) {
    stop();
    if (playing && inView) run(p);
    else {
      setActive(p, true);
      drawWires();
    }
  }
  function setPlaying(next) {
    playing = next;
    fig.toggleAttribute("data-paused", !next);
    playButton.setAttribute("aria-label", next ? "Pause animation" : "Play animation");
    if (next) run(phase);
    else stop();
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => select(Number(tab.dataset.srPhase))));
  panels.forEach((panel) =>
    panel.addEventListener("click", () => {
      const ps = panel.dataset.srPanel.split(" ").map(Number);
      if (!ps.includes(phase) || !running) select(ps.includes(phase) ? phase : ps[0]);
    }),
  );
  playButton.addEventListener("click", () => setPlaying(!playing));

  new IntersectionObserver(
    ([entry]) => {
      inView = entry.isIntersecting;
      if (inView && playing && !running) run(phase);
      if (!inView && running) stop();
    },
    { threshold: 0.25 },
  ).observe(stage);

  let queued = false;
  new ResizeObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      drawWires();
    });
  }).observe(stage);
  document.fonts?.ready.then(drawWires);

  fig.toggleAttribute("data-paused", !playing);
  fig.querySelectorAll("[data-p]").forEach((el) => el.classList.add("lit"));
  setActive(1, false);
  drawWires();
})();

/* Copy BibTeX */
document.querySelectorAll("[data-copy]").forEach((button) =>
  button.addEventListener("click", async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied ✓";
    } catch {
      button.textContent = "Select and copy";
    }
    button.classList.add("done");
    setTimeout(() => {
      button.textContent = "Copy BibTeX";
      button.classList.remove("done");
    }, 1800);
  }),
);
