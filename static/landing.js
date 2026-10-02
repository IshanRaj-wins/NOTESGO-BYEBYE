// Studit landing: ShaderGradient "halo" plane ported to raw three.js, plus GSAP scroll story.
let THREE;   // loaded lazily (dynamic import) so parsing three.js never blocks first paint

const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const isMobile = matchMedia("(max-width: 860px)").matches;
const canvas = document.getElementById("halo");

// Scroll-driven state the render loop reads (tweened by GSAP)
const S = { strength: 4, density: 1.3, speed: 0.4, rotZ: 50, posX: -1.4, dist: 3.6, bright: 1.2, pull: 0, veil: 0 };
const mouse = { x: 0, y: 0, tx: 0, ty: 0 };

// ---------------------------------------------------------------- WebGL halo
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;}
vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 permute(vec4 x){return mod289(((x*34.)+1.)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);
  vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
  float n_=.142857142857;vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.*x_);
  vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.+1.;vec4 s1=floor(b1)*2.+1.;vec4 sh=-step(h,vec4(0.));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;
  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const vertex = /* glsl */ `
uniform float uTime, uSpeed, uDensity, uStrength, uAmplitude, uFrequency, uPull;
uniform vec2 uMouse;
varying float vDist; varying vec3 vN; varying vec3 vPos;
${NOISE}
float t;
// ShaderGradient plane: noise displacement + a travelling wave, bent by cursor, pulled by scroll
float disp(vec2 q, out float n){
  n = snoise(vec3(q * uDensity * .43, t));
  float wave = sin(q.x * uFrequency * .12 + t * 1.3) * uAmplitude * .18;
  float d = (n * .75 + wave) * uStrength * .16;
  d += exp(-dot(q - uMouse * 2.2, q - uMouse * 2.2) * .35) * .35;
  d -= uPull * smoothstep(3.5, 0., length(q)) * 1.2;
  n = n * .5 + .5 + wave;
  return d;
}
void main(){
  t = uTime * uSpeed;
  float n, nx, ny, e = .04;
  float d = disp(position.xy, n);
  float dx = disp(position.xy + vec2(e, 0.), nx) - d;
  float dy = disp(position.xy + vec2(0., e), ny) - d;
  vN = normalize(normalMatrix * normalize(vec3(-dx / e, -dy / e, 1.)));
  vec3 p = vec3(position.xy, d);
  vDist = n;
  vPos = (modelViewMatrix * vec4(p, 1.)).xyz;
  gl_Position = projectionMatrix * vec4(vPos, 1.);
}`;

const fragment = /* glsl */ `
uniform vec3 uC1, uC2, uC3; uniform float uBright, uTime;
varying float vDist; varying vec3 vN; varying vec3 vPos;
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
void main(){
  float t = clamp(vDist, 0., 1.);
  // black valleys -> ember -> sand crest -> rare lilac peaks
  vec3 col = mix(vec3(0.), uC1, smoothstep(.18, .5, t));
  col = mix(col, uC2, smoothstep(.5, .74, t));
  col = mix(col, uC3, smoothstep(.8, 1., t));
  // "3d" light with a small reflection (reflection 0.1)
  vec3 N = normalize(vN); if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(-vPos);
  vec3 L = normalize(vec3(-.3, .5, .8));
  float diff = max(dot(N, L), 0.) * .55 + .55;
  float spec = pow(max(dot(reflect(-L, N), V), 0.), 32.) * .1;
  float rim = pow(1. - max(dot(N, V), 0.), 3.) * .25;
  col = col * diff * uBright + spec + rim * uC2 * t;
  col += (hash(gl_FragCoord.xy + fract(uTime) * 91.) - .5) * .06;   // grain
  gl_FragColor = vec4(col, 1.);
}`;

