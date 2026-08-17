/* Quotation list: filters + table. */

const filters = { company_id: '',
  status: '',
  customer_id: '',
  q: '',
  date_from: '',
  date_to: '',
};

const rowsEl = document.getElementById('rows');
const errorEl = document.getElementById('error');

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

async function load() {
  rowsEl.innerHTML = '<tr><td colspan="9" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listQuotations(filters);
    errorEl.classList.add('hidden');

    if (!list.length) {
      rowsEl.innerHTML = '<tr><td colspan="9" class="empty">No quotations match these filters.</td></tr>';
      return;
    }

    rowsEl.innerHTML = list
      .map(
        (row) => `
        <tr class="clickable ${row.can_edit ? '' : 'not-mine'}" data-id="${row.id}"
            title="${row.can_edit ? '' : 'Created by someone else - read only'}">
          <td class="mono"><strong>${esc(row.quotation_no)}</strong></td>
          <td>${fmtDate(row.quotation_date)}</td>
          <td>${esc(row.customer_name || '')}<br><span class="hint">${esc(row.customer_code || '')}</span></td>
          <td class="center">${statusBadge(row.status)}</td>
          <td class="right mono">${fmtNum(row.total_qty)}</td>
          <td class="right mono">${esc(row.currency)} ${fmtMoney(row.total, row.currency)}</td>
          <td>${fmtDate(row.last_follow_up)}</td>
          <td class="mono hint">${esc(row.company_code || '-')}</td>
          <td class="hint">${esc(row.created_by_name || '-')}</td>
        </tr>`
      )
      .join('');
  } catch (err) {
    rowsEl.innerHTML = '<tr><td colspan="9" class="empty">Could not load quotations.</td></tr>';
    showError(err.message);
  }
}

rowsEl.addEventListener('click', (event) => {
  const tr = event.target.closest('tr[data-id]');
  if (tr) window.location.href = `quotation-form.html?id=${tr.dataset.id}`;
});

/* ------------------------------------------------------------- filters */

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

const customerInput = document.getElementById('fCustomer');

attachAutocomplete({
  input: customerInput,
  resultsEl: document.getElementById('fCustomerResults'),
  search: (term) => api.listCustomers(term),
  render: (c) => `${esc(c.name)}<span class="code">${esc(c.code)}</span>`,
  onPick: (c) => {
    customerInput.value = c.name;
    filters.customer_id = c.id;
    load();
  },
});

// Clearing the box clears the filter - the picked id is otherwise sticky.
customerInput.addEventListener('input', () => {
  if (!customerInput.value.trim() && filters.customer_id) {
    filters.customer_id = '';
    load();
  }
});

document.getElementById('clearBtn').addEventListener('click', () => {
  ['fStatus', 'fCustomer', 'fNo', 'fFrom', 'fTo'].forEach((id) => {
    document.getElementById(id).value = '';
  });
  document.getElementById('fCompany').value = '';
  Object.keys(filters).forEach((k) => (filters[k] = ''));
  load();
});

/* ---------------------------------------------------------------- boot */

document.getElementById('fCompany').addEventListener('change', (e) => {
  filters.company_id = e.target.value;
  load();
});

(async () => {
  const user = await requireLogin();
  if (!user) return;
  await loadCompanyOptions(document.getElementById('fCompany'),
                           { allLabel: t('common.allCompanies') });
  renderTopbar('quotations', user);
  load();
})();
