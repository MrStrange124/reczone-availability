const DEFAULT_COMPLEX = 2;
const DEFAULT_SPORT = "badminton";
const BOOK_BASE = "https://reczone.mcgm.gov.in/sports-complex/book-your-sport";

const complexSelect = document.querySelector("#complex");
const facilitySelect = document.querySelector("#facility");
const startInput = document.querySelector("#start");
const endInput = document.querySelector("#end");
const courtList = document.querySelector("#court-list");
const courtSummary = document.querySelector("#courtpick-summary");
const courtAll = document.querySelector("#court-all");
const form = document.querySelector("#filters");
const goButton = document.querySelector("#go");
const banner = document.querySelector("#banner");
const venueLine = document.querySelector("#venue");
const thesisLine = document.querySelector("#thesis");
const tapeBlock = document.querySelector("#tape-block");
const tapeTable = document.querySelector("#tape");
const windowsBlock = document.querySelector("#windows-block");
const windowsList = document.querySelector("#windows");
const windowsNote = document.querySelector("#windows-note");
const bookLink = document.querySelector("#book-link");

/* ---------- small helpers ---------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function txt(value) {
  return document.createTextNode(value);
}

function showBanner(message, isError = false) {
  banner.hidden = !message;
  banner.textContent = message || "";
  banner.classList.toggle("error", Boolean(isError));
}

async function api(path) {
  const response = await fetch(path);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error((body && body.detail) || text || `RecZone proxy failed (${response.status})`);
  }
  return body;
}

function option(value, label, selected = false) {
  const node = el("option", null, label);
  node.value = String(value);
  node.selected = selected;
  return node;
}

/* ---------- time formatting ----------
   RecZone hands back slots like "01:00 PM - 02:00 PM". People say "1 – 2 PM". */

function clockParts(stamp) {
  const [clock, meridiem] = stamp.trim().split(/\s+/);
  const [hour, minute] = clock.split(":");
  return { hour: String(Number(hour)), minute, meridiem };
}

function edge(part) {
  return part.minute === "00" ? part.hour : `${part.hour}:${part.minute}`;
}

function slotRange(slot) {
  const [from, to] = slot.split(" - ");
  const a = clockParts(from);
  const b = clockParts(to);
  return a.meridiem === b.meridiem
    ? `${edge(a)} – ${edge(b)} ${b.meridiem}`
    : `${edge(a)} ${a.meridiem} – ${edge(b)} ${b.meridiem}`;
}

function slotEnd(slot) {
  const b = clockParts(slot.split(" - ")[1]);
  return `${edge(b)} ${b.meridiem}`;
}

function railLabel(slot) {
  const a = clockParts(slot.split(" - ")[0]);
  const suffix = a.meridiem === "AM" ? "a" : "p";
  return a.minute === "00" ? `${a.hour}${suffix}` : `${a.hour}:${a.minute}${suffix}`;
}

function minutesOf(stamp) {
  const { hour, minute, meridiem } = clockParts(stamp);
  const base = Number(hour) % 12;
  return (meridiem === "PM" ? base + 12 : base) * 60 + Number(minute);
}

function dayLabel(meta) {
  return `${meta.dayOfWeek} ${meta.day}`;
}

/* All seven wooden courts are the same 968 sq ft. The number is the only part
   worth showing. */
function courtChip(name = "") {
  const trailing = String(name).match(/(\d+)\s*$/);
  return trailing ? trailing[1] : String(name).replace(/^Wooden\s+/i, "").slice(0, 3);
}

function rupees(costs) {
  const unique = [...new Set(costs.filter((cost) => cost != null))].sort((a, b) => a - b);
  if (!unique.length) return null;
  return unique.length === 1 ? `₹${unique[0]}` : `₹${unique[0]}–${unique.at(-1)}`;
}

/* ---------- turning the grid into a week of hours ---------- */

