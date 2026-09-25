// Claim loader: the customer's own photos float as cards in 3D and a green scan beam passes over each in turn.
// three.js from jsdelivr. If WebGL or the CDN is unavailable, the CSS scan underneath stays visible.
(() => {
  const stage = document.querySelector(".ca-overlay .stage:not([data-live])");
  if (!stage) return;
  stage.dataset.live = "1";
  const overlay = stage.closest(".ca-overlay");
  const photos = JSON.parse(stage.dataset.photos || "[]");
  if (!photos.length || matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  import("https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.min.js")
    .then((THREE) => build(THREE))
    .catch(() => {});

  function build(THREE) {
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch (e) {
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    stage.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x0b1623, 10, 24);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    const CAMERA_Z = 9;

    // Viewfinder corners on a unit square, scaled with each card.
    const bracketGeometry = (() => {
      const L = 0.1, pts = [];
      for (const [x, y] of [[-0.5, 0.5], [0.5, 0.5], [-0.5, -0.5], [0.5, -0.5]]) {
        pts.push(x, y, 0, x - Math.sign(x) * L, y, 0, x, y, 0, x, y - Math.sign(y) * L * 1.4, 0);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      return g;
    })();

    const H = 2.1, R = 8, n = photos.length;
    const spread = Math.min(0.42, 1.2 / Math.max(n - 1, 1));
    // A ring of cards around a centre behind the stage; turning the ring brings each photo to the front.
    const ring = new THREE.Group();
    ring.position.z = -R;
    scene.add(ring);
    const textures = new THREE.TextureLoader();
    const cards = photos.map((src, i) => {
      const angle = (i - (n - 1) / 2) * spread;
      const pivot = new THREE.Group();
      pivot.position.set(Math.sin(angle) * R, 0, Math.cos(angle) * R);
      pivot.rotation.y = angle;
      const mat = new THREE.MeshBasicMaterial({ color: 0x56616f, transparent: true, opacity: 0, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
      mesh.scale.set(H * 1.5, H, 1);
      const bracket = new THREE.LineSegments(bracketGeometry,
        new THREE.LineBasicMaterial({ color: 0x2fae6b, transparent: true, opacity: 0 }));
      bracket.scale.set(H * 1.5 * 1.08, H * 1.08, 1);
      pivot.add(mesh, bracket);
      ring.add(pivot);
      textures.load(src, (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace;
        mat.map = tex;
        mat.needsUpdate = true;
        const ratio = Math.min(Math.max(tex.image.width / tex.image.height, 0.7), 1.8);
        mesh.scale.x = H * ratio;
        bracket.scale.x = H * ratio * 1.08;
      });
      return { pivot, mesh, mat, bracket, angle, phase: i * 1.7 };
    });

    // Scan beam: a thin line with a faint trail above it.
    const trailCanvas = document.createElement("canvas");
    trailCanvas.width = 2;
    trailCanvas.height = 128;
    const ctx = trailCanvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 128);
    gradient.addColorStop(0, "rgba(47,174,107,0)");
    gradient.addColorStop(1, "rgba(47,174,107,0.28)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 2, 128);
    const scanner = new THREE.Group();
    const line = new THREE.Mesh(new THREE.PlaneGeometry(1, 0.018),
      new THREE.MeshBasicMaterial({ color: 0x2fae6b, transparent: true }));
    const trail = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(trailCanvas), transparent: true, depthWrite: false }));
    scanner.add(line, trail);

    const white = new THREE.Color(0xffffff), dim = new THREE.Color(0x56616f);
    const CYCLE = 1900;
    let active = 0, cycleStart = performance.now(), first = true;
    cards[0].pivot.add(scanner);

    const resize = () => {
      const w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.z = CAMERA_Z * Math.max(1, 1 / camera.aspect);
      camera.updateProjectionMatrix();
    };
    new ResizeObserver(resize).observe(stage);
    resize();

    const start = performance.now();
    const frame = (now) => {
      if (!stage.isConnected) {
        renderer.dispose();
        return;
      }
      requestAnimationFrame(frame);
      const t = (now - start) / 1000;
      let p = (now - cycleStart) / CYCLE;
      if (p >= 1) {
        active = (active + 1) % n;
        cycleStart = now;
        p = 0;
        cards[active].pivot.add(scanner);
      }
      const intro = Math.min(t / 1.2, 1);
      cards.forEach((card, i) => {
        const on = i === active;
        card.mat.opacity = intro * (on ? 1 : 0.7);
        card.mat.color.lerp(on ? white : dim, 0.07);
        card.mesh.position.z += ((on ? 0.9 : 0) - card.mesh.position.z) * 0.07;
        card.bracket.position.z = card.mesh.position.z + 0.01;
        card.bracket.material.opacity += ((on ? 1 : 0) - card.bracket.material.opacity) * 0.1;
        card.pivot.position.y = Math.sin(t * 0.9 + card.phase) * 0.07;
      });
      const card = cards[active];
      const width = card.mesh.scale.x * 1.02;
      const eased = p < 0.85 ? p / 0.85 : 1;
      const trailLength = Math.min(0.45 * H, eased * H);
      scanner.position.set(0, H / 2 - eased * H, card.mesh.position.z + 0.02);
      line.scale.x = width;
      line.material.opacity = p < 0.85 ? 1 : 1 - (p - 0.85) / 0.15;
      trail.scale.set(width, Math.max(trailLength, 0.001), 1);
      trail.position.y = trailLength / 2;
      trail.material.opacity = line.material.opacity;
      ring.rotation.y += (-card.angle - ring.rotation.y) * 0.05;
      camera.position.x = Math.sin(t * 0.25) * 0.35;
      camera.position.y = 0.55 + Math.sin(t * 0.33) * 0.12;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
      if (first) {
        first = false;
        overlay.classList.add("webgl");
      }
    };
    requestAnimationFrame(frame);
  }
})();
