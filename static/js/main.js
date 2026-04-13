/* ================================================================
   LIONS CLUB TUNIS-MÉDINA — JavaScript principal
   Gestion : navbar scroll, menu mobile, scroll reveal, messages
   ================================================================ */

document.addEventListener('DOMContentLoaded', () => {

  /* ── 1. NAVBAR — transparent → navy au scroll ─────────────── */
  const navbar = document.getElementById('navbar');

  if (navbar) {
    const onScroll = () => {
      if (window.scrollY > 72) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll(); // état initial si on recharge la page en cours de scroll
  }


  /* ── 2. MENU MOBILE ───────────────────────────────────────── */
  const menuBtn       = document.getElementById('mobile-menu-btn');
  const mobileMenu    = document.getElementById('mobile-menu');
  const iconOpen      = document.getElementById('menu-icon-open');
  const iconClose     = document.getElementById('menu-icon-close');

  if (menuBtn && mobileMenu) {

    const toggleMenu = (forceClose = false) => {
      const isOpen = !mobileMenu.classList.contains('hidden') && !forceClose;

      if (isOpen) {
        // Fermer
        mobileMenu.classList.add('hidden');
        iconOpen?.classList.remove('hidden');
        iconClose?.classList.add('hidden');
        menuBtn.setAttribute('aria-expanded', 'false');
      } else {
        // Ouvrir
        mobileMenu.classList.remove('hidden');
        iconOpen?.classList.add('hidden');
        iconClose?.classList.remove('hidden');
        menuBtn.setAttribute('aria-expanded', 'true');
      }
    };

    menuBtn.addEventListener('click', () => toggleMenu());

    // Fermer le menu en cliquant sur un lien d'ancre
    mobileMenu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => toggleMenu(true));
    });

    // Fermer le menu avec Échap
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') toggleMenu(true);
    });

    // Fermer en cliquant en dehors
    document.addEventListener('click', (e) => {
      if (!navbar?.contains(e.target)) {
        toggleMenu(true);
      }
    });
  }


  /* ── 3. SCROLL REVEAL — IntersectionObserver ─────────────── */
  const revealElements = document.querySelectorAll('.fade-in-up');

  if (revealElements.length > 0 && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target); // animation unique
          }
        });
      },
      {
        threshold: 0.12,
        rootMargin: '0px 0px -40px 0px',
      }
    );

    revealElements.forEach(el => observer.observe(el));
  } else {
    // Pas de support IntersectionObserver → afficher directement
    revealElements.forEach(el => el.classList.add('visible'));
  }


  /* ── 4. MESSAGES DJANGO — animation d'entrée & auto-dismiss ─ */
  const toasts = document.querySelectorAll('.message-toast');

  toasts.forEach((toast, index) => {
    // Entrée avec délai progressif
    setTimeout(() => {
      toast.style.transform = 'translateX(0)';
    }, 80 + index * 120);

    // Auto-suppression après 5 secondes
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(110%)';
      toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      setTimeout(() => toast.remove(), 320);
    }, 5200 + index * 200);
  });


  /* ── 5. LIENS D'ANCRE — scroll doux avec offset navbar ─────── */
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (!href || href === '#') return;

      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        const navbarHeight = navbar?.offsetHeight || 80;
        const targetTop = target.getBoundingClientRect().top + window.scrollY - navbarHeight - 8;

        window.scrollTo({ top: targetTop, behavior: 'smooth' });
      }
    });
  });


  /* ── 6. MISE EN ÉVIDENCE DU LIEN NAV ACTIF au scroll ──────── */
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-link[href^="#"]');

  if (sections.length > 0 && navLinks.length > 0) {
    const activateLink = () => {
      const scrollPos = window.scrollY + 120;

      sections.forEach(section => {
        const top    = section.offsetTop;
        const bottom = top + section.offsetHeight;
        const id     = section.getAttribute('id');

        if (scrollPos >= top && scrollPos < bottom) {
          navLinks.forEach(link => {
            link.classList.remove('text-gold-400');
            if (link.getAttribute('href') === `#${id}`) {
              link.classList.add('text-gold-400');
            }
          });
        }
      });
    };

    window.addEventListener('scroll', activateLink, { passive: true });
  }

});
