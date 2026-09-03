/* =====================================================================
   Shared API client + small helpers. No framework, no build step.
   Loaded by every page before its own script.
   ===================================================================== */

const API_BASE = window.location.origin;
const TOKEN_KEY = 'q2o_token';
const USER_KEY = 'q2o_user';

const Auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get user() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch (e) {
      return null;
    }
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  logout() {
    Auth.clear();
    window.location.href = 'login.html';
  },
};

/** Thrown for any non-2xx response, with the API's detail message. */
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers);
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (Auth.token) headers['Authorization'] = `Bearer ${Auth.token}`;

  const response = await fetch(API_BASE + path, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  // An expired or bad token means the session is over - bounce to login.
  if (response.status === 401 && !path.startsWith('/auth/login')) {
    Auth.clear();
    window.location.href = 'login.html';
    throw new ApiError('Session expired', 401);
  }

  if (response.status === 204) return null;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(detailToMessage(payload, response.status), response.status);
  }
  return payload;
}

/** FastAPI returns `detail` as a string, or a list of validation objects. */
function detailToMessage(payload, status) {
  const detail = payload && payload.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.slice(1).join('.') : '';
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join('; ');
  }
  return `Request failed (HTTP ${status})`;
}

const api = {
  login: (username, password) =>
    apiFetch('/auth/login', { method: 'POST', body: { username, password } }),
  me: () => apiFetch('/auth/me'),

  listCustomers: (q) => apiFetch(`/customers?limit=20${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  getCustomer: (id) => apiFetch(`/customers/${id}`),

  listProducts: (q) => apiFetch(`/products?limit=20${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  getProduct: (id) => apiFetch(`/products/${id}`),

  listQuotations: (params) => {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) qs.append(k, v);
    });
    const s = qs.toString();
    return apiFetch(`/quotations${s ? `?${s}` : ''}`);
  },
  getQuotation: (id) => apiFetch(`/quotations/${id}`),
  createQuotation: (body) => apiFetch('/quotations', { method: 'POST', body }),
  updateQuotation: (id, body) => apiFetch(`/quotations/${id}`, { method: 'PUT', body }),
  setQuotationStatus: (id, status) =>
    apiFetch(`/quotations/${id}/status`, { method: 'PATCH', body: { status } }),

  listSuppliers: (q) => apiFetch(`/suppliers?limit=20${q ? `&q=${encodeURIComponent(q)}` : ''}`),

  listSalesOrders: (params) => apiFetch(`/sales-orders${qs(params)}`),
  getSalesOrder: (id) => apiFetch(`/sales-orders/${id}`),
  createSalesOrder: (body) => apiFetch('/sales-orders', { method: 'POST', body }),
  updateSalesOrder: (id, body) => apiFetch(`/sales-orders/${id}`, { method: 'PUT', body }),
  setSalesOrderStatus: (id, status) =>
    apiFetch(`/sales-orders/${id}/status`, { method: 'PATCH', body: { status } }),
  convertQuotation: (quotationId) =>
    apiFetch(`/sales-orders/from-quotation/${quotationId}`, { method: 'POST' }),

  listPurchaseOrders: (params) => apiFetch(`/purchase-orders${qs(params)}`),
  getPurchaseOrder: (id) => apiFetch(`/purchase-orders/${id}`),
  createPurchaseOrder: (body) => apiFetch('/purchase-orders', { method: 'POST', body }),
  updatePurchaseOrder: (id, body) =>
    apiFetch(`/purchase-orders/${id}`, { method: 'PUT', body }),
  setPurchaseOrderStatus: (id, status) =>
    apiFetch(`/purchase-orders/${id}/status`, { method: 'PATCH', body: { status } }),

  listDeliveryNotes: (params) => apiFetch(`/delivery-notes${qs(params)}`),
  getDeliveryNote: (id) => apiFetch(`/delivery-notes/${id}`),
  createDeliveryNote: (body) => apiFetch('/delivery-notes', { method: 'POST', body }),
  updateDeliveryNote: (id, body) =>
    apiFetch(`/delivery-notes/${id}`, { method: 'PUT', body }),
  setDeliveryNoteStatus: (id, body) =>
    apiFetch(`/delivery-notes/${id}/status`, { method: 'PATCH', body }),
  deliveryNoteFromOrder: (salesOrderId) =>
    apiFetch(`/delivery-notes/from-sales-order/${salesOrderId}`, { method: 'POST' }),
  deliveryStatus: (salesOrderId) =>
    apiFetch(`/delivery-notes/outstanding/${salesOrderId}`),

  closeReceivable: (id, body) =>
    apiFetch(`/sales-orders/${id}/close-receivable`, { method: 'POST', body }),
  reopenReceivable: (id) =>
    apiFetch(`/sales-orders/${id}/reopen-receivable`, { method: 'POST' }),

  customerStatement: (customerId, params) =>
    apiFetch(`/reports/statement/${customerId}${qs(params)}`),

  listReceipts: (params) => apiFetch(`/receipts${qs(params)}`),
  createReceipt: (body) => apiFetch('/receipts', { method: 'POST', body }),
  voidReceipt: (id) => apiFetch(`/receipts/${id}`, { method: 'DELETE' }),

  listUsers: () => apiFetch('/users'),
  listCompanies: () => apiFetch('/companies'),

  previewPoSplit: (salesOrderId) => apiFetch(`/purchase-orders/split/${salesOrderId}`),
  createPoSplit: (salesOrderId) =>
    apiFetch(`/purchase-orders/split/${salesOrderId}`, { method: 'POST' }),

  deliverySchedule: (params) => apiFetch(`/delivery-notes/schedule/board${qs(params)}`),

  salesReport: (params) => apiFetch(`/reports/sales${qs(params)}`),
  financialReport: (params) => apiFetch(`/reports/financial${qs(params)}`),
};

