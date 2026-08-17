/* =====================================================================
   Purchase order create / edit.

   PO lines are free-text materials, not catalogue products, so this page
   has its own simple line table rather than the shared line editor.
   ===================================================================== */

const state = {
  id: null,
  status: 'draft',
  poNo: null,
  supplier: null,
  salesOrder: null,
  createdBy: null,
  lines: [],
};

let lineSeq = 0;

const el = (id) => document.getElementById(id);
const errorEl = el('error');
const successEl = el('success');
const itemRows = el('itemRows');

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

/* ---------------------------------------------------------- pickers */

const supplierInput = el('supplierInput');
attachAutocomplete({
  input: supplierInput,
  resultsEl: el('supplierResults'),
  search: (term) => api.listSuppliers(term),
  render: (s) => `${esc(s.name)}<span class="code">${esc(s.code)}</span>`,
  onPick: (s) => {
    state.supplier = s;
    supplierInput.value = s.name;
    el('supplierHint').textContent = `${s.code} — selected`;
    if (s.payment_terms && !el('paymentTerms').value) {
      el('paymentTerms').value = s.payment_terms;
    }
  },
});
supplierInput.addEventListener('input', () => {
  if (state.supplier && supplierInput.value.trim() !== state.supplier.name) {
    state.supplier = null;
    el('supplierHint').textContent = 'No supplier selected';
  }
});

const soInput = el('soInput');
attachAutocomplete({
  input: soInput,
  resultsEl: el('soResults'),
  search: (term) => api.listSalesOrders({ q: term, limit: 20 }),
  render: (so) =>
    `${esc(so.so_no)}<span class="code">${esc(so.customer_name || '')} · ${esc(so.currency)} ${fmtMoney(so.total, so.currency)}</span>`,
  onPick: (so) => setSalesOrder(so),
});
soInput.addEventListener('input', () => {
  if (!soInput.value.trim()) {
    state.salesOrder = null;
    el('soHint').textContent = 'Not linked — counts as general cost only';
  }
});

function setSalesOrder(so) {
  state.salesOrder = so;
  soInput.value = so.so_no;
  el('soHint').textContent = `Linked to ${so.so_no} — this cost counts toward that order's margin`;
}

/* ------------------------------------------------------- line items */

const PO_ROW_HTML = `
  <td class="mono lineNo"></td>
  <td><input type="text" class="descInput" placeholder="e.g. Blackout fabric roll 280cm"></td>
  <td>
    <div class="autocomplete">
      <input type="text" class="prodInput" placeholder="None" autocomplete="off">
      <div class="results hidden prodResults"></div>
    </div>
  </td>
  <td><input type="text" class="unitInput" value="pcs"></td>
  <td><input type="number" class="num qtyInput" value="1" min="0" step="0.01"></td>
  <td><input type="number" class="num priceInput" min="0" step="1"></td>
  <td class="right mono totalCell">0</td>
  <td class="center"><button class="btn icon removeBtn" type="button" title="Remove line">&times;</button></td>
`;

function addRow(data) {
  const tr = document.createElement('tr');
  tr.innerHTML = PO_ROW_HTML;
  itemRows.appendChild(tr);

  const line = {
    uid: ++lineSeq,
    tr,
    productId: data ? data.product_id : null,
    refs: {
      lineNo: tr.querySelector('.lineNo'),
      desc: tr.querySelector('.descInput'),
      prodInput: tr.querySelector('.prodInput'),
      prodResults: tr.querySelector('.prodResults'),
      unit: tr.querySelector('.unitInput'),
      qty: tr.querySelector('.qtyInput'),
      price: tr.querySelector('.priceInput'),
      total: tr.querySelector('.totalCell'),
      remove: tr.querySelector('.removeBtn'),
    },
  };
  state.lines.push(line);

  attachAutocomplete({
    input: line.refs.prodInput,
    resultsEl: line.refs.prodResults,
    search: (term) => api.listProducts(term),
    render: (p) => `${esc(p.name)}<span class="code">${esc(p.code)}</span>`,
    onPick: (p) => {
      line.productId = p.id;
      line.refs.prodInput.value = p.name;
      if (!line.refs.desc.value.trim()) line.refs.desc.value = p.name;
    },
    floating: true,
  });
  line.refs.prodInput.addEventListener('input', () => {
    if (!line.refs.prodInput.value.trim()) line.productId = null;
  });

  ['qty', 'price'].forEach((key) => line.refs[key].addEventListener('input', recalc));

  line.refs.remove.addEventListener('click', () => {
    const i = state.lines.findIndex((l) => l.uid === line.uid);
    if (i >= 0) state.lines.splice(i, 1);
    tr.remove();
    if (line.refs.prodResults.parentElement === document.body) line.refs.prodResults.remove();
    recalc();
  });

  if (data) {
    line.refs.desc.value = data.description || '';
    line.refs.unit.value = data.unit || 'pcs';
    line.refs.qty.value = Number(data.quantity);
    line.refs.price.value = Number(data.unit_price);
    if (data.product_id) {
      api
        .getProduct(data.product_id)
        .then((p) => {
          line.refs.prodInput.value = p.name;
        })
        .catch(() => {});
    }
  }

  recalc();
  return line;
}

