/* The "not allowed" landing page.

   Reached when someone opens a page their role cannot use. The API is what
   actually refuses them - this page only explains the refusal in words, so
   a normal user who follows a bookmark or a colleague's link gets told what
   happened instead of a bare error or a silent bounce somewhere else. */

/**
 * Why they were turned away. Whitelisted deliberately: the reason comes off
 * the query string, and mapping it through a fixed table means no text from
 * the URL is ever rendered into the page.
 */
const REASONS = {
  products: 'denied.products',
  companies: 'denied.companies',
  financial: 'denied.financial',
};

function reasonKey() {
  const what = new URLSearchParams(window.location.search).get('what');
  return (what && REASONS[what]) || 'denied.generic';
}

function render(user) {
  document.getElementById('reason').textContent = t(reasonKey());
  document.getElementById('who').textContent = user
    ? `${t('denied.signedInAs')} ${user.full_name} (${user.role}). ${t('denied.askAdmin')}`
    : t('denied.askAdmin');
}

document.getElementById('signOutBtn').addEventListener('click', Auth.logout);

// Re-render on a language switch; the two filled-in lines are built in code,
// so the i18n sweep over static markup does not reach them.
document.addEventListener('languagechange', () => render(Auth.user));

(async () => {
  const user = await requireLogin();
  if (!user) return;
  renderTopbar('', user);
  render(user);
})();
