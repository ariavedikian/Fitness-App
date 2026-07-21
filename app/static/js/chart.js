/**
 * A minimal, dependency-free SVG line chart, themed with the app's CSS tokens.
 *
 * Deliberately hand-rolled rather than pulling in a charting library: it keeps
 * the frontend framework-free and same-origin, scales crisply as inline SVG,
 * and colours itself from `main.css` (marks carry the series colour; all axis
 * and tick text stays in the muted-ink token).
 *
 * Handles one or more series that share a single x (time) axis. A shared x is
 * the honest model for this app — weigh-ins and daily totals are both indexed
 * by date — and it lets the crosshair line up every series at one date.
 */

const NS = "http://www.w3.org/2000/svg";

// viewBox units. The SVG scales to its container width; these are just the
// internal coordinate system, chosen to give the axis labels room to breathe.
const W = 720;
const H = 260;
const PAD = { top: 16, right: 16, bottom: 28, left: 52 };

const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function svgEl(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  return node;
}

/** "Nice" round tick values spanning [min, max] — 1/2/5×10ⁿ steps, the spacing
 *  that reads naturally on an axis. Returns [min] for a flat series. */
function niceTicks(min, max, count = 4) {
  if (!(max > min)) return [min];
  const rawStep = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(rawStep));
  const norm = rawStep / mag;
  const niceNorm = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  const step = niceNorm * mag;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-6; t += step) {
    // Kill floating-point fuzz like 179.99999999.
    ticks.push(Number(t.toFixed(6)));
  }
  return ticks;
}

/** Domain covering the data with a little breathing room, snapped out to
 *  whole ticks so the top and bottom gridlines are round numbers. */
function yDomain(values) {
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const span = dataMax - dataMin;
  const pad = span === 0 ? Math.max(1, Math.abs(dataMax) * 0.05) : span * 0.12;
  const lo = dataMin - pad;
  const hi = dataMax + pad;
  const ticks = niceTicks(lo, hi, 4);
  return {
    min: Math.min(lo, ticks[0]),
    max: Math.max(hi, ticks.at(-1)),
    ticks,
  };
}

/**
 * Render a tiny axis-less sparkline into `container` — just the shape of a
 * trend, for spots too small for a full chart (e.g. a dashboard card).
 *
 * Purely decorative: it carries no axis, labels, or hover, and is marked
 * aria-hidden because the surrounding text already states the numbers. Needs
 * at least two points; fewer clears the container.
 *
 * @param {HTMLElement} container
 * @param {number[]} values  y-values in order (oldest → newest)
 * @param {string} [color]   any CSS colour for the line
 */
