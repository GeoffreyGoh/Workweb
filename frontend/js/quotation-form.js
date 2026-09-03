/* =====================================================================
   Quotation create / edit.
   Line items are handled by the shared editor in line-editor.js.
   ===================================================================== */

// Mirrors EDITABLE_STATUSES in routers/quotations.py: a sent quotation is
// still being negotiated, so it stays open for revision until it is approved.
const EDITABLE_STATUSES = ['draft', 'sent'];

const state = {
  id: null,
  status: 'draft',
  quotationNo: null,
  customer: null,
  createdBy: null,
  readonly: false,
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

const num = (value) => {
  const n = parseFloat(value);
  return isNaN(n) ? 0 : n;
};
const orNull = (value) => {
  const v = typeof value === 'string' ? value.trim() : value;
  return v === '' || v === undefined ? null : v;
};
const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

/** Can the signed-in user change this document? */
function mayEdit() {
  const user = Auth.user;
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (state.id === null) return true; // brand new, not saved yet
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
    // Installation is a taxable service, so it sits inside the PPN base.
    const taxable = round2(netto + installation);
    const ppnAmount = round2((taxable * ppn) / 100);
    const total = round2(taxable + ppnAmount);

    el('sumSubtotal').textContent = fmtMoney(subtotal, currency);
    el('sumDiscount').textContent = `- ${fmtMoney(discountTotal, currency)}`;
    el('sumNetto').textContent = fmtMoney(netto, currency);
    el('sumInstall').textContent = fmtMoney(installation, currency);
    el('sumPpn').textContent = fmtMoney(ppnAmount, currency);
    el('sumTotal').textContent = `${currency} ${fmtMoney(total, currency)}`;
    el('sumQty').textContent = fmtNum(totalQty);
    showDp(total, currency);
  },
});

/** Down payment preview. A blank DP% hides the two rows entirely. */
function showDp(total, currency) {
  const raw = el('dpPercent').value.trim();
  const rows = document.querySelectorAll('.dp-row');
  if (raw === '') {
    rows.forEach((r) => (r.style.display = 'none'));
    return;
  }
  const pct = num(raw);
  const dp = round2((total * pct) / 100);
  rows.forEach((r) => (r.style.display = ''));
  el('sumDp').textContent = `${currency} ${fmtMoney(dp, currency)}`;
  el('sumDpBalance').textContent = `${currency} ${fmtMoney(round2(total - dp), currency)}`;
}

['discountPercent', 'ppnPercent', 'installationCost', 'dpPercent'].forEach((id) =>
  el(id).addEventListener('input', state.editor.recalc)
);
el('currency').addEventListener('change', state.editor.recalc);

/* -------------------------------------------------------------- save */

function buildPayload() {
  if (!state.customer) throw new Error('Please select a customer.');
  return {
    customer_id: state.customer.id,
    quotation_date: orNull(el('quotationDate').value),
    last_follow_up: orNull(el('lastFollowUp').value),
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
    company_id: el('companySelect').value ? Number(el('companySelect').value) : null,
    discount_percent: num(el('discountPercent').value),
    ppn_percent: num(el('ppnPercent').value),
    installation_cost: num(el('installationCost').value),
    dp_percent: el('dpPercent').value.trim() === '' ? null : num(el('dpPercent').value),
    notes: orNull(el('notes').value),
    items: state.editor.getItems(),
  };
}

const ACTION_BUTTONS = ['saveBtn', 'sendBtn', 'resendBtn', 'approveBtn',
                        'convertBtn', 'pdfBtn', 'cancelBtn'];

async function save({ silent = false } = {}) {
  clearAlerts();
  ACTION_BUTTONS.forEach((id) => (el(id).disabled = true));

  try {
    const payload = buildPayload();
    const saved = state.id
      ? await api.updateQuotation(state.id, payload)
      : await api.createQuotation(payload);

    applyQuotation(saved);
    if (!silent) showSuccess(`Saved as ${saved.quotation_no}.`);

    if (!new URLSearchParams(window.location.search).get('id')) {
      window.history.replaceState({}, '', `quotation-form.html?id=${saved.id}`);
    }
    return saved;
  } catch (err) {
    showError(err.message);
    return null;
  } finally {
    ACTION_BUTTONS.forEach((id) => (el(id).disabled = false));
    updateActions();
  }
}

async function changeStatus(next, label) {
  clearAlerts();
  try {
    if (!state.id && !(await save({ silent: true }))) return;
    applyQuotation(await api.setQuotationStatus(state.id, next));
    showSuccess(`Quotation ${state.quotationNo} marked as ${label}.`);
  } catch (err) {
    showError(err.message);
  }
}

el('saveBtn').addEventListener('click', () => save());

el('sendBtn').addEventListener('click', async () => {
  if (state.status === 'draft' && state.id) await save({ silent: true });
  changeStatus('sent', 'sent');
});

/** Save the revision and stamp a fresh follow-up date on the same document. */
el('resendBtn').addEventListener('click', async () => {
  const saved = await save({ silent: true });
  if (!saved) return;
  try {
    await api.updateQuotation(state.id, {
      ...buildPayload(),
      last_follow_up: todayISO(),
    });
    applyQuotation(await api.getQuotation(state.id));
    showSuccess(t('quotation.revised'));
  } catch (err) {
    showError(err.message);
  }
});

el('approveBtn').addEventListener('click', () => changeStatus('approved', 'approved'));

el('cancelBtn').addEventListener('click', () => {
  if (confirm('Cancel this quotation? It will no longer be editable.')) {
    changeStatus('cancelled', 'cancelled');
  }
});