function startWebGL() {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: !isMobile, powerPreference: "high-performance" });
  } catch { return false; }
  renderer.setPixelRatio(isMobile ? 0.65 : Math.min(devicePixelRatio, 1.5));   // phones: the halo is a soft gradient, so sub-1x is invisible and ~60% cheaper
  renderer.setClearColor(0x000000, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 100);

  const uniforms = {
    uTime: { value: 0 }, uSpeed: { value: S.speed }, uDensity: { value: S.density }, uStrength: { value: S.strength },
    uAmplitude: { value: 1 }, uFrequency: { value: 5.5 }, uPull: { value: 0 }, uMouse: { value: new THREE.Vector2() },
    uBright: { value: S.bright },
    uC1: { value: new THREE.Color("#ff5005") }, uC2: { value: new THREE.Color("#dbba95") }, uC3: { value: new THREE.Color("#d0bce1") },
  };
  const seg = isMobile ? 96 : 300;
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(18, 18, seg, seg),
    new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: fragment, uniforms, side: THREE.DoubleSide })
  );
  const deg = THREE.MathUtils.degToRad;
  plane.rotation.set(0, deg(10), deg(50));
  plane.position.set(S.posX, 0, 0);
  scene.add(plane);

  // dust: ember/sand motes drifting in front of the halo
  const COUNT = isMobile ? 600 : 4000;
  const pos = new Float32Array(COUNT * 3), col = new Float32Array(COUNT * 3), seed = new Float32Array(COUNT);
  const palette = [new THREE.Color("#ff5005"), new THREE.Color("#dbba95"), new THREE.Color("#ede8df")];
  for (let i = 0; i < COUNT; i++) {
    pos[i * 3] = (Math.random() - .5) * 9; pos[i * 3 + 1] = (Math.random() - .5) * 6; pos[i * 3 + 2] = -Math.random() * 2.6;
    const c = palette[i % 3]; col.set([c.r, c.g, c.b], i * 3); seed[i] = Math.random();
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  const dust = new THREE.Points(g, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
    uniforms: { uTime: uniforms.uTime, uPull: uniforms.uPull, uPx: { value: renderer.getPixelRatio() } },
    vertexShader: `attribute float seed; uniform float uTime, uPull, uPx; varying vec3 vC; varying float vA;
      void main(){ vC = color; vec3 p = position;
        p.y += sin(uTime * .25 + seed * 40.) * .25; p.x += cos(uTime * .2 + seed * 30.) * .2;
        p.xy *= 1. - uPull * .85 * (0.4 + seed * .6);          // motes get sucked into the core
        vec4 mv = modelViewMatrix * vec4(p, 1.);
        gl_PointSize = (1.2 + seed * 2.6) * uPx * (3. / -mv.z);
        vA = (.25 + seed * .55) * (.6 + .4 * sin(uTime * 1.5 + seed * 20.));
        gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying vec3 vC; varying float vA;
      void main(){ float d = length(gl_PointCoord - .5); if (d > .5) discard; gl_FragColor = vec4(vC, vA * smoothstep(.5, 0., d)); }`,
  }));
  scene.add(dust);

  const resize = () => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    // keep the halo framed on portrait screens
    camera.fov = camera.aspect < 1 ? 45 + (1 - camera.aspect) * 30 : 45;
    camera.updateProjectionMatrix();
  };
  addEventListener("resize", resize); resize();

  const clock = new THREE.Clock();
  let running = true;
  document.addEventListener("visibilitychange", () => { running = !document.hidden; if (running) { clock.getDelta(); loop(); } });
  let lastFrame = 0;
  function loop(now = 0) {
    if (!running) return;
    if (isMobile && !reduce && now - lastFrame < 32) { requestAnimationFrame(loop); return; }   // phones: 30 fps
    lastFrame = now;
    const dt = Math.min(clock.getDelta(), .05);
    uniforms.uTime.value += reduce ? 0 : dt;
    mouse.x += (mouse.tx - mouse.x) * .05; mouse.y += (mouse.ty - mouse.y) * .05;
    uniforms.uMouse.value.set(-mouse.x, mouse.y);   // camera looks from -z, so x is mirrored
    uniforms.uStrength.value = S.strength; uniforms.uDensity.value = S.density; uniforms.uPull.value = S.pull;
    uniforms.uBright.value = S.bright;
    plane.rotation.z = deg(S.rotZ); plane.position.x = S.posX;
    // ShaderGradient camera: azimuth 180°, polar 90°, distance 3.6
    camera.position.set(mouse.x * .15, mouse.y * .1, -S.dist); camera.lookAt(0, 0, 0);
    dust.rotation.z = uniforms.uTime.value * .02;
    renderer.render(scene, camera);
    if (!reduce) requestAnimationFrame(loop);
  }
  loop();
  if (reduce) addEventListener("resize", () => renderer.render(scene, camera));
  return true;
}

