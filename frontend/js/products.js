/* Product catalogue - admin only.

   The catalogue is the price list every quotation is built from, so the API
   refuses writes from a normal user (403). This page is the admin's way in;
   `requireAdmin` below only hides what would be refused anyway. */

const PAGE_LIMIT = 500; // the API's ceiling - see products.list_products

const filters = { q: '', active_only: true };
let suppliers = [];

const rowsEl = document.getElementById('rows');
const errorEl = document.getElementById('error');
const successEl = document.getElementById('success');
const editorEl = document.getElementById('editor');
const formEl = document.getElementById('form');

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
function clearAlerts() {
  errorEl.classList.add('hidden');
  successEl.classList.add('hidden');
}

const PRICE_UNIT_KEYS = {
  per_sqm: 'perSqm',
  per_meter: 'perMeter',
  per_unit: 'perUnit',
};

function priceUnitLabel(unit) {
  const key = PRICE_UNIT_KEYS[unit];
  return key ? t(key) : unit;
}

/* ------------------------------------------------------------------ list */

async function load() {
  rowsEl.innerHTML = '<tr><td colspan="8" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listAllProducts({
      q: filters.q,
      active_only: filters.active_only,
      limit: PAGE_LIMIT,
    });

    if (!list.length) {
      rowsEl.innerHTML = `<tr><td colspan="8" class="empty">${esc(
        filters.q ? t('common.none') : t('product.none')
      )}</td></tr>`;
      document.getElementById('countNote').textContent = '';
      return;
    }

    // The API caps a page at PAGE_LIMIT, so say so rather than letting an
    // admin believe a product is missing when it is only off the page.
    document.getElementById('countNote').textContent =
      list.length === PAGE_LIMIT
        ? `${list.length}+ - narrow the list with search`
        : `${list.length} product(s)`;

    rowsEl.innerHTML = list
      .map(
        (p) => `
        <tr>
          <td class="mono"><strong>${esc(p.code)}</strong></td>
          <td>${esc(p.name)}</td>
          <td>${esc(p.category || '-')}</td>
          <td class="hint">${esc(priceUnitLabel(p.price_unit))}</td>
          <td class="right mono">${fmtMoney(p.unit_price)}</td>
          <td>${esc(p.supplier_name || '-')}</td>
          <td>${
            p.is_active
              ? `<span class="status status-approved">${esc(t('product.active'))}</span>`
              : `<span class="status status-cancelled">${esc(t('product.retired'))}</span>`
          }</td>
          <td class="right">
            <button class="btn small" data-edit="${p.id}" type="button">${esc(
              t('common.edit')
            )}</button>
          </td>
        </tr>`
      )
      .join('');
  } catch (err) {
    rowsEl.innerHTML =
      '<tr><td colspan="8" class="empty">Could not load the catalogue.</td></tr>';
    showError(err.message);
  }
}

/* ---------------------------------------------------------------- editor */

function fillSupplierOptions(selectedId) {
  const select = document.getElementById('fSupplierId');
  select.innerHTML =
    '<option value="">-</option>' +
    suppliers
      .map((s) => `<option value="${s.id}">${esc(s.code)} — ${esc(s.name)}</option>`)
      .join('');
  select.value = selectedId ? String(selectedId) : '';
}

function openEditor(product) {
  clearAlerts();
  editorEl.dataset.id = product ? product.id : '';
  document.getElementById('editorTitle').textContent = product
    ? t('product.edit')
    : t('product.new');

  const set = (id, value) => {
    document.getElementById(id).value = value === null || value === undefined ? '' : value;
  };

  set('fCode', product ? product.code : '');
  set('fName', product ? product.name : '');
  set('fCategory', product ? product.category : '');
  set('fPriceUnit', product ? product.price_unit : 'per_sqm');
  set('fPrice', product ? product.unit_price : 0);
  set('fMinW', product ? product.min_width_cm : '');
  set('fMaxW', product ? product.max_width_cm : '');
  set('fMinH', product ? product.min_height_cm : '');
  set('fMaxH', product ? product.max_height_cm : '');
  set('fDescription', product ? product.description : '');
  document.getElementById('fActive').checked = product ? product.is_active : true;
  fillSupplierOptions(product ? product.supplier_id : null);

  // Quotations and invoices store the code as a snapshot, but purchase-order
  // splitting and the catalogue import both match on it, so it stays put.
  const codeInput = document.getElementById('fCode');
  codeInput.readOnly = !!product;
  document.getElementById('codeNote').classList.toggle('hidden', !product);

  editorEl.classList.remove('hidden');
  (product ? document.getElementById('fName') : codeInput).focus();
}

function closeEditor() {
  editorEl.classList.add('hidden');
  editorEl.dataset.id = '';
}

/** Blank numeric inputs mean "no limit", which the API wants as null. */
function numOrNull(id) {
  const raw = document.getElementById(id).value.trim();
  return raw === '' ? null : Number(raw);
}

function readForm() {
  const supplier = document.getElementById('fSupplierId').value;
  return {
    code: document.getElementById('fCode').value.trim(),
    name: document.getElementById('fName').value.trim(),
    category: document.getElementById('fCategory').value.trim() || null,
    price_unit: document.getElementById('fPriceUnit').value,
    unit_price: Number(document.getElementById('fPrice').value || 0),
    min_width_cm: numOrNull('fMinW'),
    max_width_cm: numOrNull('fMaxW'),
    min_height_cm: numOrNull('fMinH'),
    max_height_cm: numOrNull('fMaxH'),
    description: document.getElementById('fDescription').value.trim() || null,
    is_active: document.getElementById('fActive').checked,
    supplier_id: supplier ? Number(supplier) : null,
  };
}

formEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  const id = editorEl.dataset.id;
  const body = readForm();
  const saveBtn = document.getElementById('saveBtn');
  saveBtn.disabled = true;

  try {
    if (id) {
      // The code is not editable, so leave it out of the update entirely.
      delete body.code;
      await api.updateProduct(id, body);
      showSuccess(t('product.saved'));
    } else {
      await api.createProduct(body);
      showSuccess(t('product.created'));
    }
    closeEditor();
    load();
  } catch (err) {
    showError(err.message);
  } finally {
    saveBtn.disabled = false;
  }
});

document.getElementById('cancelBtn').addEventListener('click', closeEditor);
document.getElementById('addBtn').addEventListener('click', () => openEditor(null));

rowsEl.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-edit]');
  if (!button) return;
  try {
    openEditor(await api.getProduct(button.dataset.edit));
    editorEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    showError(err.message);
  }
});

/* --------------------------------------------------------------- filters */

document.getElementById('fSearch').addEventListener(
  'input',
  debounce((event) => {
    filters.q = event.target.value.trim();
    load();
  }, 300)
);

document.getElementById('fRetired').addEventListener('change', (event) => {
  filters.active_only = !event.target.checked;
  load();
});

(async () => {
  const user = await requireLogin();
  if (!user) return;
  if (!requireAdmin(user, 'products')) return;
  renderTopbar('products', user);
  try {
    suppliers = await api.listAllSuppliers();
  } catch (e) {
    suppliers = []; // a supplier is optional on a product
  }
  load();
})();
