/* =====================================================================
   Delivery note (Surat Jalan).

   Lines are not free-form: they are the invoice's lines, each capped
   at what is still outstanding. The server enforces the cap too.
   ===================================================================== */

const state = {
  id: null,
  status: 'draft',
  sjNo: null,
  salesOrderId: null,
  createdBy: null,
  lines: [],       // { orderItemId, ordered, alreadySent, outstanding, refs }
};

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

function mayEdit() {
  const user = Auth.user;
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (state.id === null) return true;
  return state.createdBy === user.id;
}

/* -------------------------------------------------------------- lines */

function sizeText(line) {
  if (line.width_cm && line.height_cm) {
    return `${fmtNum(line.width_cm)} &times; ${fmtNum(line.height_cm)}`;
  }
  if (line.width_cm) return fmtNum(line.width_cm);
  return '-';
}

/**
 * Draw the goods table.
 *
 * A line the note does not carry starts at 0, never at its full outstanding
 * quantity. Defaulting it to the maximum meant that dropping a line to 0 and
 * saving again silently put it back and shipped goods nobody asked for.
 * The server prefills a new note, so the "deliver everything" case is
 * already covered by `onNote`.
 *
 * @param outstanding rows from /delivery-notes/outstanding/{so}
 * @param onNote      quantity already on THIS note, keyed by order line id
 */
