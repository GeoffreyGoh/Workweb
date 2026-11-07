/* =====================================================================
   Shared "confirm before generating PDF" page for every document type.

   Loaded as pdf-confirm.html?type=quotation&id=123&back=quotation-form.html.
   `type` selects which API/PDF/field config to use (DOC_CONFIG below);
   `back` is where the "Back"/"Cancel" buttons return to (so this one
   page works for every calling form without hardcoding a single return
   path).
   ===================================================================== */

// Per-document-type wiring. Receipts have no update endpoint and no
// Payment Terms field at all (see models.Receipt / routers/receipts.py -
// create and void only) - editableFields is empty for it, and the page
// falls back to a pure read-only "final look" instead of a save step.
const DOC_CONFIG = {
  quotation: {
    get: api.getQuotation,
    update: api.updateQuotation,
    pdfKind: 'quotation',
    noLabel: 'Quotation No.',
    counterpartyLabel: 'Customer',
    noField: 'quotation_no',
    counterpartyField: 'customer_name',
    totalField: 'total',
    editableFields: ['payment_terms', 'notes'],
  },
  salesOrder: {
    get: api.getSalesOrder,
    update: api.updateSalesOrder,
    pdfKind: 'salesOrder',
    noLabel: 'Invoice No.',
    counterpartyLabel: 'Customer',
    noField: 'so_no',
    counterpartyField: 'customer_name',
    totalField: 'total',
    editableFields: ['payment_terms', 'notes'],
  },
  purchaseOrder: {
    get: api.getPurchaseOrder,
    update: api.updatePurchaseOrder,
    pdfKind: 'purchaseOrder',
    noLabel: 'PO No.',
    counterpartyLabel: 'Supplier',
    noField: 'po_no',
    counterpartyField: 'supplier_name',
    totalField: 'total',
    editableFields: ['payment_terms', 'notes'],
  },
  deliveryNote: {
    get: api.getDeliveryNote,
    update: api.updateDeliveryNote,
    pdfKind: 'deliveryNote',
    noLabel: 'Surat Jalan No.',
    counterpartyLabel: 'Customer',
    noField: 'sj_no',
    counterpartyField: 'customer_name',
    totalField: null, // delivery notes carry no prices
    editableFields: ['notes'], // no payment_terms on this document type
  },
  receipt: {
    get: api.getReceipt,
    update: null, // no PUT /receipts/{id} exists - void-and-recreate only
    pdfKind: 'receipt',
    noLabel: 'Receipt No.',
    counterpartyLabel: 'Received From',
    noField: 'receipt_no',
    counterpartyField: 'received_from',
    totalField: 'amount',
    editableFields: [], // nothing to edit - pure read-only confirm
  },
};

const FIELD_LABELS = {
  payment_terms: { el: 'paymentTermsField', input: 'paymentTerms' },
  notes: { el: 'notesField', input: 'notes' },
};

const params = new URLSearchParams(window.location.search);
const docType = params.get('type');
const docId = params.get('id');
const backUrl = params.get('back') || 'index.html';

const cfg = DOC_CONFIG[docType];

document.getElementById('backLink').href = backUrl;
document.getElementById('cancelBtn').addEventListener('click', () => {
  window.location.href = backUrl;
});

function showError(message) {
  const el = document.getElementById('error');
  el.textContent = message;
  el.classList.remove('hidden');
}

let loadedDoc = null;

async function boot() {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar(null, user);

  if (!cfg || !docId) {
    showError('Missing or unknown document type.');
    return;
  }

  try {
    loadedDoc = await cfg.get(docId);
  } catch (err) {
    showError(err.message);
    return;
  }

  document.getElementById('pageTitle').textContent = `Confirm before generating ${cfg.noLabel.replace(' No.', '')} PDF`;
  document.getElementById('docNo').value = loadedDoc[cfg.noField] || '';
  document.getElementById('counterpartyLabel').textContent = cfg.counterpartyLabel;
  document.getElementById('counterpartyName').value = loadedDoc[cfg.counterpartyField] || '';

  if (cfg.totalField && loadedDoc[cfg.totalField] !== undefined) {
    document.getElementById('docTotal').value = fmtMoney(loadedDoc[cfg.totalField], loadedDoc.currency);
  } else {
    document.getElementById('docTotal').closest('.field').style.display = 'none';
  }

  // Show only the editable fields this document type actually supports,
  // pre-filled with its current value. A field this type doesn't have
  // (e.g. Delivery Note's missing Payment Terms, or Receipt's empty
  // editableFields) is hidden entirely rather than shown disabled.
  Object.entries(FIELD_LABELS).forEach(([field, ids]) => {
    const show = cfg.editableFields.includes(field);
    document.getElementById(ids.el).style.display = show ? '' : 'none';
    if (show) document.getElementById(ids.input).value = loadedDoc[field] || '';
  });

  if (cfg.editableFields.length === 0) {
    document.getElementById('readonlyNote').style.display = '';
    document.getElementById('confirmBtn').textContent = 'Confirm & Generate PDF';
  }
}

document.getElementById('confirmBtn').addEventListener('click', async () => {
  const savingHint = document.getElementById('savingHint');
  document.getElementById('error').classList.add('hidden');
  document.getElementById('confirmBtn').disabled = true;

  try {
    // Only call update when this document type actually has one AND a
    // field was actually shown to edit - skips a pointless PUT for
    // Receipts (no endpoint) and for any type with nothing editable.
    if (cfg.update && cfg.editableFields.length > 0) {
      savingHint.style.display = '';
      const body = {};
      cfg.editableFields.forEach((field) => {
        body[field] = FIELD_LABELS[field]
          ? document.getElementById(FIELD_LABELS[field].input).value.trim() || null
          : null;
      });
      await cfg.update(docId, body);
      savingHint.style.display = 'none';
    }

    await openPdf(cfg.pdfKind, docId);
    // The PDF opened in a new tab (or downloaded, if the popup was
    // blocked) - return to the originating form rather than leaving the
    // user stuck on this confirm page.
    window.location.href = backUrl;
  } catch (err) {
    savingHint.style.display = 'none';
    showError(err.message);
  } finally {
    document.getElementById('confirmBtn').disabled = false;
  }
});

boot();
