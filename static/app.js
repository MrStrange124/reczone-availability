const DEFAULT_COMPLEX = 2;
const DEFAULT_SPORT = "badminton";

const complexSelect = document.querySelector("#complex");
const facilitySelect = document.querySelector("#facility");
const startInput = document.querySelector("#start");
const endInput = document.querySelector("#end");
const courtList = document.querySelector("#court-list");
const form = document.querySelector("#filters");
const banner = document.querySelector("#banner");
const sheetWrap = document.querySelector("#sheet-wrap");
const tally = document.querySelector("#tally");
const bookLink = document.querySelector("#book-link");

let bookableDates = [];

function showBanner(message, isError = false) {
  banner.hidden = !message;
  banner.textContent = message;
  banner.classList.toggle("error", isError);
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
    const detail = body && body.detail;
    throw new Error(detail || text || `RecZone proxy failed (${response.status})`);
  }
  return body;
}

function option(value, label, selected = false) {
  const el = document.createElement("option");
  el.value = String(value);
  el.textContent = label;
  el.selected = selected;
  return el;
}

function compactHour(slot) {
  const start = slot.split(" - ")[0];
  const [clock, meridiem] = start.split(" ");
  const [h, m] = clock.split(":");
  const hour = String(Number(h));
  const suffix = meridiem === "AM" ? "a" : "p";
  return m === "00" ? `${hour}${suffix}` : `${hour}:${m}${suffix}`;
}

function selectedCourtIds() {
  const boxes = [...courtList.querySelectorAll("input[type=checkbox]")];
  const checked = boxes.filter((box) => box.checked).map((box) => box.value);
  return checked.length ? checked : boxes.map((box) => box.value);
}

function flattenDates(months) {
  return (months || []).flatMap((month) => month.dates || []);
}

async function loadFacilities() {
  const complexId = complexSelect.value;
  const payload = await api(`/api/facilities?complex_id=${complexId}`);
  const facilities = payload.data || [];
  facilitySelect.replaceChildren();
  const preferred =
    facilities.find((item) => item.slug === DEFAULT_SPORT) || facilities[0];
  for (const item of facilities) {
    facilitySelect.append(option(item.id, item.name, item.id === preferred?.id));
  }
  await loadCourtsAndDates();
}

async function loadCourtsAndDates() {
  const complexId = complexSelect.value;
  const facilityId = facilitySelect.value;
  if (!facilityId) return;
  const courtsPayload = await api(
    `/api/courts?complex_id=${complexId}&facility_id=${facilityId}`
  );
  const firstCourt = (courtsPayload.data || [])[0];
  const datesPayload = firstCourt
    ? await api(
        `/api/dates?complex_id=${complexId}&facility_id=${facilityId}&court_id=${firstCourt.id}`
      )
    : { data: [] };

  courtList.replaceChildren();
  for (const court of courtsPayload.data || []) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = court.id;
    input.checked = true;
    label.append(input, document.createTextNode(court.name));
    courtList.append(label);
  }

  bookableDates = flattenDates(datesPayload.data);
  const first = bookableDates[0]?.date;
  const last = bookableDates.at(-1)?.date;
  if (first && last) {
    startInput.min = first;
    startInput.max = last;
    endInput.min = first;
    endInput.max = last;
    if (!startInput.value) startInput.value = first;
    if (!endInput.value) endInput.value = last;
    if (startInput.value < first || startInput.value > last) startInput.value = first;
    if (endInput.value < first || endInput.value > last) endInput.value = last;
  }
}

function renderSheet(grid) {
  const table = document.createElement("table");
  table.className = "sheet";

  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.append(document.createElement("th"));
  for (const meta of grid.date_meta) {
    const th = document.createElement("th");
    th.innerHTML = `<span class="dow">${meta.dayOfWeek}</span><span class="daynum">${meta.day}</span>`;
    headRow.append(th);
  }
  head.append(headRow);

  const body = document.createElement("tbody");
  for (const court of grid.courts) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.className = "court-name";
    name.scope = "row";
    name.textContent = court.name.replace(/^Wooden\s+/i, "");
    row.append(name);
    for (const meta of grid.date_meta) {
      const td = document.createElement("td");
      const stack = document.createElement("div");
      stack.className = "hours";
      const bySlot = Object.fromEntries(
        (court.days[meta.date] || [])
          .filter((cell) => cell.slot)
          .map((cell) => [cell.slot, cell])
      );
      const closed = (court.days[meta.date] || []).some((cell) => cell.status === "closed");
      for (const hour of grid.hours) {
        const mark = document.createElement("div");
        const cell = bySlot[hour];
        mark.className = `hour ${closed ? "closed" : cell ? cell.status : "off"}`;
        const time = document.createElement("span");
        time.textContent = compactHour(hour);
        mark.append(time);
        if (cell?.cost && cell.status === "free") {
          const cost = document.createElement("span");
          cost.className = "cost";
          cost.textContent = `₹${cell.cost}`;
          mark.append(cost);
        }
        stack.append(mark);
      }
      td.append(stack);
      row.append(td);
    }
    body.append(row);
  }

  table.append(head, body);
  sheetWrap.replaceChildren(table);
  sheetWrap.hidden = false;
}

function countFree(grid) {
  let free = 0;
  let total = 0;
  for (const court of grid.courts) {
    for (const cells of Object.values(court.days)) {
      for (const cell of cells) {
        if (!cell.slot) continue;
        total += 1;
        if (cell.status === "free") free += 1;
      }
    }
  }
  return { free, total };
}

async function checkSheet(event) {
  event?.preventDefault();
  showBanner("Pulling live marks from RecZone…");
  const params = new URLSearchParams({
    complex_id: complexSelect.value,
    facility_id: facilitySelect.value,
    start: startInput.value,
    end: endInput.value,
    court_ids: selectedCourtIds().join(","),
  });
  try {
    const grid = await api(`/api/grid?${params}`);
    if (!grid.dates?.length) {
      sheetWrap.hidden = true;
      tally.hidden = true;
      showBanner("RecZone is not selling dates in this range. Stay inside the current bookable week.");
      return;
    }
    renderSheet(grid);
    const { free, total } = countFree(grid);
    tally.hidden = false;
    tally.textContent = `${free} free / ${total} marks`;
    if (grid.book_url) bookLink.href = grid.book_url;
    showBanner("");
  } catch (error) {
    sheetWrap.hidden = true;
    showBanner(error.message || "RecZone did not answer.", true);
  }
}

complexSelect.addEventListener("change", () => {
  bookLink.href = `https://reczone.mcgm.gov.in/sports-complex/book-your-sport?complex=${complexSelect.value}&type=1`;
  loadFacilities().then(() => checkSheet()).catch((error) => showBanner(error.message, true));
});
facilitySelect.addEventListener("change", () => {
  loadCourtsAndDates().then(() => checkSheet()).catch((error) => showBanner(error.message, true));
});
form.addEventListener("submit", checkSheet);

async function boot() {
  try {
    const payload = await api("/api/complexes");
    const complexes = payload.data || [];
    complexSelect.replaceChildren();
    const preferred =
      complexes.find((item) => item.id === DEFAULT_COMPLEX) || complexes[0];
    for (const item of complexes) {
      complexSelect.append(option(item.id, item.name, item.id === preferred?.id));
    }
    if (!complexes.length) {
      showBanner("RecZone returned no complexes.", true);
      return;
    }
    await loadFacilities();
    await checkSheet();
  } catch (error) {
    showBanner(error.message || "Could not reach the local RecZone proxy.", true);
  }
}

boot();
