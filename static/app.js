(() => {
  const menu = document.querySelector('.mobile-menu');
  menu?.addEventListener('click', () => {
    const open = document.body.classList.toggle('nav-open');
    menu.setAttribute('aria-expanded', String(open));
  });
  const fileInput = document.querySelector('input[type=file]');
  const preview = document.getElementById('image-preview');
  let previewUrl;
  fileInput?.addEventListener('change', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!fileInput.files[0]) { preview.hidden = true; return; }
    previewUrl = URL.createObjectURL(fileInput.files[0]);
    preview.querySelector('img').src = previewUrl;
    preview.hidden = false;
  });
  document.getElementById('retake-image')?.addEventListener('click', () => fileInput.click());
  const consent = document.querySelector('[data-consent-gate] input[name=consent]');
  const identity = document.querySelector('[data-consent-gate] input[name=name]');
  if (consent && identity) {
    const sync = () => { identity.disabled = !consent.checked; };
    consent.addEventListener('change', sync); sync();
  }
  document.querySelectorAll('form[data-dirty-warning]').forEach(form => {
    let dirty = false;
    form.addEventListener('change', () => { dirty = true; });
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('submit', () => {
      dirty = false;
      const button = form.querySelector('[data-submit-button]');
      if (button) { button.disabled = true; button.textContent = 'Saving submission…'; }
    });
    window.addEventListener('beforeunload', event => {
      if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
  });
})();
