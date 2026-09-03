/* =====================================================================
   Invoice create / edit, with the receipts panel attached.
   ===================================================================== */

const state = {
  id: null,
  status: 'draft',
  soNo: null,
  customer: null,
  createdBy: null,
  currency: 'IDR',
  balance: 0,
  editor: null,
};

const el = (id) => document.getElementById(id);
const errorEl = el('error');
const successEl = el('success');

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
  successEl.classList.add('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function showSuccess(message) {
  successEl.textContent = message;
  successEl.classList.remove('hidden');
  errorEl.classList.add('hidden');
}
function clearAlerts() {
  errorEl.classList.add('hidden');
  successEl.classList.add('hidden');
}

const num = (v) => {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
};
const orNull = (v) => {
  const s = typeof v === 'string' ? v.trim() : v;
  return s === '' || s === undefined ? null : s;
};
const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

function mayEdit() {
  const user = Auth.user;
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (state.id === null) return true;
  return state.createdBy === user.id;
}

/* ------------------------------------------------------------- header */

const customerInput = el('customerInput');

function setCustomer(customer, { fillHeader = true } = {}) {
  state.customer = customer;
  customerInput.value = customer ? customer.name : '';
  el('customerHint').textContent = customer
    ? `${customer.code} — selected`
    : 'No customer selected';
  if (!customer || !fillHeader) return;

  const map = {
    nikNpwp: customer.nik_npwp,
    address: customer.address,
    deliverTo: customer.deliver_to || customer.name,
    deliverAddress: customer.deliver_address || customer.address,
    phone: customer.phone,
    email: customer.email,
    priceGroup: customer.price_group,
    paymentTerms: customer.payment_terms,
  };
  Object.entries(map).forEach(([id, value]) => {
    el(id).value = value || '';
  });
}

attachAutocomplete({
  input: customerInput,
  resultsEl: el('customerResults'),
  search: (term) => api.listCustomers(term),
  render: (c) => `${esc(c.name)}<span class="code">${esc(c.code)}</span>`,
  onPick: (c) => setCustomer(c),
});

customerInput.addEventListener('input', () => {
  if (state.customer && customerInput.value.trim() !== state.customer.name) {
    state.customer = null;
    el('customerHint').textContent = 'No customer selected';
  }
});

/* -------------------------------------------------------- line items */

state.editor = createLineEditor({
  tbody: el('itemRows'),
  emptyEl: el('noRows'),
  addBtn: el('addRowBtn'),
  headerState: () => ({
    discount: num(el('discountPercent').value),
    currency: el('currency').value,
  }),
  onChange: ({ subtotal, discountTotal, netto, totalQty, currency }) => {
    const ppn = num(el('ppnPercent').value);
    const installation = num(el('installationCost').value);
    const taxable = round2(netto + installation);
    const ppnAmount = round2((taxable * ppn) / 100);
    el('sumSubtotal').textContent = fmtMoney(subtotal, currency);
    el('sumDiscount').textContent = `- ${fmtMoney(discountTotal, currency)}`;
    el('sumNetto').textContent = fmtMoney(netto, currency);
    el('sumInstall').textContent = fmtMoney(installation, currency);
    el('sumPpn').textContent = fmtMoney(ppnAmount, currency);
    el('sumTotal').textContent = `${currency} ${fmtMoney(round2(taxable + ppnAmount), currency)}`;
    el('sumQty').textContent = fmtNum(totalQty);
  },
});

['discountPercent', 'ppnPercent', 'installationCost', 'dpPercent'].forEach((id) =>
  el(id).addEventListener('input', state.editor.recalc)
);
el('currency').addEventListener('change', state.editor.recalc);

/* -------------------------------------------------------------- save */

