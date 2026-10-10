document.addEventListener("DOMContentLoaded", () => {
  const clock = document.getElementById("activity-clock");
  if (clock) {
    const start = Number(clock.dataset.start);
    const tick = () => {
      let seconds = Math.max(0, Math.floor(Date.now()/1000 - start));
      const h = String(Math.floor(seconds/3600)).padStart(2,"0");
      const m = String(Math.floor((seconds%3600)/60)).padStart(2,"0");
      const s = String(seconds%60).padStart(2,"0");
      clock.textContent = `${h}:${m}:${s}`;
    };
    tick(); setInterval(tick, 1000);
  }
});