function analyse(grid) {
  const courts = grid.courts || [];
  const hours = grid.hours || [];

  const days = (grid.date_meta || []).map((meta) => {
    const slotsByCourt = courts.map((court) => {
      const cells = court.days[meta.date] || [];
      return {
        court,
        closed: cells.some((cell) => cell.status === "closed"),
        bySlot: new Map(cells.filter((cell) => cell.slot).map((cell) => [cell.slot, cell])),
      };
    });

    const cells = hours.map((hour, index) => {
      const openCourts = [];
      const costs = [];
      const taken = { booked: 0, busy: 0, reserved: 0 };
      let total = 0;

      for (const entry of slotsByCourt) {
        if (entry.closed) continue;
        const cell = entry.bySlot.get(hour);
        if (!cell) continue;
        total += 1;
        if (cell.status === "free") {
          openCourts.push(entry.court);
          costs.push(cell.cost);
        } else {
          taken[cell.status] = (taken[cell.status] || 0) + 1;
        }
      }

      return { hour, index, total, open: openCourts.length, openCourts, costs, taken };
    });

    return {
      ...meta,
      cells,
      open: cells.reduce((sum, cell) => sum + cell.open, 0),
    };
  });

  const openings = [];
  for (const day of days) {
    for (const cell of day.cells) {
      if (cell.open) openings.push({ day, cell });
    }
  }

  return { days, hours, courts, openings };
}

/* ---------- the finding, in words ---------- */

/* Returns nodes rather than markup: day names and slot labels come straight from
   RecZone, and building this as an HTML string would put a third party's strings
   through innerHTML. */
function thesisFor(model) {
  const { days, hours, openings } = model;
  if (!days.length) return [txt("RecZone is not selling any dates in this range.")];

  const totalOpen = openings.reduce((sum, item) => sum + item.cell.open, 0);
  const span = days.length === 1 ? "this day" : `these ${days.length} days`;
  if (!totalOpen) {
    return [txt(`Nothing is open across ${span}. Every hour on the sheet is already taken.`)];
  }

  const daysOpen = days.filter((day) => day.open).length;
  const nodes = [
    el("span", "lit", `${totalOpen} slots`),
    txt(` open across ${daysOpen} of ${days.length} days.`),
  ];

  const firstOpen = days.findIndex((day) => day.open);
  if (firstOpen > 0) nodes.push(txt(` Nothing before ${dayLabel(days[firstOpen])}.`));

  const lastHour = Math.max(...openings.map((item) => item.cell.index));
  if (lastHour < hours.length - 1) {
    nodes.push(txt(` Nothing after ${slotEnd(hours[lastHour])}.`));
  }

  return nodes;
}

/* ---------- the tape ---------- */

/* Local, not toISOString(): RecZone dates are Mumbai dates, and before 5:30am IST
   the UTC date is still yesterday. */
