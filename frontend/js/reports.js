/* Sales and financial reports. All figures are netto (pre-PPN). */

const range = { date_from: '', date_to: '', created_by: '', customer_id: '',
                company_id: '' };
const errorEl = document.getElementById('error');

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function kpi(label, value, sub, tone) {
  return `
    <div class="kpi ${tone || ''}">
      <div class="k-label">${esc(label)}</div>
      <div class="k-value">${esc(value)}</div>
      <div class="k-sub">${esc(sub || '')}</div>
    </div>`;
}

const money = (v) => `IDR ${fmtMoney(v)}`;
const signed = (v) => (Number(v) < 0 ? 'num-neg' : 'num-pos');

/* -------------------------------------------------------------- sales */

async function loadSales() {
  const r = await api.salesReport(range);

  document.getElementById('salesKpis').innerHTML = [
    kpi('Quotations', String(r.quotation_count), money(r.quotation_value)),
    kpi('Sales Orders', String(r.order_count), money(r.order_value)),
    kpi('Conversion Rate', `${fmtNum(r.conversion_rate)}%`, 'orders raised / quotations issued'),
    kpi(
      'Average Order',
      money(r.order_count ? Number(r.order_value) / r.order_count : 0),
      'netto, excluding PPN'
    ),
  ].join('');

  document.getElementById('salesUsers').innerHTML = r.by_user.length
    ? r.by_user
        .map(
          (u) => `
        <tr>
          <td><strong>${esc(u.created_by_name)}</strong></td>
          <td class="right mono">${u.quotation_count}</td>
          <td class="right mono">${fmtMoney(u.quotation_value)}</td>
          <td class="right mono">${u.order_count}</td>
          <td class="right mono">${fmtMoney(u.order_value)}</td>
          <td class="right mono">${fmtNum(u.conversion_rate)}%</td>
        </tr>`
        )
        .join('')
    : `<tr><td colspan="6" class="empty">${esc(t('common.none'))}</td></tr>`;

  document.getElementById('salesPeriods').innerHTML = r.by_period.length
    ? r.by_period
        .map((p) => {
          const conv = p.quotation_count
            ? ((p.order_count / p.quotation_count) * 100).toFixed(1)
            : '0.0';
          return `
          <tr>
            <td class="mono">${esc(p.period)}</td>
            <td class="right mono">${p.quotation_count}</td>
            <td class="right mono">${fmtMoney(p.quotation_value)}</td>
            <td class="right mono">${p.order_count}</td>
            <td class="right mono">${fmtMoney(p.order_value)}</td>
            <td class="right mono">${conv}%</td>
          </tr>`;
        })
        .join('')
    : '<tr><td colspan="6" class="empty">No activity in this period.</td></tr>';

  const totalValue = Number(r.order_value) || 1;
  document.getElementById('salesCustomers').innerHTML = r.by_customer.length
    ? r.by_customer
        .map(
          (c) => `
        <tr>
          <td><strong>${esc(c.customer_name)}</strong></td>
          <td class="hint mono">${esc(c.customer_code || '-')}</td>
          <td class="right mono">${c.order_count}</td>
          <td class="right mono">${fmtMoney(c.order_value)}</td>
          <td class="right mono">${((Number(c.order_value) / totalValue) * 100).toFixed(1)}%</td>
        </tr>`
        )
        .join('')
    : '<tr><td colspan="5" class="empty">No orders in this period.</td></tr>';

  document.getElementById('salesProducts').innerHTML = r.by_product.length
    ? r.by_product
        .map(
          (p) => `
        <tr>
          <td><strong>${esc(p.product_name)}</strong></td>
          <td class="hint mono">${esc(p.product_code)}</td>
          <td class="right mono">${fmtNum(p.quantity)}</td>
          <td class="right mono">${fmtNum(p.measure)}</td>
          <td class="right mono">${fmtMoney(p.value)}</td>
        </tr>`
        )
        .join('')
    : '<tr><td colspan="5" class="empty">No products sold in this period.</td></tr>';
}

/* ---------------------------------------------------------- financial */

