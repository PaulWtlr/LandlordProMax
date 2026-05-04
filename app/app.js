const TARGET_BOUNDS = [
  [51.28, -0.55],
  [51.70, 0.35],
];
const DATE_FORMAT = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const GBP = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});
const WHOLE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

let map;
let markerLayer;
let boundaryLayer;
let fallbackPins;
let markerRefs = new Map();
let toastTimer;

const state = {
  all: [],
  filtered: [],
  selectedId: null,
  selectedIds: new Set(),
  datasetName: "Demo synthetique",
};

const els = {
  areaFilter: document.querySelector("#areaFilter"),
  searchInput: document.querySelector("#searchInput"),
  minPriceInput: document.querySelector("#minPriceInput"),
  maxPriceInput: document.querySelector("#maxPriceInput"),
  typeFilter: document.querySelector("#typeFilter"),
  bedroomFilter: document.querySelector("#bedroomFilter"),
  tenureFilter: document.querySelector("#tenureFilter"),
  scoreFilter: document.querySelector("#scoreFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  priceRangeLabel: document.querySelector("#priceRangeLabel"),
  scoreLabel: document.querySelector("#scoreLabel"),
  targetCount: document.querySelector("#targetCount"),
  listCount: document.querySelector("#listCount"),
  selectionStatus: document.querySelector("#selectionStatus"),
  selectedCount: document.querySelector("#selectedCount"),
  metricStrip: document.querySelector("#metricStrip"),
  listingList: document.querySelector("#listingList"),
  rankedList: document.querySelector("#rankedList"),
  detailPane: document.querySelector("#detailPane"),
  datasetLabel: document.querySelector("#datasetLabel"),
  fileInput: document.querySelector("#fileInput"),
  importButton: document.querySelector("#importButton"),
  exportButton: document.querySelector("#exportButton"),
  resetButton: document.querySelector("#resetButton"),
  selectVisibleButton: document.querySelector("#selectVisibleButton"),
  clearSelectionButton: document.querySelector("#clearSelectionButton"),
  toast: document.querySelector("#toast"),
};

async function init() {
  initMap();
  const loaded = await loadListings(false);
  state.all = loaded.rows;
  state.datasetName = loaded.label;
  state.selectedId = state.all[0]?.id ?? null;
  populateDynamicOptions();
  wireEvents();
  applyFilters();
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

async function loadListings(refresh = false) {
  try {
    const response = await fetch(`/api/listings${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
    if (response.ok) {
      const payload = await response.json();
      const rows = normaliseRows(payload.listings || []);
      if (rows.length) {
        return {
          rows,
          label: datasetLabel(payload.meta, rows.length),
        };
      }
    }
  } catch (error) {
    console.info("Local listings API unavailable, falling back to static data.", error);
  }

  const source = window.LIVE_PROPERTIES?.length ? window.LIVE_PROPERTIES : window.SAMPLE_PROPERTIES || [];
  const rows = normaliseRows(source);
  return {
    rows,
    label: window.LIVE_PROPERTIES?.length
      ? `Foxtons static export | ${rows.length} actifs`
      : "Demo synthetique",
  };
}

function normaliseRows(source) {
  return source
    .map(normaliseListing)
    .filter(Boolean)
    .filter(isLondonListing);
}

function datasetLabel(meta, count) {
  if (!meta) {
    return `Foxtons live export | ${count} actifs`;
  }
  const requested = Number(meta.requestedLimit || 0);
  const area = meta.mode === "chelsea_south_kensington"
    ? "Foxtons Chelsea / South Kensington"
    : "Foxtons Londres";
  return requested && count < requested
    ? `${area} | ${count}/${requested} actifs disponibles`
    : `${area} | ${count} actifs`;
}

function normaliseListing(raw, index = 0) {
  const lat = toNumber(firstDefined(raw.lat, raw.latitude));
  const lng = toNumber(firstDefined(raw.lng, raw.lon, raw.longitude));
  const price = toNumber(raw.price);

  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !Number.isFinite(price)) {
    return null;
  }

  const sourceId = String(firstDefined(raw.sourceId, raw.source_id, raw.id, `listing-${index + 1}`));
  const capturedAt = parseDate(firstDefined(raw.capturedAt, raw.captured_at, raw.capture_date));
  const address = String(firstDefined(raw.address, raw.displayAddress, raw.title, "Adresse inconnue"));
  const neighbourhood = normaliseArea(firstDefined(raw.neighbourhood, raw.neighborhood, raw.area, raw.district));
  const sqft = toNumber(firstDefined(raw.sqft, raw.area_sqft, raw.floor_area_sqft));
  const rentEstimate = toNumber(firstDefined(raw.rentEstimate, raw.rent_estimate, raw.monthly_rent_estimate));
  const explicitYield = toNumber(firstDefined(raw.grossYield, raw.gross_yield));
  const computedYield =
    Number.isFinite(explicitYield) && explicitYield > 0
      ? explicitYield
      : Number.isFinite(rentEstimate) && rentEstimate > 0
        ? (rentEstimate * 12 * 100) / price
        : null;

  return {
    id: `${firstDefined(raw.source, "import")}-${sourceId}`.replace(/\s+/g, "-"),
    source: String(firstDefined(raw.source, "import")),
    sourceId,
    url: String(firstDefined(raw.url, "#")),
    capturedAt,
    price,
    address,
    postcode: cleanText(firstDefined(raw.postcode, raw.post_code)),
    neighbourhood,
    lat,
    lng,
    bedrooms: toNumber(firstDefined(raw.bedrooms, raw.beds)),
    bathrooms: toNumber(firstDefined(raw.bathrooms, raw.baths)),
    sqft,
    propertyType: cleanText(firstDefined(raw.propertyType, raw.property_type, raw.type)),
    tenure: cleanText(raw.tenure),
    agent: cleanText(raw.agent),
    status: cleanText(raw.status) || "for_sale",
    priceChange: toNumber(firstDefined(raw.priceChange, raw.price_change)),
    daysOnMarket: toNumber(firstDefined(raw.daysOnMarket, raw.days_on_market)),
    serviceCharge: toNumber(firstDefined(raw.serviceCharge, raw.service_charge)),
    groundRent: toNumber(firstDefined(raw.groundRent, raw.ground_rent)),
    leaseYears: toNumber(firstDefined(raw.leaseYears, raw.lease_years)),
    rentEstimate,
    grossYield: computedYield,
    score: clampScore(toNumber(raw.score)),
    notes: cleanText(raw.notes),
  };
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function cleanText(value) {
  return value === undefined || value === null ? "" : String(value).trim();
}

function toNumber(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const parsed = Number(String(value).replace(/[GBP£,\s]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function parseDate(value) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normaliseArea(value) {
  const text = cleanText(value);
  if (/chelsea\s+harbour/i.test(text)) {
    return "Chelsea Harbour";
  }
  if (/south\s+ken/i.test(text)) {
    return "South Kensington";
  }
  if (/chelsea/i.test(text)) {
    return "Chelsea";
  }
  return text;
}

function isLondonListing(listing) {
  const inLat = listing.lat >= TARGET_BOUNDS[0][0] && listing.lat <= TARGET_BOUNDS[1][0];
  const inLng = listing.lng >= TARGET_BOUNDS[0][1] && listing.lng <= TARGET_BOUNDS[1][1];
  return inLat && inLng;
}

function clampScore(value) {
  if (!Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function initMap() {
  if (!window.L) {
    initFallbackMap();
    showToast("Carte locale activee.");
    return;
  }

  map = window.L.map("map", {
    zoomControl: false,
    scrollWheelZoom: true,
  }).setView([51.4917, -0.1782], 15);

  window.L.control.zoom({ position: "bottomright" }).addTo(map);
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  boundaryLayer = window.L.rectangle(TARGET_BOUNDS, {
    color: "#006d77",
    weight: 2,
    dashArray: "6 6",
    fillOpacity: 0.05,
  }).addTo(map);

  markerLayer = window.L.layerGroup().addTo(map);
  setTimeout(() => map.invalidateSize(), 0);
}

function initFallbackMap() {
  const mapEl = document.querySelector("#map");
  mapEl.classList.add("fallback-map");
  mapEl.innerHTML = `
    <div class="fallback-stage">
      <div class="fallback-zone"></div>
      <div class="map-road road-kings">King's Road</div>
      <div class="map-road road-fulham">Fulham Road</div>
      <div class="map-road road-brompton">Old Brompton Road</div>
      <div class="map-road road-gloucester">Gloucester Road</div>
      <div class="area-label area-chelsea">Chelsea</div>
      <div class="area-label area-southken">South Kensington</div>
      <div id="fallbackPins" class="fallback-pins"></div>
    </div>
  `;
  fallbackPins = document.querySelector("#fallbackPins");
}

function populateDynamicOptions() {
  populateSelect(els.areaFilter, uniqueValues(state.all, "neighbourhood"), "Chelsea + South Kensington");
  populateSelect(els.typeFilter, uniqueValues(state.all, "propertyType"), "Tous");
  populateSelect(els.tenureFilter, uniqueValues(state.all, "tenure"), "Tous");
}

function populateSelect(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="all">${allLabel}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map((row) => row[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function wireEvents() {
  [
    els.areaFilter,
    els.searchInput,
    els.minPriceInput,
    els.maxPriceInput,
    els.typeFilter,
    els.bedroomFilter,
    els.tenureFilter,
    els.scoreFilter,
    els.sortSelect,
  ].forEach((input) => input.addEventListener("input", applyFilters));

  els.importButton.addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", handleImport);
  els.exportButton.addEventListener("click", exportFilteredCsv);
  els.resetButton.addEventListener("click", resetDemo);
  els.selectVisibleButton.addEventListener("click", selectVisibleListings);
  els.clearSelectionButton.addEventListener("click", clearSelection);
}

function applyFilters() {
  const area = els.areaFilter.value;
  const query = els.searchInput.value.trim().toLowerCase();
  const minPrice = toNumber(els.minPriceInput.value);
  const maxPrice = toNumber(els.maxPriceInput.value);
  const type = els.typeFilter.value;
  const minBedrooms = els.bedroomFilter.value === "all" ? null : Number(els.bedroomFilter.value);
  const tenure = els.tenureFilter.value;
  const minScore = Number(els.scoreFilter.value);

  state.filtered = state.all.filter((listing) => {
    const haystack = [listing.address, listing.postcode, listing.agent, listing.source, listing.propertyType]
      .join(" ")
      .toLowerCase();

    return (
      (area === "all" || listing.neighbourhood === area) &&
      (!query || haystack.includes(query)) &&
      (!Number.isFinite(minPrice) || listing.price >= minPrice) &&
      (!Number.isFinite(maxPrice) || listing.price <= maxPrice) &&
      (type === "all" || listing.propertyType === type) &&
      (!minBedrooms || Number(listing.bedrooms || 0) >= minBedrooms) &&
      (tenure === "all" || listing.tenure === tenure) &&
      Number(listing.score || 0) >= minScore
    );
  });

  sortFiltered();
  if (!state.filtered.some((listing) => listing.id === state.selectedId)) {
    state.selectedId = state.filtered[0]?.id ?? null;
  }
  render();
}

function sortFiltered() {
  const mode = els.sortSelect.value;
  const sorters = {
    score_desc: (a, b) => (b.score || 0) - (a.score || 0),
    price_asc: (a, b) => a.price - b.price,
    price_desc: (a, b) => b.price - a.price,
    psf_asc: (a, b) => pricePerSqft(a) - pricePerSqft(b),
    newest: (a, b) => dateValue(b.capturedAt) - dateValue(a.capturedAt),
  };
  state.filtered.sort(sorters[mode] || sorters.score_desc);
}

function dateValue(date) {
  return date instanceof Date ? date.getTime() : 0;
}

function render() {
  els.datasetLabel.textContent = state.datasetName;
  els.targetCount.textContent = `${state.all.length} actifs`;
  els.listCount.textContent = `${state.filtered.length}`;
  els.scoreLabel.textContent = `${els.scoreFilter.value}+`;
  els.priceRangeLabel.textContent = priceRangeLabel();

  renderMetrics();
  renderMarkers(true);
  renderList();
  renderDetails();
  renderRanking();
}

function priceRangeLabel() {
  const min = toNumber(els.minPriceInput.value);
  const max = toNumber(els.maxPriceInput.value);
  if (Number.isFinite(min) && Number.isFinite(max)) {
    return `${compactMoney(min)} - ${compactMoney(max)}`;
  }
  if (Number.isFinite(min)) {
    return `>= ${compactMoney(min)}`;
  }
  if (Number.isFinite(max)) {
    return `<= ${compactMoney(max)}`;
  }
  return "Tout";
}

function renderMetrics() {
  const prices = state.filtered.map((listing) => listing.price);
  const psf = state.filtered.map(pricePerSqft).filter(Number.isFinite);
  const yields = state.filtered.map((listing) => listing.grossYield).filter(Number.isFinite);
  const scores = state.filtered.map((listing) => listing.score).filter(Number.isFinite);

  const metrics = [
    ["Listings", WHOLE.format(state.filtered.length), `${state.all.length} dans l'univers`],
    ["Prix median", formatMaybeMoney(median(prices)), "asking price"],
    ["GBP/sqft median", formatMaybeMoney(median(psf)), "surface declaree"],
    ["Yield median", formatPercent(median(yields)), `score med ${formatMaybeNumber(median(scores))}`],
  ];

  els.metricStrip.innerHTML = metrics
    .map(
      ([label, value, hint]) => `
        <div class="metric">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(hint)}</small>
        </div>
      `,
    )
    .join("");
}

function renderMarkers(fitMap = true) {
  if (fallbackPins) {
    renderFallbackMarkers();
    return;
  }

  if (!map || !markerLayer) {
    return;
  }
  markerLayer.clearLayers();
  markerRefs = new Map();
  const positions = markerDisplayPositions(state.filtered);

  state.filtered.forEach((listing) => {
    const point = positions.get(listing.id) || [listing.lat, listing.lng];
    const selected = state.selectedIds.has(listing.id);
    const marker = window.L.marker(point, {
      icon: window.L.divIcon({
        className: "",
        html: `<div class="listing-pin pin-${pinTone(listing)}${selected ? " selected" : ""}">${escapeHtml(compactPriceLabel(listing.price))}</div>`,
        iconSize: [68, 30],
        iconAnchor: [34, 15],
      }),
      title: listing.address,
    });

    marker.on("click", () => {
      selectListing(listing.id, false);
      marker.openPopup();
    });
    marker.bindPopup(`
      <div class="popup-card">
        <strong>${escapeHtml(listing.address)}</strong>
        <span>${escapeHtml(formatMaybeMoney(listing.price))} | ${escapeHtml(bedBath(listing))}</span>
        <span>${escapeHtml(listing.neighbourhood)} | ${escapeHtml(listing.propertyType || "-")}</span>
        <span>${escapeHtml(formatMaybeMoney(pricePerSqft(listing)))} / sqft | score ${escapeHtml(String(listing.score ?? "-"))}</span>
        <div class="popup-actions">
          <a href="${escapeAttribute(listing.url || "#")}" target="_blank" rel="noreferrer">Source</a>
          <button type="button" onclick="window.toggleListingSelection('${escapeAttribute(listing.id)}')">
            ${selected ? "Retirer" : "Select"}
          </button>
        </div>
      </div>
    `);
    marker.addTo(markerLayer);
    markerRefs.set(listing.id, marker);
  });

  if (fitMap) {
    fitMapToFiltered(positions);
  }
}

function markerDisplayPositions(listings) {
  const groups = new Map();
  listings.forEach((listing) => {
    const key = `${listing.lat.toFixed(5)}:${listing.lng.toFixed(5)}`;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(listing);
  });

  const positions = new Map();
  groups.forEach((group) => {
    if (group.length === 1) {
      positions.set(group[0].id, [group[0].lat, group[0].lng]);
      return;
    }
    const radius = Math.min(0.00024, 0.000055 + group.length * 0.000004);
    group.forEach((listing, index) => {
      const angle = (Math.PI * 2 * index) / group.length;
      positions.set(listing.id, [
        listing.lat + Math.sin(angle) * radius,
        listing.lng + Math.cos(angle) * radius,
      ]);
    });
  });
  return positions;
}

function fitMapToFiltered(positions) {
  if (!map) {
    return;
  }
  if (state.filtered.length === 1) {
    const only = state.filtered[0];
    map.setView(positions.get(only.id) || [only.lat, only.lng], 18, { animate: false });
    return;
  }
  if (state.filtered.length) {
    const points = state.filtered.map((listing) => positions.get(listing.id) || [listing.lat, listing.lng]);
    map.fitBounds(window.L.latLngBounds(points).pad(0.16), { animate: false, maxZoom: 16 });
  } else if (boundaryLayer) {
    map.fitBounds(boundaryLayer.getBounds(), { animate: false });
  }
}

function renderFallbackMarkers() {
  fallbackPins.innerHTML = state.filtered
    .map((listing) => {
      const point = projectPoint(listing);
      const active = listing.id === state.selectedId ? " active" : "";
      const selected = state.selectedIds.has(listing.id) ? " selected" : "";
      return `
        <button
          class="fallback-pin pin-${pinTone(listing)}${active}${selected}"
          type="button"
          data-id="${escapeAttribute(listing.id)}"
          style="left: ${point.x}%; top: ${point.y}%"
          aria-label="${escapeAttribute(listing.address)}"
        >
          ${escapeHtml(compactPriceLabel(listing.price))}
        </button>
      `;
    })
    .join("");

  fallbackPins.querySelectorAll(".fallback-pin").forEach((pin) => {
    pin.addEventListener("click", () => selectListing(pin.dataset.id, false));
  });
}

function projectPoint(listing) {
  const bounds = boundsForListings(state.filtered.length ? state.filtered : state.all);
  const south = bounds[0][0];
  const west = bounds[0][1];
  const north = bounds[1][0];
  const east = bounds[1][1];
  const x = ((listing.lng - west) / (east - west)) * 100;
  const y = 100 - ((listing.lat - south) / (north - south)) * 100;
  return {
    x: Math.max(4, Math.min(96, x)),
    y: Math.max(6, Math.min(94, y)),
  };
}

function boundsForListings(listings) {
  if (!listings.length) {
    return TARGET_BOUNDS;
  }
  const lats = listings.map((listing) => listing.lat).filter(Number.isFinite);
  const lngs = listings.map((listing) => listing.lng).filter(Number.isFinite);
  if (!lats.length || !lngs.length) {
    return TARGET_BOUNDS;
  }
  const padding = 0.012;
  return [
    [Math.min(...lats) - padding, Math.min(...lngs) - padding],
    [Math.max(...lats) + padding, Math.max(...lngs) + padding],
  ];
}

function pinTone(listing) {
  if ((listing.score || 0) >= 82) {
    return "strong";
  }
  if ((listing.score || 0) >= 68) {
    return "watch";
  }
  if (pricePerSqft(listing) > 2200) {
    return "rich";
  }
  return "neutral";
}

function renderList() {
  if (!state.filtered.length) {
    els.listingList.innerHTML = `<div class="empty-state">Aucun listing dans ce filtre.</div>`;
    return;
  }

  els.listingList.innerHTML = state.filtered
    .map((listing) => {
      const active = listing.id === state.selectedId ? " active" : "";
      const selected = state.selectedIds.has(listing.id);
      return `
        <article class="listing-card${active}${selected ? " selected" : ""}" data-id="${escapeAttribute(listing.id)}" role="button" tabindex="0">
          <div class="listing-main">
            <div class="listing-address">${escapeHtml(listing.address)}</div>
            <div class="listing-subline">${escapeHtml(listing.neighbourhood)} | ${escapeHtml(bedBath(listing))} | ${escapeHtml(listing.propertyType || "-")}</div>
            <div class="listing-numbers">
              <span>${escapeHtml(formatMaybeMoney(listing.price))}</span>
              <span>${escapeHtml(formatMaybeMoney(pricePerSqft(listing)))} / sqft</span>
              <span>${escapeHtml(formatPercent(listing.grossYield))}</span>
            </div>
          </div>
          <div class="listing-side">
            <div class="score-pill ${scoreClass(listing.score)}">${escapeHtml(String(listing.score ?? "-"))}</div>
            <button class="select-toggle${selected ? " selected" : ""}" type="button" data-id="${escapeAttribute(listing.id)}">
              ${selected ? "Retirer" : "Select"}
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  els.listingList.querySelectorAll(".listing-card").forEach((card) => {
    card.addEventListener("click", () => selectListing(card.dataset.id, true));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectListing(card.dataset.id, true);
      }
    });
  });

  els.listingList.querySelectorAll(".select-toggle").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleListingSelection(button.dataset.id);
    });
  });
}

function renderDetails() {
  const selected = getListingById(state.selectedId);
  els.selectionStatus.textContent = selected ? selected.source : "-";

  if (!selected) {
    els.detailPane.innerHTML = `<div class="empty-state">Importe ou ajuste les filtres pour afficher une selection.</div>`;
    return;
  }

  const badgeClass = (selected.score || 0) >= 82 ? "good" : (selected.score || 0) >= 68 ? "watch" : "";
  const sourceDate = selected.capturedAt ? DATE_FORMAT.format(selected.capturedAt) : "date inconnue";
  const comparables = getComparables(selected);
  const inRanking = state.selectedIds.has(selected.id);

  els.detailPane.innerHTML = `
    <div class="detail-title">
      <h3>${escapeHtml(selected.address)}</h3>
      <span class="badge ${badgeClass}">Score ${escapeHtml(String(selected.score ?? "-"))}</span>
    </div>
    <div class="detail-price">${escapeHtml(formatMaybeMoney(selected.price))}</div>
    <div class="detail-meta">
      <span class="badge">${escapeHtml(selected.neighbourhood)}</span>
      <span class="badge">${escapeHtml(selected.postcode || "-")}</span>
      <span class="badge">${escapeHtml(bedBath(selected))}</span>
      <span class="badge">${escapeHtml(selected.tenure || "-")}</span>
    </div>
    <div class="fact-grid">
      ${fact("GBP/sqft", `${formatMaybeMoney(pricePerSqft(selected))}`)}
      ${fact("Surface", `${formatMaybeNumber(selected.sqft)} sqft`)}
      ${fact("Yield brut", formatPercent(selected.grossYield))}
      ${fact("Jours marche", formatMaybeNumber(selected.daysOnMarket))}
      ${fact("Service charge", formatMaybeMoney(selected.serviceCharge))}
      ${fact("Lease", selected.leaseYears ? `${formatMaybeNumber(selected.leaseYears)} ans` : "-")}
      ${fact("Agent", selected.agent || "-")}
      ${fact("Statut", selected.status || "-")}
      ${fact("Reference", selected.sourceId || "-")}
      ${fact("Coordonnees", `${selected.lat.toFixed(5)}, ${selected.lng.toFixed(5)}`)}
    </div>
    <div class="detail-actions">
      <a href="${escapeAttribute(selected.url || "#")}" target="_blank" rel="noreferrer">Source</a>
      <button id="detailSelectButton" type="button" class="${inRanking ? "selected" : ""}">
        ${inRanking ? "Retirer du ranking" : "Ajouter au ranking"}
      </button>
    </div>
    <p class="notes">${escapeHtml(selected.notes || `${selected.agent || "Agent inconnu"} | capture ${sourceDate}`)}</p>
    <div class="comparable-list">
      ${comparables.map(renderComparable).join("")}
    </div>
  `;

  els.detailPane.querySelectorAll(".comparable-row").forEach((row) => {
    row.addEventListener("click", () => selectListing(row.dataset.id, true));
  });
  els.detailPane.querySelector("#detailSelectButton")?.addEventListener("click", () => {
    toggleListingSelection(selected.id);
  });
}

function fact(label, value) {
  return `
    <div class="fact">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "-")}</strong>
    </div>
  `;
}

function getComparables(selected) {
  return state.filtered
    .filter((listing) => listing.id !== selected.id)
    .map((listing) => {
      const sameArea = listing.neighbourhood === selected.neighbourhood ? 0 : 1;
      const bedroomGap = Math.abs((listing.bedrooms || 0) - (selected.bedrooms || 0));
      const typeGap = listing.propertyType === selected.propertyType ? 0 : 1;
      const psfGap = Math.abs(pricePerSqft(listing) - pricePerSqft(selected)) / 1000;
      return { listing, distance: sameArea * 2 + bedroomGap + typeGap + psfGap };
    })
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 3)
    .map((item) => item.listing);
}

function renderComparable(listing) {
  return `
    <button class="comparable-row" type="button" data-id="${escapeAttribute(listing.id)}">
      <strong>${escapeHtml(listing.address)}</strong>
      <span>${escapeHtml(formatMaybeMoney(pricePerSqft(listing)))} / sqft</span>
    </button>
  `;
}

function selectListing(id, recenter = false) {
  state.selectedId = id;
  const selected = getListingById(id);
  renderList();
  renderDetails();
  renderRanking();
  if (recenter && selected && map) {
    map.setView([selected.lat, selected.lng], Math.max(map.getZoom(), 18), { animate: true });
    window.setTimeout(() => markerRefs.get(id)?.openPopup(), 180);
  }
}

function toggleListingSelection(id) {
  if (!id) {
    return;
  }
  if (state.selectedIds.has(id)) {
    state.selectedIds.delete(id);
  } else {
    state.selectedIds.add(id);
  }
  renderSelectionViews();
}

function selectVisibleListings() {
  state.filtered.forEach((listing) => state.selectedIds.add(listing.id));
  renderSelectionViews();
  showToast(`${state.filtered.length} listings visibles ajoutes au ranking.`);
}

function clearSelection() {
  state.selectedIds.clear();
  renderSelectionViews();
  showToast("Selection ranking videe.");
}

function renderSelectionViews() {
  renderList();
  renderDetails();
  renderRanking();
  renderMarkers(false);
}

function selectedListings() {
  return state.all.filter((listing) => state.selectedIds.has(listing.id));
}

function getListingById(id) {
  return state.all.find((listing) => listing.id === id) || null;
}

function renderRanking() {
  const selected = selectedListings();
  els.selectedCount.textContent = `${selected.length} selection${selected.length > 1 ? "s" : ""}`;

  if (!selected.length) {
    els.rankedList.innerHTML = `<div class="empty-state">Selectionne des biens sur la carte ou dans la liste pour construire ton ranking.</div>`;
    return;
  }

  const ranked = selected
    .map((listing) => ({
      listing,
      rankingScore: rankingScore(listing, selected),
    }))
    .sort((a, b) => b.rankingScore - a.rankingScore || a.listing.price - b.listing.price);

  els.rankedList.innerHTML = ranked
    .map(({ listing, rankingScore }, index) => `
      <button class="ranking-row${listing.id === state.selectedId ? " active" : ""}" type="button" data-id="${escapeAttribute(listing.id)}">
        <span class="rank-badge">${index + 1}</span>
        <span class="rank-main">
          <strong>${escapeHtml(listing.address)}</strong>
          <small>${escapeHtml(formatMaybeMoney(listing.price))} | ${escapeHtml(formatMaybeMoney(pricePerSqft(listing)))} / sqft | ${escapeHtml(listing.neighbourhood)}</small>
        </span>
        <span class="rank-score">${escapeHtml(String(rankingScore))}</span>
      </button>
    `)
    .join("");

  els.rankedList.querySelectorAll(".ranking-row").forEach((row) => {
    row.addEventListener("click", () => selectListing(row.dataset.id, true));
  });
}

function rankingScore(listing, universe) {
  const psfValues = universe.map(pricePerSqft).filter(Number.isFinite);
  const baselinePsf = median(psfValues);
  const listingPsf = pricePerSqft(listing);
  let score = 55;

  if (Number.isFinite(baselinePsf) && Number.isFinite(listingPsf) && baselinePsf > 0) {
    score += clamp(((baselinePsf - listingPsf) / baselinePsf) * 85, -30, 30);
  } else {
    score -= 5;
  }

  if (Number.isFinite(listing.score)) {
    score += (listing.score - 65) * 0.35;
  }
  if (Number.isFinite(listing.grossYield)) {
    score += clamp((listing.grossYield - 3) * 4, -8, 12);
  }
  if (!Number.isFinite(listing.sqft) || listing.sqft <= 0) {
    score -= 4;
  }
  if (Number.isFinite(listing.leaseYears) && listing.leaseYears > 0 && listing.leaseYears < 85) {
    score -= 6;
  }
  if (/under\s+offer|sold|reserved/i.test(listing.status || "")) {
    score -= 8;
  }

  return Math.max(0, Math.min(100, Math.round(score)));
}

async function handleImport(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  try {
    const text = await file.text();
    const rows = file.name.toLowerCase().endsWith(".json") ? parseJsonListings(text) : parseCsvListings(text);
    replaceListings(rows, file.name);
  } catch (error) {
    showToast(`Import impossible: ${error.message}`);
  } finally {
    event.target.value = "";
  }
}

function parseJsonListings(text) {
  const parsed = JSON.parse(text);
  if (Array.isArray(parsed)) {
    return parsed;
  }
  if (Array.isArray(parsed.properties)) {
    return parsed.properties;
  }
  if (Array.isArray(parsed.listings)) {
    return parsed.listings;
  }
  throw new Error("JSON attendu: array, properties[] ou listings[]");
}

function parseCsvListings(text) {
  const rows = parseCsv(text);
  if (rows.length < 2) {
    return [];
  }
  const headers = rows[0].map((header) => header.trim());
  return rows.slice(1).map((row) => {
    const item = {};
    headers.forEach((header, index) => {
      item[header] = row[index] ?? "";
    });
    return item;
  });
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i += 1;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") {
        i += 1;
      }
      row.push(cell);
      if (row.some((value) => value.trim() !== "")) {
        rows.push(row);
      }
      row = [];
      cell = "";
      continue;
    }
    cell += char;
  }

  row.push(cell);
  if (row.some((value) => value.trim() !== "")) {
    rows.push(row);
  }
  return rows;
}

function replaceListings(rows, datasetName) {
  const normalised = rows.map(normaliseListing).filter(Boolean);
  const target = normalised.filter(isLondonListing);
  const rejected = normalised.length - target.length;

  state.all = target;
  state.datasetName = `${datasetName} | ${target.length} actifs`;
  state.selectedId = target[0]?.id ?? null;
  state.selectedIds.clear();
  populateDynamicOptions();
  applyFilters();
  showToast(`${target.length} listings charges${rejected ? `, ${rejected} hors zone ignores` : ""}.`);
}

function resetDemo() {
  els.datasetLabel.textContent = "Refresh Foxtons en cours...";
  showToast("Collecte Foxtons en cours, quelques secondes.");
  loadListings(true).then((loaded) => {
    state.all = loaded.rows;
    state.datasetName = loaded.label;
    state.selectedId = state.all[0]?.id ?? null;
    state.selectedIds.clear();
    populateDynamicOptions();
    applyFilters();
    showToast("Dataset Foxtons rafraichi.");
  }).catch((error) => {
    showToast(`Refresh impossible: ${error.message}`);
  });
}

function exportFilteredCsv() {
  const headers = [
    "source",
    "sourceId",
    "address",
    "postcode",
    "neighbourhood",
    "price",
    "bedrooms",
    "bathrooms",
    "sqft",
    "lat",
    "lng",
    "propertyType",
    "tenure",
    "agent",
    "status",
    "url",
    "capturedAt",
    "daysOnMarket",
    "serviceCharge",
    "leaseYears",
    "rentEstimate",
    "grossYield",
    "score",
    "notes",
  ];
  const rows = [headers, ...state.filtered.map((listing) => headers.map((header) => serialiseCsvValue(listing[header])))];
  const csv = rows.map((row) => row.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "foxtons-chelsea-south-kensington-listings.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function serialiseCsvValue(value) {
  const raw = value instanceof Date ? value.toISOString().slice(0, 10) : value ?? "";
  const text = String(raw);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function bedBath(listing) {
  const beds = Number.isFinite(listing.bedrooms) ? `${listing.bedrooms} bed` : "- bed";
  const baths = Number.isFinite(listing.bathrooms) ? `${listing.bathrooms} bath` : "- bath";
  return `${beds} | ${baths}`;
}

function pricePerSqft(listing) {
  if (!Number.isFinite(listing.price) || !Number.isFinite(listing.sqft) || listing.sqft <= 0) {
    return Number.POSITIVE_INFINITY;
  }
  return listing.price / listing.sqft;
}

function median(values) {
  const clean = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!clean.length) {
    return null;
  }
  const middle = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[middle] : (clean[middle - 1] + clean[middle]) / 2;
}

function compactMoney(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 1_000_000) {
    return `GBP ${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  }
  if (Math.abs(value) >= 1_000) {
    return `GBP ${Math.round(value / 1_000)}k`;
  }
  return `GBP ${WHOLE.format(value)}`;
}

function compactPriceLabel(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${Math.round(value / 1_000)}k`;
  }
  return WHOLE.format(value);
}

function formatMaybeMoney(value) {
  return Number.isFinite(value) ? GBP.format(value) : "-";
}

function formatMaybeNumber(value) {
  return Number.isFinite(value) ? WHOLE.format(value) : "-";
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${value.toFixed(2)}%` : "-";
}

function scoreClass(score) {
  if ((score || 0) >= 82) {
    return "strong";
  }
  if ((score || 0) >= 68) {
    return "watch";
  }
  return "rich";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.classList.add("show");
  toastTimer = window.setTimeout(() => els.toast.classList.remove("show"), 3200);
}

window.selectListing = selectListing;
window.toggleListingSelection = toggleListingSelection;
document.addEventListener("DOMContentLoaded", init);
