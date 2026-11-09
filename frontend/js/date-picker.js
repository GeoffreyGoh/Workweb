/* =====================================================================
   DD/MM/YYYY date picker, dropped in to replace every native
   <input type="date"> on a page.

   WHY: a native date input's displayed text (and its built-in calendar
   popup) follows the OS/browser locale - on a US-locale Windows machine
   that's MM/DD/YYYY, which read wrong to Geoffrey next to every other
   date in this app (always day/month/year - see pdf.py's fmt_date and
   api.js's fmtDate). There is no HTML/CSS way to force a native date
   input's own display format - the browser owns that rendering, not us
   - so the only real fix is to stop using the native widget's visible
   text and build our own always-DD/MM/YYYY one.

   HOW: each native <input type="date" id="x"> is swapped for a text
   input showing "08/11/2026" plus a small calendar-icon button that
   opens a lightweight grid picker. The ORIGINAL input is kept in the
   DOM (hidden) as the single source of truth - its .value stays a
   real ISO yyyy-mm-dd string throughout, exactly as every existing
   page's JS already reads/writes it via el('x').value. This means
   NOT ONE LINE of existing form code (quotation-form.js, the filter
   bars, reports.js, etc.) needs to change - they keep calling
   .value on the same id and keep getting ISO strings back, same as
   a native date input always returned. Only the pixels change.

   Call initDatePickers() once, after the page's own HTML exists (at
   the bottom of the page's <script> block, same place renderTopbar()
   is already called) - it finds and converts every type="date" input
   automatically, so no per-page wiring is needed as new date fields
   get added later.
   ===================================================================== */

/** "2026-11-08" -> "08/11/2026". Blank/invalid input returns ''. */
function isoToDisplay(iso) {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return '';
  return `${m[3]}/${m[2]}/${m[1]}`;
}