function todayStamp() {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

function nowHourIndex(model) {
  if (!model.days.some((day) => day.date === todayStamp())) return -1;
  const today = new Date();
  const minutes = today.getHours() * 60 + today.getMinutes();
  return model.hours.findIndex((hour) => {
    const [from, to] = hour.split(" - ");
    return minutes >= minutesOf(from) && minutes < minutesOf(to);
  });
}

function renderTape(model) {
  const currentHour = nowHourIndex(model);
  const head = el("thead");
  const headRow = el("tr");
  headRow.append(el("th", "corner"));

  model.hours.forEach((hour, index) => {
    const cell = el("th", "rail", railLabel(hour));
    cell.scope = "col";
    if (index % 3 !== 0) cell.classList.add("rail-minor");
    if (index === currentHour) cell.classList.add("now");
    headRow.append(cell);
  });
  head.append(headRow);

  const body = el("tbody");
  for (const day of model.days) {
    const row = el("tr");
    if (day.date === model.today) row.classList.add("today");

    const label = el("th", "day");
    label.scope = "row";
    label.append(el("span", "dow", day.dayOfWeek), el("span", "dnum", String(day.day)));
    row.append(label);

    for (const cell of day.cells) {
      const td = el("td");
      const block = el("span", "cell");

      if (cell.total === 0) {
        block.classList.add("cell-none");
      } else if (cell.open) {
        const fill = el("span", "fill");
        fill.style.setProperty("--h", `${Math.round((cell.open / cell.total) * 100)}%`);
        fill.style.setProperty("--i", String(cell.index));
        block.append(fill);
      }

      const summary = describe(day, cell);
      td.title = summary;
      td.append(el("span", "sr", summary), block);
      row.append(td);
    }
    body.append(row);
  }

  tapeTable.replaceChildren(head, body);
  tapeBlock.hidden = false;
}

/* The tape shows open against taken; this is where the three upstream flavours of
   "taken" stay reachable, for the one person who wants to know why. */
const TAKEN_WORDS = { booked: "booked", busy: "held", reserved: "reserved" };

function describe(day, cell) {
  const when = `${dayLabel(day)}, ${slotRange(cell.hour)}`;
  if (cell.total === 0) return `${when}: not on sale`;

  const taken = Object.entries(cell.taken)
    .filter(([, count]) => count)
    .map(([status, count]) => `${count} ${TAKEN_WORDS[status] || status}`)
    .join(", ");

  if (!cell.open) return `${when}: all ${cell.total} taken — ${taken}`;

  const price = rupees(cell.costs);
  const lead = `${cell.open} of ${cell.total} open${price ? ` at ${price}` : ""}`;
  return `${when}: ${lead}${taken ? ` — ${taken}` : ""}`;
}

/* ---------- open windows ---------- */

function renderWindows(model) {
  windowsList.replaceChildren();

  if (!model.openings.length) {
    const empty = el("p", "nothing");
    empty.append(
      el(
        "span",
        null,
        model.days.length
          ? "No court is open in this range. Try the far end of the bookable week — that is where slots survive."
          : "RecZone is not selling these dates."
      )
    );
    windowsList.append(empty);
    windowsNote.textContent = "";
    windowsBlock.hidden = false;
    return;
  }

  const cheapest = Math.min(
    ...model.openings.flatMap((item) => item.cell.costs.filter((cost) => cost != null))
  );
  const count = model.openings.length;
  windowsNote.textContent = `${count} ${count === 1 ? "window" : "windows"}${
    Number.isFinite(cheapest) ? ` · from ₹${cheapest} an hour` : ""
  }`;

  // openings is already in day-then-hour order, and a Map keeps that order.
  const byDay = new Map();
  for (const { day, cell } of model.openings) {
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(cell);
  }

  for (const [day, cells] of byDay) {
    const group = el("div", "daygroup");
    const head = el("h3", "dayhead");
    head.append(
      el("span", "d-dow", day.dayOfWeek),
      el("span", "d-num", String(day.day)),
      el("span", "d-tally", `${day.open} open`)
    );
    group.append(head);

    for (const cell of cells) {
      const row = el("article", "window");
      row.append(el("p", "w-time", slotRange(cell.hour)));

      const price = el("p", "w-price");
      const amount = rupees(cell.costs);
      if (amount) price.append(document.createTextNode(amount), el("span", "per", " /hr"));
      row.append(price);

      const strip = el("ol", "w-courts");
      const openIds = new Set(cell.openCourts.map((court) => court.id));
      for (const court of model.courts) {
        const chip = el("li", openIds.has(court.id) ? "c on" : "c", courtChip(court.name));
        chip.title = `${court.name} — ${openIds.has(court.id) ? "open" : "taken"}`;
        strip.append(chip);
      }
      strip.append(el("li", "c-label", `${cell.open} of ${cell.total} courts`));
      row.append(strip);
      group.append(row);
    }
    windowsList.append(group);
  }

  windowsBlock.hidden = false;
}

/* ---------- filters ---------- */

function courtBoxes() {
  return [...courtList.querySelectorAll("input[type=checkbox]")];
}

/* No boxes ticked reads as "no preference", not "no courts". */
function selectedCourtIds() {
  const boxes = courtBoxes();
  const checked = boxes.filter((box) => box.checked);
  return (checked.length ? checked : boxes).map((box) => box.value);
}

function refreshCourtSummary() {
  const boxes = courtBoxes();
  const checked = boxes.filter((box) => box.checked).length;
  const all = boxes.length;
  courtSummary.textContent =
    !all || checked === 0 || checked === all ? `All ${all} courts` : `${checked} of ${all} courts`;
}

function refreshVenueLine() {
  const complexName = complexSelect.selectedOptions[0]?.textContent || "";
  const sportName = facilitySelect.selectedOptions[0]?.textContent || "";
  venueLine.textContent = [complexName, sportName].filter(Boolean).join(" · ");
}

async function loadFacilities() {
  const payload = await api(`/api/facilities?complex_id=${complexSelect.value}`);
  const facilities = payload.data || [];
  const preferred = facilities.find((item) => item.slug === DEFAULT_SPORT) || facilities[0];
  facilitySelect.replaceChildren(
    ...facilities.map((item) => option(item.id, item.name, item.id === preferred?.id))
  );
  await loadCourtsAndDates();
}

async function loadCourtsAndDates() {
  const complexId = complexSelect.value;
  const facilityId = facilitySelect.value;
  if (!facilityId) return;

  const courtsPayload = await api(`/api/courts?complex_id=${complexId}&facility_id=${facilityId}`);
  const courts = courtsPayload.data || [];
  const first = courts[0];
  const datesPayload = first
    ? await api(`/api/dates?complex_id=${complexId}&facility_id=${facilityId}&court_id=${first.id}`)
    : { data: [] };

  courtList.replaceChildren(
    ...courts.map((court) => {
      const label = el("label");
      const input = el("input");
      input.type = "checkbox";
      input.value = court.id;
      input.checked = true;
      label.append(input, document.createTextNode(court.name.replace(/^Wooden\s+/i, "")));
      return label;
    })
  );
  refreshCourtSummary();
  refreshVenueLine();

  const bookable = (datesPayload.data || []).flatMap((month) => month.dates || []);
  const earliest = bookable[0]?.date;
  const latest = bookable.at(-1)?.date;
  if (!earliest || !latest) return;

  for (const input of [startInput, endInput]) {
    input.min = earliest;
    input.max = latest;
  }
  if (!startInput.value || startInput.value < earliest || startInput.value > latest) {
    startInput.value = earliest;
  }
  if (!endInput.value || endInput.value < earliest || endInput.value > latest) {
    endInput.value = latest;
  }
}

/* ---------- the round trip ---------- */

let inFlight = 0;

async function check(event) {
  event?.preventDefault();
  const ticket = ++inFlight;

  goButton.setAttribute("aria-busy", "true");
  goButton.textContent = "Reading…";
  showBanner("Reading RecZone. One full week takes a few seconds.");

  const params = new URLSearchParams({
    complex_id: complexSelect.value,
    facility_id: facilitySelect.value,
    start: startInput.value,
    end: endInput.value,
    court_ids: selectedCourtIds().join(","),
  });

  try {
    const grid = await api(`/api/grid?${params}`);
    if (ticket !== inFlight) return;

    if (!grid.dates?.length) {
      tapeBlock.hidden = true;
      windowsBlock.hidden = true;
      thesisLine.textContent = "RecZone is not selling these dates.";
      showBanner("RecZone sells about a week ahead. Pick dates inside that window.");
      return;
    }

    const model = analyse(grid);
    model.today = todayStamp();
    thesisLine.replaceChildren(...thesisFor(model));
    renderTape(model);
    renderWindows(model);
    if (grid.book_url) bookLink.href = grid.book_url;
    showBanner("");
  } catch (error) {
    if (ticket !== inFlight) return;
    tapeBlock.hidden = true;
    windowsBlock.hidden = true;
    thesisLine.textContent = "RecZone did not answer.";
    showBanner(error.message || "RecZone did not answer.", true);
  } finally {
    if (ticket === inFlight) {
      goButton.removeAttribute("aria-busy");
      goButton.textContent = "Refresh";
    }
  }
}

function reload(loader) {
  loader()
    .then(() => check())
    .catch((error) => showBanner(error.message, true));
}

complexSelect.addEventListener("change", () => {
  bookLink.href = `${BOOK_BASE}?complex=${complexSelect.value}&type=1`;
  reload(loadFacilities);
});
facilitySelect.addEventListener("change", () => reload(loadCourtsAndDates));
courtList.addEventListener("change", refreshCourtSummary);
courtAll.addEventListener("click", () => {
  for (const box of courtBoxes()) box.checked = true;
  refreshCourtSummary();
});
form.addEventListener("submit", check);

async function boot() {
  try {
    const payload = await api("/api/complexes");
    const complexes = payload.data || [];
    if (!complexes.length) {
      thesisLine.textContent = "RecZone returned no venues.";
      showBanner("RecZone returned no venues. Try again shortly.", true);
      return;
    }
    const preferred = complexes.find((item) => item.id === DEFAULT_COMPLEX) || complexes[0];
    complexSelect.replaceChildren(
      ...complexes.map((item) => option(item.id, item.name, item.id === preferred?.id))
    );
    await loadFacilities();
    await check();
  } catch (error) {
    thesisLine.textContent = "Could not reach RecZone.";
    showBanner(error.message || "Could not reach the RecZone proxy.", true);
  }
}

boot();
