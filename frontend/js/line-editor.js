/* =====================================================================
   Shared line-item table for quotations and invoices - both price
   lines identically, so they share this editor.

   Totals computed here are a live preview only; the API recalculates on
   save and its response overwrites the display.
   ===================================================================== */

const LINE_ROW_HTML = `
  <td class="mono lineNo"></td>
  <td>
    <div class="autocomplete">
      <input type="text" class="prodInput" placeholder="Search product..." autocomplete="off">
      <div class="results hidden prodResults"></div>
    </div>
    <span class="hint prodCode"></span>
  </td>
  <td>
    <input type="text" class="descInput" placeholder="Optional">
    <div class="components hidden"></div>
  </td>
  <td><input type="number" class="num qtyInput" value="1" min="0" step="0.01"></td>
  <td><input type="number" class="num widthInput" min="0" step="0.1"></td>
  <td><input type="number" class="num heightInput" min="0" step="0.1"></td>
  <td class="right mono measureCell">0</td>
  <td><input type="number" class="num priceInput" min="0" step="1"></td>
  <td><input type="number" class="num discInput" min="0" max="100" step="0.01"></td>
  <td class="right mono totalCell">0</td>
  <td class="right mono netCell">0</td>
  <td class="center"><button class="btn icon removeBtn" type="button" title="Remove line">&times;</button></td>
`;

/**
 * @param tbody      <tbody> that holds the rows
 * @param emptyEl    element shown when there are no rows
 * @param addBtn     "add line" button
 * @param headerState () => ({ discount, currency }) - the header values
 * @param onChange   called after any recalculation, with the running totals
 */