function renderLines(outstanding, onNote = {}) {
  state.lines = [];
  itemRows.innerHTML = '';

  outstanding.forEach((line, index) => {
    const mine = onNote[line.sales_order_item_id];
    // Editing an existing note: its own quantity is available again.
    const capacity = Number(line.outstanding) + Number(mine || 0);
    if (capacity <= 0 && mine === undefined) return;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="mono">${index + 1}</td>
      <td><strong>${esc(line.product_name)}</strong><br><span class="hint">${esc(line.product_code)}</span></td>
      <td class="hint">${esc(line.description || '-')}</td>
      <td class="right mono">${sizeText(line)}</td>
      <td class="right mono">${fmtNum(line.ordered)}</td>
      <td class="right mono">${fmtNum(Number(line.delivered) - Number(mine || 0))}</td>
      <td class="right mono capacity">${fmtNum(capacity)}</td>
      <td><input type="number" class="num qtyInput" min="0" step="0.01"
                 max="${capacity}" value="${mine !== undefined ? Number(mine) : 0}"></td>
      <td><input type="text" class="unitInput" value="pcs"></td>
    `;
    itemRows.appendChild(tr);

    const entry = {
      orderItemId: line.sales_order_item_id,
      capacity,
      refs: {
        qty: tr.querySelector('.qtyInput'),
        unit: tr.querySelector('.unitInput'),
      },
    };
    entry.refs.qty.addEventListener('input', () => {
      // Flag an over-delivery before the server has to.
      entry.refs.qty.classList.toggle('invalid', num(entry.refs.qty.value) > capacity);
      recalc();
    });
    state.lines.push(entry);
  });

  if (!state.lines.length) {
    itemRows.innerHTML =
      '<tr><td colspan="9" class="empty">Nothing left to deliver on this order.</td></tr>';
  }
  recalc();
}

function recalc() {
  const total = state.lines.reduce((sum, line) => sum + num(line.refs.qty.value), 0);
  el('sumQty').textContent = fmtNum(total);
}

/* -------------------------------------------------------------- save */

function buildPayload() {
  const items = state.lines
    .filter((line) => num(line.refs.qty.value) > 0)
    .map((line) => ({
      sales_order_item_id: line.orderItemId,
      quantity: num(line.refs.qty.value),
      unit: line.refs.unit.value.trim() || 'pcs',
    }));

  if (!items.length) throw new Error('Enter a quantity for at least one line.');

  const over = state.lines.find((line) => num(line.refs.qty.value) > line.capacity);
  if (over) throw new Error('One or more quantities exceed what is still outstanding.');

  return {
    delivery_date: orNull(el('deliveryDate').value),
    deliver_to: orNull(el('deliverTo').value),
    deliver_address: orNull(el('deliverAddress').value),
    phone: orNull(el('phone').value),
    time_slot: orNull(el('timeSlot').value),
    vehicle_no: orNull(el('vehicleNo').value),
    driver_name: orNull(el('driverName').value),
    notes: orNull(el('notes').value),
    items,
  };
}

async function save({ silent = false } = {}) {
  clearAlerts();
  try {
    const payload = buildPayload();
    const saved = state.id
      ? await api.updateDeliveryNote(state.id, payload)
      : await api.createDeliveryNote({ ...payload, sales_order_id: state.salesOrderId });

    await applyNote(saved);
    if (!silent) showSuccess(`Saved as ${saved.sj_no}.`);
    if (!new URLSearchParams(window.location.search).get('id')) {
      window.history.replaceState({}, '', `delivery-note-form.html?id=${saved.id}`);
    }
    return saved;
  } catch (err) {
    showError(err.message);
    return null;
  }
}

async function changeStatus(next, label, extra = {}) {
  clearAlerts();
  try {
    if (!state.id && !(await save({ silent: true }))) return null;
    const updated = await api.setDeliveryNoteStatus(state.id, { status: next, ...extra });
    await applyNote(updated);
    showSuccess(`${state.sjNo} marked as ${label}.`);
    return updated;
  } catch (err) {
    showError(err.message);
    return null;
  }
}

el('saveBtn').addEventListener('click', () => save());

el('issueBtn').addEventListener('click', async () => {
  if (state.status === 'draft' && state.id) await save({ silent: true });
  if (await changeStatus('issued', 'issued')) {
    try {
      await openPdf('deliveryNote', state.id);
    } catch (err) {
      showError(err.message);
    }
  }
});

el('deliveredBtn').addEventListener('click', () =>
  changeStatus('delivered', 'delivered', {
    received_by: orNull(el('receivedBy').value),
    received_at: orNull(el('receivedAt').value),
  })
);

el('cancelBtn').addEventListener('click', () => {
  if (confirm('Cancel this delivery note? The goods go back on the outstanding list.')) {
    changeStatus('cancelled', 'cancelled');
  }
});

el('pdfBtn').addEventListener('click', async () => {
  clearAlerts();
  if (!state.id) return showError('Save the delivery note first.');
  try {
    await openPdf('deliveryNote', state.id);
  } catch (err) {
    showError(err.message);
  }
});

/* --------------------------------------------------------- load/render */

async function applyNote(note) {
  state.id = note.id;
  state.status = note.status;
  state.sjNo = note.sj_no;
  state.salesOrderId = note.sales_order_id;
  state.createdBy = note.created_by;

  el('sjNo').value = note.sj_no;
  el('deliveryDate').value = note.delivery_date || '';
  el('deliverTo').value = note.deliver_to || '';
  el('deliverAddress').value = note.deliver_address || '';
  el('phone').value = note.phone || '';
  el('timeSlot').value = note.time_slot || '';
  el('vehicleNo').value = note.vehicle_no || '';
  el('driverName').value = note.driver_name || '';
  el('notes').value = note.notes || '';
  el('receivedBy').value = note.received_by || '';
  el('receivedAt').value = note.received_at || '';

  el('pageTitle').textContent = `${t('sj.list')} ${note.sj_no}`;
  el('statusBadge').innerHTML = statusBadge(note.status);
  el('ownerNote').textContent = note.created_by_name ? `Created by ${note.created_by_name}` : '';
  document.title = `${note.sj_no} · Q2O`;

  const link = el('orderLink');
  link.innerHTML =
    `For invoice <a href="sales-order-form.html?id=${note.sales_order_id}">` +
    `<strong>${esc(note.so_no || '')}</strong></a> — ${esc(note.customer_name || '')}`;
  link.style.display = '';

  // Rebuild the table against the order's live outstanding figures.
  const outstanding = await api.deliveryStatus(note.sales_order_id);
  const onNote = {};
  (note.items || []).forEach((item) => {
    onNote[item.sales_order_item_id] = Number(item.quantity);
  });
  renderLines(outstanding.lines, onNote);
  (note.items || []).forEach((item) => {
    const line = state.lines.find((l) => l.orderItemId === item.sales_order_item_id);
    if (line) line.refs.unit.value = item.unit;
  });
  recalc();

  setReadonly(!['draft', 'issued'].includes(note.status) || !mayEdit());
}

const HEADER_FIELDS = [
  'deliveryDate', 'timeSlot', 'deliverTo', 'deliverAddress', 'phone',
  'vehicleNo', 'driverName', 'notes',
];

function setReadonly(readonly) {
  HEADER_FIELDS.forEach((id) => (el(id).disabled = readonly));
  state.lines.forEach((line) => {
    line.refs.qty.disabled = readonly;
    line.refs.unit.disabled = readonly;
  });
  ['receivedBy', 'receivedAt'].forEach((id) => {
    el(id).disabled = state.status === 'delivered' ? true : !mayEdit();
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

  show('saveBtn', ['draft', 'issued'].includes(s) && editable);
  show('issueBtn', s === 'draft' && editable);
  show('deliveredBtn', s === 'issued' && editable);
  show('pdfBtn', saved);
  show('cancelBtn', saved && editable && !['cancelled', 'delivered'].includes(s));

  el('receiptCard').style.display = ['issued', 'delivered'].includes(s) ? '' : 'none';

  const locked = el('lockedNote');
  if (saved && !editable) {
    locked.textContent =
      'Read-only: this delivery note belongs to another user. An admin can change it.';
    locked.style.display = '';
  } else {
    locked.style.display = 'none';
  }
}

/* ---------------------------------------------------------------- boot */

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('delivery-notes', user);

  const params = new URLSearchParams(window.location.search);
  const id = params.get('id');

  if (id) {
    try {
      await applyNote(await api.getDeliveryNote(id));
    } catch (err) {
      showError(err.message);
    }
    return;
  }

  // Arrived from "Create Delivery Note" on an invoice.
  const soId = params.get('sales_order_id');
  if (!soId) {
    showError('Open a confirmed invoice and choose "Create Delivery Note".');
    return;
  }

  try {
    const note = await api.deliveryNoteFromOrder(soId);
    window.location.replace(`delivery-note-form.html?id=${note.id}`);
  } catch (err) {
    showError(err.message);
    el('statusBadge').innerHTML = statusBadge('draft');
  }
})();
