(() => {
  document.querySelectorAll('[data-companion-button]').forEach((button) => {
    const speech = button.querySelector('.companion-speech');
    const lines = (button.dataset.lines || speech?.textContent || '')
      .split('|')
      .map((line) => line.trim())
      .filter(Boolean);
    let lineIndex = 0;
    let settleTimer = 0;

    button.addEventListener('click', () => {
      if (lines.length > 1) {
        lineIndex = (lineIndex + 1) % lines.length;
        if (speech) speech.textContent = lines[lineIndex];
      }

      clearTimeout(settleTimer);
      button.classList.remove('is-reacting');
      void button.offsetWidth;
      button.classList.add('is-reacting');
      button.setAttribute('aria-pressed', 'true');

      settleTimer = window.setTimeout(() => {
        button.classList.remove('is-reacting');
        button.setAttribute('aria-pressed', 'false');
      }, 2400);
    });
  });
})();
