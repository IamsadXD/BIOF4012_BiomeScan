/* =========================================================================
   Biomescan platform — application

   Design rule: this file RENDERS, it does not COMPUTE. Every scientific number
   shown here was produced and validated by the Python pipeline and arrives via
   data/bundle.json. The only arithmetic performed in the browser is formatting,
   and the one live recomputation (coverage economics) is delegated to the
   server, which calls the same mikania.economics functions the pipeline uses.

   Two implementations of a metric is one implementation too many.
   ========================================================================= */

const S = { bundle: null, view: 'overview', site: null, layer: 'rgb', probe: null };

/* ------------------------------- helpers ------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2).toLowerCase(), v);
    else n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.appendChild(typeof kid === 'string' || typeof kid === 'number'
      ? document.createTextNode(String(kid)) : kid);
  }
  return n;
};
const pct = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : (v * 100).toFixed(d) + '%';
const num = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);
const hkd = v => (v === null || v === undefined) ? '—' : 'HK$' + Math.round(v).toLocaleString();
const clsColor = id => (S.bundle.classes.find(c => c.id === id) || {}).color || '#666';
const clsLabel = id => (S.bundle.classes.find(c => c.id === id) || {}).label || String(id);

/* -------------------------- tiny SVG chart kit -------------------------
   Hand-rolled rather than a charting library: no CDN (the platform must work
   offline on an evaluator's laptop), and the charts needed here are few and
   specific enough that a dependency would cost more than it saves.          */
function svgChart(w, h, pad = { t: 14, r: 14, b: 30, l: 44 }) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', `0 0 ${w} ${h}`);
  s.setAttribute('class', 'chart');
  s.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  return { s, w, h, pad, iw, ih,
    x: (t) => pad.l + t * iw,
    y: (t) => pad.t + (1 - t) * ih };
}
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) n.setAttribute(k, v);
  return n;
};
function axes(c, { xTicks = [], yTicks = [], xLabel = '', yLabel = '' }) {
  const g = svgEl('g', { class: 'axis' });
  g.appendChild(svgEl('line', { x1: c.pad.l, y1: c.pad.t + c.ih, x2: c.pad.l + c.iw, y2: c.pad.t + c.ih, stroke: 'currentColor', 'stroke-opacity': .18 }));
  g.appendChild(svgEl('line', { x1: c.pad.l, y1: c.pad.t, x2: c.pad.l, y2: c.pad.t + c.ih, stroke: 'currentColor', 'stroke-opacity': .18 }));
  yTicks.forEach(([t, lab]) => {
    const y = c.y(t);
    const ln = svgEl('line', { x1: c.pad.l, y1: y, x2: c.pad.l + c.iw, y2: y, stroke: '#1a212c' });
    g.appendChild(ln);
    const tx = svgEl('text', { x: c.pad.l - 7, y: y + 3.5, 'text-anchor': 'end' });
    tx.textContent = lab; g.appendChild(tx);
  });
  xTicks.forEach(([t, lab]) => {
    const x = c.x(t);
    const tx = svgEl('text', { x, y: c.pad.t + c.ih + 15, 'text-anchor': 'middle' });
    tx.textContent = lab; g.appendChild(tx);
  });
  if (xLabel) { const t = svgEl('text', { x: c.pad.l + c.iw / 2, y: c.h - 3, 'text-anchor': 'middle', class: 'lbl' }); t.textContent = xLabel; g.appendChild(t); }
  if (yLabel) { const t = svgEl('text', { x: 11, y: c.pad.t + c.ih / 2, 'text-anchor': 'middle', class: 'lbl', transform: `rotate(-90 11 ${c.pad.t + c.ih / 2})` }); t.textContent = yLabel; g.appendChild(t); }
  c.s.appendChild(g);
}

/* ================================ views ================================ */
const VIEWS = {};

