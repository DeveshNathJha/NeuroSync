// Small dependency-free SVG charts (no external libraries, works offline).

import { h, mmss, s } from "./dom.js";

const MARGIN = { top: 14, right: 16, bottom: 30, left: 48 };

function niceTicks(min, max, count) {
  if (!(max > min)) return [min];
  const step = (max - min) / Math.max(1, count - 1);
  return Array.from({ length: count }, (_, i) => min + i * step);
}

function scale(d0, d1, r0, r1) {
  const span = d1 - d0 || 1;
  return (v) => r0 + ((v - d0) / span) * (r1 - r0);
}

/**
 * Line chart, e.g. heart rate over a session.
 * points: [[x, y], ...]; spans: [{start, end, status}] shaded behind the line.
 * Returns null when there are fewer than two valid points (caller shows a text instead).
 */
export function lineChart({
  points, spans = [], baseline = null, title, yUnit = "",
  xFormat = mmss, width = 720, height = 220, showDots = false,
}) {
  const pts = (points || []).filter((p) => Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1])))
    .map((p) => [Number(p[0]), Number(p[1])]);
  if (pts.length < 2) return null;

  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  for (const sp of spans) {
    if (Number.isFinite(sp.start)) xs.push(sp.start);
    if (Number.isFinite(sp.end)) xs.push(sp.end);
  }
  if (Number.isFinite(baseline)) ys.push(baseline);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const pad = Math.max(3, (Math.max(...ys) - Math.min(...ys)) * 0.1);
  const yMin = Math.floor(Math.min(...ys) - pad);
  const yMax = Math.ceil(Math.max(...ys) + pad);

  const x = scale(xMin, xMax, MARGIN.left, width - MARGIN.right);
  const y = scale(yMin, yMax, height - MARGIN.bottom, MARGIN.top);

  const svg = s("svg", {
    class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": title || "Chart",
  });
  if (title) svg.append(s("title", {}, title));

  for (const sp of spans) {
    if (!Number.isFinite(sp.start) || !Number.isFinite(sp.end)) continue;
    const x0 = x(sp.start);
    const w = Math.max(2, x(sp.end) - x0);
    svg.append(s("rect", {
      class: `span span-${sp.status || "pending"}`, x: x0, y: MARGIN.top, width: w,
      height: height - MARGIN.top - MARGIN.bottom,
    }, s("title", {}, `${sp.label || "Event"} ${mmss(sp.start)}–${mmss(sp.end)} (${sp.status || "pending"})`)));
  }

  for (const tick of niceTicks(yMin, yMax, 5)) {
    const ty = y(tick);
    svg.append(s("line", { class: "grid", x1: MARGIN.left, x2: width - MARGIN.right, y1: ty, y2: ty }));
    svg.append(s("text", { class: "axis-label", x: MARGIN.left - 6, y: ty + 4, "text-anchor": "end" },
      `${Math.round(tick)}${yUnit ? ` ${yUnit}` : ""}`));
  }
  for (const tick of niceTicks(xMin, xMax, Math.min(6, pts.length))) {
    svg.append(s("text", { class: "axis-label", x: x(tick), y: height - 8, "text-anchor": "middle" }, xFormat(tick)));
  }

  if (Number.isFinite(baseline)) {
    const by = y(baseline);
    svg.append(s("line", { class: "baseline", x1: MARGIN.left, x2: width - MARGIN.right, y1: by, y2: by }));
    svg.append(s("text", { class: "axis-label baseline-label", x: width - MARGIN.right, y: by - 4, "text-anchor": "end" },
      `baseline ${Math.round(baseline)}`));
  }

  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  svg.append(s("path", { class: "line", d }));
  if (showDots) {
    for (const p of pts) {
      svg.append(s("circle", { class: "dot", cx: x(p[0]), cy: y(p[1]), r: 3.5 },
        s("title", {}, `${xFormat(p[0])}: ${Math.round(p[1])}${yUnit ? ` ${yUnit}` : ""}`)));
    }
  }
  return svg;
}

/**
 * Stacked bar chart, e.g. confirmed events per kind per session.
 * categories: x labels; series: [{label, values: [n per category]}].
 * Returns {chart, legend} or null when every value is zero.
 */
export function stackedBars({ categories, series, title, width = 720, height = 240 }) {
  const totals = categories.map((_, i) => series.reduce((sum, ser) => sum + (Number(ser.values[i]) || 0), 0));
  const maxTotal = Math.max(0, ...totals);
  if (!categories.length || maxTotal === 0) return null;

  const yMax = Math.max(1, Math.ceil(maxTotal));
  const y = scale(0, yMax, height - MARGIN.bottom, MARGIN.top);
  const plotW = width - MARGIN.left - MARGIN.right;
  const slot = plotW / categories.length;
  const barW = Math.max(6, Math.min(48, slot * 0.6));

  const svg = s("svg", {
    class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": title || "Chart",
  });
  if (title) svg.append(s("title", {}, title));

  const tickCount = Math.min(yMax, 5) + 1;
  for (const tick of niceTicks(0, yMax, tickCount)) {
    const ty = y(tick);
    svg.append(s("line", { class: "grid", x1: MARGIN.left, x2: width - MARGIN.right, y1: ty, y2: ty }));
    svg.append(s("text", { class: "axis-label", x: MARGIN.left - 6, y: ty + 4, "text-anchor": "end" },
      String(Math.round(tick))));
  }

  categories.forEach((cat, i) => {
    const cx = MARGIN.left + slot * i + slot / 2;
    let acc = 0;
    series.forEach((ser, si) => {
      const v = Number(ser.values[i]) || 0;
      if (!v) return;
      const yTop = y(acc + v);
      const yBottom = y(acc);
      svg.append(s("rect", {
        class: `bar series-${si % 6}`, x: cx - barW / 2, y: yTop, width: barW, height: Math.max(1, yBottom - yTop),
      }, s("title", {}, `${cat}: ${ser.label} ${v}`)));
      acc += v;
    });
    svg.append(s("text", { class: "axis-label", x: cx, y: height - 8, "text-anchor": "middle" }, cat));
  });

  const legend = h("ul", { class: "legend", "aria-label": "Legend" },
    series.map((ser, si) => h("li", {},
      h("span", { class: `swatch series-${si % 6}`, "aria-hidden": "true" }), ser.label)));
  return { chart: svg, legend };
}
