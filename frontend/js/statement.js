/* =====================================================================
   Rincian pembayaran customer - the customer statement.

   Answers the question a customer actually asks: what did you invoice me,
   what have I paid, and what is still open. Payments carry a running
   balance so the account can be read top to bottom.
   ===================================================================== */

const state = { customerId: null, customerName: '' };
const filters = { company_id: '', date_from: '', date_to: '', open_only: '' };

const el = (id) => document.getElementById(id);
const errorEl = el('error');

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

const money = (v) => `IDR ${fmtMoney(v)}`;

function kpi(label, value, sub, tone) {
  return `
    <div class="kpi ${tone || ''}">
      <div class="k-label">${esc(label)}</div>
      <div class="k-value">${esc(value)}</div>
      <div class="k-sub">${esc(sub || '')}</div>
    </div>`;
}

async function load() {
  if (!state.customerId) return;
  try {
    const s = await api.customerStatement(state.customerId, filters);
    errorEl.classList.add('hidden');
    el('pickHint').style.display = 'none';
    el('statement').style.display = '';

    el('kpis').innerHTML = [
      kpi(t('statement.invoiced'), money(s.invoiced), `${s.invoices.length} invoice(s)`),
      kpi(t('statement.paid'), money(s.paid), `${s.payments.length} payment(s)`),
      kpi(t('statement.outstanding'), money(s.outstanding),
          `${s.open_invoice_count} ${t('statement.openInvoices').toLowerCase()}`,
          Number(s.outstanding) > 0 ? 'bad' : 'good'),
      kpi(t('common.customer'), s.customer_name, s.customer_code || ''),
    ].join('');

    el('invoiceNote').textContent = `${fmtDate(s.date_from)} \u2014 ${fmtDate(s.date_to)}`;

    el('invoiceRows').innerHTML = s.invoices.length
      ? s.invoices.map((inv) => {
          const owing = Number(inv.balance) > 0 && !inv.is_closed;
          const receivable = inv.is_closed
            ? `<span class="badge status-completed">${esc(t('ar.settled'))}` +
              `</span> <span class="hint">${fmtDate(inv.receivable_closed_at)}</span>`
            : owing
              ? `<span class="hint num-neg">${esc(t('ar.open'))}</span>`
              : `<span class="hint">&mdash;</span>`;
          return `
        <tr class="clickable" data-id="${inv.id}">
          <td class="mono"><strong>${esc(inv.so_no)}</strong></td>
          <td>${fmtDate(inv.order_date)}</td>
          <td class="mono hint">${esc(inv.company_code || '-')}</td>
          <td class="center">${statusBadge(inv.status)}</td>
          <td class="right mono">${fmtMoney(inv.total)}</td>
          <td class="right mono">${fmtMoney(inv.paid)}</td>
          <td class="right mono ${owing ? 'num-neg' : 'num-pos'}">${fmtMoney(inv.balance)}</td>
          <td>${receivable}</td>
        </tr>`;
        }).join('')
      : `<tr><td colspan="8" class="empty">${esc(t('common.none'))}</td></tr>`;

    el('paymentRows').innerHTML = s.payments.length
      ? s.payments.map((p) => `
        <tr>
          <td>${fmtDate(p.receipt_date)}</td>
          <td class="mono"><strong>${esc(p.receipt_no)}</strong></td>
          <td class="mono hint">
            <a href="sales-order-form.html?id=${p.sales_order_id}">${esc(p.so_no || '-')}</a>
          </td>
          <td>${esc(p.payment_method)}</td>
          <td class="hint">${esc(p.reference || '-')}</td>
          <td class="right mono">${fmtMoney(p.amount)}</td>
          <td class="right mono">${fmtMoney(p.running_balance)}</td>
          <td class="hint">${esc(p.recorded_by || '-')}</td>
          <td class="right">
            <button class="btn small" data-pdf="${p.id}" type="button">PDF</button>
          </td>
        </tr>`).join('')
      : `<tr><td colspan="9" class="empty">${esc(t('common.none'))}</td></tr>`;
  } catch (err) {
    showError(err.message);
  }
}

el('invoiceRows').addEventListener('click', (event) => {
  const row = event.target.closest('tr[data-id]');
  if (row) window.location.href = `sales-order-form.html?id=${row.dataset.id}`;
});

el('paymentRows').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-pdf]');
  if (!button) return;
  try {
    await openPdf('receipt', button.dataset.pdf);
  } catch (err) {
    showError(err.message);
  }
});

['fFrom', 'fTo'].forEach((id) =>
  el(id).addEventListener('change', () => {
    filters.date_from = el('fFrom').value;
    filters.date_to = el('fTo').value;
    load();
  })
);
el('fCompany').addEventListener('change', (e) => {
  filters.company_id = e.target.value;
  load();
});
el('fOpenOnly').addEventListener('change', (e) => {
  filters.open_only = e.target.checked ? 'true' : '';
  load();
});

document.addEventListener('languagechange', load);

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('statement', user);
  await loadCompanyOptions(el('fCompany'), { allLabel: t('common.allCompanies') });

  const input = el('fCustomer');
  attachAutocomplete({
    input,
    resultsEl: el('fCustomerResults'),
    search: (term) => api.listCustomers(term),
    render: (c) => `${esc(c.name)}<span class="code">${esc(c.code)}</span>`,
    onPick: (c) => {
      state.customerId = c.id;
      state.customerName = c.name;
      input.value = c.name;
      load();
    },
  });

  // Deep link: statement.html?customer_id=7
  const wanted = new URLSearchParams(window.location.search).get('customer_id');
  if (wanted) {
    try {
      const customer = await api.getCustomer(wanted);
      state.customerId = customer.id;
      input.value = customer.name;
      load();
    } catch (err) {
      showError(err.message);
    }
  }
})();
