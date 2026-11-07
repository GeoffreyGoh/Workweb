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
//
// Rendered as cards rather than table rows: the two optional custom-unit
// groups (label + basis + factor each) don't fit in a table cell
// legibly, and most spareparts only ever use the simple qty-per-unit
// rule, so the custom-unit fields are visually secondary (smaller, under
// a sub-heading) rather than competing for space with name/price.

const BASIS_OPTIONS = [
  { value: '', label: '(not used)' },
  { value: 'quantity', label: 'Main quantity' },
  { value: 'width_cm', label: 'Width (cm)' },
  { value: 'height_cm', label: 'Height (cm)' },
  { value: 'measure', label: 'Measure (sqm/metre/panel billed)' },
];

const sparepartCardsEl = document.getElementById('sparepartCards');

function basisOptionsHtml(selected) {
  return BASIS_OPTIONS.map(
    (o) => `<option value="${o.value}" ${o.value === (selected || '') ? 'selected' : ''}>${esc(o.label)}</option>`
  ).join('');
}

function sparepartCardHtml(sp) {
  const name = sp ? sp.name : '';
  const price = sp ? sp.unit_price : 0;
  const qty = sp ? sp.qty_per_unit : 1;
  return `
    <div class="sparepart-card" style="border:1px solid var(--border); border-radius:6px; padding:10px; margin-bottom:8px">
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end">
        <div class="field" style="flex:2; min-width:160px">
          <label data-i18n="product.sparepartName">Name</label>
          <input type="text" class="spName" maxlength="100" value="${esc(name)}" required>
        </div>
        <div class="field" style="width:140px">
          <label data-i18n="product.unitPrice">Unit Price</label>
          <input type="number" class="spPrice num" min="0" step="0.01" value="${esc(price)}">
        </div>
        <div class="field" style="width:120px">
          <label data-i18n="product.sparepartQtyPerUnit">Qty per unit</label>
          <input type="number" class="spQty num" min="0.01" step="0.01" value="${esc(qty)}">
        </div>
        <button class="btn small danger" type="button" data-remove-sparepart>&times;</button>
      </div>
      <div class="hint" style="margin-top:6px" data-i18n="product.sparepartCustomUnitSubhead">
        Optional - use instead of Qty per unit when priced by a real measurement:
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:4px">
        ${sparepartCustomUnitHtml(1, sp)}
        ${sparepartCustomUnitHtml(2, sp)}
      </div>
    </div>`;
}

function sparepartCustomUnitHtml(n, sp) {
  const label = sp ? sp[`custom_unit_${n}_label`] : '';
  const basis = sp ? sp[`custom_unit_${n}_basis`] : '';
  const factor = sp ? sp[`custom_unit_${n}_factor`] : '';
  return `
    <div style="display:flex; gap:6px; align-items:flex-end; border-left:2px solid var(--border); padding-left:8px">
      <div class="field" style="width:120px">
        <label data-i18n="product.sparepartUnitLabel">Unit label</label>
        <input type="text" class="spCuLabel${n}" maxlength="30" value="${esc(label || '')}" placeholder="e.g. per m width">
      </div>
      <div class="field" style="width:150px">
        <label data-i18n="product.sparepartBasis">Based on</label>
        <select class="spCuBasis${n}">${basisOptionsHtml(basis)}</select>
      </div>
      <div class="field" style="width:100px">
        <label data-i18n="product.sparepartFactor">Factor</label>
        <input type="number" class="spCuFactor${n}" min="0" step="0.0001" value="${esc(factor || '')}" placeholder="e.g. 0.01">
      </div>
    </div>`;
}

function renderSpareparts(spareparts) {
  sparepartCardsEl.innerHTML = (spareparts || []).map(sparepartCardHtml).join('');
}

function readSpareparts() {
  return Array.from(sparepartCardsEl.querySelectorAll('.sparepart-card')).map((card) => {
    const readCustomUnit = (n) => {
      const label = card.querySelector(`.spCuLabel${n}`).value.trim();
      const basis = card.querySelector(`.spCuBasis${n}`).value;
      const factorRaw = card.querySelector(`.spCuFactor${n}`).value;
      // A custom unit only counts if it actually has a basis chosen -
      // a label typed without picking "Based on" is treated as unset
      // rather than silently defaulting to something, since there is
      // no safe guess for which measurement was intended.
      if (!basis) return { label: null, basis: null, factor: null };
      return {
        label: label || null,
        basis,
        factor: factorRaw === '' ? null : Number(factorRaw),
      };
    };
    const cu1 = readCustomUnit(1);
    const cu2 = readCustomUnit(2);
    return {
      name: card.querySelector('.spName').value.trim(),
      unit_price: Number(card.querySelector('.spPrice').value || 0),
      qty_per_unit: Number(card.querySelector('.spQty').value || 1),
      custom_unit_1_label: cu1.label,
      custom_unit_1_basis: cu1.basis,
      custom_unit_1_factor: cu1.factor,
      custom_unit_2_label: cu2.label,
      custom_unit_2_basis: cu2.basis,
      custom_unit_2_factor: cu2.factor,
      is_optional: true, // the only kind this form creates - see the clarify log
      is_active: true,
    };
  }).filter((sp) => sp.name); // drop a card left blank by mistake rather than reject the whole save
}

document.getElementById('addSparepartBtn').addEventListener('click', () => {
  sparepartCardsEl.insertAdjacentHTML('beforeend', sparepartCardHtml(null));
});

sparepartCardsEl.addEventListener('click', (event) => {
  const button = event.target.closest('[data-remove-sparepart]');
  if (!button) return;
  button.closest('.sparepart-card').remove();
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