/* ------------------------------- overview ------------------------------ */
VIEWS.overview = () => {
  const b = S.bundle;
  const kc = b.validation?.kill_criterion || {};
  const abl = b.separability?.sensor_ablation || {};
  const fol = abl.wet_summer || {};
  const bench = b.benchmark || {};
  const sweep = b.contrast_sweep || {};

  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Biomescan — Mikania reference demonstrator'),
    el('h1', {}, 'Invasive species mapping and surveying'),
    el('p', { class: 'lede' },
      'Biomescan develops surveys for invasive plants, animals and harmful insects, using ' +
      'target-specific sensing and field verification. This demonstrator covers Mikania: ' +
      'spectral library, Tier-2 scene simulation, ' +
      'site-disjoint validation, severity-ranked prioritisation, and post-treatment efficacy ' +
      'verification. Aedes breeding-habitat mapping and further species are planned; this demo ' +
      'does not detect mosquitoes or implement animal surveys. Scene imagery is simulated; ' +
      'the leaf spectra, the Hong Kong occurrence ' +
      'records and the benchmark hyperspectral cube are real open data.')));

  wrap.appendChild(el('div', { class: 'grid g4' },
    kpi('Kill criterion', kc.verdict || '—',
      `Mikania vs native ≥ ${pct(kc.threshold_accuracy, 0)}`,
      kc.verdict === 'PASS' ? 'good' : 'bad'),
    kpi('Mikania vs native', pct(kc.measured_accuracy),
      `leave-one-site-out · lower CI ${pct(kc.measured_accuracy_lower_ci)}`,
      kc.accuracy_pass ? 'good' : 'bad'),
    kpi('False positives', pct(kc.measured_false_positive),
      `native cleared by mistake · max ${pct(kc.threshold_false_positive, 0)}`,
      kc.false_positive_pass ? 'good' : 'bad'),
    kpi('Leakage inflation', (b.validation?.leakage_inflation_pp || 0).toFixed(1) + ' pp',
      'random pixel split vs site-disjoint', 'warn')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  // The two findings that matter most, stated up front.
  const s = el('section', {},
    el('h2', {}, 'What the pipeline establishes'),
    el('div', { class: 'grid g2' },
      el('div', { class: 'card' },
        el('h3', {}, 'The moat is seasonal, and it is measurable'),
        el('p', { class: 'hint' },
          'During the autumn bloom every sensor tier separates Mikania from native climbers — ' +
          'which reproduces the published finding that RGB deep learning works on blooming ' +
          'outbreak points. The advantage appears only in the foliage-only case.'),
        tierBars(abl)),
      el('div', { class: 'card' },
        el('h3', {}, 'Spatial leakage is real, and large'),
        el('p', { class: 'hint' },
          'Measured on the Botswana EO-1 Hyperion scene — real satellite hyperspectral data ' +
          'this project did not generate. Random pixel splitting inflates accuracy by ' +
          (bench.leakage_inflation_pp_trainable || 0).toFixed(1) + ' pp.'),
        leakageBars(bench))));
  wrap.appendChild(s);

  wrap.appendChild(el('div', { class: 'callout' },
    el('strong', {}, 'Scope of these numbers. '),
    'Accuracy figures come from simulated scenes at a chosen species contrast. They ' +
    'characterise the pipeline, not Hong Kong. Whether Mikania is genuinely separable from ' +
    'Bauhinia glauca and Byttneria aspera in real canopy remains unproven (proposal Appendix B.5) ' +
    'and is exactly what the Phase 0 ground spectral library buys. ' +
    (sweep.contrast_required_mean != null
      ? `The sweep in Validation shows the required real contrast is ≈ ${num(sweep.contrast_required_mean)} on the nominal scale.`
      : '')));

  return wrap;
};

function kpi(label, value, note, tone = '') {
  return el('div', { class: 'card kpi ' + tone },
    el('div', { class: 'label' }, label),
    el('div', { class: 'value' }, value),
    note ? el('div', { class: 'note' }, note) : null);
}

function tierBars(abl) {
  const tiers = ['rgb', 'multispectral', 'hyperspectral'];
  const names = { rgb: 'RGB', multispectral: '5-band MS', hyperspectral: 'Hyperspectral' };
  const c = svgChart(420, 190, { t: 16, r: 12, b: 34, l: 46 });
  axes(c, {
    yTicks: [[0, '40'], [0.25, '55'], [0.5, '70'], [0.75, '85'], [1, '100']],
    yLabel: 'balanced acc. (%)'
  });
  const norm = v => Math.max(0, Math.min(1, (v * 100 - 40) / 60));
  const bw = c.iw / (tiers.length * 2.4);
  tiers.forEach((t, i) => {
    const base = c.pad.l + c.iw * ((i + 0.5) / tiers.length);
    [['autumn_flower', '#5c6675'], ['wet_summer', '#34d3a0']].forEach(([sk, col], j) => {
      const v = abl[sk]?.[t]?.balanced_accuracy_mikania_vs_native;
      if (v == null) return;
      const y = c.y(norm(v)), y0 = c.y(0);
      c.s.appendChild(svgEl('rect', {
        x: base + (j - 1) * bw - 1, y, width: bw - 2, height: Math.max(y0 - y, 1),
        fill: col, rx: 2
      }));
    });
    const tx = svgEl('text', { x: base, y: c.pad.t + c.ih + 15, 'text-anchor': 'middle' });
    tx.textContent = names[t]; c.s.appendChild(tx);
  });
  const wrap = el('div', {});
  wrap.appendChild(c.s);
  wrap.appendChild(el('div', { class: 'legend' },
    el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#5c6675' }), 'in bloom (Sep–Nov)'),
    el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#34d3a0' }), 'foliage only (Jun–Aug)')));
  return wrap;
}

function leakageBars(bench) {
  const rows = [
    ['Random pixel split', bench.random_split_overall_accuracy, '#c0392b'],
    ['Spatially blocked', (bench.blocked_overall_accuracy_trainable_classes || [])[0], '#34d3a0'],
  ];
  const c = svgChart(420, 190, { t: 16, r: 12, b: 34, l: 46 });
  axes(c, { yTicks: [[0, '0'], [0.5, '50'], [1, '100']], yLabel: 'overall accuracy (%)' });
  rows.forEach(([lab, v, col], i) => {
    if (v == null) return;
    const x = c.pad.l + c.iw * ((i + 0.5) / rows.length);
    const y = c.y(v), y0 = c.y(0), bw = c.iw / (rows.length * 2.1);
    c.s.appendChild(svgEl('rect', { x: x - bw / 2, y, width: bw, height: y0 - y, fill: col, rx: 3 }));
    const t1 = svgEl('text', { x, y: y - 6, 'text-anchor': 'middle', class: 'lbl' });
    t1.textContent = pct(v, 1); c.s.appendChild(t1);
    const t2 = svgEl('text', { x, y: c.pad.t + c.ih + 15, 'text-anchor': 'middle' });
    t2.textContent = lab; c.s.appendChild(t2);
  });
  return c.s;
}

/* ------------------------------ evidence ------------------------------- */
VIEWS.evidence = () => {
  const b = S.bundle;
  const sep = b.separability || {};
  const abl = sep.sensor_ablation || {};
  const feats = sep.features || {};

  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stage 02 — pre-flight separability audit'),
    el('h1', {}, 'Can a cheaper sensor do this?'),
    el('p', { class: 'lede' },
      'The commercial case rests on hyperspectral doing something multispectral and RGB ' +
      'cannot. That is testable, so it is tested here rather than asserted — with each ' +
      'sensor tier given the best feature set it can physically compute.')));

  // Seasonal ablation table
  const seasons = [['autumn_flower', 'Sep–Nov, in bloom'], ['wet_summer', 'Jun–Aug, foliage only']];
  const tbl = el('table', {},
    el('thead', {}, el('tr', {},
      el('th', {}, 'Sensor'), el('th', {}, 'Example payload'),
      el('th', { class: 'num' }, 'Bands'), el('th', { class: 'num' }, 'Features'),
      ...seasons.map(([, lab]) => el('th', { class: 'num' }, lab)),
      el('th', { class: 'num' }, 'FP (foliage)'))),
    el('tbody', {}, ...['rgb', 'multispectral', 'hyperspectral'].map(t => {
      const a = abl.autumn_flower?.[t] || {};
      const f = abl.wet_summer?.[t] || {};
      return el('tr', {},
        el('td', {}, el('span', { class: 'tier-' + t, style: 'font-weight:600' }, a.label || t)),
        el('td', { class: 'hint' }, a.example || ''),
        el('td', { class: 'num' }, a.n_bands ?? '—'),
        el('td', { class: 'num' }, a.n_features ?? '—'),
        el('td', { class: 'num' }, pct(a.balanced_accuracy_mikania_vs_native)),
        el('td', { class: 'num' }, pct(f.balanced_accuracy_mikania_vs_native)),
        el('td', { class: 'num' }, pct(f.false_positive_rate)));
    })));

  wrap.appendChild(el('section', {},
    el('h2', {}, 'Sensor ablation — same classifier, same data, same validation'),
    el('div', { class: 'card pad-0' }, tbl),
    el('div', { class: 'callout good' },
      el('strong', {}, 'Read this carefully. '),
      'In the flowering window every tier performs well. That is not a weakness of the ' +
      'simulation — it reproduces the published result that RGB deep learning succeeds on ' +
      'blooming outbreak points, and validates the model. The entire commercial argument ' +
      'is the foliage-only column: ' +
      (abl._summary
        ? `hyperspectral leads RGB by ${num(abl._summary.foliage_only_hyperspectral_gain_over_rgb_pp, 1)} pp ` +
          `and 5-band multispectral by ${num(abl._summary.foliage_only_hyperspectral_gain_over_multispectral_pp, 1)} pp, ` +
          'while roughly halving the false-positive rate.'
        : ''))));

  // Per-feature separability
  const items = Object.entries(feats)
    .filter(([, v]) => v.worst_case != null)
    .sort((a, b2) => b2[1].worst_case - a[1].worst_case);
  const colOf = t => ({ rgb: 'var(--rgb)', multispectral: 'var(--multispec)', hyperspectral: 'var(--accent)' }[t] || '#666');
  const maxD = Math.max(1.2, ...items.map(([, v]) => v.worst_case));

  wrap.appendChild(el('section', {},
    el('h2', {}, "Single-feature separability (d′, foliage only)"),
    el('div', { class: 'card' },
      el('p', { class: 'hint' },
        "d′ is the class-mean separation in pooled standard deviations, against the " +
        "worst-case native climber. Below 1 the distributions overlap so heavily that no " +
        "threshold separates them. Note that no single feature is strong — the hyperspectral " +
        "advantage is multivariate, which is why the ablation above is the real test."),
      el('div', { class: 'spacer' }),
      ...items.slice(0, 14).map(([name, v]) => el('div', {
        style: 'display:grid;grid-template-columns:130px 1fr 46px;gap:10px;align-items:center;margin-bottom:5px'
      },
        el('span', { style: 'font-size:11.5px;color:var(--fg-1)' }, name.replace(/^(bb|nb)_/, '')),
        el('div', { style: 'height:9px;background:var(--bg-3);border-radius:5px;overflow:hidden' },
          el('div', { style: `height:100%;width:${Math.min(100, v.worst_case / maxD * 100)}%;background:${colOf(v.tier)};border-radius:5px` })),
        el('span', { class: 'mono', style: 'text-align:right;font-size:11px;color:var(--fg-2)' }, num(v.worst_case)))),
      el('div', { class: 'legend' },
        el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:var(--rgb)' }), 'RGB camera'),
        el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:var(--multispec)' }), '5-band multispectral'),
        el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:var(--accent)' }), 'hyperspectral only')))));

  return wrap;
};

/* ------------------------------- survey -------------------------------- */
VIEWS.survey = () => {
  const b = S.bundle;
  if (!S.site) S.site = b.sites[0]?.key;
  const site = b.sites.find(s => s.key === S.site) || b.sites[0];

  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stages 03 + 06 — acquisition and deliverables'),
    el('h1', {}, 'Survey viewer'),
    el('p', { class: 'lede' },
      'Simulated Tier-2 acquisitions at real Hong Kong catchment centroids. ' +
      'Click anywhere on the scene to read that pixel’s spectrum.')));

  // controls
  const siteSel = el('select', {
    onchange: e => { S.site = e.target.value; S.probe = null; render(); }
  }, ...b.sites.map(s => el('option', { value: s.key, selected: s.key === site.key || null },
    `${s.name} — ${s.role}`)));

  const layers = [['rgb', 'RGB'], ['truth', 'Ground truth'], ['classified', 'Predicted'],
                  ['severity', 'Severity'], ['change', 'Change']]
    .filter(([k]) => site.layers[k]);
  const seg = el('div', { class: 'seg' }, ...layers.map(([k, lab]) =>
    el('button', {
      'aria-pressed': String(S.layer === k),
      onclick: () => { S.layer = k; render(); }
    }, lab)));

  wrap.appendChild(el('div', { class: 'controls' }, siteSel, seg,
    el('span', { class: 'badge ' + (site.role === 'holdout' ? 'real' : 'muted') },
      site.role === 'holdout' ? 'HOLD-OUT — model never saw this site' : 'training site'),
    el('span', { class: 'badge sim' }, 'simulated scene')));

  // viewer
  const canvasWrap = el('div', { class: 'canvas-wrap' });
  const img = new Image();
  const cvs = el('canvas', { width: site.shape[1], height: site.shape[0] });
  canvasWrap.appendChild(cvs);
  canvasWrap.appendChild(el('div', { class: 'canvas-badge' },
    `${site.season_label} · ${site.shape[0]}×${site.shape[1]} px · ${b.wavelengths.length} bands`));

  const src = site.layers[S.layer] || site.layers.rgb;
  img.onload = () => {
    const ctx = cvs.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cvs.width, cvs.height);
    ctx.drawImage(img, 0, 0, cvs.width, cvs.height);
  };
  img.src = src;

  const spectrumBox = el('div', { class: 'card' }, el('h3', {}, 'Pixel spectrum'),
    el('p', { class: 'hint' }, 'Click the scene to probe a pixel.'));

  const marker = el('div', { class: 'crosshair hidden' });
  canvasWrap.appendChild(marker);
  canvasWrap.addEventListener('click', ev => {
    const r = canvasWrap.getBoundingClientRect();
    const fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
    marker.style.left = (fx * 100) + '%';
    marker.style.top = (fy * 100) + '%';
    marker.classList.remove('hidden');
    const row = Math.floor(fy * site.shape[0]), col = Math.floor(fx * site.shape[1]);
    spectrumBox.replaceChildren(...spectrumPanel(site, row, col));
  });

  // side panel: site facts
  const m = site.metrics || {};
  const facts = el('div', { class: 'card' },
    el('h3', {}, site.name),
    el('dl', { class: 'kv' },
      el('dt', {}, 'Role'), el('dd', {}, site.role),
      el('dt', {}, 'Season'), el('dd', {}, site.season_label),
      el('dt', {}, 'Centroid'), el('dd', {}, site.centroid.map(v => v.toFixed(4)).join(', ')),
      el('dt', {}, 'Overall acc.'), el('dd', {}, pct(m.overall_accuracy)),
      el('dt', {}, 'Mikania vs native'), el('dd', {}, pct(m.climber_accuracy)),
      el('dt', {}, 'Treatment units'), el('dd', {}, m.n_units ?? '—'),
      el('dt', {}, 'Infested'), el('dd', {}, num(m.infested_ha) + ' ha'),
      el('dt', {}, 'Masked (too dark)'), el('dd', {}, num(m.masked_pct, 1) + '%'),
      el('dt', {}, 'Sub-canopy hidden'), el('dd', {}, num(site.occluded_pct, 1) + '%'),
      el('dt', {}, 'GBIF records ≤3 km'), el('dd', {},
        `${site.occurrence?.n_mikania ?? 0} Mikania / ${site.occurrence?.n_native_climbers ?? 0} native`)),
    el('div', { class: 'callout' }, el('strong', {}, 'Honest limitation. '), site.limitation_note));

  if (S.layer === 'truth' || S.layer === 'classified') {
    facts.appendChild(el('div', { class: 'legend' },
      ...b.classes.filter(c => c.id > 0).map(c =>
        el('span', { class: 'item' },
          el('span', { class: 'sw', style: `background:${c.color}` }), c.label))));
  }

  const dl = el('div', { class: 'card' }, el('h3', {}, 'GIS deliverables'),
    el('p', { class: 'hint' }, 'Exactly what AFCD would receive — georeferenced, EPSG:4326.'),
    el('div', { style: 'display:flex;flex-direction:column;gap:5px;margin-top:8px' },
      ...[['_classified.tif', 'Class map (GeoTIFF)'],
          ['_severity.tif', 'Severity raster (GeoTIFF)'],
          ['_abundance.tif', 'Endmember abundances (GeoTIFF)'],
          ['_units.geojson', 'Treatment units (GeoJSON)'],
          ['_units.csv', 'Treatment units (CSV)']].map(([suf, lab]) =>
        el('a', { class: 'dl', href: `/deliverables/${site.key}${suf}`, download: '' }, lab))));

  wrap.appendChild(el('div', { class: 'viewer' },
    el('div', {}, canvasWrap, el('div', { class: 'spacer' }), spectrumBox),
    el('div', {}, facts, el('div', { class: 'spacer' }), dl)));

  return wrap;
};

function spectrumPanel(site, row, col) {
  const b = S.bundle, g = site.spectra_grid;
  const gr = Math.min(g.shape[0] - 1, Math.floor(row / g.step));
  const gc = Math.min(g.shape[1] - 1, Math.floor(col / g.step));
  const nb = b.wavelengths.length;
  const off = (gr * g.shape[1] + gc) * nb;
  const spec = g.data.slice(off, off + nb);
  if (!spec.length) return [el('p', { class: 'hint' }, 'No spectrum at that location.')];

  const c = svgChart(560, 210, { t: 14, r: 14, b: 34, l: 46 });
  const wl = b.wavelengths, w0 = wl[0], w1 = wl[wl.length - 1];
  const maxR = Math.max(0.1, ...spec) * 1.1;
  axes(c, {
    xTicks: [[0, '400'], [0.33, '600'], [0.66, '800'], [1, '1000']],
    yTicks: [[0, '0'], [0.5, num(maxR / 2)], [1, num(maxR)]],
    xLabel: 'wavelength (nm)', yLabel: 'reflectance'
  });
  // red-edge shading, the region the whole method depends on
  c.s.appendChild(svgEl('rect', {
    x: c.x((680 - w0) / (w1 - w0)), y: c.pad.t,
    width: c.x((760 - w0) / (w1 - w0)) - c.x((680 - w0) / (w1 - w0)),
    height: c.ih, fill: '#ff4d6d', 'fill-opacity': .07
  }));
  const d = spec.map((v, i) => `${i ? 'L' : 'M'}${c.x((wl[i] - w0) / (w1 - w0))},${c.y(v / maxR)}`).join(' ');
  c.s.appendChild(svgEl('path', { d, fill: 'none', stroke: '#34d3a0', 'stroke-width': 1.8 }));

  // overlay the Mikania endmember for comparison
  const em = b.library?.endmembers?.mikania;
  if (em) {
    const d2 = em.map((v, i) => `${i ? 'L' : 'M'}${c.x((wl[i] - w0) / (w1 - w0))},${c.y(v / maxR)}`).join(' ');
    c.s.appendChild(svgEl('path', { d: d2, fill: 'none', stroke: '#ff4d6d', 'stroke-width': 1.2, 'stroke-dasharray': '4 3', 'stroke-opacity': .85 }));
  }

  return [
    el('h3', {}, `Pixel spectrum — row ${row}, col ${col}`),
    c.s,
    el('div', { class: 'legend' },
      el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#34d3a0' }), 'this pixel'),
      el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#ff4d6d' }), 'Mikania endmember'),
      el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:rgba(255,77,109,.25)' }), 'red edge 680–760 nm')),
    el('p', { class: 'hint' }, `Probe grid is 1 sample per ${site.spectra_grid.step} px to keep the bundle small.`)
  ];
}

/* ------------------------------- spectra ------------------------------- */
VIEWS.spectra = () => {
  const b = S.bundle, lib = b.library || {};
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stage 02 — the spectral library'),
    el('h1', {}, 'Spectral lab'),
    el('p', { class: 'lede' },
      'The endmember library that drives classification and unmixing. The base is real: ' +
      `${lib.n_measured_spectra || 0} measured tropical broadleaf leaf spectra from EcoSIS, ` +
      'resampled through the sensor’s spectral response. Species differences are modelled ' +
      'from the mechanism table in proposal §3.2 — and that boundary is marked explicitly below.')));

  const wl = b.wavelengths, w0 = wl[0], w1 = wl[wl.length - 1];

  // endmember plot
  const c = svgChart(760, 300, { t: 16, r: 16, b: 36, l: 50 });
  axes(c, {
    xTicks: [[0, '400'], [0.25, '550'], [0.5, '700'], [0.75, '850'], [1, '1000']],
    yTicks: [[0, '0'], [0.25, '0.15'], [0.5, '0.30'], [0.75, '0.45'], [1, '0.60']],
    xLabel: 'wavelength (nm)', yLabel: 'reflectance'
  });
  c.s.appendChild(svgEl('rect', {
    x: c.x((680 - w0) / (w1 - w0)), y: c.pad.t,
    width: c.x((760 - w0) / (w1 - w0)) - c.x((680 - w0) / (w1 - w0)),
    height: c.ih, fill: '#ff4d6d', 'fill-opacity': .06
  }));
  const MAXR = 0.60;
  const colorFor = k => {
    const cl = b.classes.find(x => x.key === k);
    return cl ? cl.color : ({ npv: '#b08968', soil_rock: '#a68a64', shadow: '#3b4252' }[k] || '#888');
  };
  Object.entries(lib.endmembers || {}).forEach(([k, v]) => {
    const d = v.map((y, i) => `${i ? 'L' : 'M'}${c.x((wl[i] - w0) / (w1 - w0))},${c.y(Math.min(y, MAXR) / MAXR)}`).join(' ');
    c.s.appendChild(svgEl('path', {
      d, fill: 'none', stroke: colorFor(k),
      'stroke-width': k === 'mikania' ? 2.6 : 1.5,
      'stroke-dasharray': ['soil_rock', 'shadow', 'npv'].includes(k) ? '5 3' : null
    }));
  });

  wrap.appendChild(el('section', {},
    el('h2', {}, 'Endmember library'),
    el('div', { class: 'card' }, c.s,
      el('div', { class: 'legend' }, ...Object.keys(lib.endmembers || {}).map(k =>
        el('span', { class: 'item' },
          el('span', { class: 'sw', style: `background:${colorFor(k)}` }), k.replace(/_/g, ' ')))))));

  // provenance of each endmember — the measured/modelled boundary
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Measured or modelled?'),
    el('div', { class: 'card pad-0' },
      el('table', {},
        el('thead', {}, el('tr', {}, el('th', {}, 'Endmember'), el('th', {}, 'Provenance'), el('th', {}, 'Status'))),
        el('tbody', {}, ...Object.entries(lib.provenance || {}).map(([k, v]) =>
          el('tr', {},
            el('td', {}, el('span', { style: `color:${colorFor(k)};font-weight:600` }, k.replace(/_/g, ' '))),
            el('td', { class: 'hint' }, v),
            el('td', {}, el('span', { class: 'badge ' + (v.startsWith('measured (') ? 'real' : 'sim') },
              v.startsWith('measured (') ? 'measured' : v.startsWith('measured base') ? 'hybrid' : 'modelled'))))))),
    el('div', { class: 'callout' },
      el('strong', {}, 'This table is the point. '),
      'Phase 0’s field spectroradiometer campaign replaces the modelled species block with ' +
      'real Hong Kong measurements. Drop CSVs into data/raw/field_spectra/ and the pipeline ' +
      'uses them automatically — the code path already exists.')));

  // real measured bank
  if (lib.measured_sample?.length) {
    const c2 = svgChart(760, 220, { t: 14, r: 16, b: 34, l: 50 });
    axes(c2, {
      xTicks: [[0, '400'], [0.5, '700'], [1, '1000']],
      yTicks: [[0, '0'], [0.5, '0.30'], [1, '0.60']],
      xLabel: 'wavelength (nm)', yLabel: 'reflectance'
    });
    lib.measured_sample.forEach(row => {
      const d = row.map((y, i) => `${i ? 'L' : 'M'}${c2.x((wl[i] - w0) / (w1 - w0))},${c2.y(Math.min(y, MAXR) / MAXR)}`).join(' ');
      c2.s.appendChild(svgEl('path', { d, fill: 'none', stroke: '#34d3a0', 'stroke-width': .7, 'stroke-opacity': .35 }));
    });
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Real measured leaf spectra (EcoSIS)'),
      el('div', { class: 'card' },
        el('p', { class: 'hint' }, (lib.measured_sources || []).join(' · ')),
        c2.s,
        el('p', { class: 'hint' },
          'These are actual field-spectroradiometer measurements of tropical broadleaf foliage. ' +
          'Their principal modes of variation supply the within-class scatter of the simulated ' +
          'classes, so the synthetic covariance resembles real vegetation rather than white noise.'))));
  }

  return wrap;
};

