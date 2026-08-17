/* Purchase order list: filters + table. */

const filters = { company_id: '', status: '', supplier_id: '', q: '', date_from: '', date_to: '' };

const rowsEl = document.getElementById('rows');
const errorEl = document.getElementById('error');

async function load() {
  rowsEl.innerHTML = '<tr><td colspan="8" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listPurchaseOrders(filters);
    errorEl.classList.add('hidden');

    if (!list.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="8" class="empty">No purchase orders match these filters.</td></tr>';
      return;
    }

    rowsEl.innerHTML = list
      .map(
        (row) => `
        <tr class="clickable ${row.can_edit ? '' : 'not-mine'}" data-id="${row.id}"
            title="${row.can_edit ? '' : 'Created by someone else - read only'}">
          <td class="mono"><strong>${esc(row.po_no)}</strong></td>
          <td>${fmtDate(row.order_date)}</td>
          <td>${esc(row.supplier_name || '')}<br><span class="hint">${esc(row.supplier_code || '')}</span></td>
          <td class="mono hint">${esc(row.so_no || '-')}</td>
          <td class="center">${statusBadge(row.status)}</td>
          <td>${fmtDate(row.expected_date)}</td>
          <td class="right mono">${esc(row.currency)} ${fmtMoney(row.total, row.currency)}</td>
          <td class="hint">${esc(row.created_by_name || '-')}</td>
        </tr>`
      )
      .join('');
  } catch (err) {
    rowsEl.innerHTML = '<tr><td colspan="8" class="empty">Could not load purchase orders.</td></tr>';
    errorEl.textContent = err.message;
    errorEl.classList.remove('hidden');
  }
}

rowsEl.addEventListener('click', (event) => {
  const tr = event.target.closest('tr[data-id]');
  if (tr) window.location.href = `purchase-order-form.html?id=${tr.dataset.id}`;
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

const supplierInput = document.getElementById('fSupplier');
attachAutocomplete({
  input: supplierInput,
  resultsEl: document.getElementById('fSupplierResults'),
  search: (term) => api.listSuppliers(term),
  render: (s) => `${esc(s.name)}<span class="code">${esc(s.code)}</span>`,
  onPick: (s) => {
    supplierInput.value = s.name;
    filters.supplier_id = s.id;
    load();
  },
});
supplierInput.addEventListener('input', () => {
  if (!supplierInput.value.trim() && filters.supplier_id) {
    filters.supplier_id = '';
    load();
  }
});

document.getElementById('clearBtn').addEventListener('click', () => {
  ['fStatus', 'fSupplier', 'fNo', 'fFrom', 'fTo'].forEach((id) => {
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
  renderTopbar('purchase-orders', user);
  load();
})();