el('addRowBtn').addEventListener('click', () => addRow().refs.desc.focus());

function recalc() {
  const currency = el('currency').value;
  const ppn = num(el('ppnPercent').value);
  let subtotal = 0;
  let totalQty = 0;

  state.lines.forEach((line, i) => {
    const amount = round2(num(line.refs.qty.value) * num(line.refs.price.value));
    line.refs.lineNo.textContent = i + 1;
    line.refs.total.textContent = fmtMoney(amount, currency);
    subtotal += amount;
    totalQty += num(line.refs.qty.value);
  });

  const ppnAmount = round2((subtotal * ppn) / 100);
  el('sumSubtotal').textContent = fmtMoney(subtotal, currency);
  el('sumPpn').textContent = fmtMoney(ppnAmount, currency);
  el('sumTotal').textContent = `${currency} ${fmtMoney(round2(subtotal + ppnAmount), currency)}`;
  el('sumQty').textContent = fmtNum(totalQty);
  el('noRows').style.display = state.lines.length ? 'none' : 'block';
}

['ppnPercent'].forEach((id) => el(id).addEventListener('input', recalc));
el('currency').addEventListener('change', recalc);

/* -------------------------------------------------------------- save */

function buildPayload() {
  if (!state.supplier) throw new Error('Please select a supplier.');
  if (!state.lines.length) throw new Error('Add at least one material line.');

  const items = state.lines.map((line, i) => {
    const description = line.refs.desc.value.trim();
    if (!description) throw new Error(`Line ${i + 1}: enter a description.`);
    return {
      product_id: line.productId,
      description,
      unit: line.refs.unit.value.trim() || 'pcs',
      quantity: num(line.refs.qty.value),
      unit_price: num(line.refs.price.value),
    };
  });

  return {
    supplier_id: state.supplier.id,
    sales_order_id: state.salesOrder ? state.salesOrder.id : null,
    order_date: orNull(el('orderDate').value),
    expected_date: orNull(el('expectedDate').value),
    currency: el('currency').value,
    exchange_rate: num(el('exchangeRate').value) || 1,
    payment_terms: orNull(el('paymentTerms').value),
    ppn_percent: num(el('ppnPercent').value),
    notes: orNull(el('notes').value),
    items,
  };
}

async function save({ silent = false } = {}) {
  clearAlerts();
  try {
    const payload = buildPayload();
    const saved = state.id
      ? await api.updatePurchaseOrder(state.id, payload)
      : await api.createPurchaseOrder(payload);
    await applyPO(saved);
    if (!silent) showSuccess(`Saved as ${saved.po_no}.`);
    if (!new URLSearchParams(window.location.search).get('id')) {
      window.history.replaceState({}, '', `purchase-order-form.html?id=${saved.id}`);
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
    await applyPO(await api.setPurchaseOrderStatus(state.id, next));
    showSuccess(`${state.poNo} marked as ${label}.`);
  } catch (err) {
    showError(err.message);
  }
}

el('saveBtn').addEventListener('click', () => save());
el('sendBtn').addEventListener('click', async () => {
  if (state.status === 'draft' && state.id) await save({ silent: true });
  changeStatus('sent', 'sent');
});
el('receivedBtn').addEventListener('click', () => changeStatus('received', 'received'));
el('cancelBtn').addEventListener('click', () => {
  if (confirm('Cancel this purchase order?')) changeStatus('cancelled', 'cancelled');
});
el('pdfBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!state.id) return showError('Save the purchase order first.');
  try {
    await openPdf('purchaseOrder', state.id);
  } catch (err) {
    showError(err.message);
  }
});