// Instant hero: show the static CSS halo first, then boot WebGL when the main thread is idle
// and cross-fade to it. Keeps three.js parse + shader compile out of the first second on phones.
const fallback = document.querySelector(".halo-fallback");
fallback.hidden = false;
const whenIdle = window.requestIdleCallback || ((f) => setTimeout(f, 300));
const bootWebGL = () => whenIdle(async () => {
  try { THREE = await import("three"); } catch { canvas.hidden = true; return; }
  if (!startWebGL()) { canvas.hidden = true; return; }
  fallback.style.transition = "opacity 1.2s ease";
  requestAnimationFrame(() => (fallback.style.opacity = 0));
  setTimeout(() => (fallback.hidden = true), 1300);
}, { timeout: 2500 });
if (document.readyState === "complete") bootWebGL(); else addEventListener("load", bootWebGL);
addEventListener("pointermove", (e) => { mouse.tx = e.clientX / innerWidth - .5; mouse.ty = -(e.clientY / innerHeight - .5); });

// ---------------------------------------------------------------- split headline
document.querySelectorAll("[data-split]").forEach((el) => {
  const walk = (node) => [...node.childNodes].map((c) => {
    if (c.nodeType === 3) return c.textContent.split(/(\s+)/).map((w) => (w.trim() ? `<span class="w"><span>${w}</span></span>` : w)).join("");
    if (c.nodeName === "BR") return "<br>";
    const tag = c.nodeName.toLowerCase(); return `<${tag}${c.className ? ` class="${c.className}"` : ""}>${walk(c)}</${tag}>`;
  }).join("");
  el.innerHTML = walk(el);
});

// ---------------------------------------------------------------- counters
function countUp(el, dur = 1.6) {
  const end = Number(el.dataset.count) || 0;
  if (reduce || !window.gsap) { el.textContent = end.toLocaleString("en-IN"); return; }
  const o = { v: 0 };
  gsap.to(o, { v: end, duration: dur, ease: "power3.out", onUpdate: () => (el.textContent = Math.round(o.v).toLocaleString("en-IN")) });
}

// ---------------------------------------------------------------- typed search
function typeIt(el) {
  const text = el.dataset.typed; let i = 0;
  const tick = () => { el.textContent = text.slice(0, ++i); if (i < text.length) setTimeout(tick, 55 + Math.random() * 60); };
  tick();
}

// ---------------------------------------------------------------- scroll story
const bar = document.querySelector(".progress");
addEventListener("scroll", () => { if (bar) bar.style.transform = `scaleX(${scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight)})`; }, { passive: true });

function intro() {
  document.body.classList.remove("is-loading");
  if (!window.gsap || reduce) return;
  gsap.timeline({ defaults: { ease: "expo.out" } })
    .from(".hero-title .w > span", { yPercent: 110, duration: 1.4, stagger: .06 }, .15)
    .from(".reveal-up", { y: 24, opacity: 0, duration: 1.1, stagger: .12 }, .5)
    .from(".hero-foot > *", { y: 12, opacity: 0, duration: .9, stagger: .08 }, .9)
    .from(S, { strength: 9, dist: 5.2, duration: 2.6, ease: "power3.out" }, 0);
}

