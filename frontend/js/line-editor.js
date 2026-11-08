/* =====================================================================
   Shared line-item table for quotations and invoices - both price
   lines identically, so they share this editor.

   Totals computed here are a live preview only; the API recalculates on
   save and its response overwrites the display.
   ===================================================================== */

// Same mapping as pdf.py's UNIT_LABEL - shown next to the Measure
// number so "0.8800" on screen reads as an area/length/count rather
// than a bare, unexplained number. per_sqm and per_sqm_min1m both
// measure in square metres; per_meter and per_curtain_panel in running
// metres; per_unit is a plain count with no physical unit.
const MEASURE_UNIT_LABEL = {
  per_sqm: 'm²', per_sqm_min1m: 'm²',
  per_meter: 'm', per_curtain_panel: 'm',
  per_unit: 'pcs',
};

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
  // Maps a saved line's server-assigned line_no -> the frontend row's uid,
  // rebuilt as each row is added during a load. A sparepart row's saved
  // parent_line_no is resolved through this map (see applySparepartData) -
  // it only works because items always arrive in line_no order and a
  // sparepart's parent always has a lower line_no, so the parent's row
  // exists in this map before the sparepart row needs it.
  let lineNoToUid = {};

  const num = (v) => {
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  };
  const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

  /**
   * Which dimension inputs a price_unit needs.
   *
   * Single source of truth for this - previously duplicated separately in
   * selectProduct() and setRowReadonly(), and the second copy was missed
   * when per_sqm_min1m/per_curtain_panel were added to pricing.py, which
   * silently disabled and blanked Width/Height for every product using
   * either formula (blinds and curtains - most of the real catalogue).
   * Must stay in sync with pricing.compute_measure's price_unit branches.
   */
  function dimensionsNeeded(priceUnit) {
    return {
      width: ['per_sqm', 'per_meter', 'per_sqm_min1m', 'per_curtain_panel'].includes(priceUnit),
      height: ['per_sqm', 'per_sqm_min1m', 'per_curtain_panel'].includes(priceUnit),
    };
  }

  function computeLine(line, headerDiscount) {
    if (line.isSparepart) {
      // A sparepart has no dimensions and no catalogue product - billed
      // flat as quantity x its own price, same discount rule as any line.
      const qty = num(line.refs.qty.value);
      const price = num(line.refs.price.value);
      const discText = line.refs.disc.value.trim();
      const pct = discText === '' ? headerDiscount : num(discText);
      const lineTotal = round2(qty * price);
      const discount = round2((lineTotal * pct) / 100);
      return { measure: qty, lineTotal, discount, net: round2(lineTotal - discount), qty };
    }
    if (!line.product) {
      return { measure: 0, lineTotal: 0, discount: 0, net: 0, qty: num(line.refs.qty.value) };
    }
    const qty = num(line.refs.qty.value);
    const width = num(line.refs.width.value);
    const height = num(line.refs.height.value);
    const price = num(line.refs.price.value);

    let measure = 0;
    if (line.product.price_unit === 'per_sqm') {
      // Minimum is a pricing floor for every unit now, not just
      // per_sqm_min1m - mirrors pricing.compute_measure on the backend.
      const widthM = Math.max(width, Number(line.product.min_width_cm) || 0) / 100;
      const heightM = Math.max(height, Number(line.product.min_height_cm) || 0) / 100;
      measure = widthM * heightM * qty;
    } else if (line.product.price_unit === 'per_meter') {
      const widthM = Math.max(width, Number(line.product.min_width_cm) || 0) / 100;
      measure = widthM * qty;
    } else if (line.product.price_unit === 'per_sqm_min1m') {
      // "RUMUS BLINDS" - mirrors pricing.compute_measure: each side
      // floored at the PRODUCT's own configured minimum (min_width_cm/
      // min_height_cm), falling back to 1m/100cm only when the product
      // has no minimum set. Must stay in sync with the backend formula -
      // this is a live preview only, the server's number is what saves.
      const widthFloor = line.product.min_width_cm != null ? Number(line.product.min_width_cm) : 100;
      const heightFloor = line.product.min_height_cm != null ? Number(line.product.min_height_cm) : 100;
      const widthM = Math.max(width, widthFloor) / 100;
      const heightM = Math.max(height, heightFloor) / 100;
      measure = widthM * heightM * qty;
    } else if (line.product.price_unit === 'per_curtain_panel') {
      // "RUMUS GORDEN" - mirrors pricing.compute_measure exactly, including
      // the half-metre rounding, so this live preview matches what the
      // server actually saves rather than just being a rough estimate.
      // Width is floored the same as every other unit before the panel
      // count is derived from it.
      //
      // Guard: the formula has a fixed +0.4m belt/strap allowance and
      // rounds UP to the nearest half-metre, so even width=0/height=0
      // (a brand new, not-yet-filled-in row) computes a phantom 0.5m -
      // Geoffrey caught this showing up as a default-looking "0.5 m²"
      // before anything was typed. Width is required for this price
      // unit (see validate_dimensions), so until it's actually > 0
      // there is nothing real to measure yet.
      if (width <= 0) {
        measure = 0;
      } else {
        const flooredWidth = Math.max(width, Number(line.product.min_width_cm) || 0);
        let panels = Math.ceil(flooredWidth / 60);
        const fabricWidth = Number(line.product.fabric_width_cm) || 0;
        if (fabricWidth >= 280) panels = Math.ceil(panels / 2);
        const heightM = height / 100;
        const rawMetres = (heightM + 0.3) * panels + 0.4;
        measure = Math.ceil(rawMetres / 0.5) * 0.5 * qty;
      }
    } else {
      measure = qty;
    }

    const discText = line.refs.disc.value.trim();
    const pct = discText === '' ? headerDiscount : num(discText);
    const lineTotal = round2(measure * price);
    const discount = round2((lineTotal * pct) / 100);
    return { measure, lineTotal, discount, net: round2(lineTotal - discount), qty };
  }

  function markDimensions(line) {
    if (!line.product) return;
    // The minimum is a pricing floor for every unit, never an input
    // restriction - see pricing.compute_measure/validate_dimensions on
    // the backend - so the minimum side of this check never flags
    // "invalid" for any price unit. The maximum still flags normally.
    const check = (input, max) => {
      const value = num(input.value);
      const bad =
        !input.disabled &&
        value > 0 &&
        max !== null && max !== undefined && value > Number(max);
      input.classList.toggle('invalid', Boolean(bad));
    };
    check(line.refs.width, line.product.max_width_cm);
    check(line.refs.height, line.product.max_height_cm);
  }

  function recalc() {
    const { discount: headerDiscount, currency } = headerState();
    let subtotal = 0;
    let discountTotal = 0;
    let totalQty = 0;

    // line_no is just the row's 1-based position - matches the server's
    // own numbering (see routers' _apply_items), which is what lets a
    // sparepart's parent_line_no line up correctly once this is submitted.
    lineNoToUid = {};
    lines.forEach((line, i) => {
      lineNoToUid[i + 1] = line.uid;
    });

    lines.forEach((line, i) => {
      const calc = computeLine(line, headerDiscount);
      line.refs.lineNo.textContent = i + 1;
      line.refs.measure.textContent = line.product
        ? `${fmtNum(calc.measure, 4)} ${MEASURE_UNIT_LABEL[line.product.price_unit] || ''}`.trim()
        : fmtNum(calc.measure, 4);
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

    // Just the product name in the field itself now - no code/price-unit/
    // size-range hint cluttering the row. Dimension LIMITS are still
    // enforced (see markDimensions below); this only removes the extra
    // text that used to display alongside the name.
    line.refs.prodCode.textContent = '';

    // Auto-fill the line's own Description box from the product
    // catalogue's Description - same idea as Code/Category already
    // existing as product-level fields; a salesperson can still edit or
    // clear it by hand, this is just a starting point. Only on a fresh
    // pick (resetPrice=true), not when re-applying a saved line - a
    // saved line's description was something the salesperson typed (or
    // deliberately left blank) and must not be silently overwritten by
    // the catalogue text on every page load.
    if (resetPrice) {
      line.refs.desc.value = product.description || '';
    }

    if (resetPrice) line.refs.price.value = Number(product.unit_price);
    renderComponents(line, product);

    const { width: needsWidth, height: needsHeight } = dimensionsNeeded(product.price_unit);
    line.refs.width.disabled = !needsWidth || readonly;
    line.refs.height.disabled = !needsHeight || readonly;
    if (!needsWidth) line.refs.width.value = '';
    if (!needsHeight) line.refs.height.value = '';

    // Only auto-add sparepart sub-lines when the salesperson just picked
    // this product fresh from the dropdown (resetPrice=true) - NOT when
    // re-applying a saved line on load (resetPrice=false), where any
    // sparepart sub-lines already exist as their own saved rows and would
    // otherwise be duplicated.
    if (resetPrice) syncSpareparts(line);

    recalc();
  }

  /**
   * Auto-populate (or refresh) this line's sparepart sub-rows from its
   * product's catalogue spareparts. Any sub-rows already under this line
   * are removed first, so switching to a different product does not leave
   * the old product's spareparts behind.
   */
  function syncSpareparts(line) {
    removeChildSpareparts(line);
    const spareparts = (line.product && line.product.spareparts) || [];
    spareparts.forEach((sp) => addSparepartRow(line, sp));
  }

  function addSparepartRow(parentLine, sparepart) {
    const qty = computeSparepartQty(parentLine, sparepart);
    return addRow(
      {
        is_sparepart: true,
        product_name: sparepart.name,
        unit_price: sparepart.unit_price,
        quantity: qty,
        description: null,
        line_discount_pct: null,
      },
      { parentUid: parentLine.uid, sparepartRule: sparepart }
    );
  }

  /**
   * How many units of a sparepart the parent line needs right now.
   *
   * Default rule: qty_per_unit x the main line's quantity (e.g. 2
   * brackets per blind) - unchanged from before this feature existed.
   *
   * Custom-unit rule: if either custom_unit_N is configured, it REPLACES
   * the default rule rather than combining with it - a sparepart is
   * either "N per main unit" or "driven by a real measurement", not
   * both at once, so there's one unambiguous formula per sparepart. Both
   * custom units (if both are set) ADD together, e.g. a trim that needs
   * both width and height contributes width_m + height_m.
   */
  function computeSparepartQty(parentLine, sparepart) {
    const mainQty = num(parentLine.refs.qty.value);
    const basisValue = (basis) => {
      if (basis === 'width_cm') return num(parentLine.refs.width.value);
      if (basis === 'height_cm') return num(parentLine.refs.height.value);
      if (basis === 'measure') return computeLine(parentLine, 0).measure;
      return mainQty; // 'quantity' or anything unrecognised
    };

    const hasCustom = sparepart.custom_unit_1_basis || sparepart.custom_unit_2_basis;
    if (!hasCustom) {
      const qtyPerUnit = Number(sparepart.qty_per_unit) || 1;
      return round2(mainQty * qtyPerUnit);
    }

    let total = 0;
    if (sparepart.custom_unit_1_basis) {
      total += basisValue(sparepart.custom_unit_1_basis) * (Number(sparepart.custom_unit_1_factor) || 0);
    }
    if (sparepart.custom_unit_2_basis) {
      total += basisValue(sparepart.custom_unit_2_basis) * (Number(sparepart.custom_unit_2_factor) || 0);
    }
    return round2(total);
  }

  /** Remove every sparepart row that auto-followed this product line. */
  function removeChildSpareparts(parentLine) {
    lines
      .filter((l) => l.isSparepart && l.parentUid === parentLine.uid)
      .forEach((l) => removeLineRow(l));
  }

  /**
   * Keep sparepart quantities scaled to the main line's quantity (the
   * "qty matters" rule - e.g. 2 brackets per blind). Re-applied every time
   * the main line's qty changes, so a sparepart's own qty field always
   * reflects qty_per_unit x the current main qty rather than going stale.
   * A salesperson can still edit a sparepart's qty by hand, but it reverts
   * to the formula the next time the main line's qty is touched - a
   * deliberate simplicity trade-off flagged to Geoffrey, not a bug.
   */
  function syncSparepartQuantities(parentLine) {
    if (parentLine.isSparepart) return;
    lines
      .filter((l) => l.isSparepart && l.parentUid === parentLine.uid && l.sparepartRule)
      .forEach((l) => {
        l.refs.qty.value = computeSparepartQty(parentLine, l.sparepartRule);
      });
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
    if (data.is_sparepart) {
      applySparepartData(line, data);
      return;
    }
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

  /**
   * Apply a sparepart sub-line's saved data. Unlike a normal line, there
   * is no catalogue product to fetch - the name/price travel with the
   * line itself (see schemas.QuotationItemOut.product_name/unit_price).
   * parent_line_no (the saved line's position in the DOCUMENT) is
   * resolved through lineNoToUid, built fresh in recalc() as each row is
   * added in order - this only works because a sparepart's parent line
   * always loads before it (lower line_no), which the server guarantees.
   */
  function applySparepartData(line, data) {
    line.isSparepart = true;
    line.tr.classList.add('sparepart-row');
    line.refs.prodInput.value = `↳ ${data.product_name}`;
    line.refs.prodInput.disabled = true; // not swappable - remove and let it regenerate instead
    line.refs.width.disabled = true;
    line.refs.height.disabled = true;
    line.refs.width.value = '';
    line.refs.height.value = '';

    line.refs.desc.value = data.description || '';
    line.refs.qty.value = Number(data.quantity);
    line.refs.price.value = Number(data.unit_price);
    line.refs.disc.value = data.line_discount_pct === null ? '' : Number(data.line_discount_pct);

    // addRow already set line.parentUid from opts.parentUid when this row
    // was created fresh via addSparepartRow (the live-editing path) - only
    // resolve it from the saved data.parent_line_no when that wasn't the
    // case (the load-from-server path, where opts is never passed).
    if (line.parentUid === null && data.parent_line_no != null) {
      line.parentUid = lineNoToUid[data.parent_line_no] || null;
    }
  }

  function setRowReadonly(line, flag) {
    ['prodInput', 'desc', 'qty', 'width', 'height', 'price', 'disc'].forEach((key) => {
      line.refs[key].disabled = flag;
    });
    line.refs.remove.disabled = flag;
    (line.componentSelects || []).forEach((sel) => (sel.disabled = flag));
    if (!flag && line.isSparepart) {
      // A sparepart's product field and dimensions are permanently
      // read-only regardless of the row's overall readonly state - only
      // name was ever free text, and it has no catalogue counterpart to
      // swap in via the dropdown.
      line.refs.prodInput.disabled = true;
      line.refs.width.disabled = true;
      line.refs.height.disabled = true;
    } else if (!flag && line.product) {
      const { width: needsWidth, height: needsHeight } = dimensionsNeeded(line.product.price_unit);
      line.refs.width.disabled = !needsWidth;
      line.refs.height.disabled = !needsHeight;
    }
  }

  function addRow(data, opts) {
    const tr = document.createElement('tr');
    tr.innerHTML = LINE_ROW_HTML;
    tbody.appendChild(tr);

    const line = {
      uid: ++seq,
      tr,
      product: null,
      isSparepart: false,
      parentUid: opts && opts.parentUid ? opts.parentUid : null,
      sparepartRule: (opts && opts.sparepartRule) || null,
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

    // A row created directly as a sparepart (addSparepartRow, not loaded
    // from saved data) needs the same markup/behaviour applyLineData
    // gives a loaded one - name prefix, read-only dimensions, no product
    // autocomplete. data.is_sparepart (the saved-row path) is handled
    // inside applyLineData below instead.
    if (opts && opts.parentUid && !(data && data.is_sparepart)) {
      line.isSparepart = true;
      line.tr.classList.add('sparepart-row');
      line.refs.prodInput.disabled = true;
      line.refs.width.disabled = true;
      line.refs.height.disabled = true;
    }

    attachAutocomplete({
      input: line.refs.prodInput,
      resultsEl: line.refs.prodResults,
      search: (term) => api.listProducts(term),
      render: (p) =>
        // Just the name and price - code/price_unit were internal jargon
        // that cluttered the list without helping pick the right fabric;
        // price is kept since it's actually useful when choosing.
        `${esc(p.name)}<span class="code">${fmtMoney(p.unit_price)}</span>`,
      onPick: (p) => selectProduct(line, p, { resetPrice: true }),
      floating: true,
      // Can't find the fabric you want? Jump straight to the admin
      // Product Catalogue to add it, rather than abandoning the
      // quotation to go hunt for the right page. Opens in a new tab so
      // the in-progress quotation is never lost. Products.html itself
      // still enforces admin-only - a normal user just lands on the
      // same "not allowed" page they'd get from the nav menu.
      extraRow: { href: 'products.html', label: '+ Add Product' },
    });

    ['width', 'height', 'price', 'disc'].forEach((key) =>
      line.refs[key].addEventListener('input', recalc)
    );
    // width/height/qty can all drive a sparepart's quantity now (a custom
    // unit may read width_cm, height_cm, or measure - not just quantity),
    // so all three re-scale any sparepart children, not just qty alone.
    ['width', 'height'].forEach((key) =>
      line.refs[key].addEventListener('input', () => syncSparepartQuantities(line))
    );
    line.refs.qty.addEventListener('input', () => {
      syncSparepartQuantities(line);
      recalc();
    });

    line.refs.remove.addEventListener('click', () => {
      removeLineRow(line, { removeChildren: true });
      recalc();
    });

    if (data) applyLineData(line, data);
    if (!line.isSparepart) line.refs.prodInput.disabled = readonly;
    if (readonly) setRowReadonly(line, true);

    recalc();
    return line;
  }

  /** Detach one row's DOM and bookkeeping without triggering a recalc -
   * callers (the remove button, removeChildSpareparts) call recalc()
   * themselves once, after any cascaded removals are done. */
  function removeLineRow(line, { removeChildren = false } = {}) {
    if (removeChildren) removeChildSpareparts(line);
    const i = lines.findIndex((l) => l.uid === line.uid);
    if (i >= 0) lines.splice(i, 1);
    line.tr.remove();
    if (line.refs.prodResults.parentElement === document.body) {
      line.refs.prodResults.remove(); // floating dropdowns live on <body>
    }
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

    // Submission order is the line_no the server will assign (see
    // routers' _apply_items), so a sparepart's parent_line_no has to be
    // the 1-based INDEX of its parent within THIS array, not the parent's
    // frontend uid.
    const uidToSubmissionNo = {};
    lines.forEach((line, i) => {
      if (!line.isSparepart) uidToSubmissionNo[line.uid] = i + 1;
    });

    return lines
      .map((line, i) => {
        if (line.isSparepart) {
          const parentNo = line.parentUid ? uidToSubmissionNo[line.parentUid] : null;
          if (!parentNo) return null; // parent was removed - drop this orphan silently
          return {
            is_sparepart: true,
            sparepart_name: line.refs.prodInput.value.replace(/^↳\s*/, '').trim(),
            parent_line_no: parentNo,
            description: line.refs.desc.value.trim() || null,
            quantity: num(line.refs.qty.value),
            unit_price: line.refs.price.value === '' ? null : num(line.refs.price.value),
            line_discount_pct:
              line.refs.disc.value.trim() === '' ? null : num(line.refs.disc.value),
          };
        }
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
      })
      .filter((item) => item !== null);
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
    <th class="right" style="width:96px">Measure</th>
    <th class="right" style="width:120px">Unit Price</th>
    <th class="right" style="width:76px">Disc %</th>
    <th class="right" style="width:120px">Line Total</th>
    <th class="right" style="width:120px">Net</th>
    <th style="width:36px"></th>
  </tr>
`;