/** Build a query string, skipping blanks. */
function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) search.append(k, v);
  });
  const s = search.toString();
  return s ? `?${s}` : '';
}

const PDF_PATHS = {
  quotation: (id) => `/documents/quotations/${id}.pdf`,
  salesOrder: (id) => `/documents/sales-orders/${id}.pdf`,
  purchaseOrder: (id) => `/documents/purchase-orders/${id}.pdf`,
  receipt: (id) => `/documents/receipts/${id}.pdf`,
  deliveryNote: (id) => `/documents/delivery-notes/${id}.pdf`,
};

/**
 * Fetch a PDF with the bearer token and hand the browser a blob.
 *
 * Opening `/documents/....pdf?token=...` in a new tab would be simpler, but it
 * puts the token in browser history, the address bar and any proxy log. A blob
 * URL keeps it in the Authorization header where it belongs.
 */
async function openPdf(kind, id, { download = false } = {}) {
  // Claim the tab NOW, while we are still inside the click's user-gesture
  // window. Calling window.open() after `await fetch` looks unprompted to a
  // popup blocker and gets swallowed.
  const tab = download ? null : window.open('', '_blank');

  try {
    const response = await fetch(API_BASE + PDF_PATHS[kind](id), {
      headers: { Authorization: `Bearer ${Auth.token}` },
    });

    if (!response.ok) {
      let message = `Could not generate the PDF (HTTP ${response.status})`;
      try {
        message = detailToMessage(JSON.parse(await response.text()), response.status);
      } catch (e) {
        /* keep the generic message */
      }
      throw new ApiError(message, response.status);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const match = (response.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
    const filename = match ? match[1] : 'document.pdf';

    // No tab means the popup was blocked - save the file instead of losing it.
    if (tab) {
      tab.location.href = url;
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
    }
    // Give the viewer time to read it before the blob is reclaimed.
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return filename;
  } catch (err) {
    if (tab) tab.close();
    throw err;
  }
}

/* --------------------------------------------------------------- format */

/** Money with thousands separators. IDR has no cents in practice. */
function fmtMoney(value, currency) {
  const n = Number(value || 0);
  const decimals = currency === 'IDR' || currency === undefined ? 0 : 2;
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Trims trailing zeros: 2.50 -> "2.5", 3.00 -> "3". */
function fmtNum(value, maxDecimals = 2) {
  const n = Number(value || 0);
  return n.toLocaleString('en-US', { maximumFractionDigits: maxDecimals });
}

function fmtDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (isNaN(d)) return value;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function todayISO() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function statusBadge(status) {
  // The chip text is data, so it translates through i18n rather than the
  // data-i18n sweep (which only touches static markup).
  const label =
    typeof statusLabel === 'function'
      ? statusLabel(status)
      : String(status || '').replace(/_/g, ' ');
  return `<span class="status status-${esc(status)}">${esc(label)}</span>`;
}

/** Minimal escaping for values interpolated into innerHTML. */
function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function debounce(fn, wait = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

/* ------------------------------------------------------------- chrome  */

/** Redirect to login if there's no session; returns the current user. */
async function requireLogin() {
  if (!Auth.token) {
    window.location.href = 'login.html';
    return null;
  }
  try {
    const user = await api.me();
    Auth.save(Auth.token, user);
    return user;
  } catch (e) {
    Auth.logout();
    return null;
  }
}

function renderTopbar(activePage, user) {
  const el = document.getElementById('topbar');
  if (!el) return;
  const links = [
    { href: 'quotations.html', i18n: 'nav.quotations', key: 'quotations' },
    { href: 'sales-orders.html', i18n: 'nav.salesOrders', key: 'sales-orders' },
    { href: 'purchase-orders.html', i18n: 'nav.purchaseOrders', key: 'purchase-orders' },
    { href: 'delivery-notes.html', i18n: 'nav.deliveryNotes', key: 'delivery-notes' },
    { href: 'schedule.html', i18n: 'nav.schedule', key: 'schedule' },
    { href: 'statement.html', i18n: 'nav.statement', key: 'statement' },
    { href: 'receipts.html', i18n: 'nav.receipts', key: 'receipts' },
    { href: 'reports.html', i18n: 'nav.reports', key: 'reports' },
  ];
  el.className = 'topbar';
  el.innerHTML = `
    <div class="brand">Q2O <span>| Quotation to Order</span></div>
    <nav>
      ${links
        .map(
          (l) =>
            `<a href="${l.href}" class="${l.key === activePage ? 'active' : ''}" data-i18n="${l.i18n}">${t(l.i18n)}</a>`
        )
        .join('')}
    </nav>
    <div class="spacer"></div>
    <div class="who">
      <strong>${esc(user ? user.full_name : '')}</strong>
      <span class="company-chip" id="companyChip"></span>
      <span class="role-chip">${esc(user ? user.role : '')}</span>
    </div>
    <button class="btn small lang-btn" id="langBtn" type="button"
            title="Switch language / Ganti bahasa">
      <span class="lang-code">${Lang.current === 'en' ? 'EN' : 'ID'}</span>
      <span data-i18n="app.language">${t('app.language')}</span>
    </button>
    <button class="btn small" id="logoutBtn" type="button"
            data-i18n="app.signOut">${t('app.signOut')}</button>
  `;
  document.getElementById('logoutBtn').addEventListener('click', Auth.logout);
  showDefaultCompany(user);
  document.getElementById('langBtn').addEventListener('click', () => {
    Lang.toggle();
    document.querySelector('#langBtn .lang-code').textContent =
      Lang.current === 'en' ? 'EN' : 'ID';
  });
}

/* --------------------------------------------------------- autocomplete */

/**
 * Wires a text input to a dropdown of search results.
 * `search(term)` returns rows; `render(row)` returns the label HTML;
 * `onPick(row)` fires on selection.
 */
function attachAutocomplete({
  input,
  resultsEl,
  search,
  render,
  onPick,
  minChars = 0,
  floating = false,
}) {
  let rows = [];
  let activeIndex = -1;

  // Inside a horizontally scrolling table the dropdown would be clipped, so
  // float it: move it to <body> and position it against the input.
  if (floating) {
    resultsEl.classList.add('floating');
    document.body.appendChild(resultsEl);
  }

  const close = () => {
    resultsEl.classList.add('hidden');
    activeIndex = -1;
  };

  const position = () => {
    const r = input.getBoundingClientRect();
    resultsEl.style.top = `${r.bottom + 2}px`;
    resultsEl.style.left = `${r.left}px`;
    resultsEl.style.width = `${Math.max(r.width, 240)}px`;
  };

  const draw = () => {
    if (!rows.length) {
      resultsEl.innerHTML = '<div class="empty">No matches</div>';
    } else {
      resultsEl.innerHTML = rows
        .map((row, i) => `<div data-i="${i}" class="${i === activeIndex ? 'active' : ''}">${render(row)}</div>`)
        .join('');
    }
    if (floating) position();
    resultsEl.classList.remove('hidden');
  };

  if (floating) {
    window.addEventListener(
      'scroll',
      (event) => {
        // Capture phase catches scrolling anywhere - including inside this
        // dropdown. Closing on that made the product list impossible to
        // scroll with the wheel, so ignore its own scroll events.
        if (event.target === resultsEl || resultsEl.contains(event.target)) return;
        close();
      },
      true
    );
    window.addEventListener('resize', close);
  }

  const run = debounce(async () => {
    const term = input.value.trim();
    if (term.length < minChars) return close();
    try {
      rows = await search(term);
      activeIndex = -1;
      draw();
    } catch (e) {
      close();
    }
  }, 220);

  input.addEventListener('input', run);
  input.addEventListener('focus', () => {
    // Only re-search when the list is actually closed. Re-running on every
    // focus would redraw the rows and throw away the user's scroll position
    // the moment focus returns after dragging the scrollbar.
    if (resultsEl.classList.contains('hidden')) run();
  });

  input.addEventListener('keydown', (event) => {
    if (resultsEl.classList.contains('hidden') || !rows.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex += event.key === 'ArrowDown' ? 1 : -1;
      if (activeIndex < 0) activeIndex = rows.length - 1;
      if (activeIndex >= rows.length) activeIndex = 0;
      draw();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (activeIndex >= 0) {
        onPick(rows[activeIndex]);
        close();
      }
    } else if (event.key === 'Escape') {
      close();
    }
  });

  resultsEl.addEventListener('mousedown', (event) => {
    // mousedown, not click - the input's blur would close the list first.
    const row = event.target.closest('[data-i]');
    if (!row) return;
    event.preventDefault();
    onPick(rows[Number(row.dataset.i)]);
    close();
  });

  /**
   * Is the pointer over the dropdown?
   *
   * Deliberately geometric rather than `resultsEl.contains(event.target)`:
   * pressing an element's scrollbar does not reliably report that element as
   * the event target, so a target-based check treats a scrollbar drag as a
   * click outside and dismisses the list - which is exactly what made the
   * product list impossible to scroll.
   */
  const pointerOverList = (event) => {
    if (resultsEl.classList.contains('hidden')) return false;
    const r = resultsEl.getBoundingClientRect();
    return (
      event.clientX >= r.left &&
      event.clientX <= r.right &&
      event.clientY >= r.top &&
      event.clientY <= r.bottom
    );
  };

  // Dragging the scrollbar also blurs the input, so hold the list open for
  // the duration of the drag.
  let grabbing = false;

  document.addEventListener('mousedown', (event) => {
    if (pointerOverList(event)) {
      grabbing = true;
    } else if (event.target !== input) {
      close();
    }
  });

  document.addEventListener('mouseup', () => {
    if (!grabbing) return;
    grabbing = false;
    // Hand focus back so the arrow keys keep working after a scroll.
    if (!resultsEl.classList.contains('hidden')) input.focus();
  });

  input.addEventListener('blur', () =>
    setTimeout(() => {
      if (!grabbing) close();
    }, 150)
  );

  return { close };
}


/** Name the user's own entity in the top bar. */
async function showDefaultCompany(user) {
  const chip = document.getElementById('companyChip');
  if (!chip || !user || !user.default_company_id) return;
  try {
    const companies = await api.listCompanies();
    const mine = companies.find((c) => c.id === user.default_company_id);
    if (mine) chip.textContent = mine.code;
  } catch (e) {
    /* the chip is a convenience, not a requirement */
  }
}

/**
 * Fill a <select> with the active companies.
 *
 * `selected` pins an existing document's company even if it has since been
 * deactivated, so historic documents still display the entity that issued
 * them rather than falling back to a blank.
 */
async function loadCompanyOptions(select, { selected = null, allLabel = null } = {}) {
  if (!select) return [];
  const companies = await api.listCompanies();
  select.innerHTML =
    (allLabel ? `<option value="">${esc(allLabel)}</option>` : '') +
    companies
      .map((c) => `<option value="${c.id}">${esc(c.code)} \u2014 ${esc(c.name)}</option>`)
      .join('');
  if (selected && !companies.some((c) => c.id === selected)) {
    const row = document.createElement('option');
    row.value = selected;
    row.textContent = '(inactive company)';
    select.appendChild(row);
  }
  if (selected) select.value = selected;
  return companies;
}
