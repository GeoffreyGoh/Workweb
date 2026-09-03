/* Receipts list. New payments are recorded from the invoice they
   belong to, so this page is a register plus PDF reprints. */

const filters = { company_id: '', q: '', date_from: '', date_to: '' };

const rowsEl = document.getElementById('rows');
const errorEl = document.getElementById('error');
const successEl = document.getElementById('success');

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
  successEl.classList.add('hidden');
}
function showSuccess(message) {
  successEl.textContent = message;
  successEl.classList.remove('hidden');
  errorEl.classList.add('hidden');
}

async function load() {
  rowsEl.innerHTML = '<tr><td colspan="9" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listReceipts(filters);
    errorEl.classList.add('hidden');

    if (!list.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="9" class="empty">No receipts yet. Record a payment from a confirmed invoice.</td></tr>';
      document.getElementById('totalNote').textContent = '';
      return;
    }

    const total = list.reduce((sum, r) => sum + Number(r.amount), 0);
    document.getElementById('totalNote').textContent =
      `${list.length} receipt(s) · IDR ${fmtMoney(total)}`;

    rowsEl.innerHTML = list
      .map(
        (r) => `
        <tr>
          <td class="mono"><strong>${esc(r.receipt_no)}</strong></td>
          <td>${fmtDate(r.receipt_date)}</td>
          <td class="mono"><a href="sales-order-form.html?id=${r.sales_order_id}">${esc(r.so_no || '-')}</a></td>
          <td>${esc(r.customer_name || '-')}</td>
          <td>${esc(r.payment_method)}</td>
          <td class="hint">${esc(r.reference || '-')}</td>
          <td class="right mono">${fmtMoney(r.amount)}</td>
          <td class="hint">${esc(r.created_by_name || '-')}</td>
          <td class="right">
            <button class="btn small" data-pdf="${r.id}" type="button">PDF</button>
            ${r.can_edit ? `<button class="btn small danger" data-void="${r.id}" type="button">Void</button>` : ''}
          </td>
        </tr>`
      )
      .join('');
  } catch (err) {
    rowsEl.innerHTML = '<tr><td colspan="9" class="empty">Could not load receipts.</td></tr>';
    showError(err.message);
  }
}

rowsEl.addEventListener('click', async (event) => {
  const pdfBtn = event.target.closest('[data-pdf]');
  const voidBtn = event.target.closest('[data-void]');
  if (!pdfBtn && !voidBtn) return;

  try {
    if (pdfBtn) {
      await openPdf('receipt', pdfBtn.dataset.pdf);
    } else {
      if (!confirm('Void this receipt? The payment will no longer count.')) return;
      await api.voidReceipt(voidBtn.dataset.void);
      showSuccess('Receipt voided.');
      load();
    }
  } catch (err) {
    showError(err.message);
  }
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
  ['fNo', 'fFrom', 'fTo'].forEach((id) => (document.getElementById(id).value = ''));
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
  renderTopbar('receipts', user);
  load();
})();
