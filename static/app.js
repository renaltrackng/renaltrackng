(() => {
  // Mobile navigation drawer
  const menu = document.querySelector('.mobile-menu');
  const setNav = open => {
    document.body.classList.toggle('nav-open', open);
    menu?.setAttribute('aria-expanded', String(open));
  };
  menu?.addEventListener('click', () => setNav(!document.body.classList.contains('nav-open')));
  document.querySelector('[data-nav-close]')?.addEventListener('click', () => setNav(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') setNav(false); });

  // Top bar gains a hairline once the page scrolls
  const topbar = document.querySelector('.topbar');
  if (topbar) {
    const onScroll = () => topbar.classList.toggle('scrolled', window.scrollY > 4);
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  }

  // Show / hide password
  document.querySelectorAll('[data-reveal]').forEach(btn => {
    const input = document.getElementById(btn.dataset.reveal);
    btn.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', String(show));
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.querySelector('use')?.setAttribute('href', show ? '#i-eye' : '#i-eye-off');
    });
  });

  // Team member form: only show the settings that apply to the chosen role
  document.querySelectorAll('form[data-role-form]').forEach(form => {
    const role = form.querySelector('select[name=role]');
    if (!role) return;
    const rules = { facility: ['staff'], assigned_facilities: ['reviewer'] };
    const sync = () => {
      Object.entries(rules).forEach(([name, roles]) => {
        const field = form.querySelector(`[data-field="${name}"]`);
        if (field) field.hidden = !roles.includes(role.value);
      });
    };
    role.addEventListener('change', sync); sync();
  });

  // Photo preview before submitting
  const fileInput = document.querySelector('input[type=file]');
  const preview = document.getElementById('image-preview');
  let previewUrl;
  fileInput?.addEventListener('change', () => {
    if (!preview) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!fileInput.files[0]) { preview.hidden = true; return; }
    previewUrl = URL.createObjectURL(fileInput.files[0]);
    preview.querySelector('img').src = previewUrl;
    preview.hidden = false;
  });
  document.getElementById('retake-image')?.addEventListener('click', () => fileInput.click());

  // Participant name is only enabled once consent is ticked
  const consent = document.querySelector('[data-consent-gate] input[name=consent]');
  const identity = document.querySelector('[data-consent-gate] input[name=name]');
  if (consent && identity) {
    const sync = () => { identity.disabled = !consent.checked; };
    consent.addEventListener('change', sync); sync();
  }

  // Warn before leaving a half-filled form; prevent double submission
  document.querySelectorAll('form[data-dirty-warning]').forEach(form => {
    let dirty = false;
    form.addEventListener('change', () => { dirty = true; });
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('submit', () => {
      dirty = false;
      const button = form.querySelector('[data-submit-button]');
      if (button) { button.disabled = true; button.textContent = 'Submitting…'; }
    });
    window.addEventListener('beforeunload', event => {
      if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
  });
})();