/* ------------------------------ validation ----------------------------- */
VIEWS.validation = () => {
  const b = S.bundle, v = b.validation || {}, sweep = b.contrast_sweep || {};
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stages 04 + 05 + 08 — validation'),
    el('h1', {}, 'Validation, done the only way that counts'),
    el('p', { class: 'lede' },
      'All reported accuracy is from spatially disjoint hold-out sites with confidence ' +
      'intervals bootstrapped over sites, not pixels. Random pixel splitting is computed ' +
      'alongside purely to quantify how much it would have inflated the result.')));

  // model comparison
  const models = v.models || {};
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Leave-one-site-out model comparison'),
    el('div', { class: 'card pad-0' },
      el('table', {},
        el('thead', {}, el('tr', {},
          el('th', {}, 'Model'), el('th', { class: 'num' }, 'Overall acc.'),
          el('th', { class: 'num' }, 'Kappa'),
          el('th', { class: 'num' }, 'Mikania vs native'),
          el('th', { class: 'num' }, 'False positives'), el('th', {}, ''))),
        el('tbody', {}, ...Object.entries(models).map(([name, r]) => {
          const oa = r.overall_accuracy_ci || [], kp = r.kappa_ci || [];
          const cb = r.climber_balanced_accuracy_ci || [], fp = r.climber_false_positive_ci || [];
          return el('tr', {},
            el('td', {}, el('strong', {}, name.toUpperCase())),
            el('td', { class: 'num' }, `${pct(oa[0])}`, el('div', { class: 'hint' }, `${pct(oa[1], 0)}–${pct(oa[2], 0)}`)),
            el('td', { class: 'num' }, num(kp[0], 3)),
            el('td', { class: 'num' }, `${pct(cb[0])}`, el('div', { class: 'hint' }, `${pct(cb[1], 0)}–${pct(cb[2], 0)}`)),
            el('td', { class: 'num' }, pct(fp[0])),
            el('td', {}, name === v.best_model ? el('span', { class: 'badge pass' }, 'selected') : null));
        })))),
    el('div', { class: 'callout' },
      el('strong', {}, 'The confidence intervals are wide, and that is the finding. '),
      'With only a handful of sites the interval on the Mikania-versus-native figure spans ' +
      'tens of percentage points. A point estimate from three catchments is not a result — ' +
      'which is precisely the argument for the multi-site Phase 1 in proposal §7.3.')));

  // contrast sweep
  const rows = sweep.sweep || [];
  if (rows.length) {
    const c = svgChart(760, 300, { t: 18, r: 18, b: 40, l: 52 });
    const cs = rows.map(r => r.contrast);
    const xmax = Math.max(...cs);
    const norm = a => Math.max(0, Math.min(1, (a * 100 - 40) / 60));
    axes(c, {
      xTicks: cs.map(x => [x / xmax, String(x)]),
      yTicks: [[0, '40'], [0.25, '55'], [0.5, '70'], [0.75, '85'], [1, '100']],
      xLabel: 'species contrast scale (1.0 = nominal)',
      yLabel: 'Mikania vs native (%)'
    });
    // CI band
    const up = rows.map(r => `${c.x(r.contrast / xmax)},${c.y(norm(r.climber_accuracy[2]))}`);
    const dn = rows.slice().reverse().map(r => `${c.x(r.contrast / xmax)},${c.y(norm(r.climber_accuracy[1]))}`);
    c.s.appendChild(svgEl('polygon', { points: [...up, ...dn].join(' '), fill: '#34d3a0', 'fill-opacity': .14 }));
    // kill criterion
    const kill = b.kill_criteria.mikania_vs_native_min_accuracy;
    c.s.appendChild(svgEl('line', {
      x1: c.pad.l, x2: c.pad.l + c.iw, y1: c.y(norm(kill)), y2: c.y(norm(kill)),
      stroke: '#ff5c5c', 'stroke-width': 1.2, 'stroke-dasharray': '5 4'
    }));
    const kt = svgEl('text', { x: c.pad.l + 6, y: c.y(norm(kill)) - 5, class: 'lbl', fill: '#ff5c5c' });
    kt.textContent = `§7.3 kill criterion ${pct(kill, 0)}`; c.s.appendChild(kt);
    // chance
    c.s.appendChild(svgEl('line', {
      x1: c.pad.l, x2: c.pad.l + c.iw, y1: c.y(norm(0.5)), y2: c.y(norm(0.5)),
      stroke: '#6b7789', 'stroke-width': 1, 'stroke-dasharray': '2 4'
    }));
    // lines
    const mk = (accessor, color, dash) => {
      const d = rows.map((r, i) => `${i ? 'L' : 'M'}${c.x(r.contrast / xmax)},${c.y(norm(accessor(r)))}`).join(' ');
      c.s.appendChild(svgEl('path', { d, fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-dasharray': dash }));
      rows.forEach(r => c.s.appendChild(svgEl('circle', {
        cx: c.x(r.contrast / xmax), cy: c.y(norm(accessor(r))), r: 3, fill: color
      })));
    };
    mk(r => r.climber_accuracy[0], '#34d3a0', null);
    mk(r => r.random_split_climber, '#c0392b', '5 4');

    wrap.appendChild(el('section', {},
      el('h2', {}, 'How separable must the species really be?'),
      el('div', { class: 'card' },
        el('p', { class: 'hint' },
          'Species separability in real Hong Kong canopy is unmeasured, so it is swept rather ' +
          'than assumed. Contrast 0 makes the climbers spectrally identical — accuracy must ' +
          'collapse to chance there, and it does, which is the control proving nothing else is leaking.'),
        c.s,
        el('div', { class: 'legend' },
          el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#34d3a0' }), 'leave-one-site-out'),
          el('span', { class: 'item' }, el('span', { class: 'sw', style: 'background:#c0392b' }), 'random split (leaky)')),
        el('div', { class: 'grid g3', style: 'margin-top:14px' },
          kpi('Control at contrast 0', pct(sweep.control_contrast_zero?.contrast_zero_climber_accuracy),
            sweep.control_contrast_zero?.passed ? 'chance, as required — PASS' : 'NOT chance — investigate',
            sweep.control_contrast_zero?.passed ? 'good' : 'bad'),
          kpi('Contrast needed', num(sweep.contrast_required_mean), 'to reach the kill criterion (mean)', 'warn'),
          kpi('On the lower CI', sweep.contrast_required_lower_ci == null ? 'not reached' : num(sweep.contrast_required_lower_ci),
            'conservative bound across the swept range', 'warn')))));
  }

  // Botswana benchmark
  const bm = b.benchmark || {};
  if (bm.dataset) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Real-data control — EO-1 Hyperion, Botswana'),
      el('div', { class: 'grid g2' },
        el('div', { class: 'card' },
          el('div', { class: 'grid g2' },
            kpi('Spatially blocked', pct((bm.blocked_overall_accuracy_trainable_classes || [])[0]),
              'trainable classes only — the fair number', 'good'),
            kpi('Random pixel split', pct(bm.random_split_overall_accuracy),
              'the number most papers quote', 'bad')),
          el('div', { class: 'callout danger', style: 'margin-top:12px' },
            el('strong', {}, `+${num(bm.leakage_inflation_pp_trainable, 1)} pp inflation. `),
            'Measured on real satellite hyperspectral imagery this project did not generate. ' +
            'The leakage effect is not an artefact of our simulation.')),
        el('div', { class: 'card' },
          el('h3', {}, 'What this proves — and what it does not'),
          el('p', { class: 'hint' }, el('strong', { style: 'color:var(--accent)' }, 'Proves: '), bm.what_this_proves),
          el('p', { class: 'hint' }, el('strong', { style: 'color:var(--danger)' }, 'Does not prove: '), bm.what_this_does_not_prove),
          el('img', { src: '/figures/fig08_benchmark_botswana.png', style: 'width:100%;margin-top:10px;border-radius:8px' })))));
  }

  return wrap;
};

