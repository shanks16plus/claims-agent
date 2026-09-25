// Page motion with GSAP. Runs once per browser tab and watches for new Streamlit elements.
// Mark up elements in HTML, no per-page code:
//   data-reveal="up|fade|clip|stagger"  animate in when scrolled into view (data-delay in seconds)
//   data-split                           headline words rise in one by one
//   data-count="1500"                    number counts up (data-decimals, data-suffix)
//   data-flow                            the decision diagram draws itself, then pulses run along it
//   data-parallax="40"                   photo drifts up to 40px while scrolling
(() => {
  if (window.__caMotion) { window.__caMotion.scan(); return; }
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let motionScan = () => {};
  const scan = () => { mountSvgs(); mountVideos(); mountSteps(); motionScan(); };
  window.__caMotion = { scan };

  // Videos are created here, in the live page: a video tag parsed by st.html plays but never paints.
  // (Keep this file free of a less-than sign followed by a letter: Streamlit drops a script that has one.)
  // Each one plays only while on screen. With reduced motion the poster photo stays instead.
  const visible = new Set();
  const onScreen = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        visible.add(entry.target);
        entry.target.play().catch(() => {});
      } else {
        visible.delete(entry.target);
        entry.target.pause();
      }
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) visible.forEach((video) => video.isConnected && video.play().catch(() => {}));
  });
  // SVG arrives base64-encoded in data-svg (st.html strips SVG tags).
  function mountSvgs() {
    document.querySelectorAll("[data-svg]:not([data-mounted])").forEach((slot) => {
      slot.dataset.mounted = "1";
      const bytes = Uint8Array.from(atob(slot.dataset.svg), (c) => c.charCodeAt(0));
      slot.innerHTML = new TextDecoder().decode(bytes);
    });
  }

  // "How it works": the step in the middle of the screen lights up and its photo shows.
  function mountSteps() {
    document.querySelectorAll("[data-how]:not([data-mounted])").forEach((block) => {
      block.dataset.mounted = "1";
      const steps = [...block.querySelectorAll(".ca-how-step")];
      const photos = [...block.querySelectorAll(".ca-how-media .ca-photo")];
      const show = (i) => {
        steps.forEach((s) => s.classList.toggle("on", s.dataset.i === i));
        photos.forEach((p) => p.classList.toggle("on", p.dataset.i === i));
      };
      const watch = new IntersectionObserver((entries) => {
        entries.forEach((e) => e.isIntersecting && show(e.target.dataset.i));
      }, { rootMargin: "-45% 0px -45% 0px" });
      steps.forEach((s) => watch.observe(s));
    });
  }

  function mountVideos() {
    if (reduce) return;
    document.querySelectorAll(".ca-video[data-src]:not([data-mounted])").forEach((slot) => {
      slot.dataset.mounted = "1";
      const video = document.createElement("video");
      Object.assign(video, { muted: true, loop: true, playsInline: true, autoplay: true, preload: "auto" });
      if (slot.dataset.controls) video.controls = true;
      else video.className = "zoom";
      video.src = slot.dataset.src;
      video.addEventListener("playing", () => slot.classList.add("on"), { once: true });
      slot.appendChild(video);
      onScreen.observe(video);
    });
  }

  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; scan(); });
  }).observe(document.body, { childList: true, subtree: true });
  scan();

  if (reduce) return;
  const html = document.documentElement;
  html.classList.add("ca-motion");
  const failsafe = setTimeout(() => html.classList.remove("ca-motion"), 3500);

  const script = document.createElement("script");
  script.src = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js";
  script.onload = start;
  script.onerror = () => html.classList.remove("ca-motion");
  document.head.appendChild(script);

  function start() {
    clearTimeout(failsafe);
    const gsap = window.gsap;
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        io.unobserve(entry.target);
        play(entry.target);
      }
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

    function splitWords(el) {
      if (el.dataset.splitDone) return;
      el.dataset.splitDone = "1";
      const walk = (node) => {
        for (const child of [...node.childNodes]) {
          if (child.nodeType === 3) {
            const parts = child.textContent.split(/(\s+)/);
            const frag = document.createDocumentFragment();
            for (const part of parts) {
              if (!part) continue;
              if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); continue; }
              const outer = document.createElement("span");
              outer.className = "w";
              const inner = document.createElement("span");
              inner.textContent = part;
              outer.appendChild(inner);
              frag.appendChild(outer);
            }
            child.replaceWith(frag);
          } else if (child.nodeType === 1) {
            walk(child);
          }
        }
      };
      walk(el);
      el.classList.add("ca-split");
    }

    function prepare(el) {
      el.dataset.revealed = "ready";
      const kind = el.dataset.reveal || "up";
      if (el.hasAttribute("data-split")) {
        splitWords(el);
        gsap.set(el, { opacity: 1 });
        gsap.set(el.querySelectorAll(".w > span"), { yPercent: 115 });
      } else if (kind === "clip") {
        // Clip the image, not the observed element: a fully clipped target never counts as on screen.
        gsap.set(el, { opacity: 1 });
        gsap.set(el.querySelector("img") || el, { clipPath: "inset(100% 0% 0% 0%)", scale: 1.25 });
      } else if (kind === "stagger") {
        gsap.set(el, { opacity: 1 });
        gsap.set(el.children, { opacity: 0, y: 44 });
      } else if (kind === "fade") {
        gsap.set(el, { opacity: 0 });
      } else {
        gsap.set(el, { opacity: 0, y: 36 });
      }
      if (el.hasAttribute("data-flow")) prepareFlow(el);
      io.observe(el);
    }

    function play(el) {
      el.dataset.revealed = "done";
      const kind = el.dataset.reveal || "up";
      const delay = parseFloat(el.dataset.delay || "0");
      if (el.hasAttribute("data-split")) {
        gsap.to(el.querySelectorAll(".w > span"), { yPercent: 0, duration: 1.1, ease: "power4.out", stagger: 0.055, delay });
      } else if (kind === "clip") {
        const img = el.querySelector("img") || el;
        gsap.to(img, { clipPath: "inset(0% 0% 0% 0%)", duration: 1.35, ease: "expo.out", delay });
        gsap.to(img, { scale: 1, duration: 1.8, ease: "expo.out", delay });
      } else if (kind === "stagger") {
        gsap.to(el.children, { opacity: 1, y: 0, duration: 1, ease: "power3.out", stagger: 0.12, delay });
      } else if (kind === "fade") {
        gsap.to(el, { opacity: 1, duration: 1.2, ease: "power2.out", delay });
      } else {
        gsap.to(el, { opacity: 1, y: 0, duration: 1, ease: "power3.out", delay });
      }
      el.querySelectorAll("[data-count]").forEach((n) => countUp(n, delay + 0.2));
      if (el.hasAttribute("data-flow")) playFlow(el, delay);
    }

    function countUp(node, delay) {
      const target = parseFloat(node.dataset.count);
      const decimals = parseInt(node.dataset.decimals || "0", 10);
      const state = { v: 0 };
      const render = () => {
        node.textContent = state.v.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      };
      render();
      gsap.to(state, { v: target, duration: 1.8, ease: "power2.out", delay, onUpdate: render });
    }

    // Decision diagram: nodes appear in order, wires draw between them, then pulses travel the two routes.
    function prepareFlow(el) {
      gsap.set(el.querySelectorAll(".node"), { opacity: 0, y: 12 });
      el.querySelectorAll(".wire").forEach((wire) => {
        const length = wire.getTotalLength();
        gsap.set(wire, { strokeDasharray: length, strokeDashoffset: length });
      });
      gsap.set(el.querySelectorAll(".pulse"), { opacity: 0 });
    }

    function playFlow(el, delay) {
      // Wires with data-order n connect the nodes of order n - 1 to those of order n.
      const tl = gsap.timeline({ delay: delay + 0.3 });
      const orders = [...new Set([...el.querySelectorAll(".node")].map((n) => +n.dataset.order))].sort((a, b) => a - b);
      orders.forEach((order, i) => {
        tl.to(el.querySelectorAll(`.node[data-order="${order}"]`), { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, i * 0.5);
        const next = el.querySelectorAll(`.wire[data-order="${order + 1}"]`);
        if (next.length) tl.to(next, { strokeDashoffset: 0, duration: 0.55, ease: "power2.inOut" }, i * 0.5 + 0.3);
      });
      tl.call(() => el.querySelectorAll(".pulse").forEach((pulse, i) => runPulse(el, pulse, i * 2.2)));
    }

    function runPulse(el, pulse, delay) {
      const route = pulse.dataset.route.split(",").map((id) => el.querySelector(`#${id}`));
      const lengths = route.map((p) => p.getTotalLength());
      const total = lengths.reduce((a, b) => a + b, 0);
      const state = { d: 0 };
      const place = () => {
        let d = state.d;
        for (let i = 0; i < route.length; i++) {
          if (d <= lengths[i] || i === route.length - 1) {
            const pt = route[i].getPointAtLength(Math.min(d, lengths[i]));
            pulse.setAttribute("cx", pt.x);
            pulse.setAttribute("cy", pt.y);
            return;
          }
          d -= lengths[i];
        }
      };
      gsap.timeline({ repeat: -1, delay, repeatDelay: 2.2 })
        .set(pulse, { opacity: 1 })
        .to(state, { d: total, duration: 2.6, ease: "power1.inOut", onUpdate: place })
        .to(pulse, { opacity: 0, duration: 0.3 });
    }

    // Parallax inside Streamlit's scrolling main section.
    const drifting = new Set();
    let ticking = false;
    const scroller = () => document.querySelector("section.stMain") || window;
    const drift = () => {
      ticking = false;
      const mid = innerHeight / 2;
      drifting.forEach((el) => {
        if (!el.isConnected) { drifting.delete(el); return; }
        const rect = el.getBoundingClientRect();
        if (rect.bottom < -200 || rect.top > innerHeight + 200) return;
        const shift = ((rect.top + rect.height / 2 - mid) / innerHeight) * parseFloat(el.dataset.parallax);
        const img = el.querySelector("img");
        if (img) img.style.translate = `0 ${(-shift).toFixed(1)}px`;
      });
    };
    let boundScroller = null;
    const bindScroll = () => {
      const s = scroller();
      if (s === boundScroller) return;
      boundScroller = s;
      s.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(drift); } }, { passive: true });
    };

    function scanReveals() {
      document.querySelectorAll("[data-reveal]:not([data-revealed])").forEach(prepare);
      document.querySelectorAll("[data-parallax]:not([data-drifting])").forEach((el) => {
        el.dataset.drifting = "1";
        drifting.add(el);
      });
      bindScroll();
      drift();
    }

    motionScan = scanReveals;
    scanReveals();
  }
})();
