APP_CSS = r"""
<style>
:root {
  --ink: #111111;
  --muted: #737782;
  --line: #dfe2e8;
  --soft: #f5f7fa;
  --blue: #1248f5;
  --blue-soft: #eef2ff;
  --radius: 12px;
}

.stApp { background: #ffffff; color: var(--ink); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppViewContainer"] > .main .block-container {
  max-width: 1440px; padding: 1.4rem 3rem 4rem;
}
html, body, [class*="css"] { font-family: Inter, "Noto Sans SC", "PingFang SC", sans-serif; }
h1, h2, h3, p { color: var(--ink); }

.brand-row {
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--line); padding: .1rem 0 1.1rem; margin-bottom: 2.2rem;
}
.brand { font-size: 2rem; font-weight: 850; letter-spacing: -.07em; }
.api-state { color: var(--muted); font-size: .88rem; }
.api-state strong { color: var(--blue); font-weight: 650; }

.api-copy { padding: 3.2rem 2.5rem 0 0; }
.api-copy .eyebrow {
  color: var(--blue); font-size: .78rem; font-weight: 850;
  letter-spacing: .16em; text-transform: uppercase; margin-bottom: 1rem;
}
.api-copy h1 {
  font-family: Georgia, "Noto Serif SC", serif; font-size: clamp(3.1rem, 5vw, 5.4rem);
  line-height: 1.02; letter-spacing: -.06em; margin: 0 0 1.5rem;
}
.api-copy h1 em { color: var(--blue); font-style: normal; }
.api-copy p { color: var(--muted); font-size: 1.05rem; line-height: 1.75; max-width: 35rem; }
.setup-title {
  font-family: Georgia, "Noto Serif SC", serif; font-size: 2rem;
  font-weight: 750; margin: 2.8rem 0 1.15rem;
}

.hero-copy { padding: 2.2rem 2rem 0 0; }
.hero-copy h1 {
  font-family: Georgia, "Noto Serif SC", serif; font-size: clamp(3.15rem, 4.6vw, 5.2rem);
  line-height: 1.02; letter-spacing: -.06em; margin: 0 0 1.8rem;
}
.hero-copy h1 em { color: var(--blue); font-style: normal; }
.hero-copy p { color: var(--muted); font-size: 1.14rem; line-height: 1.8; max-width: 34rem; }
.garment-mark {
  width: 19rem; height: 15rem; margin: 2.4rem auto 0; opacity: .94;
  background: var(--blue); clip-path: polygon(32% 8%, 43% 0, 57% 0, 68% 8%, 91% 28%, 77% 52%, 69% 44%, 69% 100%, 31% 100%, 31% 44%, 23% 52%, 9% 28%);
}
.garment-mark::after { content: ""; display: block; width: 65%; height: 100%; border-right: 1px solid white; opacity: .45; }

[data-testid="stFileUploader"] {
  border: 1px dashed var(--blue); border-radius: var(--radius); padding: .55rem;
  background: #fbfcff;
}
[data-testid="stFileUploaderDropzone"] { min-height: 160px; background: transparent; }
[data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 1.15rem; font-weight: 650; }
[data-testid="stFileUploaderDropzoneInstructions"] small { color: var(--muted); }

.question { font-size: 1.16rem; font-weight: 760; margin: 1.05rem 0 .4rem; }
[data-testid="stRadio"] > div { gap: .55rem; flex-wrap: wrap; }
[data-testid="stRadio"] label {
  border: 1px solid var(--line); border-radius: 9px; padding: .55rem .85rem;
  background: white; transition: all .18s ease;
}
[data-testid="stRadio"] label:has(input:checked) { color: var(--blue); border-color: var(--blue); background: var(--blue-soft); }
[data-testid="stRadio"] label > div:first-child { display: none; }

.stButton > button, .stDownloadButton > button {
  min-height: 2.8rem; border-radius: 9px; font-weight: 700; font-size: .95rem;
  border: 1px solid var(--line); box-shadow: none; transition: transform .16s ease, border-color .16s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--blue); color: var(--blue); transform: translateY(-1px); }
button[kind="primary"] { background: var(--blue) !important; color: white !important; border-color: var(--blue) !important; }
button[kind="primary"] p, button[kind="primary"] span { color: white !important; }
.mode-note { color: var(--muted); font-size: .86rem; text-align: center; margin-top: .6rem; }

.results-head h1 {
  font-family: Georgia, "Noto Serif SC", serif; font-size: clamp(2.5rem, 4vw, 4.5rem);
  letter-spacing: -.055em; margin: 0 0 .35rem;
}
.results-head p { color: var(--muted); font-size: 1rem; }
.source-rail {
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  padding: 1.2rem 0; margin: 1.3rem 0 2.3rem;
}
.source-title { font-size: .78rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
.source-name { font-family: Georgia, "Noto Serif SC", serif; font-size: 1.65rem; margin: .2rem 0 .55rem; }
.tags { display: flex; flex-wrap: wrap; gap: .45rem; }
.tag { border: 1px solid var(--line); padding: .32rem .58rem; border-radius: 7px; font-size: .82rem; }

.look-head { display: flex; align-items: baseline; gap: .65rem; margin-bottom: .8rem; }
.look-index { font-size: .78rem; font-weight: 800; letter-spacing: .12em; }
.look-style { font-family: Georgia, "Noto Serif SC", serif; font-size: 1.65rem; font-weight: 700; }
.look-score { color: var(--blue); font-family: Georgia, serif; font-size: 1.35rem; font-weight: 700; margin-left: auto; }
.look-image-label { color: var(--muted); font-size: .72rem; margin-top: -.25rem; }
.look-body { display: grid; grid-template-columns: .9fr 1.1fr; gap: 1rem; margin: 1rem 0 .7rem; min-height: 11.8rem; }
.piece-list { margin: 0; padding-left: 1.15rem; font-size: .91rem; line-height: 1.75; }
.reason { border-left: 1px solid var(--line); padding-left: 1rem; }
.reason strong { display: block; font-size: .84rem; margin-bottom: .55rem; }
.reason p { color: #34363c; font-size: .87rem; line-height: 1.68; margin: 0; }
.preference-note { color: var(--blue); font-size: .82rem; margin-top: .35rem; }

[data-testid="stImage"] img { border-radius: 10px; }
[data-testid="stExpander"] { border-color: var(--blue); border-radius: 9px; }
[data-testid="stAlert"] { border-radius: 9px; }

@media (max-width: 900px) {
  [data-testid="stAppViewContainer"] > .main .block-container { padding: 1rem 1.15rem 3rem; }
  .brand-row { margin-bottom: 1rem; }
  .hero-copy { padding-top: .5rem; }
  .hero-copy h1 { font-size: 3.35rem; }
  .api-copy { padding: .5rem 0 0; }
  .api-copy h1 { font-size: 3.35rem; }
  .setup-title { margin-top: 1rem; }
  .garment-mark { display: none; }
  .look-body { grid-template-columns: 1fr; min-height: auto; }
  .reason { border-left: 0; border-top: 1px solid var(--line); padding: .8rem 0 0; }
}

/* 手机尺寸：无横向溢出，触控目标更大，三套结果纵向堆叠后可自然滑动切换。 */
@media (max-width: 640px) {
  html, body { overflow-x: hidden; max-width: 100vw; }
  [data-testid="stAppViewContainer"] > .main .block-container { padding: .8rem .85rem 3rem; }
  [data-testid="stVerticalBlock"] { min-width: 0; }
  [data-testid="stImage"] img { max-width: 100%; height: auto; }
  [data-testid="stRadio"] label { padding: .65rem .7rem; font-size: .95rem; }
  [data-testid="stFileUploader"] { padding: .35rem; }
  [data-testid="stFileUploaderDropzone"] { min-height: 130px; }
  .stButton > button, .stDownloadButton > button {
    min-height: 3rem; font-size: 1rem; border-radius: 10px;
  }
  .brand { font-size: 1.55rem; }
  .api-state { font-size: .8rem; }
  .hero-copy h1, .api-copy h1 { font-size: 2.6rem; }
  .results-head h1 { font-size: 2.1rem; }
  .look-style { font-size: 1.3rem; }
  .look-score { font-size: 1.1rem; }
  .question { font-size: 1.05rem; margin: .85rem 0 .35rem; }
  .piece-list { font-size: .88rem; }
  .reason p { font-size: .85rem; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; scroll-behavior: auto !important; }
}
</style>
"""
