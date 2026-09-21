const COLORS = {
  jev: "#c63b22",
  gpt: "#2a5d6e",
  human: "#2f5d3a",
  gold: "#b8860b",
};

function fmtPct(value, digits = 2) {
  return `${value.toFixed(digits)}%`;
}

function fmtNum(value, digits = 4) {
  return value.toFixed(digits);
}

function fmtCost(value) {
  if (value == null) return "n/a";
  if (value >= 10) return `~$${Math.round(value)}`;
  return `$${value.toFixed(2)}`;
}

function svgEl(name, attrs, children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  (children || []).forEach((child) => node.append(child));
  return node;
}

function rowChart(host, rows, { max, height = 34 }) {
  host.replaceChildren();
  const width = Math.max(host.clientWidth || 640, 320);
  const left = 178;
  const right = 72;
  const barW = width - left - right;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${rows.length * height + 6}`, role: "img" });

  rows.forEach((row, index) => {
    const y = 6 + index * height;
    const w = Math.max(2, (row.value / max) * barW);
    svg.append(
      svgEl("text", { class: "label", x: "0", y: String(y + 16), fill: "currentColor" }, [
        document.createTextNode(row.label),
      ]),
      svgEl("rect", {
        class: "bar",
        x: String(left),
        y: String(y + 4),
        width: String(w),
        height: "16",
        fill: row.color,
        opacity: row.muted ? "0.4" : "0.92",
      }),
      svgEl("text", { class: "value", x: String(left + w + 8), y: String(y + 16), fill: "currentColor" }, [
        document.createTextNode(row.display),
      ]),
    );
  });
  host.append(svg);
}

function metricStack(host, blocks) {
  host.replaceChildren();
  for (const block of blocks) {
    const wrap = document.createElement("div");
    const title = document.createElement("p");
    title.className = "bench-kicker";
    title.textContent = block.title;
    const chart = document.createElement("div");
    wrap.append(title, chart);
    host.append(wrap);
    rowChart(chart, block.rows, { max: block.max, height: block.height || 30 });
  }
}

const EssayCharts = {
  floors(host, figures) {
    const panel = figures.panel.arms;
    rowChart(
      host,
      [
        { label: "Human test–retest", value: figures.constants.human_ceiling_pct, display: fmtPct(figures.constants.human_ceiling_pct), color: COLORS.human },
        { label: "Paper’s published twin", value: figures.constants.paper_twin_pct, display: fmtPct(figures.constants.paper_twin_pct), color: "#8a9698" },
        { label: "Prior answers", value: panel.prior_answers_stateless.accuracy_pct, display: fmtPct(panel.prior_answers_stateless.accuracy_pct), color: COLORS.gpt },
        { label: "Demographics, stateless", value: panel.demographics_stateless.accuracy_pct, display: fmtPct(panel.demographics_stateless.accuracy_pct), color: COLORS.gpt, muted: true },
        { label: "Demographics, stateful", value: panel.demographics_stateful.accuracy_pct, display: fmtPct(panel.demographics_stateful.accuracy_pct), color: COLORS.gpt, muted: true },
      ],
      { max: 100, height: 34 },
    );
  },

  panel(host, figures) {
    const arms = [
      ["Demographics, stateless", figures.panel.arms.demographics_stateless, "#8a9698"],
      ["Demographics, stateful", figures.panel.arms.demographics_stateful, COLORS.gpt],
      ["Prior answers, stateless", figures.panel.arms.prior_answers_stateless, COLORS.gold],
    ];
    metricStack(host, [
      {
        title: "Accuracy",
        max: 100,
        rows: arms.map(([label, arm, color]) => ({
          label, value: arm.accuracy_pct, display: fmtPct(arm.accuracy_pct), color,
        })),
      },
      {
        title: "Yes/no distribution gap · lower better",
        max: 0.3,
        rows: arms.map(([label, arm, color]) => ({
          label, value: arm.soft_nominal, display: fmtNum(arm.soft_nominal), color,
        })),
      },
      {
        title: "Ordinal gap · lower better",
        max: 0.8,
        rows: arms.map(([label, arm, color]) => ({
          label, value: arm.soft_ordinal, display: fmtNum(arm.soft_ordinal, 3), color,
        })),
      },
      {
        title: "Collapsed columns",
        max: 30,
        rows: arms.map(([label, arm, color]) => ({
          label, value: arm.collapsed_columns, display: `${arm.collapsed_columns} / 108`, color,
        })),
      },
    ]);
  },

  comparison(host, figures) {
    const spec = [
      ["Jev Choice", "jev_choice", COLORS.jev, false],
      ["Jev + descriptions", "jev_described", "#e07a68", false],
      ["Jev Noul", "jev_noul", COLORS.gold, false],
      ["gpt-4.1 probabilities", "gpt41_probs", COLORS.gpt, false],
      ["gpt-4.1 hard answer", "gpt41_hard", "#7a8b90", true],
    ];
    const arm = (key) => figures.comparison.arms[key];
    metricStack(host, [
      {
        title: "Yes/no distribution gap · lower better",
        max: 0.22,
        rows: spec.map(([label, key, color, muted]) => ({
          label, value: arm(key).soft_nominal, display: fmtNum(arm(key).soft_nominal), color, muted,
        })),
      },
      {
        title: "Ordinal gap · lower better",
        max: 0.8,
        rows: spec.map(([label, key, color, muted]) => ({
          label, value: arm(key).soft_ordinal, display: fmtNum(arm(key).soft_ordinal), color, muted,
        })),
      },
      {
        title: "Calibration (ECE) · lower better",
        max: 0.4,
        rows: spec.map(([label, key, color, muted]) => ({
          label, value: arm(key).ece, display: fmtNum(arm(key).ece), color, muted,
        })),
      },
      {
        title: "Accuracy",
        max: 80,
        rows: spec.map(([label, key, color]) => ({
          label, value: arm(key).accuracy_pct, display: fmtPct(arm(key).accuracy_pct), color,
        })),
      },
    ]);
  },

  noul(host, figures) {
    metricStack(host, [
      {
        title: "Yes/no distribution gap · lower better",
        max: 0.22,
        rows: [
          { label: "Jev Choice", value: figures.noul.choice_soft_nominal, display: fmtNum(figures.noul.choice_soft_nominal), color: COLORS.jev },
          { label: "Jev Noul", value: figures.noul.noul_soft_nominal, display: fmtNum(figures.noul.noul_soft_nominal), color: COLORS.gold },
        ],
      },
      {
        title: "Cells that put probability zero on one option",
        max: 20,
        rows: [
          { label: "Jev Choice", value: figures.noul.choice_zero_pct, display: `${figures.noul.choice_zero_pct}%`, color: COLORS.jev },
          { label: "Jev Noul", value: figures.noul.noul_zero_pct, display: `${figures.noul.noul_zero_pct}%`, color: COLORS.gold },
        ],
      },
    ]);
  },

  grounding(host, figures) {
    const g = figures.grounding;
    metricStack(host, [
      {
        title: "Across the population · distribution gap · lower better",
        max: 0.2,
        rows: [
          { label: "14 demographics", value: g.demog_soft_nominal, display: fmtNum(g.demog_soft_nominal), color: COLORS.jev },
          { label: "620 prior answers", value: g.prior_soft_nominal, display: fmtNum(g.prior_soft_nominal), color: COLORS.gold },
        ],
      },
      {
        title: "Per person · rank correlation with the human · higher better",
        max: 0.2,
        rows: [
          { label: "14 demographics", value: g.demog_rho, display: fmtNum(g.demog_rho, 3), color: COLORS.jev },
          { label: "620 prior answers", value: g.prior_rho, display: fmtNum(g.prior_rho, 3), color: COLORS.gold },
        ],
      },
    ]);
  },

  segments(host, figures) {
    const seg = figures.segments;
    metricStack(host, [
      {
        title: "How much of the real gap between groups each arm reproduces",
        max: 1.4,
        rows: [
          { label: "The humans", value: 1, display: "1.00", color: COLORS.human },
          { label: "Jev Noul", value: seg.spread_jev, display: fmtNum(seg.spread_jev, 2), color: COLORS.gold },
          { label: "gpt-4.1 hard", value: seg.spread_gpt41, display: fmtNum(seg.spread_gpt41, 2), color: COLORS.gpt },
        ],
      },
    ]);
  },

  economics(host, figures) {
    const e = figures.economics;
    metricStack(host, [
      {
        title: "Cost for the same 24,596 answers",
        max: 150,
        rows: [
          { label: "Jev", value: e.jev_cost, display: fmtCost(e.jev_cost), color: COLORS.jev },
          { label: "gpt-4.1 · inferred", value: e.gpt41_cost, display: fmtCost(e.gpt41_cost), color: COLORS.gpt },
        ],
      },
      {
        title: "Wall clock for one 300-respondent run",
        max: 25,
        rows: [
          { label: `Jev · ${e.jev_concurrency} at a time`, value: e.jev_minutes, display: `${e.jev_minutes} min`, color: COLORS.jev },
          { label: `gpt-4.1 · ${e.gpt41_concurrency} at a time`, value: e.gpt41_minutes, display: `${e.gpt41_minutes} min`, color: COLORS.gpt },
        ],
      },
    ]);
  },

  cost(host, figures) {
    const arms = figures.comparison.arms;
    rowChart(
      host,
      [
        { label: "Jev Choice", value: arms.jev_choice.cost, display: fmtCost(arms.jev_choice.cost), color: COLORS.jev },
        { label: "Jev Noul", value: arms.jev_noul.cost, display: fmtCost(arms.jev_noul.cost), color: COLORS.gold },
        { label: "gpt-4.1 probabilities", value: arms.gpt41_probs.cost, display: fmtCost(arms.gpt41_probs.cost), color: COLORS.gpt },
      ],
      { max: 140, height: 38 },
    );
  },

  price(host, figures) {
    const price = figures.price;
    rowChart(
      host,
      [
        { label: "Humans · mean P(yes)", value: price.human_mean_p_yes, display: fmtNum(price.human_mean_p_yes, 3), color: COLORS.human },
        { label: "Jev Choice", value: price.jev_choice_mean_p_yes, display: fmtNum(price.jev_choice_mean_p_yes, 3), color: COLORS.jev },
        { label: "Jev Noul", value: price.jev_noul_mean_p_yes, display: fmtNum(price.jev_noul_mean_p_yes, 3), color: COLORS.gold },
        { label: "gpt-4.1 probabilities", value: price.gpt41_mean_p_yes, display: fmtNum(price.gpt41_mean_p_yes, 3), color: COLORS.gpt },
      ],
      { max: 0.7, height: 34 },
    );
  },

  demo(host, pairs, color) {
    rowChart(
      host,
      pairs.map(([label, value]) => ({
        label,
        value,
        display: fmtPct(value * 100, 0),
        color,
      })),
      { max: 1, height: 32 },
    );
  },
};