/* ------------------------------- workplan ------------------------------ */
VIEWS.workplan = () => {
  const b = S.bundle, units = b.work_plan || [];
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stage 06 — deliverable 2'),
    el('h1', {}, 'Severity-ranked work plan'),
    el('p', { class: 'lede' },
      'A map is not a product; a ranked polygon table with an action column is. Units are ' +
      'ranked by severity × area, because a large moderate patch is a bigger ecological ' +
      'problem than a tiny severe one and the crew’s day is finite.')));

  const bands = {};
  units.forEach(u => { bands[u.band] = bands[u.band] || { n: 0, ha: 0 }; bands[u.band].n++; bands[u.band].ha += u.area_ha; });

  wrap.appendChild(el('div', { class: 'grid g4' },
    ...b.severity_bands.map(bd => {
      const v = bands[bd.label] || { n: 0, ha: 0 };
      return el('div', { class: 'card kpi' },
        el('div', { class: 'label' }, el('span', { class: 'badge band-' + bd.label }, bd.label)),
        el('div', { class: 'value' }, v.n, el('span', { class: 'unit' }, ' units')),
        el('div', { class: 'note' }, `${num(v.ha)} ha · ${bd.action}`));
    })));

  wrap.appendChild(el('div', { class: 'spacer' }));

  const wsum = Object.entries(b.severity_weights || {});
  wrap.appendChild(el('section', {},
    el('h2', {}, 'How severity is scored'),
    el('div', { class: 'card' },
      el('p', { class: 'hint' },
        'The five factors come from proposal §3.1, and their weights live in config so they ' +
        'can be renegotiated with AFCD without touching code. Every unit carries its own ' +
        'component breakdown, because a prioritisation contract must be able to answer ' +
        '“why does this patch outrank that one?”'),
      el('div', { class: 'spacer' }),
      ...wsum.map(([k, w]) => el('div', {
        style: 'display:grid;grid-template-columns:190px 1fr 46px;gap:10px;align-items:center;margin-bottom:5px'
      },
        el('span', { style: 'font-size:12px;color:var(--fg-1)' }, k.replace(/_/g, ' ')),
        el('div', { style: 'height:9px;background:var(--bg-3);border-radius:5px;overflow:hidden' },
          el('div', { style: `height:100%;width:${w * 100 / 0.4 * 0.85}%;background:var(--accent);border-radius:5px` })),
        el('span', { class: 'mono', style: 'text-align:right;font-size:11px;color:var(--fg-2)' }, w.toFixed(2)))))));

  wrap.appendChild(el('section', {},
    el('h2', {}, `All treatment units (${units.length})`),
    el('div', { class: 'card pad-0' },
      el('div', { class: 'table-wrap' },
        el('table', {},
          el('thead', {}, el('tr', {},
            el('th', { class: 'num' }, '#'), el('th', {}, 'Unit'), el('th', {}, 'Site'),
            el('th', { class: 'num' }, 'Area (ha)'), el('th', { class: 'num' }, 'Severity'),
            el('th', { class: 'num' }, 'Coverage'), el('th', {}, 'Band'), el('th', {}, 'Action'),
            el('th', { class: 'num' }, 'Survey cost'))),
          el('tbody', {}, ...units.map(u => el('tr', {},
            el('td', { class: 'num' }, u.territory_rank ?? u.rank),
            el('td', { class: 'mono' }, u.unit_id),
            el('td', {}, u.site_name, u.role === 'holdout' ? el('span', { class: 'badge muted', style: 'margin-left:6px' }, 'hold-out') : null),
            el('td', { class: 'num' }, num(u.area_ha, 3)),
            el('td', { class: 'num' }, num(u.severity, 3)),
            el('td', { class: 'num' }, pct(u.mean_coverage_fraction, 0)),
            el('td', {}, el('span', { class: 'badge band-' + u.band }, u.band)),
            el('td', { class: 'hint' }, u.action),
            el('td', { class: 'num' }, u.survey_cost_hkd ? `${hkd(u.survey_cost_hkd[0])}–${hkd(u.survey_cost_hkd[1])}` : '—')))))))));

  return wrap;
};

/* ------------------------------- efficacy ------------------------------ */
VIEWS.efficacy = () => {
  const b = S.bundle, ef = b.efficacy || {};
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stage 07 — deliverable 3'),
    el('h1', {}, 'Post-treatment efficacy loop'),
    el('p', { class: 'lede' },
      'Government has acknowledged that Mikania re-emerges after weeding, but nobody measures ' +
      'where, how fast, or which sites are failing. This closes that loop — and it is the ' +
      'recurring-revenue line.')));

  const methods = Object.entries(ef.by_method || {}).filter(([k]) => k !== 'no_treatment');
  wrap.appendChild(el('section', {},
    el('h2', {}, `Re-emergence by treatment method (${ef.reflight_interval_months || 6}-month re-flight)`),
    el('div', { class: 'card pad-0' },
      el('table', {},
        el('thead', {}, el('tr', {},
          el('th', {}, 'Method'), el('th', { class: 'num' }, 'Units'),
          el('th', { class: 'num' }, 'Re-emerged'), el('th', { class: 'num' }, 'Measured rate'),
          el('th', { class: 'num' }, 'True rate'), el('th', { class: 'num' }, 'Mean reduction'),
          el('th', { class: 'num' }, 'Cost/ha'))),
        el('tbody', {}, ...methods.map(([k, v]) => el('tr', {},
          el('td', {}, el('strong', {}, k.replace(/_/g, ' '))),
          el('td', { class: 'num' }, v.n_units),
          el('td', { class: 'num' }, v.n_reemerged),
          el('td', { class: 'num' }, pct(v.observed_reemergence_rate, 0)),
          el('td', { class: 'num hint' }, pct(v.configured_reemergence_rate, 0)),
          el('td', { class: 'num' }, v.mean_reduction_pct != null ? v.mean_reduction_pct + '%' : '—'),
          el('td', { class: 'num' }, hkd(v.cost_per_ha_hkd))))))),
    el('div', { class: 'callout' },
      el('strong', {}, 'Measured rates sit below the true rates. '),
      'That gap is the detection floor, not an error: small re-emergence patches fall below ' +
      'what the sensor and classifier can honestly resolve. Reporting a rate below the ' +
      'detection floor would be the fastest way to lose a client who holds the real records.')));

  if (ef.confound_note) {
    wrap.appendChild(el('div', { class: 'callout danger' },
      el('strong', {}, 'Confound, stated rather than buried. '), ef.confound_note));
  }

  const sites = ef.per_site || [];
  if (sites.length) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Per-site outcome'),
      el('div', { class: 'card pad-0' },
        el('table', {},
          el('thead', {}, el('tr', {},
            el('th', {}, 'Site'), el('th', { class: 'num' }, 'Units'),
            el('th', { class: 'num' }, 'Significant'), el('th', { class: 'num' }, 'Re-emerged'),
            el('th', { class: 'num' }, 'Cleared (ha)'), el('th', { class: 'num' }, 'New/regrowth (ha)'),
            el('th', { class: 'num' }, 'Treatment cost'))),
          el('tbody', {}, ...sites.map(s => el('tr', {},
            el('td', {}, s.name),
            el('td', { class: 'num' }, s.n_units),
            el('td', { class: 'num' }, s.n_significant),
            el('td', { class: 'num' }, s.n_reemerged),
            el('td', { class: 'num', style: 'color:var(--accent)' }, num(s.cleared_ha, 3)),
            el('td', { class: 'num', style: 'color:var(--mikania)' }, num(s.emerged_ha, 3)),
            el('td', { class: 'num' }, hkd(s.treatment_cost_hkd)))))))));
  }

  wrap.appendChild(el('img', { src: '/figures/fig07_efficacy.png', style: 'width:100%;border-radius:10px;border:1px solid var(--line)' }));
  return wrap;
};