function buildPayload() {
  if (!state.customer) throw new Error('Please select a customer.');
  return {
    customer_id: state.customer.id,
    order_date: orNull(el('orderDate').value),
    delivery_date: orNull(el('deliveryDate').value),
    po_reference: orNull(el('poReference').value),
    nik_npwp: orNull(el('nikNpwp').value),
    surveyor: orNull(el('surveyor').value),
    address: orNull(el('address').value),
    deliver_to: orNull(el('deliverTo').value),
    deliver_address: orNull(el('deliverAddress').value),
    phone: orNull(el('phone').value),
    email: orNull(el('email').value),
    currency: el('currency').value,
    exchange_rate: num(el('exchangeRate').value) || 1,
    price_group: orNull(el('priceGroup').value),
    payment_terms: orNull(el('paymentTerms').value),
    discount_percent: num(el('discountPercent').value),
    ppn_percent: num(el('ppnPercent').value),
    installation_cost: num(el('installationCost').value),
    dp_percent: el('dpPercent').value.trim() === '' ? null : num(el('dpPercent').value),
    notes: orNull(el('notes').value),
    items: state.editor.getItems(),
  };
}

async function save({ silent = false } = {}) {
  clearAlerts();
  try {
    const payload = buildPayload();
    const saved = state.id
      ? await api.updateSalesOrder(state.id, payload)
      : await api.createSalesOrder(payload);

    await applyOrder(saved);
    if (!silent) showSuccess(`Saved as ${saved.so_no}.`);
    if (!new URLSearchParams(window.location.search).get('id')) {
      window.history.replaceState({}, '', `sales-order-form.html?id=${saved.id}`);
    }
    return saved;
  } catch (err) {
    showError(err.message);
    return null;
  }
}

async function changeStatus(next, label) {
  clearAlerts();
  try {
    if (!state.id && !(await save({ silent: true }))) return;
    await applyOrder(await api.setSalesOrderStatus(state.id, next));
    showSuccess(`${state.soNo} marked as ${label}.`);
  } catch (err) {
    showError(err.message);
  }
}

el('saveBtn').addEventListener('click', () => save());
el('confirmBtn').addEventListener('click', async () => {
  if (state.status === 'draft' && state.id) await save({ silent: true });
  changeStatus('confirmed', 'confirmed');
});
el('productionBtn').addEventListener('click', () => changeStatus('in_production', 'in production'));
el('deliveredBtn').addEventListener('click', () => changeStatus('delivered', 'delivered'));
el('completeBtn').addEventListener('click', () => changeStatus('completed', 'completed'));
el('cancelBtn').addEventListener('click', () => {
  if (confirm('Cancel this invoice?')) changeStatus('cancelled', 'cancelled');
});

el('pdfBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!state.id) return showError('Save the order first.');
  try {
    await openPdf('salesOrder', state.id);
  } catch (err) {
    showError(err.message);
  }
});

el('poBtn').addEventListener('click', () => {
  window.location.href = `purchase-order-form.html?sales_order_id=${state.id}`;
});

/* ---------------------------------------------------------- receipts */

async function loadReceipts() {
  if (!state.id) return;
  const list = await api.listReceipts({ sales_order_id: state.id });
  const tbody = el('receiptRows');

  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">No payments recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = list
    .map(
      (r) => `
      <tr>
        <td class="mono"><strong>${esc(r.receipt_no)}</strong></td>
        <td>${fmtDate(r.receipt_date)}</td>
        <td>${esc(r.payment_method)}</td>
        <td class="hint">${esc(r.reference || '-')}</td>
        <td class="right mono">${fmtMoney(r.amount, state.currency)}</td>
        <td class="hint">${esc(r.created_by_name || '-')}</td>
        <td class="right">
          <button class="btn small" data-pdf="${r.id}" type="button">PDF</button>
          ${r.can_edit ? `<button class="btn small danger" data-void="${r.id}" type="button">Void</button>` : ''}
        </td>
      </tr>`
    )
    .join('');
}

el('receiptRows').addEventListener('click', async (event) => {
  const pdfBtn = event.target.closest('[data-pdf]');
  const voidBtn = event.target.closest('[data-void]');
  clearAlerts();
  try {
    if (pdfBtn) {
      await openPdf('receipt', pdfBtn.dataset.pdf);
    } else if (voidBtn) {
      if (!confirm('Void this receipt? The payment will no longer count.')) return;
      await api.voidReceipt(voidBtn.dataset.void);
      await applyOrder(await api.getSalesOrder(state.id));
      showSuccess('Receipt voided.');
    }
  } catch (err) {
    showError(err.message);
  }
});

