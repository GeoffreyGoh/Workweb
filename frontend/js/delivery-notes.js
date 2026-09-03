/* Delivery note list. New notes are raised from the invoice they deliver. */

const filters = { company_id: '', status: '', q: '', date_from: '', date_to: '' };

const rowsEl = document.getElementById('rows');
const errorEl = document.getElementById('error');

async function load() {
  rowsEl.innerHTML = '<tr><td colspan="10" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listDeliveryNotes(filters);
    errorEl.classList.add('hidden');

    if (!list.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="10" class="empty">No delivery notes yet. Open a confirmed invoice and choose &ldquo;Create Delivery Note&rdquo;.</td></tr>';
      return;
    }

    rowsEl.innerHTML = list
      .map(
        (row) => `
        <tr class="clickable ${row.can_edit ? '' : 'not-mine'}" data-id="${row.id}"
            title="${row.can_edit ? '' : 'Created by someone else - read only'}">
          <td class="mono"><strong>${esc(row.sj_no)}</strong></td>
          <td>${fmtDate(row.delivery_date)}</td>
          <td class="mono hint">${esc(row.so_no || '-')}</td>
          <td>${esc(row.customer_name || '-')}</td>
          <td>${esc(row.deliver_to || '-')}</td>
          <td class="hint">${esc(row.vehicle_no || '-')}<br>${esc(row.driver_name || '-')}</td>
          <td class="center">${statusBadge(row.status)}</td>
          <td class="right mono">${row.line_count}</td>
          <td class="right mono">${fmtNum(row.total_qty)}</td>
          <td class="hint">${esc(row.created_by_name || '-')}</td>
        </tr>`
      )
      .join('');
  } catch (err) {
    rowsEl.innerHTML = '<tr><td colspan="10" class="empty">Could not load delivery notes.</td></tr>';
    errorEl.textContent = err.message;
    errorEl.classList.remove('hidden');
  }
}

rowsEl.addEventListener('click', (event) => {
  const tr = event.target.closest('tr[data-id]');
  if (tr) window.location.href = `delivery-note-form.html?id=${tr.dataset.id}`;
});

document.getElementById('fStatus').addEventListener('change', (e) => {
  filters.status = e.target.value;
  load();
});

const debouncedLoad = debounce(load, 350);
document.getElementById('fNo').addEventListener('input', (e) => {
  filters.q = e.target.value.trim();
  debouncedLoad();
});
document.getElementById('fFrom').addEventListener('change', (e) => {
  filters.date_from = e.target.value;
  load();
});
document.getElementById('fTo').addEventListener('change', (e) => {
  filters.date_to = e.target.value;
  load();
});
document.getElementById('clearBtn').addEventListener('click', () => {
  ['fStatus', 'fNo', 'fFrom', 'fTo'].forEach((id) => {
    document.getElementById(id).value = '';
  });
  document.getElementById('fCompany').value = '';
  Object.keys(filters).forEach((k) => (filters[k] = ''));
  load();
});

document.getElementById('fCompany').addEventListener('change', (e) => {
  filters.company_id = e.target.value;
  load();
});

(async () => {
  const user = await requireLogin();
  if (!user) return;
  await loadCompanyOptions(document.getElementById('fCompany'),
                           { allLabel: t('common.allCompanies') });
  renderTopbar('delivery-notes', user);
  load();
})();