function createLineEditor({ tbody, emptyEl, addBtn, headerState, onChange }) {
  const lines = [];
  let seq = 0;
  let readonly = false;

  const num = (v) => {
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  };
  const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

  function computeLine(line, headerDiscount) {
    if (!line.product) {
      return { measure: 0, lineTotal: 0, discount: 0, net: 0, qty: num(line.refs.qty.value) };
    }
    const qty = num(line.refs.qty.value);
    const width = num(line.refs.width.value);
    const height = num(line.refs.height.value);
    const price = num(line.refs.price.value);

    let measure = 0;
    if (line.product.price_unit === 'per_sqm') measure = (width / 100) * (height / 100) * qty;
    else if (line.product.price_unit === 'per_meter') measure = (width / 100) * qty;
    else measure = qty;

    const discText = line.refs.disc.value.trim();
    const pct = discText === '' ? headerDiscount : num(discText);
    const lineTotal = round2(measure * price);
    const discount = round2((lineTotal * pct) / 100);
    return { measure, lineTotal, discount, net: round2(lineTotal - discount), qty };
  }

  function markDimensions(line) {
    if (!line.product) return;
    const check = (input, min, max) => {
      const value = num(input.value);
      const bad =
        !input.disabled &&
        value > 0 &&
        ((min !== null && min !== undefined && value < Number(min)) ||
          (max !== null && max !== undefined && value > Number(max)));
      input.classList.toggle('invalid', Boolean(bad));
    };
    check(line.refs.width, line.product.min_width_cm, line.product.max_width_cm);
    check(line.refs.height, line.product.min_height_cm, line.product.max_height_cm);
  }

  function recalc() {
    const { discount: headerDiscount, currency } = headerState();
    let subtotal = 0;
    let discountTotal = 0;
    let totalQty = 0;

    lines.forEach((line, i) => {
      const calc = computeLine(line, headerDiscount);
      line.refs.lineNo.textContent = i + 1;
      line.refs.measure.textContent = fmtNum(calc.measure, 4);
      line.refs.total.textContent = fmtMoney(calc.lineTotal, currency);
      line.refs.net.textContent = fmtMoney(calc.net, currency);
      line.refs.disc.placeholder = String(headerDiscount);
      markDimensions(line);

      subtotal += calc.lineTotal;
      discountTotal += calc.discount;
      totalQty += calc.qty;
    });

    const netto = round2(subtotal - discountTotal);
    if (emptyEl) emptyEl.style.display = lines.length ? 'none' : 'block';
    if (onChange) onChange({ subtotal, discountTotal, netto, totalQty, currency });
  }

  function selectProduct(line, product, { resetPrice = false } = {}) {
    line.product = product;
    line.refs.prodInput.value = product.name;

    const ranges = [];
    if (product.min_width_cm || product.max_width_cm) {
      ranges.push(`W ${fmtNum(product.min_width_cm || 0)}-${fmtNum(product.max_width_cm || '∞')}`);
    }
    if (product.min_height_cm || product.max_height_cm) {
      ranges.push(`H ${fmtNum(product.min_height_cm || 0)}-${fmtNum(product.max_height_cm || '∞')}`);
    }
    line.refs.prodCode.textContent =
      `${product.code} · ${product.price_unit}` + (ranges.length ? ` · ${ranges.join(' ')} cm` : '');

    if (resetPrice) line.refs.price.value = Number(product.unit_price);
    renderComponents(line, product);

    const needsWidth = product.price_unit === 'per_sqm' || product.price_unit === 'per_meter';
    const needsHeight = product.price_unit === 'per_sqm';
    line.refs.width.disabled = !needsWidth || readonly;
    line.refs.height.disabled = !needsHeight || readonly;
    if (!needsWidth) line.refs.width.value = '';
    if (!needsHeight) line.refs.height.value = '';

    recalc();
  }

  /**
   * Show a dropdown per option group the fabric can be made in.
   *
   * The compatibility matrix (FABRIC CHART) already excludes combinations the
   * mill will not make, so a group with no available option simply does not
   * appear rather than offering something that cannot be produced.
   */
  function renderComponents(line, product) {
    const box = line.refs.components;
    const options = (product && product.options) || [];
    if (!options.length) {
      box.innerHTML = '';
      box.classList.add('hidden');
      line.componentSelects = [];
      return;
    }

    const groups = {};
    options.forEach((o) => {
      (groups[o.option_group] = groups[o.option_group] || []).push(o.option_name);
    });

    box.innerHTML =
      `<div class="components-label">${esc(t('quotation.componentsHint'))}</div>` +
      Object.entries(groups)
        .map(
          ([group, names]) => `
          <label class="component">
            <span>${esc(group)}</span>
            <select data-group="${esc(group)}">
              <option value="">&mdash;</option>
              ${names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('')}
            </select>
          </label>`
        )
        .join('');
    box.classList.remove('hidden');
    line.componentSelects = Array.from(box.querySelectorAll('select'));
    line.componentSelects.forEach((sel) => sel.addEventListener('change', recalc));
  }

  /** "Roller: Standard Roll | Bottom Rail: Flat" */
  function readComponents(line) {
    const chosen = (line.componentSelects || [])
      .filter((sel) => sel.value)
      .map((sel) => `${sel.dataset.group}: ${sel.value}`);
    return chosen.length ? chosen.join(' | ') : null;
  }

  function writeComponents(line, text) {
    if (!text) return;
    const wanted = {};
    text.split('|').forEach((part) => {
      const bits = part.split(':');
      const group = (bits[0] || '').trim();
      const value = (bits[1] || '').trim();
      if (group && value) wanted[group] = value;
    });
    (line.componentSelects || []).forEach((sel) => {
      if (wanted[sel.dataset.group] !== undefined) sel.value = wanted[sel.dataset.group];
    });
  }

  function applyLineData(line, data) {
    // A saved line carries only a product snapshot, so show that at once...
    selectProduct(
      line,
      {
        id: data.product_id,
        code: data.product_code,
        name: data.product_name,
        price_unit: data.price_unit,
        unit_price: data.unit_price,
      },
      { resetPrice: false }
    );

    line.refs.desc.value = data.description || '';
    line.refs.qty.value = Number(data.quantity);
    line.refs.width.value = data.width_cm === null ? '' : Number(data.width_cm);
    line.refs.height.value = data.height_cm === null ? '' : Number(data.height_cm);
    line.refs.price.value = Number(data.unit_price);
    line.refs.disc.value = data.line_discount_pct === null ? '' : Number(data.line_discount_pct);

    // ...then fetch the master so the min/max range check works on reload too.
    api
      .getProduct(data.product_id)
      .then((product) => {
        if (!line.product || line.product.id !== product.id) return;
        selectProduct(line, product, { resetPrice: false });
        line.refs.price.value = Number(data.unit_price); // keep any manual override
        writeComponents(line, data.component_options);
        recalc();
      })
      .catch(() => {
        /* deleted product - the snapshot still displays fine */
      });
  }

  function setRowReadonly(line, flag) {
    ['prodInput', 'desc', 'qty', 'width', 'height', 'price', 'disc'].forEach((key) => {
      line.refs[key].disabled = flag;
    });
    line.refs.remove.disabled = flag;
    (line.componentSelects || []).forEach((sel) => (sel.disabled = flag));
    if (!flag && line.product) {
      const unit = line.product.price_unit;
      line.refs.width.disabled = !(unit === 'per_sqm' || unit === 'per_meter');
      line.refs.height.disabled = unit !== 'per_sqm';
    }
  }

  function addRow(data) {
    const tr = document.createElement('tr');
    tr.innerHTML = LINE_ROW_HTML;
    tbody.appendChild(tr);

    const line = {
      uid: ++seq,
      tr,
      product: null,
      refs: {
        lineNo: tr.querySelector('.lineNo'),
        prodInput: tr.querySelector('.prodInput'),
        prodResults: tr.querySelector('.prodResults'),
        prodCode: tr.querySelector('.prodCode'),
        desc: tr.querySelector('.descInput'),
        components: tr.querySelector('.components'),
        qty: tr.querySelector('.qtyInput'),
        width: tr.querySelector('.widthInput'),
        height: tr.querySelector('.heightInput'),
        measure: tr.querySelector('.measureCell'),
        price: tr.querySelector('.priceInput'),
        disc: tr.querySelector('.discInput'),
        total: tr.querySelector('.totalCell'),
        net: tr.querySelector('.netCell'),
        remove: tr.querySelector('.removeBtn'),
      },
    };
    lines.push(line);

    attachAutocomplete({
      input: line.refs.prodInput,
      resultsEl: line.refs.prodResults,
      search: (term) => api.listProducts(term),
      render: (p) =>
        `${esc(p.name)}<span class="code">${esc(p.code)} · ${esc(p.price_unit)} · ${fmtMoney(
          p.unit_price
        )}</span>`,
      onPick: (p) => selectProduct(line, p, { resetPrice: true }),
      floating: true,
    });

    ['qty', 'width', 'height', 'price', 'disc'].forEach((key) =>
      line.refs[key].addEventListener('input', recalc)
    );

    line.refs.remove.addEventListener('click', () => {
      const i = lines.findIndex((l) => l.uid === line.uid);
      if (i >= 0) lines.splice(i, 1);
      tr.remove();
      if (line.refs.prodResults.parentElement === document.body) {
        line.refs.prodResults.remove(); // floating dropdowns live on <body>
      }
      recalc();
    });

    if (data) applyLineData(line, data);
    if (readonly) setRowReadonly(line, true);

    recalc();
    return line;
  }

  function clear() {
    lines.forEach((line) => {
      if (line.refs.prodResults.parentElement === document.body) line.refs.prodResults.remove();
    });
    lines.length = 0;
    tbody.innerHTML = '';
  }

  function setReadonly(flag) {
    readonly = flag;
    if (addBtn) addBtn.disabled = flag;
    lines.forEach((line) => setRowReadonly(line, flag));
  }

  /** Payload items. Throws with a readable message if a row is incomplete. */
  function getItems() {
    if (!lines.length) throw new Error('Add at least one line item.');
    return lines.map((line, i) => {
      if (!line.product) throw new Error(`Line ${i + 1}: pick a product.`);
      return {
        product_id: line.product.id,
        description: line.refs.desc.value.trim() || null,
        quantity: num(line.refs.qty.value),
        width_cm: line.refs.width.value === '' ? null : num(line.refs.width.value),
        height_cm: line.refs.height.value === '' ? null : num(line.refs.height.value),
        unit_price: line.refs.price.value === '' ? null : num(line.refs.price.value),
        line_discount_pct:
          line.refs.disc.value.trim() === '' ? null : num(line.refs.disc.value),
        component_options: readComponents(line),
      };
    });
  }

  if (addBtn) {
    addBtn.addEventListener('click', () => addRow().refs.prodInput.focus());
  }

  return { lines, addRow, clear, setReadonly, getItems, recalc, count: () => lines.length };
}

/** The <thead> markup that matches LINE_ROW_HTML. */
const LINE_TABLE_HEAD = `
  <tr>
    <th style="width:34px">#</th>
    <th style="min-width:220px">Product</th>
    <th style="min-width:150px">Description</th>
    <th class="right" style="width:80px">Qty</th>
    <th class="right" style="width:90px">Width cm</th>
    <th class="right" style="width:90px">Height cm</th>
    <th class="right" style="width:78px">Measure</th>
    <th class="right" style="width:120px">Unit Price</th>
    <th class="right" style="width:76px">Disc %</th>
    <th class="right" style="width:120px">Line Total</th>
    <th class="right" style="width:120px">Net</th>
    <th style="width:36px"></th>
  </tr>
`;