el('addReceiptBtn').addEventListener('click', () => {
  el('receiptForm').style.display = '';
  el('rcDate').value = todayISO();
  el('rcAmount').value = '';
  el('rcHint').textContent = `Outstanding: ${state.currency} ${fmtMoney(state.balance, state.currency)}`;
  el('rcAmount').focus();
});
el('rcCancelBtn').addEventListener('click', () => {
  el('receiptForm').style.display = 'none';
});
el('rcFullBtn').addEventListener('click', () => {
  el('rcAmount').value = state.balance;
});

el('rcSaveBtn').addEventListener('click', async () => {
  clearAlerts();
  try {
    const receipt = await api.createReceipt({
      sales_order_id: state.id,
      amount: num(el('rcAmount').value),
      receipt_date: orNull(el('rcDate').value),
      payment_method: el('rcMethod').value,
      reference: orNull(el('rcReference').value),
    });
    el('receiptForm').style.display = 'none';
    el('rcReference').value = '';
    await applyOrder(await api.getSalesOrder(state.id));
    showSuccess(`Payment recorded as ${receipt.receipt_no}.`);
  } catch (err) {
    showError(err.message);
  }
});

/* -------------------------------------------------------- deliveries */

async function loadDeliveries() {
  if (!state.id) return;

  const [notes, outstanding] = await Promise.all([
    api.listDeliveryNotes({ sales_order_id: state.id }),
    api.deliveryStatus(state.id),
  ]);

  el('deliveryRows').innerHTML = notes.length
    ? notes
        .map(
          (n) => `
        <tr>
          <td class="mono"><a href="delivery-note-form.html?id=${n.id}"><strong>${esc(n.sj_no)}</strong></a></td>
          <td>${fmtDate(n.delivery_date)}</td>
          <td class="hint">${esc(n.vehicle_no || '-')} / ${esc(n.driver_name || '-')}</td>
          <td class="center">${statusBadge(n.status)}</td>
          <td class="right mono">${fmtNum(n.total_qty)}</td>
          <td class="right"><button class="btn small" data-sjpdf="${n.id}" type="button">PDF</button></td>
        </tr>`
        )
        .join('')
    : '<tr><td colspan="6" class="empty">Nothing delivered yet.</td></tr>';

  el('outstandingRows').innerHTML = outstanding.lines
    .map(
      (line) => `
      <tr>
        <td>${esc(line.product_name)}<br><span class="hint">${esc(line.product_code)}</span></td>
        <td class="right mono">${fmtNum(line.ordered)}</td>
        <td class="right mono">${fmtNum(line.delivered)}</td>
        <td class="right mono ${Number(line.outstanding) > 0 ? 'num-neg' : 'num-pos'}">${fmtNum(line.outstanding)}</td>
      </tr>`
    )
    .join('');

  el('deliveryHint').textContent = outstanding.fully_delivered
    ? 'Everything on this order has been delivered'
    : 'Some items are still outstanding';
  el('newSjBtn').style.display = outstanding.fully_delivered ? 'none' : '';
}

el('deliveryRows').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-sjpdf]');
  if (!button) return;
  clearAlerts();
  try {
    await openPdf('deliveryNote', button.dataset.sjpdf);
  } catch (err) {
    showError(err.message);
  }
});

/** One purchase order per supplier, grouped by each product's default. */
el('splitPoBtn').addEventListener('click', async () => {
  clearAlerts();
  try {
    const preview = await api.previewPoSplit(state.id);
    if (!preview.groups.length) {
      showError(t('po.splitNone'));
      return;
    }
    const summary = preview.groups
      .map((g) => `  - ${g.supplier_name}: ${g.lines.length} line(s)`)
      .join('\n');
    const warning = preview.unassigned.length
      ? `\n\n${preview.unassigned.length} ${t('po.splitUnassigned')}.`
      : '';
    if (!confirm(`${t('po.splitCreate')}?\n\n${summary}${warning}`)) return;

    const created = await api.createPoSplit(state.id);
    await applyOrder(await api.getSalesOrder(state.id));
    showSuccess(`${created.length} purchase order(s) created: ${created.map((p) => p.po_no).join(', ')}`);
  } catch (err) {
    showError(err.message);
  }
});