/* ------------------------------ economics ------------------------------ */
VIEWS.economics = () => {
  const b = S.bundle, ec = b.economics || {};
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Proposal §5.3 and §7.2'),
    el('h1', {}, 'Coverage economics'),
    el('p', { class: 'lede' },
      'Coverage rate is the binding constraint on the whole business. It is computed here ' +
      'from platform geometry rather than quoted, so that when the two [VERIFY] items — real ' +
      'swath and achievable line rate — are measured, one edit propagates through the ' +
      'field-day count, the contract value and the funnel together.')));

  const out = el('div', { class: 'grid g4' });
  const funnelBox = el('div', { class: 'card' });

  const sliders = [
    ['swath_m', 'Swath (m)', 10, 80, 1, b.platform.swath_m],
    ['ground_speed_ms', 'Ground speed (m/s)', 2, 14, 0.5, b.platform.ground_speed_ms],
    ['sidelap_frac', 'Sidelap', 0, 0.6, 0.05, b.platform.sidelap_frac],
    ['operational_efficiency', 'Operational efficiency', 0.15, 1, 0.01, b.platform.operational_efficiency],
    ['hours_per_field_day', 'Hours per field day', 2, 10, 0.5, b.platform.hours_per_field_day],
  ];
  const state = Object.fromEntries(sliders.map(([k, , , , , v]) => [k, v]));

  const liveStatus = el('p', { class: 'hint coverage-status', role: 'status' });
  let latestCoverageRequest = 0;
  async function refresh() {
    const request = ++latestCoverageRequest;
    const qs = new URLSearchParams({ ...state, area_ha: 3000 }).toString();
    let d;
    try {
      const response = await fetch('/api/coverage?' + qs);
      if (!response.ok) throw new Error('Live economics unavailable');
      d = await response.json();
      if (request !== latestCoverageRequest) return;
      liveStatus.textContent = 'Live model · updated from the platform geometry below.';
    } catch {
      if (request !== latestCoverageRequest) return;
      d = { coverage: ec.coverage, programme: {}, funnel: ec.funnel };
      liveStatus.textContent = 'Showing bundled baseline economics. Live updates require the Python dependencies listed in the README; programme days are unavailable in this mode.';
      ctrl.querySelectorAll('input[type=range]').forEach(input => { input.disabled = true; });
      ctrl.querySelectorAll('output').forEach((output, i) => { output.textContent = String(sliders[i][5]); });
      ctrl.querySelectorAll('input[type=range]').forEach((input, i) => { input.value = sliders[i][5]; });
    }
    const cov = d.coverage || {}, pr = d.programme || {};
    out.replaceChildren(
      kpi('Raw rate', num(cov.raw_ha_per_hr, 1), 'ha/hr — swath × speed'),
      kpi('Effective rate', num(cov.effective_ha_per_hr, 1), 'ha/hr — after sidelap and overhead', 'good'),
      kpi('Per field day', num(cov.ha_per_field_day, 0), 'hectares', 'good'),
      kpi('3,000 ha programme', num(pr.field_days_with_weather_margin, 0),
        'field days incl. weather margin', 'warn'));

    const f = d.funnel || {};
    funnelBox.replaceChildren(
      el('h3', {}, 'Why the three-tier funnel is mandatory, not optional'),
      el('p', { class: 'hint' },
        `Flying all ${Math.round(f.total_afcd_area_ha || 0).toLocaleString()} ha of AFCD estate at ` +
        `this rate would take ${num(f.naive_full_coverage_field_days, 0)} field days — ` +
        `about ${num(f.naive_full_coverage_years_one_crew, 1)} years with one crew. ` +
        'Tier-1 screening reduces the hyperspectral footprint to what is achievable:'),
      el('table', {},
        el('thead', {}, el('tr', {},
          el('th', {}, 'Tier-1 flags'), el('th', { class: 'num' }, 'Tier-2 area'),
          el('th', { class: 'num' }, 'Field days'), el('th', { class: 'num' }, 'Contract value'),
          el('th', {}, 'One crew?'))),
        el('tbody', {}, ...(f.tiers || []).map(t => el('tr', {},
          el('td', {}, pct(t.tier1_flag_fraction, 0)),
          el('td', { class: 'num' }, Math.round(t.tier2_area_ha).toLocaleString() + ' ha'),
          el('td', { class: 'num' }, num(t.field_days_with_weather_margin, 0)),
          el('td', { class: 'num' }, `${hkd(t.contract_value_hkd[0])}–${hkd(t.contract_value_hkd[1])}`),
          el('td', {}, el('span', { class: 'badge ' + (t.feasible_with_one_crew ? 'pass' : 'fail') },
            t.feasible_with_one_crew ? 'feasible' : 'not feasible')))))));
  }

  const ctrl = el('div', { class: 'card' }, el('h3', {}, 'Platform geometry'),
    ...sliders.map(([k, lab, min, max, step, val]) => {
      const outEl = el('output', {}, String(val));
      return el('div', { class: 'slider-row' },
        el('label', {}, lab),
        el('input', {
          type: 'range', min, max, step, value: val, 'aria-label': lab,
          oninput: e => { state[k] = parseFloat(e.target.value); outEl.textContent = e.target.value; refresh(); }
        }),
        outEl);
    }),
    el('p', { class: 'hint', style: 'margin-top:10px' },
      'Recomputed server-side by the same mikania.economics functions the pipeline uses — ' +
      'the browser never reimplements a metric.'));

  wrap.appendChild(out);
  wrap.appendChild(liveStatus);
  wrap.appendChild(el('div', { class: 'spacer' }));
  wrap.appendChild(el('div', { class: 'grid g2' }, ctrl, funnelBox));

  // Populate immediately — refresh() is otherwise only bound to slider input,
  // which left the KPI row and the funnel table blank until the user dragged
  // something. Placeholders keep the layout from jumping while the fetch lands.
  out.replaceChildren(...Array.from({ length: 4 }, () => kpi('—', '…', '')));
  refresh();

  // the §5.3 arithmetic problem
  const chk = ec.consistency_check || {};
  if (chk.discrepancies?.length) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Discrepancy found in the proposal’s own §5.3 table'),
      el('div', { class: 'card' },
        el('div', { class: 'callout danger' },
          el('strong', {}, 'The published table does not reconcile with itself.'),
          el('ul', { style: 'margin:8px 0 0 16px;padding:0' },
            ...chk.discrepancies.map(d => el('li', { style: 'margin-bottom:5px' }, d.detail)))),
        el('p', { class: 'hint' },
          `To match the stated 80–120 ha per field day, operational efficiency would have to be ` +
          `${num((chk.implied_operational_efficiency_to_match_field_day || [])[0])}–` +
          `${num((chk.implied_operational_efficiency_to_match_field_day || [])[1])}, ` +
          `not the ${num(b.platform.operational_efficiency)} assumed here.`),
        el('p', { class: 'hint' }, chk.recommendation))));
  }

  // Phase 0 budget
  const p0 = ec.phase0 || {};
  if (p0.line_items) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Phase 0 budget reconstruction'),
      el('div', { class: 'grid g2' },
        el('div', { class: 'card pad-0' },
          el('table', {},
            el('thead', {}, el('tr', {}, el('th', {}, 'Line item'), el('th', { class: 'num' }, 'HK$'))),
            el('tbody', {},
              ...Object.entries(p0.line_items).map(([k, v]) =>
                el('tr', {}, el('td', { class: 'hint' }, k), el('td', { class: 'num' }, hkd(v)))),
              el('tr', {}, el('td', {}, el('strong', {}, 'Bottom-up total')),
                el('td', { class: 'num' }, el('strong', {}, hkd(p0.bottom_up_total_hkd)))),
              el('tr', {}, el('td', {}, el('strong', {}, 'Proposal ask')),
                el('td', { class: 'num' }, el('strong', {}, hkd(p0.budget_hkd))))))),
        el('div', { class: 'card' },
          kpi('Headroom', hkd(p0.headroom_hkd),
            p0.fits ? 'the ask reconstructs from its own workplan' : 'the ask does not cover the workplan',
            p0.fits ? 'good' : 'bad'),
          el('p', { class: 'hint', style: 'margin-top:12px' }, p0.note)))));
  }

  return wrap;
};

/* ----------------------------- provenance ------------------------------ */
VIEWS.provenance = () => {
  const b = S.bundle;
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Stage 01 — data lineage'),
    el('h1', {}, 'Where every number comes from'),
    el('p', { class: 'lede' },
      'Real open data and simulated data are kept strictly separable, in the code and here. ' +
      'Conflating them is how a feasibility study becomes a misrepresentation.')));

  const occ = b.occurrences || {};
  wrap.appendChild(el('div', { class: 'grid g3' },
    kpi('Real HK occurrence records', (occ.n || 0).toLocaleString(), occ.source || '', 'good'),
    kpi('Real leaf spectra', (b.library?.n_measured_spectra || 0).toLocaleString(),
      'EcoSIS field spectroradiometer, 350–2500 nm', 'good'),
    kpi('Real benchmark cube', b.benchmark?.dataset || '—',
      'EO-1 Hyperion, 145 bands, 14 vegetation classes', 'good')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  if (occ.by_taxon) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'GBIF occurrence records by taxon (Hong Kong)'),
      el('div', { class: 'card pad-0' },
        el('table', {},
          el('thead', {}, el('tr', {}, el('th', {}, 'Queried name'), el('th', { class: 'num' }, 'Records'))),
          el('tbody', {}, ...Object.entries(occ.by_taxon).map(([k, v]) =>
            el('tr', {}, el('td', { style: 'font-style:italic' }, k), el('td', { class: 'num' }, v)))))),
      el('div', { class: 'callout info' },
        el('strong', {}, 'A taxonomy trap worth knowing about. '),
        'Querying GBIF for “Bauhinia glauca” returns zero Hong Kong records, because the ' +
        'accepted name is Phanera glauca. A pipeline that silently accepted the empty result ' +
        'would have trained a Mikania classifier with nothing to confuse it with — and reported ' +
        'a beautiful, meaningless accuracy.')));
  }

  const prov = b.provenance || [];
  if (prov.length) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Download provenance'),
      el('div', { class: 'card pad-0' },
        el('table', {},
          el('thead', {}, el('tr', {},
            el('th', {}, 'Kind'), el('th', {}, 'Name'), el('th', {}, 'Source'),
            el('th', {}, 'Retrieved'), el('th', {}, 'Note'))),
          el('tbody', {}, ...prov.map(p => el('tr', {},
            el('td', {}, el('span', { class: 'badge real' }, p.kind)),
            el('td', { class: 'hint' }, (p.name || '').slice(0, 52)),
            el('td', { class: 'hint mono', style: 'font-size:10.5px' }, (p.source || '').slice(0, 46)),
            el('td', { class: 'hint mono', style: 'font-size:10.5px' }, (p.retrieved_utc || '').slice(0, 10)),
            el('td', { class: 'hint', style: 'font-size:11px' }, (p.note || '').slice(0, 130)))))))));
  }

  wrap.appendChild(el('section', {},
    el('h2', {}, 'What is simulated'),
    el('div', { class: 'card' },
      el('p', {},
        el('span', { class: 'badge sim' }, 'simulated'), ' ',
        'All five catchment scenes, their class truth, infestation geometry, treatment ' +
        'outcomes and re-flights. Species spectral differences are modelled from the ' +
        'mechanism table in proposal §3.2, on top of a real measured leaf base.'),
      el('p', {},
        el('span', { class: 'badge real' }, 'real'), ' ',
        'Leaf reflectance base and its variance modes (EcoSIS), Hong Kong occurrence records ' +
        'and per-site ecological context (GBIF), the benchmark hyperspectral cube and its ' +
        'validation result (EO-1 Hyperion), catchment coordinates, and every regulatory and ' +
        'pricing constant carried from the proposal.'),
      el('div', { class: 'callout' },
        el('strong', {}, 'The consequence. '),
        'Accuracy figures here validate the pipeline and the validation methodology — not ' +
        'Hong Kong field separability, which is unmeasured. Phase 0’s ground spectral library ' +
        'is what converts these into real numbers, and the code path for dropping in field ' +
        'spectra already exists.'))));

  return wrap;
};

