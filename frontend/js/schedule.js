/* =====================================================================
   Delivery schedule - the run sheet for Surat Jalan.

   Grouped by day rather than listed flat, because the question the office
   actually asks is "what goes out on Thursday, and on which van".
   ===================================================================== */

const filters = { date_from: '', date_to: '', driver: '', company_id: '' };

const boardEl = document.getElementById('board');
const errorEl = document.getElementById('error');

const SLOT_KEY = {
  morning: 'sj.morning',
  afternoon: 'sj.afternoon',
  evening: 'sj.evening',
};

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function dayHeading(day) {
  const when = new Date(`${day.delivery_date}T00:00:00`);
  const weekday = when.toLocaleDateString(Lang.current === 'id' ? 'id-ID' : 'en-GB', {
    weekday: 'long',
  });
  const chips = [];
  if (day.is_today) chips.push(`<span class="badge status-issued">${esc(t('schedule.today'))}</span>`);
  if (day.is_overdue) chips.push(`<span class="badge status-cancelled">${esc(t('schedule.overdue'))}</span>`);
  return `
    <header>
      <strong>${esc(weekday)}, ${fmtDate(day.delivery_date)}</strong>
      ${chips.join(' ')}
      <div class="spacer"></div>
      <span class="hint">${day.stop_count} ${esc(t('schedule.stops'))} &middot;
        ${fmtNum(day.total_qty)} ${esc(t('common.qty').toLowerCase())}</span>
    </header>`;
}

function stopRow(stop) {
  const slot = stop.time_slot
    ? `<span class="slot slot-${esc(stop.time_slot)}">${esc(t(SLOT_KEY[stop.time_slot], stop.time_slot))}</span>`
    : '<span class="hint">&mdash;</span>';
  return `
    <tr class="clickable" data-id="${stop.id}">
      <td>${slot}</td>
      <td class="mono"><strong>${esc(stop.sj_no)}</strong></td>
      <td class="mono hint">${esc(stop.so_no || '-')}</td>
      <td>${esc(stop.customer_name || '-')}<br>
          <span class="hint">${esc(stop.deliver_to || '')}</span></td>
      <td class="hint">${esc(stop.deliver_address || '-')}</td>
      <td class="hint">${esc(stop.vehicle_no || '-')}<br>${esc(stop.driver_name || '-')}</td>
      <td class="center">${statusBadge(stop.status)}</td>
      <td class="right mono">${fmtNum(stop.total_qty)}</td>
      <td class="right"><button class="btn small" data-pdf="${stop.id}" type="button">PDF</button></td>
    </tr>`;
}

async function load() {
  boardEl.innerHTML = `<div class="card"><div class="body"><div class="empty">${esc(t('common.loading'))}</div></div></div>`;
  try {
    const board = await api.deliverySchedule(filters);
    errorEl.classList.add('hidden');

    boardEl.innerHTML = board.days.length
      ? board.days
          .map(
            (day) => `
        <div class="card day-card ${day.is_today ? 'today' : ''} ${day.is_overdue ? 'overdue' : ''}">
          ${dayHeading(day)}
          <div class="table-wrap">
            <table class="data">
              <thead>
                <tr>
                  <th style="width:90px">${esc(t('sj.timeSlot'))}</th>
                  <th>${esc(t('sj.no'))}</th>
                  <th>${esc(t('so.no'))}</th>
                  <th>${esc(t('common.customer'))}</th>
                  <th>${esc(t('quotation.deliverAddress'))}</th>
                  <th>${esc(t('sj.vehicle'))}</th>
                  <th class="center">${esc(t('common.status'))}</th>
                  <th class="right">${esc(t('common.qty'))}</th>
                  <th style="width:70px"></th>
                </tr>
              </thead>
              <tbody>${day.stops.map(stopRow).join('')}</tbody>
            </table>
          </div>
        </div>`
          )
          .join('')
      : `<div class="card"><div class="body"><div class="empty">${esc(t('schedule.empty'))}</div></div></div>`;

    const card = document.getElementById('unscheduledCard');
    if (board.unscheduled.length) {
      card.style.display = '';
      document.getElementById('unscheduledRows').innerHTML = board.unscheduled
        .map(
          (stop) => `
        <tr>
          <td class="mono"><strong>${esc(stop.so_no)}</strong></td>
          <td>${esc(stop.customer_name || '-')}</td>
          <td class="hint">${esc(stop.deliver_to || '-')}</td>
          <td class="right mono num-neg">${fmtNum(stop.total_qty)}</td>
          <td class="right">
            <button class="btn small brass" data-schedule="${esc(stop.so_no)}" type="button">
              ${esc(t('so.createSj'))}
            </button>
          </td>
        </tr>`
        )
        .join('');
    } else {
      card.style.display = 'none';
    }
  } catch (err) {
    boardEl.innerHTML = '';
    showError(err.message);
  }
}

boardEl.addEventListener('click', async (event) => {
  const pdf = event.target.closest('[data-pdf]');
  if (pdf) {
    event.stopPropagation();
    try {
      await openPdf('deliveryNote', pdf.dataset.pdf);
    } catch (err) {
      showError(err.message);
    }
    return;
  }
  const row = event.target.closest('tr[data-id]');
  if (row && row.dataset.id !== '0') {
    window.location.href = `delivery-note-form.html?id=${row.dataset.id}`;
  }
});

document.getElementById('unscheduledRows').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-schedule]');
  if (!button) return;
  // Find the order by its number, then jump into a new Surat Jalan for it.
  try {
    const orders = await api.listSalesOrders({ q: button.dataset.schedule, limit: 1 });
    if (orders.length) {
      window.location.href = `delivery-note-form.html?sales_order_id=${orders[0].id}`;
    }
  } catch (err) {
    showError(err.message);
  }
});

document.getElementById('applyBtn').addEventListener('click', () => {
  filters.date_from = document.getElementById('fFrom').value;
  filters.date_to = document.getElementById('fTo').value;
  filters.driver = document.getElementById('fDriver').value.trim();
  filters.company_id = document.getElementById('fCompany').value;
  load();
});

document.addEventListener('languagechange', load);

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('schedule', user);
  await loadCompanyOptions(document.getElementById('fCompany'),
                           { allLabel: t('common.allCompanies') });
  load();
})();