/* ------------------------------------- closing pembayaran piutang */

el('closeArBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!confirm(t('ar.confirmClose'))) return;
  try {
    await applyOrder(await api.closeReceivable(state.id, {
      note: orNull(el('closeNote').value),
    }));
    showSuccess(`${state.soNo}: ${t('ar.closed')}.`);
  } catch (err) {
    showError(err.message);
  }
});

el('reopenArBtn').addEventListener('click', async () => {
  clearAlerts();
  try {
    await applyOrder(await api.reopenReceivable(state.id));
    showSuccess(`${state.soNo} reopened.`);
  } catch (err) {
    showError(err.message);
  }
});

/** The panel only makes sense on a live invoice that owes, or is closed. */
function updateReceivable(so) {
  const card = el('receivableCard');
  const live = !['draft', 'cancelled'].includes(so.status);
  card.style.display = live ? '' : 'none';
  if (!live) return;

  const closed = so.is_closed;
  const settled = Number(so.balance_due) === 0;
  el('closeNote').value = so.receivable_close_note || '';
  el('closeNote').disabled = closed;
  el('closeArBtn').style.display = closed ? 'none' : '';
  el('closeArBtn').disabled = !settled || !mayEdit();
  el('reopenArBtn').style.display = closed ? '' : 'none';
  el('reopenArBtn').disabled = !mayEdit();

  el('receivableState').textContent = closed
    ? `${t('ar.closedOn')} ${fmtDate(so.receivable_closed_at)}` +
      (so.receivable_closed_by_name ? ` — ${so.receivable_closed_by_name}` : '')
    : settled
      ? `${t('ar.settled')}: ${so.currency} 0`
      : `${t('ar.open')}: ${so.currency} ${fmtMoney(so.balance_due, so.currency)}`;
}

el('newSjBtn').addEventListener('click', () => {
  window.location.href = `delivery-note-form.html?sales_order_id=${state.id}`;
});

/* --------------------------------------------------------- load/render */