/* ======================= v2.0 — molecular layer views =======================
   Same rule as everything above: these RENDER, they do not COMPUTE. Every
   number arrives from the Python pipeline via data/bundle.json. Where a view
   needs a report that was not produced (someone ran --no-molecular), it says so
   rather than throwing.
   ========================================================================== */

function missing(what, stage) {
  return el('div', { class: 'callout' },
    el('strong', {}, 'Not built. '),
    `${what} is missing from the bundle. Run `,
    el('span', { class: 'mono' }, stage),
    ' and then ', el('span', { class: 'mono' }, 'scripts/15_export_platform.py'), '.');
}

const TIER_LABEL = {
  published_genomic: 'published genomic',
  published_physiological: 'published physiological',
  published_transcriptomic: 'published transcriptomic',
  inferred_trait: 'inferred trait',
  inferred_optical: 'inferred optical',
};

/* ---------------------------- 09 genomic desk study ---------------------- */
VIEWS.genomics = () => {
  const b = S.bundle;
  const gp = b.genomic_priors, gv = b.genomic_validation;
  const wrap = el('div');

  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Proposal §3.3 · Next Action 0 · stages 00 and 10'),
    el('h1', {}, 'Why Mikania should be spectrally separable at all'),
    el('p', { class: 'lede' },
      'v1.0 asserted separability from one published accuracy figure. This is the ' +
      'mechanistic argument underneath it: published genomic findings, traced through ' +
      'inferred traits to signed, falsifiable predictions about specific bands — then ' +
      'tested against the ground spectral library.')));

  if (!gp || !gp.ranked_operational) return wrap.appendChild(
    missing('genomic_priors.json', 'scripts/00_genomic_desk_study.py')), wrap;

  const ranked = gp.ranked_operational;
  const tested = gv && gv.predictions_foliage ? gv.predictions_foliage : null;
  const counts = (gv && gv.verdict_counts_foliage) || {};

  wrap.appendChild(el('div', { class: 'grid g4' },
    kpi('Published findings', String(gp.n_findings), 'each with a citation'),
    kpi('Spectral predictions', String(gp.n_predictions), 'signed and falsifiable'),
    kpi('Supported in foliage', String(counts.SUPPORTED ?? '—'),
      tested ? `of ${tested.length} tested, site-blocked` : 'run stage 10',
      counts.SUPPORTED > 0 ? 'good' : ''),
    kpi('Refuted / struck', String(counts.REFUTED ?? '—'),
      'measured opposite to prediction',
      (counts.REFUTED || 0) > 0 ? 'bad' : 'good')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  // ---- the headline finding: best-supported is not most-useful ----
  const worst = ranked.reduce((a, c) => c.operational_score < a.operational_score ? c : a, ranked[0]);
  const shift = (gp.rank_disagreement || [])[0];
  wrap.appendChild(el('section', {},
    el('h2', {}, 'The finding: best-supported is not most-useful'),
    el('p', { class: 'hint' },
      'Two rankings come out of the same literature. Biological score measures how well ' +
      'the published work supports a prediction. Operational score discounts it by how ' +
      'badly the field confounders in config §3 corrupt that particular feature — leaf ' +
      'area index, leaf angle, slope and illumination.'),
    shift ? el('div', { class: 'callout' },
      el('strong', {}, shift.id.replace(/_/g, ' ') + '. '),
      `Biological rank #${shift.biological_rank}, operational rank #${shift.operational_rank}. ` +
      'It rests on directly measured photosynthetic physiology and is close to useless ' +
      'from a drone, because nuisance variation moves it far more than species does. ' +
      'A desk study reporting only the literature ranking would have sent the field ' +
      'campaign to measure the wrong thing.') : null));

  // ---- ranked prediction table with verdicts ----
  const testedById = {};
  (tested || []).forEach(t => { testedById[t.id] = t; });
  const bloomById = {};
  ((gv && gv.predictions_bloom) || []).forEach(t => { bloomById[t.id] = t; });

  const rows = ranked.map(p => {
    const t = testedById[p.id];
    const bl = bloomById[p.id];
    const d = t && t.test ? t.test.cohens_d_site_blocked : null;
    const db = bl && bl.test ? bl.test.cohens_d_site_blocked : null;
    return el('tr', {},
      el('td', {}, el('span', { class: 'mono' }, p.id.split('_').slice(1).join(' '))),
      el('td', {}, `${p.window_nm[0]}–${p.window_nm[1]}`),
      el('td', {}, p.direction === 'two_sided' ? '±' : (p.direction === 'positive' ? '+' : '−')),
      el('td', {}, num(p.biological_score, 3)),
      el('td', {}, num(p.operational_score, 3)),
      el('td', {}, num(p.nuisance_exposure, 2)),
      el('td', {}, d === null || d === undefined ? '—' : (d >= 0 ? '+' : '') + num(d, 2)),
      el('td', {}, db === null || db === undefined ? '—' : (db >= 0 ? '+' : '') + num(db, 2)),
      el('td', {}, t && t.test
        ? el('span', { class: 'verdict ' + t.test.verdict }, t.test.verdict.replace('_', ' '))
        : '—'));
  });

  wrap.appendChild(el('section', {},
    el('h2', {}, 'Every prediction, ranked and tested'),
    el('p', { class: 'hint' },
      'Effect sizes are Cohen’s d for Mikania minus native climber, computed within ' +
      'each site and averaged over sites — the same site-blocking rule §5.1(6) imposes on ' +
      'the classifier, applied to the desk study.'),
    el('div', { class: 'table-wrap' },
      el('table', {},
        el('thead', {}, el('tr', {},
          ...['prediction', 'window (nm)', 'pred', 'bio', 'ops', 'nuis',
            'd foliage', 'd in bloom', 'verdict'].map(h => el('th', {}, h)))),
        el('tbody', {}, rows)))));

  // ---- the a-priori acquisition constraint, tested ----
  if (gv && gv.sign_reversals_between_seasons) {
    const flips = gv.sign_reversals_between_seasons;
    wrap.appendChild(el('section', {},
      el('h2', {}, 'A constraint predicted before any spectrum was measured'),
      el('div', { class: 'callout ' + (flips.length ? 'good' : '') },
        el('strong', {}, 'Constraint A2. '),
        'The desk study derived, from the genomics alone, that a constitutive photosystem ' +
        'signal must be measured OUT of the flowering window to mean anything. Tested: ' +
        `${(gv.verdict_changes_between_seasons || []).length} of ${ranked.length} predictions ` +
        `change verdict between seasons and ${flips.length} reverse the SIGN of their effect` +
        (flips.length ? ` (${flips.map(f => f.replace(/_/g, ' ')).join(', ')}).` : '.') +
        ' The autumn bloom adds a bright floral component that fills the red absorption ' +
        'well and lifts the NIR plateau, so features built on those quantities measure the ' +
        'flower rather than the photosystem. Measuring in bloom alone would have produced ' +
        'confident, wrongly-signed conclusions.')));
  }

  // ---- did the ranking predict measurability, and does the prior help? ----
  const bs = gv && gv.band_selection;
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Was the desk study worth doing?'),
    el('div', { class: 'grid g2' },
      el('div', { class: 'card' },
        el('h3', {}, 'Did the ranking predict measurability?'),
        el('div', { class: 'kv' },
          el('div', {}, 'Spearman ρ (operational score vs |observed d|)'),
          el('div', {}, gv && gv.ranking_vs_measurability_spearman != null
            ? num(gv.ranking_vs_measurability_spearman, 2) : '—')),
        el('p', { class: 'hint' },
          gv && gv.ranking_informative
            ? 'Positive: the predictions the desk study said were worth measuring are the ' +
              'ones with measurable effects. That is the return on a few weeks of analyst ' +
              'time and zero capital.'
            : 'Weak: the defensible value is the evidence chain and the falsification ' +
              'specification, not the ordering.')),
      el('div', { class: 'card' },
        el('h3', {}, 'Does the prior improve the classifier?'),
        bs ? el('div', {},
          el('div', { class: 'kv' },
            el('div', {}, 'prior-selected vs random bands'),
            el('div', {}, (bs.delta_vs_random_pp >= 0 ? '+' : '') +
              num(bs.delta_vs_random_pp, 2) + ' pp')),
          el('p', { class: 'hint' },
            bs.claim_supported
              ? 'Supported when implemented as band SELECTION.'
              : 'Not supported. Reported as measured. §3.3(a) claims biology-informed ' +
                'weighting reduces overfitting; that claim does not survive testing here, ' +
                'and the proposal should make the narrower claim — the prior directs the ' +
                'field campaign, it does not improve the model.'),
          el('div', { class: 'callout' },
            el('strong', {}, 'A methodological catch worth stating. '),
            'Applying the prior as per-band feature WEIGHTS measures exactly zero effect: ' +
            'StandardScaler restores unit variance per band and annihilates it, and tree ' +
            'ensembles are invariant to monotone rescaling anyway. §3.3(a)’s wording — ' +
            '“weight and interrogate the regions the biology predicts” — is not ' +
            'implementable as a weight. A band prior can only enter as selection.'))
          : el('p', { class: 'hint' }, 'Run stage 10.')))));

  // ---- evidence chain for the top prediction ----
  const top = ranked[0];
  if (top && top.chain) {
    const c = top.chain;
    const chain = el('div', { class: 'chain' });
    c.findings.forEach(f => chain.appendChild(el('div', { class: 'chain-step' },
      el('span', { class: 'tier tier-' + f.evidence }, TIER_LABEL[f.evidence] || f.evidence),
      el('span', {}, f.claim, ' ', el('span', { class: 'hint' }, '— ' + f.source)))));
    chain.appendChild(el('div', { class: 'chain-arrow' }, '↓ inferred'));
    c.traits.forEach(t => chain.appendChild(el('div', { class: 'chain-step' },
      el('span', { class: 'tier tier-' + t.evidence }, TIER_LABEL[t.evidence] || t.evidence),
      el('span', {}, t.trait))));
    chain.appendChild(el('div', { class: 'chain-arrow' }, '↓ inferred'));
    chain.appendChild(el('div', { class: 'chain-step' },
      el('span', { class: 'tier tier-' + c.prediction_evidence },
        TIER_LABEL[c.prediction_evidence] || c.prediction_evidence),
      el('span', {}, top.measures, ' — ', el('strong', {}, `${top.window_nm[0]}–${top.window_nm[1]} nm`))));

    wrap.appendChild(el('section', {},
      el('h2', {}, 'Evidence chain: ' + top.id.split('_').slice(1).join(' ')),
      el('p', { class: 'hint' },
        'Confidence is floored by the weakest link, not averaged. This chain’s weakest ' +
        'link is ' + (c.weakest_link || '').replace(/_/g, ' ') +
        ', which is where the risk sits.'),
      chain,
      el('div', { class: 'callout' },
        el('strong', {}, 'Falsification test. '), top.falsification)));
  }

  wrap.appendChild(el('div', { class: 'callout' },
    el('strong', {}, 'The honest headline. '), gp.headline));
  return wrap;
};

