/**
 * STUDY GUARD — "OBSIDIAN & EMBER" DYNAMIC SCRIPT
 * Theme switching, micro-interactions, quiz engine, drag-drop upload, count-ups, confetti
 */

(function () {
  'use strict';

  // 1. THEME SWITCHER WITH LOCALSTORAGE PERSISTENCE
  const THEME_KEY = 'studyguard-theme-preference';

  function applyTheme(theme) {
    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    const themeIcon = document.getElementById('theme-toggle-icon');
    if (themeIcon) {
      themeIcon.className = theme === 'light' ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
    }
  }

  const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(savedTheme);

  document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
        const next = current === 'light' ? 'dark' : 'light';
        localStorage.setItem(THEME_KEY, next);
        applyTheme(next);
      });
    }

    // 2. STAGGERED FADE-UP ANIMATIONS
    const fadeItems = document.querySelectorAll('.fade-up-item');
    fadeItems.forEach((el, index) => {
      setTimeout(() => {
        el.classList.add('is-visible');
      }, index * 80);
    });

    // 3. STAT NUMBER COUNT-UP ANIMATION
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const countUpElements = document.querySelectorAll('[data-countup]');

    countUpElements.forEach(el => {
      const targetStr = el.getAttribute('data-countup');
      const target = parseFloat(targetStr);
      if (isNaN(target)) return;
      const isPercent = targetStr.includes('%') || el.innerText.includes('%');
      const duration = prefersReducedMotion ? 0 : 1200;

      if (duration === 0) {
        el.textContent = isPercent ? `${target}%` : target;
        return;
      }

      let startTime = null;
      function animateCount(timestamp) {
        if (!startTime) startTime = timestamp;
        const progress = Math.min((timestamp - startTime) / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3); // cubic ease-out
        const currentVal = Math.round(easeProgress * target * 10) / 10;
        el.textContent = isPercent ? `${currentVal}%` : currentVal;
        if (progress < 1) {
          requestAnimationFrame(animateCount);
        } else {
          el.textContent = isPercent ? `${target}%` : target;
        }
      }
      requestAnimationFrame(animateCount);
    });

    // 4. TOAST AUTO-DISMISS
    const toastItems = document.querySelectorAll('.custom-toast');
    toastItems.forEach(t => {
      setTimeout(() => {
        t.style.opacity = '0';
        t.style.transform = 'translateY(10px)';
        t.style.transition = 'all 0.3s ease';
        setTimeout(() => t.remove(), 300);
      }, 5000);
    });

    // 5. DRAG-AND-DROP FILE UPLOAD ZONE
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-upload-input');
    const filePreview = document.getElementById('file-preview-wrap');
    const fileNameSpan = document.getElementById('preview-file-name');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const uploadForm = document.getElementById('upload-notes-form');
    const uploadProgress = document.getElementById('upload-progress-wrap');
    const uploadFill = document.getElementById('upload-progress-fill');

    if (dropzone && fileInput) {
      ['dragenter', 'dragover'].forEach(evt => {
        dropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('is-dragover');
        });
      });

      ['dragleave', 'drop'].forEach(evt => {
        dropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('is-dragover');
        });
      });

      dropzone.addEventListener('drop', e => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
          fileInput.files = files;
          updateFilePreview(files[0]);
        }
      });

      dropzone.addEventListener('click', (e) => {
        if (e.target !== removeFileBtn && !removeFileBtn?.contains(e.target)) {
          fileInput.click();
        }
      });

      fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
          updateFilePreview(fileInput.files[0]);
        }
      });

      if (removeFileBtn) {
        removeFileBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          fileInput.value = '';
          if (filePreview) filePreview.style.display = 'none';
        });
      }

      function updateFilePreview(file) {
        if (filePreview && fileNameSpan) {
          const sizeKb = Math.round(file.size / 1024);
          fileNameSpan.textContent = `${file.name} (${sizeKb} KB)`;
          filePreview.style.display = 'flex';
        }
      }

      if (uploadForm && uploadProgress && uploadFill) {
        uploadForm.addEventListener('submit', () => {
          uploadProgress.style.display = 'block';
          let progress = 10;
          uploadFill.style.width = '10%';
          const interval = setInterval(() => {
            progress += 15;
            if (progress > 90) clearInterval(interval);
            uploadFill.style.width = `${progress}%`;
          }, 150);
        });
      }
    }

    // 6. QUIZ GENERATING SKELETON / SPINNER OVERLAY
    const quizForms = document.querySelectorAll('.quiz-generator-form');
    const quizOverlay = document.getElementById('quiz-generating-overlay');
    quizForms.forEach(form => {
      form.addEventListener('submit', () => {
        if (quizOverlay) {
          quizOverlay.style.display = 'flex';
        }
      });
    });

    // 7. QUIZ RUNNER (ONE QUESTION AT A TIME & KEYBOARD SHORTCUTS)
    const quizRunner = document.getElementById('quiz-runner');
    if (quizRunner) {
      const slides = Array.from(document.querySelectorAll('.quiz-card-slide'));
      const totalQuestions = slides.length;
      let currentIndex = 0;

      const progressFill = document.getElementById('quiz-progress-fill');
      const progressText = document.getElementById('quiz-progress-text');
      const prevBtn = document.getElementById('quiz-prev-btn');
      const nextBtn = document.getElementById('quiz-next-btn');
      const submitBtn = document.getElementById('quiz-submit-btn');

      function updateQuizView() {
        slides.forEach((slide, idx) => {
          if (idx === currentIndex) {
            slide.classList.add('is-active');
          } else {
            slide.classList.remove('is-active');
          }
        });

        const pct = Math.round(((currentIndex + 1) / totalQuestions) * 100);
        if (progressFill) progressFill.style.width = `${pct}%`;
        if (progressText) progressText.textContent = `Question ${currentIndex + 1} of ${totalQuestions} (${pct}%)`;

        if (prevBtn) {
          prevBtn.disabled = currentIndex === 0;
          prevBtn.style.opacity = currentIndex === 0 ? '0.35' : '1';
        }

        if (nextBtn && submitBtn) {
          if (currentIndex === totalQuestions - 1) {
            nextBtn.style.display = 'none';
            submitBtn.style.display = 'inline-flex';
          } else {
            nextBtn.style.display = 'inline-flex';
            submitBtn.style.display = 'none';
          }
        }
      }

      // Option card click handling
      slides.forEach(slide => {
        const optionCards = slide.querySelectorAll('.quiz-option-card');
        optionCards.forEach(card => {
          card.addEventListener('click', () => {
            const radio = card.querySelector('input[type="radio"]');
            if (radio) {
              radio.checked = true;
              optionCards.forEach(c => c.classList.remove('is-selected'));
              card.classList.add('is-selected');
            }
          });
        });
      });

      if (prevBtn) {
        prevBtn.addEventListener('click', () => {
          if (currentIndex > 0) {
            currentIndex--;
            updateQuizView();
          }
        });
      }

      if (nextBtn) {
        nextBtn.addEventListener('click', () => {
          if (currentIndex < totalQuestions - 1) {
            currentIndex++;
            updateQuizView();
          }
        });
      }

      // Keyboard Shortcuts: 1,2,3,4 for options, Enter/Right for next, Left for back
      document.addEventListener('keydown', (e) => {
        const activeSlide = slides[currentIndex];
        if (!activeSlide) return;

        const key = e.key;
        if (['1', '2', '3', '4'].includes(key)) {
          const index = parseInt(key, 10) - 1;
          const optionCards = activeSlide.querySelectorAll('.quiz-option-card');
          if (optionCards[index]) {
            optionCards[index].click();
          }
        } else if (key === 'ArrowRight' || key === 'Enter') {
          if (currentIndex < totalQuestions - 1) {
            e.preventDefault();
            currentIndex++;
            updateQuizView();
          }
        } else if (key === 'ArrowLeft' || key === 'Backspace') {
          if (e.target.tagName !== 'INPUT' && currentIndex > 0) {
            e.preventDefault();
            currentIndex--;
            updateQuizView();
          }
        }
      });

      updateQuizView();
    }

    // 8. QUIZ RESULT: CIRCULAR PROGRESS RING & CONFETTI
    const scoreCircle = document.getElementById('score-circle-fill');
    if (scoreCircle) {
      const score = parseFloat(scoreCircle.getAttribute('data-score')) || 0;
      const circumference = 2 * Math.PI * 90; // r=90 => 565.48
      const offset = circumference - (score / 100) * circumference;

      setTimeout(() => {
        scoreCircle.style.strokeDashoffset = offset;
      }, 150);

      if (score >= 70 && !prefersReducedMotion) {
        triggerConfettiBurst();
      }
    }

    // 9. LIGHTWEIGHT CANVAS CONFETTI BURST (STANDALONE VANILLA JS)
    function triggerConfettiBurst() {
      const canvas = document.createElement('canvas');
      canvas.id = 'confetti-canvas';
      canvas.style.position = 'fixed';
      canvas.style.top = '0';
      canvas.style.left = '0';
      canvas.style.width = '100vw';
      canvas.style.height = '100vh';
      canvas.style.pointerEvents = 'none';
      canvas.style.zIndex = '9999';
      document.body.appendChild(canvas);

      const ctx = canvas.getContext('2d');
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;

      const particles = [];
      const colors = ['#FF6B35', '#FFA26B', '#C6F432', '#E2FF66', '#FFFFFF'];

      for (let i = 0; i < 90; i++) {
        particles.push({
          x: canvas.width / 2,
          y: canvas.height / 2 - 50,
          vx: (Math.random() - 0.5) * 16,
          vy: (Math.random() - 0.75) * 18,
          size: Math.random() * 7 + 4,
          color: colors[Math.floor(Math.random() * colors.length)],
          rotation: Math.random() * 360,
          rotationSpeed: (Math.random() - 0.5) * 10,
          opacity: 1,
          gravity: 0.38,
        });
      }

      let animationFrame;
      function renderConfetti() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let alive = false;

        particles.forEach(p => {
          p.x += p.vx;
          p.y += p.vy;
          p.vy += p.gravity;
          p.rotation += p.rotationSpeed;
          p.opacity -= 0.012;

          if (p.opacity > 0) {
            alive = true;
            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate((p.rotation * Math.PI) / 180);
            ctx.fillStyle = p.color;
            ctx.globalAlpha = Math.max(p.opacity, 0);
            ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.7);
            ctx.restore();
          }
        });

        if (alive) {
          animationFrame = requestAnimationFrame(renderConfetti);
        } else {
          cancelAnimationFrame(animationFrame);
          canvas.remove();
        }
      }

      renderConfetti();
    }
  });
})();