/** "08/11/2026" -> "2026-11-08". Returns '' if not a complete, valid date. */
function displayToIso(display) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((display || '').trim());
  if (!m) return '';
  const day = Number(m[1]);
  const month = Number(m[2]);
  const year = Number(m[3]);
  // New Date(...) silently rolls an invalid day/month into a different
  // real date (e.g. 31/02 becomes March 3rd) rather than rejecting it -
  // checking the constructed date's own fields back out catches that.
  const d = new Date(year, month - 1, day);
  if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${year}-${pad(month)}-${pad(day)}`;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Build the calendar grid popup for one picker instance.
 * viewDate: a Date for whichever month is currently displayed (day is
 * ignored - only year/month matter for the grid itself).
 */
function buildCalendarGrid(popup, viewDate, selectedIso, onPick) {
  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstOfMonth = new Date(year, month, 1);
  // Monday-first grid (ISO week, matches the dd/mm/yyyy convention this
  // whole picker exists for) - getDay() is 0=Sunday, shift so Monday=0.
  const startOffset = (firstOfMonth.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const pad = (n) => String(n).padStart(2, '0');
  const todayIso = todayISO();

  let cells = '';
  for (let i = 0; i < startOffset; i++) cells += '<div class="dp-cell dp-blank"></div>';
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = `${year}-${pad(month + 1)}-${pad(day)}`;
    const classes = ['dp-cell', 'dp-day'];
    if (iso === todayIso) classes.push('dp-today');
    if (iso === selectedIso) classes.push('dp-selected');
    cells += `<div class="${classes.join(' ')}" data-iso="${iso}">${day}</div>`;
  }

  popup.innerHTML = `
    <div class="dp-header">
      <button type="button" class="dp-nav dp-prev" aria-label="Previous month">&lsaquo;</button>
      <span class="dp-month-label">${MONTH_NAMES[month]} ${year}</span>
      <button type="button" class="dp-nav dp-next" aria-label="Next month">&rsaquo;</button>
    </div>
    <div class="dp-weekdays">
      <div>Mo</div><div>Tu</div><div>We</div><div>Th</div><div>Fr</div><div>Sa</div><div>Su</div>
    </div>
    <div class="dp-grid">${cells}</div>
    <div class="dp-footer">
      <button type="button" class="dp-today-btn">Today</button>
      <button type="button" class="dp-clear-btn">Clear</button>
    </div>
  `;

  popup.querySelector('.dp-prev').addEventListener('click', (e) => {
    e.stopPropagation();
    buildCalendarGrid(popup, new Date(year, month - 1, 1), selectedIso, onPick);
  });
  popup.querySelector('.dp-next').addEventListener('click', (e) => {
    e.stopPropagation();
    buildCalendarGrid(popup, new Date(year, month + 1, 1), selectedIso, onPick);
  });
  popup.querySelectorAll('.dp-day').forEach((cell) => {
    cell.addEventListener('click', (e) => {
      e.stopPropagation();
      onPick(cell.dataset.iso);
    });
  });
  popup.querySelector('.dp-today-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    onPick(todayIso);
  });
  popup.querySelector('.dp-clear-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    onPick('');
  });
}

/**
 * Replace one native <input type="date"> with the DD/MM/YYYY widget.
 * The original input is hidden but kept as the real, authoritative
 * .value every other script reads/writes - see the module doc comment.
 */
function convertDateInput(nativeInput) {
  if (nativeInput.dataset.dpConverted) return; // already done, e.g. a second init call
  nativeInput.dataset.dpConverted = '1';
  nativeInput.style.display = 'none';

  const wrapper = document.createElement('div');
  wrapper.className = 'dp-wrapper';

  const textInput = document.createElement('input');
  textInput.type = 'text';
  textInput.className = 'dp-text';
  textInput.placeholder = 'dd/mm/yyyy';
  textInput.value = isoToDisplay(nativeInput.value);
  // Carry over anything a page set directly on the date input (min/max/
  // disabled/required) so existing per-field constraints keep working.
  if (nativeInput.disabled) textInput.disabled = true;
  if (nativeInput.required) textInput.required = true;

  const iconBtn = document.createElement('button');
  iconBtn.type = 'button';
  iconBtn.className = 'dp-icon-btn';
  iconBtn.setAttribute('aria-label', 'Open calendar');
  iconBtn.textContent = '\u{1F4C5}'; // 📅 - no icon font dependency

  const popup = document.createElement('div');
  popup.className = 'dp-popup hidden';

  wrapper.appendChild(textInput);
  wrapper.appendChild(iconBtn);
  wrapper.appendChild(popup);
  nativeInput.insertAdjacentElement('afterend', wrapper);

  // Keep the visible text in sync even when some OTHER script sets
  // nativeInput.value directly (e.g. quotation-form.js's
  // el('quotationDate').value = todayISO() on a new quotation) - not
  // just when this widget's own UI (calendar click / typing) changes
  // it. Overriding the property itself, rather than only reacting to
  // 'change'/'input' events, is what makes every existing page's
  // direct .value assignment keep working with zero changes to that
  // page's own code - the crux of the drop-in-replacement design (see
  // the module doc comment up top).
  const nativeProto = Object.getPrototypeOf(nativeInput);
  const nativeValueDescriptor = Object.getOwnPropertyDescriptor(nativeProto, 'value');
  Object.defineProperty(nativeInput, 'value', {
    get() {
      return nativeValueDescriptor.get.call(nativeInput);
    },
    set(iso) {
      nativeValueDescriptor.set.call(nativeInput, iso);
      textInput.value = isoToDisplay(iso);
    },
    configurable: true,
  });

  // Fires the SAME 'change' event the native input would have fired, so
  // every existing addEventListener('change', ...) elsewhere keeps
  // working untouched - this is the crux of the drop-in-replacement
  // design (see the module doc comment).
  function commit(iso) {
    nativeInput.value = iso; // goes through the overridden setter above
    nativeInput.dispatchEvent(new Event('change', { bubbles: true }));
    nativeInput.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function openPopup() {
    const baseIso = nativeInput.value || todayISO();
    const [y, m] = baseIso.split('-').map(Number);
    buildCalendarGrid(popup, new Date(y, m - 1, 1), nativeInput.value, (iso) => {
      commit(iso);
      popup.classList.add('hidden');
    });
    popup.classList.remove('hidden');
  }

  iconBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (popup.classList.contains('hidden')) openPopup();
    else popup.classList.add('hidden');
  });

  // Typing a full dd/mm/yyyy commits it the moment it parses - no need
  // to tab out first. An incomplete or invalid date is just left as
  // typed text (not forced back to blank) until it either completes
  // into a valid date or the field loses focus.
  textInput.addEventListener('input', () => {
    const iso = displayToIso(textInput.value);
    if (iso) commit(iso);
  });
  // On blur, snap back to the last valid value's display text - stops
  // a half-typed/garbage string lingering in the box after clicking away.
  textInput.addEventListener('blur', () => {
    textInput.value = isoToDisplay(nativeInput.value);
  });

  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) popup.classList.add('hidden');
  });
}

/** Convert every native date input currently on the page. Idempotent. */
function initDatePickers() {
  document.querySelectorAll('input[type="date"]').forEach(convertDateInput);
}

// Auto-run on every page that loads this script - this is what lets every
// page pick up DD/MM/YYYY just by adding the one <script> tag, with zero
// changes to that page's own init code. Most date inputs already exist
// in the static HTML and are ready at DOMContentLoaded; a few pages build
// their filter bar or form fields dynamically after login (quotation-form,
// sales-order-form, etc.) - initDatePickers() is safely re-callable (see
// the dpConverted guard in convertDateInput), so those pages' own scripts
// can call it again themselves once their dynamic fields exist, same as
// they already call renderTopbar() once the user is confirmed logged in.
document.addEventListener('DOMContentLoaded', initDatePickers);