async function loadFinancial() {
  const r = await api.financialReport(range);
  const profitable = Number(r.gross_profit) >= 0;

  document.getElementById('finKpis').innerHTML = [
    kpi('Revenue', money(r.revenue), 'sales orders, netto'),
    kpi('Cost', money(r.cost), 'purchase orders, netto'),
    kpi(
      'Gross Profit',
      money(r.gross_profit),
      `${fmtNum(r.margin_pct)}% margin`,
      profitable ? 'good' : 'bad'
    ),
    kpi('Collected', money(r.collected), `${money(r.outstanding)} outstanding`),
  ].join('');

  const note = document.getElementById('finNote');
  if (Number(r.cost_unlinked) > 0) {
    note.innerHTML =
      `<strong>${money(r.cost_unlinked)}</strong> of purchase cost is not linked to a specific ` +
      `sales order, so it counts toward the totals above but not toward any single order's margin. ` +
      `Link a purchase order to a sales order when raising it to attribute the cost.`;
    note.style.display = '';
  } else {
    note.style.display = 'none';
  }

  document.getElementById('finPeriods').innerHTML = r.by_period.length
    ? r.by_period
        .map(
          (p) => `
        <tr>
          <td class="mono">${esc(p.period)}</td>
          <td class="right mono">${fmtMoney(p.revenue)}</td>
          <td class="right mono">${fmtMoney(p.cost)}</td>
          <td class="right mono ${signed(p.gross_profit)}">${fmtMoney(p.gross_profit)}</td>
          <td class="right mono ${signed(p.margin_pct)}">${fmtNum(p.margin_pct)}%</td>
        </tr>`
        )
        .join('')
    : '<tr><td colspan="5" class="empty">No activity in this period.</td></tr>';

  document.getElementById('finOrders').innerHTML = r.by_order.length
    ? r.by_order
        .map(
          (o) => `
        <tr class="clickable" onclick="window.location.href='sales-order-form.html?id=${o.sales_order_id}'">
          <td class="mono"><strong>${esc(o.so_no)}</strong></td>
          <td>${fmtDate(o.order_date)}</td>
          <td>${esc(o.customer_name)}</td>
          <td class="right mono">${fmtMoney(o.revenue)}</td>
          <td class="right mono">${fmtMoney(o.cost)}</td>
          <td class="center mono">${o.po_count || '-'}</td>
          <td class="right mono ${signed(o.gross_profit)}">${fmtMoney(o.gross_profit)}</td>
          <td class="right mono ${signed(o.margin_pct)}">${fmtNum(o.margin_pct)}%</td>
        </tr>`
        )
        .join('')
    : '<tr><td colspan="8" class="empty">No sales orders in this period.</td></tr>';
}

/* --------------------------------------------------------------- tabs */

let activeTab = 'sales';

document.querySelectorAll('.tabs button').forEach((button) => {
  button.addEventListener('click', () => {
    activeTab = button.dataset.tab;
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.remove('active'));
    button.classList.add('active');
    document.getElementById('tab-sales').style.display = activeTab === 'sales' ? '' : 'none';
    document.getElementById('tab-financial').style.display =
      activeTab === 'financial' ? '' : 'none';
    refresh();
  });
});

async function refresh() {
  errorEl.classList.add('hidden');
  try {
    if (activeTab === 'sales') await loadSales();
    else await loadFinancial();
  } catch (err) {
    showError(err.message);
  }
}

/**
 * Choosing a month is just a shortcut for "the range covering that month" -
 * one control instead of two dates, which is how the office actually asks
 * the question ("how did August go?").
 */
document.getElementById('fMonth').addEventListener('change', (e) => {
  const value = e.target.value;                 // "2026-08"
  if (!value) return;
  const [year, month] = value.split('-').map(Number);
  const last = new Date(year, month, 0).getDate();
  range.date_from = `${value}-01`;
  range.date_to = `${value}-${String(last).padStart(2, '0')}`;
  document.getElementById('fFrom').value = range.date_from;
  document.getElementById('fTo').value = range.date_to;
  refresh();
});

document.getElementById('applyBtn').addEventListener('click', () => {
  range.date_from = document.getElementById('fFrom').value;
  range.date_to = document.getElementById('fTo').value;
  document.getElementById('fMonth').value = '';   // an explicit range wins
  range.created_by = document.getElementById('fUser').value;
  range.company_id = document.getElementById('fCompany').value;
  refresh();
});

document.getElementById('clearBtn').addEventListener('click', () => {
  ['fFrom', 'fTo', 'fCustomer', 'fMonth'].forEach((id) => {
    document.getElementById(id).value = '';
  });
  document.getElementById('fUser').value = '';
  document.getElementById('fCompany').value = '';
  Object.keys(range).forEach((k) => (range[k] = ''));
  refresh();
});

/** Populate the salesperson filter once, from the staff list. */
async function loadUsers() {
  try {
    const users = await api.listUsers();
    const select = document.getElementById('fUser');
    users.forEach((u) => {
      const option = document.createElement('option');
      option.value = u.id;
      option.textContent = u.full_name;
      select.appendChild(option);
    });
  } catch (err) {
    /* the filter simply stays as "All" */
  }
}

const customerFilter = document.getElementById('fCustomer');
attachAutocomplete({
  input: customerFilter,
  resultsEl: document.getElementById('fCustomerResults'),
  search: (term) => api.listCustomers(term),
  render: (c) => `${esc(c.name)}<span class="code">${esc(c.code)}</span>`,
  onPick: (c) => {
    customerFilter.value = c.name;
    range.customer_id = c.id;
    refresh();
  },
});
customerFilter.addEventListener('input', () => {
  if (!customerFilter.value.trim() && range.customer_id) {
    range.customer_id = '';
    refresh();
  }
});

document.addEventListener('languagechange', refresh);

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('reports', user);
  await loadUsers();
  await loadCompanyOptions(document.getElementById('fCompany'),
                           { allLabel: t('common.allCompanies') });
  refresh();
})();