export function renderSparkline(container, values, color = "var(--color-accent)") {
  if (values.length < 2) {
    container.replaceChildren();
    return;
  }

  const w = 160;
  const h = 40;
  const pad = 4;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const sx = (i) => pad + (i / (values.length - 1)) * (w - 2 * pad);
  const sy = (v) =>
    max === min ? h / 2 : pad + (1 - (v - min) / (max - min)) * (h - 2 * pad);

  const svg = svgEl("svg", {
    viewBox: `0 0 ${w} ${h}`,
    class: "sparkline",
    "aria-hidden": "true",
  });
  const d = values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${sx(i)} ${sy(v)}`)
    .join(" ");
  svg.append(
    svgEl("path", { class: "chart__line", d, fill: "none", stroke: color }),
  );
  // A dot marks the latest value — the end the eye should land on.
  svg.append(
    svgEl("circle", {
      cx: sx(values.length - 1),
      cy: sy(values.at(-1)),
      r: 2.5,
      fill: color,
    }),
  );
  container.replaceChildren(svg);
}

/**
 * Render a line chart into `container`.
 *
 * @param {HTMLElement} container
 * @param {object} config
 * @param {{points: {x:number, y:number}[], color: string, label?: string}[]} config.series
 *        Each series shares the same ordered x values. `x` is a sortable number
 *        (a timestamp); `color` is any CSS colour (e.g. "var(--color-accent)").
 * @param {(x:number)=>string} config.formatX  x value → axis/tooltip label
 * @param {(y:number)=>string} config.formatY  y value → axis-tick label
 * @param {(y:number)=>string} [config.formatValue]  y value → tooltip value
 *        (defaults to formatY; use it to add a unit only in the tooltip)
 * @param {string} config.ariaLabel            one-sentence summary for screen readers
 */
export function renderLineChart(container, config) {
  const { series, formatX, formatY, ariaLabel } = config;
  const formatValue = config.formatValue || formatY;

  const allX = series[0].points.map((p) => p.x);
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const xMin = Math.min(...allX);
  const xMax = Math.max(...allX);
  const { min: yMin, max: yMax, ticks: yTicks } = yDomain(allY);

  // Data → viewBox coordinate maps. Guard the degenerate single-x case so a
  // lone column of points lands mid-plot instead of dividing by zero.
  const sx = (x) =>
    xMax === xMin
      ? PAD.left + PLOT_W / 2
      : PAD.left + ((x - xMin) / (xMax - xMin)) * PLOT_W;
  const sy = (y) =>
    yMax === yMin
      ? PAD.top + PLOT_H / 2
      : PAD.top + (1 - (y - yMin) / (yMax - yMin)) * PLOT_H;

  const svg = svgEl("svg", {
    viewBox: `0 0 ${W} ${H}`,
    class: "chart__svg",
    role: "img",
    "aria-label": ariaLabel,
  });

  // --- y gridlines + labels ---
  for (const t of yTicks) {
    const y = sy(t);
    svg.append(
      svgEl("line", {
        class: "chart__grid",
        x1: PAD.left,
        y1: y,
        x2: W - PAD.right,
        y2: y,
      }),
    );
    const label = svgEl("text", {
      class: "chart__tick chart__tick--y",
      x: PAD.left - 8,
      y,
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    label.textContent = formatY(t);
    svg.append(label);
  }

  // --- x tick labels (endpoints, plus a middle one when there is room) ---
  const xTickXs =
    xMax === xMin ? [xMin] : [xMin, (xMin + xMax) / 2, xMax];
  for (const [i, xv] of xTickXs.entries()) {
    const label = svgEl("text", {
      class: "chart__tick",
      x: sx(xv),
      y: H - 8,
      "text-anchor": i === 0 ? "start" : i === xTickXs.length - 1 ? "end" : "middle",
    });
    label.textContent = formatX(xv);
    svg.append(label);
  }

  // --- series: line + markers ---
  for (const s of series) {
    const d = s.points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.x)} ${sy(p.y)}`)
      .join(" ");
    svg.append(
      svgEl("path", {
        class: "chart__line",
        d,
        fill: "none",
        stroke: s.color,
      }),
    );
    for (const p of s.points) {
      svg.append(
        svgEl("circle", {
          class: "chart__dot",
          cx: sx(p.x),
          cy: sy(p.y),
          r: 3,
          fill: s.color,
        }),
      );
    }
  }

  // --- hover layer: crosshair + highlight dots + tooltip ---
  const crosshair = svgEl("line", {
    class: "chart__crosshair",
    y1: PAD.top,
    y2: PAD.top + PLOT_H,
    x1: 0,
    x2: 0,
    hidden: "",
  });
  svg.append(crosshair);

  const highlights = series.map((s) => {
    const dot = svgEl("circle", { class: "chart__highlight", r: 4.5, fill: s.color, hidden: "" });
    svg.append(dot);
    return dot;
  });

  const tooltip = document.createElement("div");
  tooltip.className = "chart__tooltip";
  tooltip.hidden = true;

  const overlay = svgEl("rect", {
    class: "chart__overlay",
    x: PAD.left,
    y: PAD.top,
    width: PLOT_W,
    height: PLOT_H,
    fill: "transparent",
  });
  svg.append(overlay);

  function nearestIndex(dataX) {
    let best = 0;
    let bestDist = Infinity;
    allX.forEach((x, i) => {
      const dist = Math.abs(x - dataX);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    });
    return best;
  }

  function onMove(event) {
    const rect = svg.getBoundingClientRect();
    // Pointer px → viewBox units (the SVG stretches to fill its container).
    const vbX = ((event.clientX - rect.left) / rect.width) * W;
    // Invert sx to a data x, then snap to the nearest real point.
    const dataX =
      xMax === xMin ? xMin : xMin + ((vbX - PAD.left) / PLOT_W) * (xMax - xMin);
    const i = nearestIndex(dataX);
    const px = sx(allX[i]);

    crosshair.setAttribute("x1", px);
    crosshair.setAttribute("x2", px);
    crosshair.removeAttribute("hidden");

    const lines = [`<strong>${formatX(allX[i])}</strong>`];
    series.forEach((s, si) => {
      const p = s.points[i];
      highlights[si].setAttribute("cx", sx(p.x));
      highlights[si].setAttribute("cy", sy(p.y));
      highlights[si].removeAttribute("hidden");
      const swatch = s.label
        ? `<span class="chart__tooltip-swatch" style="background:${s.color}"></span>${s.label}: `
        : "";
      lines.push(`${swatch}${formatValue(p.y)}`);
    });
    tooltip.innerHTML = lines.join("<br>");
    tooltip.hidden = false;

    // Position the HTML tooltip over the point, in container px, nudged to
    // stay inside the container's width.
    const leftPx = (px / W) * rect.width;
    tooltip.style.left = `${leftPx}px`;
    tooltip.style.top = `${(sy(series[0].points[i].y) / H) * rect.height}px`;
  }

  function onLeave() {
    crosshair.setAttribute("hidden", "");
    highlights.forEach((h) => h.setAttribute("hidden", ""));
    tooltip.hidden = true;
  }

  overlay.addEventListener("pointermove", onMove);
  overlay.addEventListener("pointerleave", onLeave);

  const figure = document.createElement("div");
  figure.className = "chart__figure";
  figure.append(svg, tooltip);

  // A legend is mandatory for two or more series so identity is never carried
  // by colour alone; a single series is named by the section title instead.
  const labelled = series.filter((s) => s.label);
  if (labelled.length >= 2) {
    const legend = document.createElement("div");
    legend.className = "chart__legend";
    for (const s of labelled) {
      const item = document.createElement("span");
      item.className = "chart__legend-item";
      const swatch = document.createElement("span");
      swatch.className = "chart__legend-swatch";
      swatch.style.background = s.color;
      item.append(swatch, document.createTextNode(s.label));
      legend.append(item);
    }
    container.replaceChildren(legend, figure);
  } else {
    container.replaceChildren(figure);
  }
}
