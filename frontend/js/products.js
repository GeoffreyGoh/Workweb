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
  rowsEl.innerHTML = '<tr><td colspan="7" class="empty">Loading...</td></tr>';
  try {
    const list = await api.listAllProducts({
      q: filters.q,
      active_only: filters.active_only,
      limit: PAGE_LIMIT,
    });

    if (!list.length) {
      rowsEl.innerHTML = `<tr><td colspan="7" class="empty">${esc(
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

    // Group by category so the catalogue reads as sections (Roller,
    // Curtain, ...) instead of one long alphabetical-by-name table -
    // easier to scan when picking a product's category also tells you
    // roughly what it is. A blank/missing category becomes its own
    // "Uncategorised" group rather than being silently dropped.
    const groups = new Map();
    list.forEach((p) => {
      const key = p.category || 'Uncategorised';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(p);
    });

    // Category order: alphabetical, with "Uncategorised" always last so a
    // data-entry gap doesn't visually jump to the top of the page.
    const categoryNames = Array.from(groups.keys()).sort((a, b) => {
      if (a === 'Uncategorised') return 1;
      if (b === 'Uncategorised') return -1;
      return a.localeCompare(b);
    });

    rowsEl.innerHTML = categoryNames
      .map((category) => {
        const rows = groups
          .get(category)
          .map(
            (p) => `
            <tr>
              <td class="mono"><strong>${esc(p.code)}</strong></td>
              <td>${esc(p.name)}</td>
              <td class="right mono">${fmtMoney(p.unit_price)}</td>
              <td class="hint">${esc(priceUnitLabel(p.price_unit))}</td>
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
        return `
          <tr class="category-row">
            <td colspan="7">${esc(category)} <span class="hint">(${groups.get(category).length})</span></td>
          </tr>
          ${rows}`;
      })
      .join('');
  } catch (err) {
    rowsEl.innerHTML =
      '<tr><td colspan="7" class="empty">Could not load the catalogue.</td></tr>';
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
  renderSpareparts(product ? product.spareparts : []);

  // Quotations and invoices store the code as a snapshot, but purchase-order
  // splitting and the catalogue import both match on it, so it stays put.
  const codeInput = document.getElementById('fCode');
  codeInput.readOnly = !!product;
  document.getElementById('codeNote').classList.toggle('hidden', !product);

  editorEl.classList.remove('hidden');
  (product ? document.getElementById('fName') : codeInput).focus();

  // Delete only makes sense for a product that already exists - a brand
  // new, unsaved one has nothing to delete yet.
  document.getElementById('deleteBtn').style.display = product ? '' : 'none';
}

function closeEditor() {
  editorEl.classList.add('hidden');
  editorEl.dataset.id = '';
}

/* ------------------------------------------------------------ spareparts */
// Each row is plain HTML inputs, not a data structure - readSpareparts()
// below reads the DOM directly when the form is submitted, matching how
// the rest of this form already works (readForm() does the same for the
// main fields).

const sparepartRowsEl = document.getElementById('sparepartRows');

function sparepartRowHtml(sp) {
  const name = sp ? sp.name : '';
  const price = sp ? sp.unit_price : 0;
  const qty = sp ? sp.qty_per_unit : 1;
  return `
    <tr>
      <td><input type="text" class="spName" maxlength="100" value="${esc(name)}" required></td>
      <td><input type="number" class="spPrice num" min="0" step="0.01" value="${esc(price)}"></td>
      <td><input type="number" class="spQty num" min="0.01" step="0.01" value="${esc(qty)}"></td>
      <td class="right"><button class="btn small danger" type="button" data-remove-sparepart>&times;</button></td>
    </tr>`;
}

function renderSpareparts(spareparts) {
  sparepartRowsEl.innerHTML = (spareparts || []).map(sparepartRowHtml).join('');
}

function readSpareparts() {
  return Array.from(sparepartRowsEl.querySelectorAll('tr')).map((row) => ({
    name: row.querySelector('.spName').value.trim(),
    unit_price: Number(row.querySelector('.spPrice').value || 0),
    qty_per_unit: Number(row.querySelector('.spQty').value || 1),
    is_optional: true, // the only kind this form creates - see the clarify log
    is_active: true,
  })).filter((sp) => sp.name); // drop a row left blank by mistake rather than reject the whole save
}

document.getElementById('addSparepartBtn').addEventListener('click', () => {
  sparepartRowsEl.insertAdjacentHTML('beforeend', sparepartRowHtml(null));
});

sparepartRowsEl.addEventListener('click', (event) => {
  const button = event.target.closest('[data-remove-sparepart]');
  if (!button) return;
  button.closest('tr').remove();
});

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
    spareparts: readSpareparts(),
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

document.getElementById('deleteBtn').addEventListener('click', async () => {
  const id = editorEl.dataset.id;
  if (!id) return;
  const name = document.getElementById('fName').value;

  // A real confirm() dialog, not a one-click action - this is a hard,
  // irreversible delete (unlike "Active = false", which just hides it),
  // so the extra click is deliberate friction against a misclick.
  if (!confirm(`Permanently delete "${name}"? This cannot be undone.`)) return;

  try {
    await api.deleteProduct(id);
    closeEditor();
    showSuccess(t('product.deleted'));
    load();
  } catch (err) {
    // The 409 case (already used on a document) comes back with a
    // specific, readable server message - show it as-is rather than a
    // generic failure, since it tells the admin exactly what to do
    // instead (retire it, don't delete it).
    showError(err.message);
  }
});

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