function story() {
  if (!window.gsap || !window.ScrollTrigger || reduce) {
    document.querySelectorAll("[data-count]").forEach((el) => countUp(el));
    document.querySelectorAll("[data-typed]").forEach((el) => (el.textContent = el.dataset.typed));
    return;
  }
  gsap.registerPlugin(ScrollTrigger);

  // Lenis smooth scroll driven by GSAP's ticker
  // phones scroll natively; Lenis there only doubles ScrollTrigger updates per frame
  if (window.Lenis && !isMobile) {
    const lenis = new Lenis({ lerp: .09, smoothWheel: true });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); lenis.scrollTo(a.getAttribute("href")); }));
  }

  // hero exit: halo drifts to centre and the copy lifts away
  gsap.timeline({ scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } })
    .to(".hero-in", { yPercent: -18, opacity: 0, ease: "none" }, 0)
    .to(".hero-foot", { opacity: 0, ease: "none" }, 0)
    .to(S, { posX: 0, rotZ: 20, dist: 3.1, ease: "none" }, 0);

  // problem: chips swirl into the halo, which collapses into a core
  const chips = gsap.utils.toArray(".chip");
  const tl = gsap.timeline({ scrollTrigger: { trigger: ".problem", start: "top top", end: isMobile ? "+=100%" : "+=130%", scrub: 1, pin: true } });
  // blur() filters repaint every frame: desktop only
  const blurIn = isMobile ? {} : { filter: "blur(10px)" }, blurOut = isMobile ? {} : { filter: "blur(6px)" };
  tl.from(chips, { opacity: 0, scale: .6, ...blurIn, stagger: .05, duration: .5, ease: "power2.out" }, 0)
    .from(".p-line-1, .p-title-1", { opacity: 0, y: 40, duration: .4 }, .1)
    .to(chips, { x: 0, y: 0, rotation: () => gsap.utils.random(-40, 40), scale: .05, opacity: 0, ...blurOut,
                 duration: 1, stagger: .04, ease: "power3.in" }, .9)
    .to(S, { pull: 1, strength: 6.5, rotZ: 140, dist: 2.7, duration: 1.2, ease: "power2.inOut" }, .9)
    .to(".p-line-1, .p-title-1", { opacity: 0, y: -40, scale: .96, duration: .4 }, 1.5)
    .fromTo(".p-core", { opacity: 0, scale: .4 }, { opacity: .55, scale: 1, duration: .8, ease: "power2.out" }, 1.3)
    .to(".p-title-2", { opacity: 1, duration: .5 }, 1.8)
    .from(".p-title-2", { scale: 1.12, ...(isMobile ? {} : { filter: "blur(12px)" }), duration: .5 }, 1.8)
    .to(S, { pull: .15, strength: 3.2, rotZ: 200, dist: 4.4, duration: 1, ease: "power2.out" }, 2.1)
    .to(".veil", { opacity: .45, duration: .6 }, 2.4);

  // features: bento tiles reveal (no scroll-jacking); halo drifts while the grid passes
  gsap.utils.toArray(".tile").forEach((t, i) => gsap.from(t, { y: 60, opacity: 0, duration: 1.1, ease: "expo.out", delay: (i % 3) * .08, scrollTrigger: { trigger: t, start: "top 88%" } }));
  gsap.to(S, { posX: 1.6, rotZ: 250, strength: 2.4, ease: "none", scrollTrigger: { trigger: ".features", start: "top bottom", end: "bottom top", scrub: true } });
  ScrollTrigger.create({ trigger: ".features", start: "top 60%", once: true, onEnter: () => document.querySelectorAll("[data-typed]").forEach(typeIt) });

  // numbers
  ScrollTrigger.create({ trigger: ".numbers", start: "top 70%", once: true, onEnter: () => document.querySelectorAll(".num-grid [data-count]").forEach((el) => countUp(el, 2)) });
  gsap.from(".num-grid > div", { y: 50, opacity: 0, stagger: .1, duration: 1.1, ease: "expo.out", scrollTrigger: { trigger: ".num-grid", start: "top 85%" } });

  // sdg
  gsap.from(".sdg-badge", { rotate: -12, scale: .7, opacity: 0, duration: 1.2, ease: "back.out(1.6)", scrollTrigger: { trigger: ".sdg", start: "top 75%" } });
  gsap.from(".sdg-in > div:last-child > *", { y: 30, opacity: 0, stagger: .1, duration: 1, ease: "expo.out", scrollTrigger: { trigger: ".sdg", start: "top 75%" } });

  // final: halo floods the screen, veil lifts
  gsap.timeline({ scrollTrigger: { trigger: ".final", start: "top bottom", end: "top top", scrub: true } })
    .to(".veil", { opacity: 0, ease: "none" }, 0)
    .to(S, { posX: 0, rotZ: 320, dist: 2.2, strength: 5, pull: 0, bright: 1.05, ease: "none" }, 0);
  gsap.from(".final-title, .final .hero-ctas, .final .eyebrow", { y: 50, opacity: 0, stagger: .12, duration: 1.2, ease: "expo.out", scrollTrigger: { trigger: ".final", start: "top 55%" } });
}

const boot = () => { intro(); story(); };
if (document.readyState === "complete") boot(); else addEventListener("load", boot);