/* ---------------------------- 10 barcode certification ------------------- */
VIEWS.barcode = () => {
  const b = S.bundle;
  const cov = b.barcode_coverage, ver = b.barcode_verification;
  const wrap = el('div');

  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Proposal §3.4 · stages 11 and 12'),
    el('h1', {}, 'Molecular certification of the label set'),
    el('p', { class: 'lede' },
      'Supervised classification inherits the error rate of its labels, and labelling a ' +
      'sterile vine tangled through a canopy by eye is the single most error-prone task ' +
      'in the workflow. Every voucher is barcode-verified before it can train anything. ' +
      'The sequences below are real, downloaded from NCBI.')));

  if (!cov) return wrap.appendChild(
    missing('barcode_reference_coverage.json', 'scripts/11_fetch_barcode_references.py')), wrap;

  const minRefs = cov.min_reference_seqs_per_species;

  wrap.appendChild(el('div', { class: 'grid g4' },
    kpi('Real sequences', String(cov.total_sequences), 'NCBI + BOLD, cited'),
    kpi('Empty taxon × locus', String((cov.empty_cells || []).length),
      `of ${cov.accepted_taxa.length * cov.loci.length} cells`,
      (cov.empty_cells || []).length ? 'warn' : 'good'),
    ver ? kpi('Certified correctly', pct(ver.precision_of_certified, 1),
      `${ver.n_correct}/${ver.n_certified} certified vouchers`,
      ver.n_wrong === 0 ? 'good' : 'bad') : kpi('Certified', '—', 'run stage 12'),
    ver ? kpi('Quarantined', pct(1 - ver.certification_rate, 1),
      'refused rather than guessed', 'warn') : kpi('Quarantined', '—', '')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  // ---- Appendix B.9 verdict ----
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Appendix B.9, tested'),
    el('div', { class: 'callout ' + ((cov.taxa_below_two_locus_requirement || []).length ? 'danger' : 'good') },
      el('strong', {}, 'Assumption B.9: '),
      '“Barcode reference coverage is assumed adequate … Unverified.” ',
      el('br', {}), el('strong', {}, 'Verdict: '), cov.appendix_b9_verdict,
      (cov.taxa_below_two_locus_requirement || []).length
        ? el('div', { style: 'margin-top:8px' },
            'Vouchers of ' + cov.taxa_below_two_locus_requirement.join(', ') +
            ' will quarantine rather than certify, because public references cannot reach ' +
            'the two-locus agreement §13.5 requires. That is Risk 10 measured on real data, ' +
            'and it is the direct argument for curating our own reference set — the ' +
            'mitigation the proposal already names.')
        : null),
    (cov.synonyms_merged && Object.keys(cov.synonyms_merged).length)
      ? el('div', { class: 'callout' },
          el('strong', {}, 'A taxonomy trap that fails silently. '),
          Object.entries(cov.synonyms_merged).map(([k, v]) => `${k} → ${v}`).join('; ') +
          '. Both names return records, many of them the same records. Treated as two ' +
          'species they generate “interspecific” pairs at ~zero distance, which collapses ' +
          'the minimum between-species distance and makes every locus report no barcode ' +
          'gap — a conclusion about DNA barcoding drawn from a nomenclatural artefact.')
      : null));

  // ---- coverage matrix ----
  const loci = cov.loci.map(l => l.key);
  const head = el('tr', {}, el('th', {}, ''),
    ...cov.loci.map(l => el('th', {}, l.key, el('div', { class: 'hint' }, l.role))));
  const body = cov.accepted_taxa.map(t => el('tr', {},
    el('th', { class: 'taxon' }, t),
    ...loci.map(k => {
      const n = (cov.matrix[t] || {})[k] || 0;
      const cls = n === 0 ? 'cell-none' : (n < minRefs ? 'cell-thin' : 'cell-ok');
      return el('td', { class: cls }, n === 0 ? 'none' : String(n));
    })));
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Public reference coverage'),
    el('p', { class: 'hint' },
      `Red = no public reference at all. Amber = below the ${minRefs}-sequence floor at ` +
      'which an intraspecific range can be established, so no species call is licensed.'),
    el('div', { class: 'table-wrap' },
      el('table', { class: 'matrix' }, el('thead', {}, head), el('tbody', {}, body)))));

  if (!ver) { wrap.appendChild(missing('barcode_verification.json', 'scripts/12_barcode_verify_vouchers.py')); return wrap; }

  // ---- barcode gap ----
  const gaps = ver.barcode_gap || {};
  const gapRows = Object.keys(gaps).filter(k => gaps[k].status === 'ok').map(k => {
    const g = gaps[k];
    const tag = g.barcode_gap ? 'strict gap' : (g.barcode_gap_robust ? 'robust only' : 'no gap');
    const cls = g.barcode_gap ? 'pass' : (g.barcode_gap_robust ? 'warn' : 'fail');
    return el('tr', {},
      el('td', {}, el('span', { class: 'mono' }, k)),
      el('td', {}, num(g.max_within, 4)), el('td', {}, num(g.p95_within, 4)),
      el('td', {}, num(g.min_between, 4)), el('td', {}, num(g.p05_between, 4)),
      el('td', {}, el('span', { class: 'badge ' + cls }, tag)));
  });
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Barcode gap, measured on real sequences'),
    el('p', { class: 'hint' },
      'A gap exists when interspecific distances exceed intraspecific ones. The strict ' +
      'criterion compares the two extremes, so one defective public record can sink a ' +
      'locus; the robust criterion uses the 95th and 5th percentiles. Both are shown ' +
      'rather than whichever flatters.' +
      ((ver.n_reference_records_flagged || 0)
        ? ` ${ver.n_reference_records_flagged} public record(s) were excluded as discordant ` +
          'with their own species and retained in the audit trail.' : '')),
    el('div', { class: 'table-wrap' },
      el('table', {},
        el('thead', {}, el('tr', {}, ...['locus', 'within max', 'within p95',
          'between min', 'between p05', 'verdict'].map(h => el('th', {}, h)))),
        el('tbody', {}, gapRows))),
    el('p', { class: 'hint' },
      'Where a locus has no gap it cannot carry a species call on its own — which is why ' +
      '§13.5 requires two loci to agree rather than trusting one.')));

  // ---- certificates ----
  const certs = (ver.certificates || []).slice(0, 24);
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Voucher certificates'),
    el('p', { class: 'hint' },
      'Vouchers are real GenBank sequences held out of the reference set and degraded into ' +
      'simulated Sanger reads, so “the pipeline recovered the right species” is measurable ' +
      'against a real answer key. ' + (ver.n_wrong === 0
        ? 'No voucher was certified to the wrong species: everything the gate passed was ' +
          'correct, and what it could not resolve was quarantined rather than guessed.'
        : `${ver.n_wrong} voucher(s) were certified WRONG — the failure mode that matters.`)),
    el('div', { class: 'cert-grid' }, certs.map(c => el('div', { class: 'cert ' + c.status },
      el('div', { class: 'vid' }, c.voucher_id, ' · ', c.site_key, ' · ',
        c.sterile ? 'sterile' : 'fertile'),
      el('div', { class: 'taxon' }, c.certified_taxon || c.proposed_taxon || 'unresolved'),
      el('div', { class: 'loci' },
        c.status === 'certified'
          ? `certified · confidence ${num(c.confidence, 2)} · ${(c.loci_used || []).join(', ')}`
          : 'quarantined'),
      c.status === 'certified' && !c.correct
        ? el('div', { class: 'why' }, 'WRONG — true identity ' + c.true_taxon) : null,
      c.status === 'quarantined'
        ? el('div', { class: 'why' }, (c.reasons || [])[0] || '') : null)))));

  // ---- concordance ----
  const conc = ver.concordance;
  if (conc && conc.n) {
    wrap.appendChild(el('section', {},
      el('h2', {}, 'Visual field call vs sequence'),
      el('div', { class: 'grid g3' },
        kpi('Agreement', pct(conc.agreement, 1), `n = ${conc.n} certified vouchers`),
        kpi('Cohen’s κ', num(conc.cohens_kappa, 2), 'chance-corrected'),
        kpi('Native called Mikania', String(conc.native_called_mikania),
          'would have been cleared', conc.native_called_mikania ? 'bad' : 'good')),
      el('p', { class: 'hint' },
        '§5.1(2) proposes measuring exactly this and notes it is saleable in its own right: ' +
        'if visual identification is, say, 90% concordant with barcode identity, AFCD has ' +
        'learned something material about its own programme that nobody has measured. ' +
        'Small n here — this is the shape of the Phase 0 deliverable, not a Hong Kong result.')));
  }
  return wrap;
};