el('pdfBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!state.id) {
    showError('Save the quotation first - a PDF needs a quotation number.');
    return;
  }
  try {
    await openPdf('quotation', state.id);
  } catch (err) {
    showError(err.message);
  }
});

el('convertBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!confirm('Create an invoice from this quotation?')) return;
  try {
    const so = await api.convertQuotation(state.id);
    window.location.href = `sales-order-form.html?id=${so.id}`;
  } catch (err) {
    showError(err.message);
  }
});

/* --------------------------------------------------------- load/render */

function applyQuotation(q) {
  state.id = q.id;
  state.status = q.status;
  state.quotationNo = q.quotation_no;
  state.createdBy = q.created_by;

  el('quotationNo').value = q.quotation_no;
  loadCompanyOptions(el('companySelect'), { selected: q.company_id });
  el('quotationDate').value = q.quotation_date || '';
  el('lastFollowUp').value = q.last_follow_up || '';
  el('nikNpwp').value = q.nik_npwp || '';
  el('surveyor').value = q.surveyor || '';
  el('address').value = q.address || '';
  el('deliverTo').value = q.deliver_to || '';
  el('deliverAddress').value = q.deliver_address || '';
  el('phone').value = q.phone || '';
  el('email').value = q.email || '';
  el('currency').value = q.currency;
  el('exchangeRate').value = Number(q.exchange_rate);
  el('priceGroup').value = q.price_group || '';
  el('paymentTerms').value = q.payment_terms || '';
  el('discountPercent').value = Number(q.discount_percent);
  el('ppnPercent').value = Number(q.ppn_percent);
  el('installationCost').value = Number(q.installation_cost || 0);
  el('dpPercent').value = q.dp_percent === null || q.dp_percent === undefined
    ? '' : Number(q.dp_percent);
  el('notes').value = q.notes || '';

  setCustomer(
    { id: q.customer_id, code: q.customer_code, name: q.customer_name },
    { fillHeader: false }
  );

  state.editor.clear();
  (q.items || []).forEach((item) => state.editor.addRow(item));

  el('pageTitle').textContent = `Quotation ${q.quotation_no}`;
  el('statusBadge').innerHTML = statusBadge(q.status);
  el('ownerNote').textContent = q.created_by_name ? `Created by ${q.created_by_name}` : '';
  document.title = `${q.quotation_no} · Q2O`;

  setReadonly(!EDITABLE_STATUSES.includes(q.status) || !mayEdit());
  state.editor.recalc();

  // Server totals are authoritative - show them, not the local preview.
  el('sumSubtotal').textContent = fmtMoney(q.subtotal, q.currency);
  el('sumDiscount').textContent = `- ${fmtMoney(q.discount_amount, q.currency)}`;
  el('sumNetto').textContent = fmtMoney(q.netto, q.currency);
  el('sumInstall').textContent = fmtMoney(q.installation_cost, q.currency);
  el('sumPpn').textContent = fmtMoney(q.ppn_amount, q.currency);
  el('sumTotal').textContent = `${q.currency} ${fmtMoney(q.total, q.currency)}`;
  el('sumQty').textContent = fmtNum(q.total_qty);
  showDp(Number(q.total), q.currency);
}

const HEADER_FIELDS = [
  'quotationDate', 'lastFollowUp', 'surveyor', 'customerInput', 'nikNpwp', 'phone',
  'address', 'deliverAddress', 'deliverTo', 'email', 'currency', 'exchangeRate',
  'priceGroup', 'paymentTerms', 'discountPercent', 'ppnPercent',
  'installationCost', 'dpPercent', 'notes',
];

function setReadonly(readonly) {
  state.readonly = readonly;
  HEADER_FIELDS.forEach((id) => (el(id).disabled = readonly));
  // The quotation number encodes the company, so it is fixed once issued -
  // even while the rest of a draft stays editable.
  el('companySelect').disabled = readonly || state.id !== null;
  state.editor.setReadonly(readonly);
  updateActions();
}

function updateActions() {
  const show = (id, visible) => {
    el(id).style.display = visible ? '' : 'none';
  };
  const status = state.status;
  const editable = mayEdit();

  show('saveBtn', EDITABLE_STATUSES.includes(status) && editable);
  show('sendBtn', status === 'draft' && editable);
  show('resendBtn', status === 'sent' && editable);
  show('approveBtn', status === 'sent' && editable);
  show('convertBtn', ['sent', 'approved'].includes(status) && Boolean(state.id));
  show('pdfBtn', Boolean(state.id));
  show('cancelBtn', Boolean(state.id) && editable && ['draft', 'sent', 'approved'].includes(status));

  const locked = el('lockedNote');
  if (state.id && !editable) {
    locked.textContent =
      'Read-only: this quotation belongs to another user. An admin can change it.';
    locked.style.display = '';
  } else {
    locked.style.display = 'none';
  }
}

/* ---------------------------------------------------------------- boot */

(async () => {
  const user = await requireLogin();
  if (!user) return;

  const id = new URLSearchParams(window.location.search).get('id');
  renderTopbar('quotations', user);

  if (id) {
    try {
      applyQuotation(await api.getQuotation(id));
    } catch (err) {
      showError(err.message);
    }
    return;
  }

  el('quotationDate').value = todayISO();
  el('statusBadge').innerHTML = statusBadge('draft');
  await loadCompanyOptions(el('companySelect'), { selected: user.default_company_id });
  state.editor.addRow();
  updateActions();
})();
