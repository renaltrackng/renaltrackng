(() => {
  const doc = document.documentElement;
  doc.classList.add('js');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Sticky nav styling + active section highlight
  const nav = document.querySelector('.nav');
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 10);
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll();

  const links = [...document.querySelectorAll('.nav-links a')];
  const sections = links.map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
  if ('IntersectionObserver' in window) {
    const spy = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    sections.forEach(s => spy.observe(s));
  }

  // Mobile menu
  const toggle = document.querySelector('.nav-toggle');
  const menu = document.getElementById('mobile-menu');
  const setMenu = open => { menu.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); nav.classList.toggle('scrolled', open || window.scrollY > 10); };
  toggle?.addEventListener('click', () => setMenu(menu.hidden));
  menu?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setMenu(false)));

  // Reveal on scroll
  const items = document.querySelectorAll('.rv, [data-steps]');
  if (reduced || !('IntersectionObserver' in window)) {
    items.forEach(el => el.classList.add('in'));
  } else {
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: 0.14, rootMargin: '0px 0px -40px 0px' });
    items.forEach(el => io.observe(el));
  }

  // Gentle parallax tilt on the hero screenshot
  const visual = document.querySelector('.hero-visual');
  const frame = visual?.querySelector('.browser.tilt');
  if (frame && !reduced && window.matchMedia('(pointer: fine)').matches && window.innerWidth > 1100) {
    visual.addEventListener('mousemove', e => {
      const r = visual.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      frame.style.transform = `rotateY(${-6 + x * 8}deg) rotateX(${3 - y * 6}deg)`;
    });
    visual.addEventListener('mouseleave', () => { frame.style.transform = ''; });
  }

  // Platform tabs (auto-advance until the visitor interacts)
  const tabs = [...document.querySelectorAll('.tabs [role=tab]')];
  const shots = [...document.querySelectorAll('.shots img')];
  let current = 0, timer;
  const show = i => {
    current = i;
    tabs.forEach((t, k) => { t.setAttribute('aria-selected', String(k === i)); t.tabIndex = k === i ? 0 : -1; });
    shots.forEach((s, k) => s.classList.toggle('on', k === i));
  };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => { clearInterval(timer); show(i); });
    t.addEventListener('keydown', e => {
      if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      e.preventDefault(); clearInterval(timer);
      const n = (current + (e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      show(n); tabs[n].focus();
    });
  });
  if (tabs.length && !reduced) timer = setInterval(() => show((current + 1) % tabs.length), 5000);

  // Contact form: submit without leaving the page
  const form = document.querySelector('.contact-form');
  const success = document.querySelector('.form-success');
  if (form && window.fetch) {
    const button = form.querySelector('button[type=submit]');
    const label = button.querySelector('.label');
    const formError = form.querySelector('.form-error');
    form.addEventListener('submit', async e => {
      e.preventDefault();
      form.querySelectorAll('.err').forEach(el => { el.textContent = ''; });
      form.querySelectorAll('.f.invalid').forEach(el => el.classList.remove('invalid'));
      formError.hidden = true;
      button.classList.add('loading'); label.textContent = 'Sending…';
      try {
        const res = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch' } });
        const data = await res.json();
        if (data.ok) {
          form.reset(); form.hidden = true; success.hidden = false;
          success.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
        } else {
          Object.entries(data.errors || {}).forEach(([field, msgs]) => {
            if (field === '__all__') { formError.textContent = msgs.join(' '); formError.hidden = false; return; }
            const slot = form.querySelector(`[data-err="${field}"]`);
            if (slot) { slot.textContent = msgs.join(' '); slot.closest('.f')?.classList.add('invalid'); }
          });
          form.querySelector('.f.invalid input, .f.invalid textarea, .f.invalid select')?.focus();
        }
      } catch (err) {
        formError.textContent = 'Something went wrong while sending. Please try again, or email renaltrackng@gmail.com.';
        formError.hidden = false;
      } finally {
        button.classList.remove('loading'); label.textContent = 'Send message';
      }
    });
    document.querySelector('[data-send-another]')?.addEventListener('click', () => { success.hidden = true; form.hidden = false; form.querySelector('input:not([type=hidden])')?.focus(); });
  }
})();