async function applyOrder(so) {
  state.id = so.id;
  state.status = so.status;
  state.soNo = so.so_no;
  state.createdBy = so.created_by;
  state.currency = so.currency;
  state.balance = Number(so.balance_due);

  el('soNo').value = so.so_no;
  el('orderDate').value = so.order_date || '';
  el('deliveryDate').value = so.delivery_date || '';
  el('poReference').value = so.po_reference || '';
  el('nikNpwp').value = so.nik_npwp || '';
  el('surveyor').value = so.surveyor || '';
  el('address').value = so.address || '';
  el('deliverTo').value = so.deliver_to || '';
  el('deliverAddress').value = so.deliver_address || '';
  el('phone').value = so.phone || '';
  el('email').value = so.email || '';
  el('currency').value = so.currency;
  el('exchangeRate').value = Number(so.exchange_rate);
  el('priceGroup').value = so.price_group || '';
  el('paymentTerms').value = so.payment_terms || '';
  el('discountPercent').value = Number(so.discount_percent);
  el('ppnPercent').value = Number(so.ppn_percent);
  el('installationCost').value = Number(so.installation_cost || 0);
  el('dpPercent').value = so.dp_percent === null || so.dp_percent === undefined
    ? '' : Number(so.dp_percent);
  el('notes').value = so.notes || '';

  setCustomer(
    { id: so.customer_id, code: so.customer_code, name: so.customer_name },
    { fillHeader: false }
  );

  state.editor.clear();
  (so.items || []).forEach((item) => state.editor.addRow(item));

  el('pageTitle').textContent = `Invoice ${so.so_no}`;
  el('statusBadge').innerHTML = statusBadge(so.status);
  el('ownerNote').textContent = so.created_by_name ? `Created by ${so.created_by_name}` : '';
  document.title = `${so.so_no} · Q2O`;

  const fromQ = el('fromQuotation');
  if (so.quotation_no) {
    fromQ.innerHTML = `Raised from quotation <a href="quotation-form.html?id=${so.quotation_id}"><strong>${esc(so.quotation_no)}</strong></a>`;
    fromQ.style.display = '';
  } else {
    fromQ.style.display = 'none';
  }

  setReadonly(!['draft', 'confirmed'].includes(so.status) || !mayEdit());
  state.editor.recalc();

  el('sumSubtotal').textContent = fmtMoney(so.subtotal, so.currency);
  el('sumDiscount').textContent = `- ${fmtMoney(so.discount_amount, so.currency)}`;
  el('sumNetto').textContent = fmtMoney(so.netto, so.currency);
  el('sumInstall').textContent = fmtMoney(so.installation_cost, so.currency);
  el('sumPpn').textContent = fmtMoney(so.ppn_amount, so.currency);
  const dpRows = document.querySelectorAll('.dp-row');
  if (so.dp_percent === null || so.dp_percent === undefined) {
    dpRows.forEach((r) => (r.style.display = 'none'));
  } else {
    dpRows.forEach((r) => (r.style.display = ''));
    el('sumDp').textContent = `${so.currency} ${fmtMoney(so.dp_amount, so.currency)}`;
  }
  el('sumTotal').textContent = `${so.currency} ${fmtMoney(so.total, so.currency)}`;
  el('sumQty').textContent = fmtNum(so.total_qty);
  el('sumPaid').textContent = fmtMoney(so.amount_paid, so.currency);
  el('sumBalance').textContent = `${so.currency} ${fmtMoney(so.balance_due, so.currency)}`;

  // Payments and deliveries only make sense once the order is committed.
  const isLive = !['draft', 'cancelled'].includes(so.status);
  el('receiptsCard').style.display = isLive ? '' : 'none';
  el('addReceiptBtn').style.display = state.balance > 0 ? '' : 'none';
  el('deliveryCard').style.display = isLive ? '' : 'none';
  updateReceivable(so);
  if (isLive) {
    await loadReceipts();
    await loadDeliveries();
  }
}

const HEADER_FIELDS = [
  'orderDate', 'deliveryDate', 'poReference', 'customerInput', 'nikNpwp', 'phone',
  'address', 'deliverAddress', 'deliverTo', 'surveyor', 'email', 'currency',
  'exchangeRate', 'priceGroup', 'paymentTerms', 'discountPercent', 'ppnPercent',
  'installationCost', 'dpPercent', 'notes',
];

function setReadonly(readonly) {
  HEADER_FIELDS.forEach((id) => (el(id).disabled = readonly));
  state.editor.setReadonly(readonly);
  updateActions();
}

function updateActions() {
  const show = (id, visible) => {
    el(id).style.display = visible ? '' : 'none';
  };
  const s = state.status;
  const editable = mayEdit();
  const saved = Boolean(state.id);

  show('saveBtn', ['draft', 'confirmed'].includes(s) && editable);
  show('confirmBtn', s === 'draft' && editable);
  show('productionBtn', s === 'confirmed' && editable);
  show('deliveredBtn', s === 'in_production' && editable);
  show('completeBtn', s === 'delivered' && editable);
  show('pdfBtn', saved);
  show('poBtn', saved && !['draft', 'cancelled'].includes(s));
  show('splitPoBtn', saved && !['draft', 'cancelled'].includes(s));
  show('cancelBtn', saved && editable && !['completed', 'cancelled'].includes(s));

  const locked = el('lockedNote');
  if (saved && !editable) {
    locked.textContent =
      'Read-only: this invoice belongs to another user. An admin can change it.';
    locked.style.display = '';
  } else {
    locked.style.display = 'none';
  }
}

/* ---------------------------------------------------------------- boot */

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('sales-orders', user);

  const id = new URLSearchParams(window.location.search).get('id');
  if (id) {
    try {
      await applyOrder(await api.getSalesOrder(id));
    } catch (err) {
      showError(err.message);
    }
    return;
  }

  el('orderDate').value = todayISO();
  el('statusBadge').innerHTML = statusBadge('draft');
  state.editor.addRow();
  updateActions();
})();