/* ---------------------------- 11 label-error risk ------------------------ */
VIEWS.labelrisk = () => {
  const b = S.bundle;
  const le = b.label_error;
  const wrap = el('div');

  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Proposal §9 Risk 9 · stage 13'),
    el('h1', {}, 'What wrong labels actually do'),
    el('p', { class: 'lede' },
      'Risk 9 says label error “inflates apparent accuracy while degrading real ' +
      'performance”. That is a specific, directional, testable claim. It was tested.')));

  if (!le || !le.sweep) return wrap.appendChild(
    missing('label_error.json', 'scripts/13_label_error_propagation.py')), wrap;

  const sw = le.sweep, at = sw.at_nominal, val = le.certification_value;
  const confirmed = (sw.curves || []).some(c => c.max_apparent_minus_true_pp > 0.5);

  wrap.appendChild(el('div', { class: 'grid g4' },
    kpi('Apparent accuracy', num(at.apparent_climber_accuracy, 3),
      'scored on the same faulty labels'),
    kpi('True accuracy', num(at.true_climber_accuracy, 3),
      'scored on certified labels', 'good'),
    kpi('Gap', (at.apparent_minus_true_pp >= 0 ? '+' : '') +
      num(at.apparent_minus_true_pp, 1) + ' pp',
      at.apparent_minus_true_pp < 0 ? 'programme understates itself' : 'flatters reality',
      'warn'),
    kpi('§7.3 kill criterion', sw.kill_criterion_spuriously_failed ? 'SPURIOUS FAIL'
      : (sw.kill_criterion_masked ? 'MASKED' : 'intact'),
      `threshold ${pct(sw.kill_threshold, 0)}`,
      (sw.kill_criterion_spuriously_failed || sw.kill_criterion_masked) ? 'bad' : 'good')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  wrap.appendChild(el('section', {},
    el('h2', {}, 'The direction does not survive measurement'),
    el('div', { class: 'callout ' + (confirmed ? '' : 'danger') },
      el('strong', {}, confirmed ? 'Risk 9 confirmed. ' : 'Risk 9 is real, severe, and stated backwards. '),
      confirmed
        ? 'Biased label error flatters the reportable number while real performance degrades.'
        : 'Under site-disjoint validation the gap is negative throughout: corrupted labels ' +
          'make the programme look WORSE than it is, not better. The proposal’s mechanism ' +
          'needs the model’s errors to correlate with the VALIDATION set’s label errors, ' +
          'and a site-disjoint split makes that impossible. A random pixel split — the ' +
          'regime §5.1(6) already condemns — was run too, on the theory that a corrupted ' +
          'patch straddling the boundary could be memorised. It deflates as well: a ' +
          'mislabelled patch of Bauhinia is still spectrally Bauhinia, and is outvoted by ' +
          'every correctly-labelled Bauhinia patch in training.'),
    sw.kill_criterion_spuriously_failed
      ? el('div', { class: 'callout danger' },
          el('strong', {}, 'The harm, restated. '),
          `The true classifier clears the §7.3 threshold at ${num(at.true_climber_accuracy, 3)}, ` +
          `but a programme scoring against its own uncertified labels reads ` +
          `${num(at.apparent_climber_accuracy, 3)} and stops the project. HK$1.4M spent to ` +
          'reach a wrong STOP decision — the expensive failure mode for a venture built ' +
          'around a kill criterion, and the opposite of what Risk 9 predicts. Certification ' +
          'protects the go/no-go decision itself, which is a better argument than the one ' +
          'the proposal currently makes.')
      : null));

  // ---- sweep table ----
  const curves = sw.curves || [];
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Error rate × bias'),
    el('p', { class: 'hint' },
      'Bias is the fraction of misidentifications that go toward Mikania — a surveyor ' +
      'working a control programme is primed to find it. Bias 0.50 is the symmetric ' +
      'control. Corruption is applied to whole specimen blocks, not to individual pixels: ' +
      'a surveyor identifies one vine and that judgement propagates to every pixel of the ' +
      'polygon drawn around it.'),
    el('div', { class: 'table-wrap' },
      el('table', {},
        el('thead', {}, el('tr', {}, el('th', {}, 'error rate'),
          ...curves.map(c => el('th', {}, `bias ${pct(c.bias, 0)}`,
            el('div', { class: 'hint' }, 'apparent / true'))))),
        el('tbody', {}, (sw.rates || []).map((r, i) => el('tr', {},
          el('td', {}, pct(r, 0)),
          ...curves.map(c => {
            const p = c.points[i];
            return el('td', {}, p
              ? `${num(p.apparent_climber_accuracy, 3)} / ${num(p.true_climber_accuracy, 3)}`
              : '—');
          }))))))));

  // ---- the fix (stage 16) ----
  const rem = b.remediation && b.remediation.certification_allocation;
  if (rem) {
    const arms = rem.arms;
    const last = a => a[a.length - 1].p_correct_decision;
    wrap.appendChild(el('section', {},
      el('h2', {}, 'The fix: certify the validation set, not the training set'),
      el('p', { class: 'hint' },
        'The §7.3 verdict is read off the hold-out, and the classifier overrides ' +
        'training-label noise rather than learning it. So training labels barely move ' +
        'the decision and validation labels move it one-for-one. Measured over ' +
        rem.n_trials + ' trials; the metric is P(the go/no-go decision is correct), ' +
        'because a programme acts on a verdict, not on a number.'),
      el('div', { class: 'grid g3' },
        kpi('Uncertified', pct(arms.none[0].p_correct_decision, 0),
          'decisions correct — worse than a coin flip', 'bad'),
        kpi('Training certified', pct(last(arms.train_only), 0),
          'certifying 100% of training data', 'bad'),
        kpi('Validation certified', pct(last(arms.val_only), 0),
          rem.min_validation_fraction_for_correct_decision != null
            ? `reliable from ${pct(rem.min_validation_fraction_for_correct_decision, 0)} of ` +
              `${rem.n_validation_specimens} specimens`
            : '', 'good')),
      el('div', { class: 'table-wrap' },
        el('table', {},
          el('thead', {}, el('tr', {}, el('th', {}, 'certified'),
            ...Object.keys(arms).map(k => el('th', {}, k.replace('_', ' '))))),
          el('tbody', {}, arms.none.map((_, i) => el('tr', {},
            el('td', {}, pct(arms.none[i].fraction_certified, 0)),
            ...Object.keys(arms).map(k => el('td', {}, pct(arms[k][i].p_correct_decision, 0)))))))),
      el('div', { class: 'callout good' },
        el('strong', {}, 'It costs nothing. '),
        'This is a reallocation inside the existing §7.3 line, not an addition. ' +
        'The `both` column is identical to `val_only` at every fraction — the entire ' +
        'benefit of certification comes from the validation half, and everything spent ' +
        'on the training half bought nothing for this decision.')));
  }

  // ---- certification value ----
  if (val) {
    const u = val.uncertified_programme, c = val.certified_programme;
    wrap.appendChild(el('section', {},
      el('h2', {}, 'What certification costs, and what it saves'),
      el('div', { class: 'grid g3' },
        kpi('Certification', hkd(val.total_certification_cost_hkd),
          `${val.n_vouchers} vouchers at ${hkd(val.cost_per_voucher_hkd)} each · ` +
          (val.within_budget_line ? 'within the §7.3 line' : 'OUTSIDE the §7.3 line'),
          val.within_budget_line ? 'good' : 'bad'),
        kpi('Avoided cost / yr', hkd(val.avoided_cost_hkd_per_year),
          `${num(u.wrongly_cleared_ha, 1)} → ${num(c.wrongly_cleared_ha, 1)} ha wrongly cleared`),
        kpi('Benefit : cost', String(val.benefit_cost_ratio),
          'on a 3,000 ha programme',
          val.benefit_cost_ratio >= 1 ? 'good' : 'warn')),
      el('p', { class: 'hint' },
        'Two costs are counted: crews sent to the wrong polygon, and the induced cost — ' +
        '§2.1(b) warns that clearing a native climber “may itself create a niche for ' +
        'Mikania to invade”, so a wrongly cleared patch is a seedbed, not a neutral ' +
        'outcome.'),
      el('div', { class: 'callout' },
        el('strong', {}, 'Read the ratio carefully. '),
        (val.benefit_cost_ratio < 1
          ? 'Below 1. On avoided wrong-clearance alone, certification does not pay for ' +
            'itself at this programme size — and that is the honest number. The case for ' +
            'it rests on protecting the go/no-go decision above, on the auditability a ' +
            'government client is actually buying (§6.1.6), and on the reference database ' +
            'being an asset with its own revenue (§7.2). Selling it on avoided clearance ' +
            'cost would not survive an evaluator with a calculator.'
          : 'Above 1 on avoided wrong-clearance alone, before counting auditability or ' +
            'the asset value of the resulting database.')),
      el('ul', { class: 'hint' }, (val.caveats || []).map(x => el('li', {}, x)))));
  }
  return wrap;
};

/* ---------------------------- 12 reference database ---------------------- */
VIEWS.asset = () => {
  const b = S.bundle;
  const rd = b.reference_database;
  const wrap = el('div');

  wrap.appendChild(el('div', { class: 'page-head' },
    el('div', { class: 'kicker' }, 'Proposal §3.1 deliverable 4 · §7.1 · stage 14'),
    el('h1', {}, 'The asset is a database, not a drone'),
    el('p', { class: 'lede' },
      'The sensor, the aircraft and the classifier are purchasable by anyone. What is not ' +
      'is a barcode-certified, spectrally-paired, georeferenced reference set for Hong ' +
      'Kong invasive flora, accumulating across seasons and contract years.')));

  if (!rd || !rd.release) return wrap.appendChild(
    missing('reference_database.json', 'scripts/14_reference_database.py')), wrap;

  const rel = rd.release, val = rd.valuation, sum = rd.summary, ic = rd.integrity;

  wrap.appendChild(el('div', { class: 'grid g4' },
    kpi('Certified vouchers', String(rel.n_certified), 'released to training'),
    kpi('Quarantined', String(rel.n_quarantined), 'structurally unreachable', 'warn'),
    kpi('Replacement cost', hkd(val.replacement_cost_hkd), 'current contents'),
    kpi('Calendar years', String(val.calendar_years_to_replicate),
      'cannot be bought out of', 'good')));

  wrap.appendChild(el('div', { class: 'spacer' }));

  wrap.appendChild(el('section', {},
    el('h2', {}, 'Release'),
    el('div', { class: 'card' },
      el('div', { class: 'kv' },
        el('div', {}, 'Release id'), el('div', { class: 'release-id' }, rel.release_id),
        el('div', {}, 'Content SHA-256'), el('div', { class: 'sha' }, rel.content_sha256),
        el('div', {}, 'Integrity'), el('div', {},
          el('span', { class: 'badge ' + (ic.ok ? 'pass' : 'fail') }, ic.ok ? 'PASS' : 'FAIL'))),
      el('p', { class: 'hint' },
        'The checksum is over the row content, not the file. SQLite rewrites pages on ' +
        'vacuum and on version upgrade, so a file hash changes when nothing scientific ' +
        'has — and a licensee needs to verify the rows they hold, not the byte layout.'),
      (ic.warnings || []).length
        ? el('div', { class: 'callout' }, el('strong', {}, 'Warnings. '),
            el('ul', {}, ic.warnings.map(w => el('li', {}, w))))
        : null)));

  wrap.appendChild(el('section', {},
    el('h2', {}, 'The release gate is a function, not a policy'),
    el('div', { class: 'callout good' },
      el('strong', {}, 'training_label_set() '),
      'returns certified vouchers and nothing else, so a training stage cannot include ' +
      'an uncertified specimen however the calling code is written. ' +
      `${rd.training_label_set_size} voucher(s) are reachable through it; ` +
      `${(rd.quarantine || {}).n_quarantined} are not. Quarantined vouchers are kept rather ` +
      'than deleted — the set of specimens that cannot be identified molecularly is the ' +
      'direct measurement of Risk 10, not a loss.')));

  // ---- licence tiers ----
  const tiers = rd.licences || {};
  wrap.appendChild(el('section', {},
    el('h2', {}, 'Licence tiers — and what each one does not get'),
    el('div', { class: 'card' }, Object.entries(tiers).map(([name, t]) => {
      const p = t.price_hkd_per_year;
      const ptxt = p == null ? '—' : (Array.isArray(p) ? `${hkd(p[0])}–${hkd(p[1])}/yr` : hkd(p) + '/yr');
      return el('div', { class: 'tier-row' },
        el('div', { class: 'name' }, name),
        el('div', {},
          el('div', { class: 'granted' }, '✓ ' + t.tables_granted.join(', ')),
          t.tables_withheld.length
            ? el('div', { class: 'withheld' }, '✗ ' + t.tables_withheld.join(', ')) : null,
          el('div', { class: 'hint' }, (t.notes || []).join(' '))),
        el('div', {}, ptxt));
    })),
    el('p', { class: 'hint' },
      'The withheld column is the commercial substance. §7.1: contracts must reserve ' +
      'database ownership while granting the client unlimited use of derived maps and ' +
      'reports — “the single most important commercial term in the agreement”. Stating ' +
      'the boundary in a manifest is what makes it negotiable at signature rather than ' +
      'disputed later.')));

  // ---- deposition ----
  const dep = rd.deposition;
  if (dep) {
    wrap.appendChild(el('section', {},
      el('h2', {}, '§8.4 sequence deposition policy'),
      el('div', { class: 'grid g3' },
        kpi('To deposit', String(dep.n_deposit), `public coverage < ${dep.threshold}`),
        kpi('Withheld', String(dep.n_withhold), 'coverage already adequate'),
        kpi('Coordinates', dep.coordinate_generalisation_km + ' km',
          'generalised before publication')),
      el('p', { class: 'hint' },
        'Always withheld regardless of tier: ' + (dep.withheld_fields || []).join(', ') +
        '. A barcode sequence alone does not let a competitor build the product; the ' +
        'sequence-to-spectrum-to-place linkage does, and it is not reconstructable from ' +
        'public data. Depositing the former buys scientific credibility at no ' +
        'competitive cost.')));
  }

  wrap.appendChild(el('div', { class: 'callout' },
    el('strong', {}, 'Scope. '), rd.scope));
  return wrap;
};