/* --------------------------------------------------------- load/render */

async function applyPO(po) {
  state.id = po.id;
  state.status = po.status;
  state.poNo = po.po_no;
  state.createdBy = po.created_by;

  el('poNo').value = po.po_no;
  el('orderDate').value = po.order_date || '';
  el('expectedDate').value = po.expected_date || '';
  el('currency').value = po.currency;
  el('exchangeRate').value = Number(po.exchange_rate);
  el('paymentTerms').value = po.payment_terms || '';
  el('ppnPercent').value = Number(po.ppn_percent);
  el('notes').value = po.notes || '';

  state.supplier = { id: po.supplier_id, code: po.supplier_code, name: po.supplier_name };
  supplierInput.value = po.supplier_name || '';
  el('supplierHint').textContent = po.supplier_code ? `${po.supplier_code} — selected` : '';

  if (po.sales_order_id) {
    state.salesOrder = { id: po.sales_order_id, so_no: po.so_no };
    soInput.value = po.so_no || '';
    el('soHint').textContent = `Linked to ${po.so_no} — this cost counts toward that order's margin`;
  } else {
    state.salesOrder = null;
    soInput.value = '';
    el('soHint').textContent = 'Not linked — counts as general cost only';
  }

  state.lines.forEach((line) => {
    if (line.refs.prodResults.parentElement === document.body) line.refs.prodResults.remove();
  });
  state.lines = [];
  itemRows.innerHTML = '';
  (po.items || []).forEach((item) => addRow(item));

  el('pageTitle').textContent = `Purchase Order ${po.po_no}`;
  el('statusBadge').innerHTML = statusBadge(po.status);
  el('ownerNote').textContent = po.created_by_name ? `Created by ${po.created_by_name}` : '';
  document.title = `${po.po_no} · Q2O`;

  setReadonly(!['draft', 'sent'].includes(po.status) || !mayEdit());
  recalc();

  el('sumSubtotal').textContent = fmtMoney(po.subtotal, po.currency);
  el('sumPpn').textContent = fmtMoney(po.ppn_amount, po.currency);
  el('sumTotal').textContent = `${po.currency} ${fmtMoney(po.total, po.currency)}`;
  el('sumQty').textContent = fmtNum(po.total_qty);
}

const HEADER_FIELDS = [
  'orderDate', 'expectedDate', 'supplierInput', 'soInput', 'paymentTerms',
  'currency', 'exchangeRate', 'ppnPercent', 'notes',
];

function setReadonly(readonly) {
  HEADER_FIELDS.forEach((id) => (el(id).disabled = readonly));
  el('addRowBtn').disabled = readonly;
  state.lines.forEach((line) => {
    ['desc', 'prodInput', 'unit', 'qty', 'price'].forEach((k) => {
      line.refs[k].disabled = readonly;
    });
    line.refs.remove.disabled = readonly;
  });
  updateActions();
}

function updateActions() {
  const show = (id, visible) => {
    el(id).style.display = visible ? '' : 'none';
  };
  const s = state.status;
  const editable = mayEdit();
  const saved = Boolean(state.id);

  show('saveBtn', ['draft', 'sent'].includes(s) && editable);
  show('sendBtn', s === 'draft' && editable);
  show('receivedBtn', s === 'sent' && editable);
  show('pdfBtn', saved);
  show('cancelBtn', saved && editable && !['cancelled', 'received'].includes(s));

  const locked = el('lockedNote');
  if (saved && !editable) {
    locked.textContent =
      'Read-only: this purchase order belongs to another user. An admin can change it.';
    locked.style.display = '';
  } else {
    locked.style.display = 'none';
  }
}

/* ---------------------------------------------------------------- boot */

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('purchase-orders', user);

  const params = new URLSearchParams(window.location.search);
  const id = params.get('id');
  if (id) {
    try {
      await applyPO(await api.getPurchaseOrder(id));
    } catch (err) {
      showError(err.message);
    }
    return;
  }

  el('orderDate').value = todayISO();
  el('statusBadge').innerHTML = statusBadge('draft');

  // Arrived here from "Raise Purchase Order" on a sales order.
  const soId = params.get('sales_order_id');
  if (soId) {
    try {
      setSalesOrder(await api.getSalesOrder(soId));
    } catch (err) {
      /* the SO picker is optional - leave it blank */
    }
  }

  addRow();
  updateActions();
})();
