# 2026-09-15 V34 圖像製作紀錄

本次使用內建 imagegen，未使用 API／CLI fallback。三張交付圖屬概念示意，不是產品截圖或測試結果；沒有價格、辨識成效或真車驗證資料。原始檔保留於本機 `_local/qa-v34/source/`，交付 WebP 只放在 `private_assets/brand/concepts/`。

## hero：初始 prompt

```text
Use case: product-mockup. Asset type: private paid engineering concept overview, 16:9 landscape, high-quality modern industrial/editorial 3D visualization. Show a realistic modern desktop software simulation workstation on a clean pale grey desk, three-quarter view. A large central display shows a neutral silver unbranded virtual passenger car in an abstract simulated grid, a small amber paused propulsion symbol, and a clean small waveform panel; a compact keyboard and mouse are the only input equipment. A thin graphical separation makes clear this is software on a monitor, not a physical vehicle controller. Refined metallic greys, teal signal lines and restrained amber events, bright daylight, detailed realistic materials, clean depth and premium technical illustration finish. Legible minimal text ONLY: "ReLock" at the top of the display and "SIMULATION ONLY" beneath it. No performance numbers or confidence scores. No physical vehicle, car keys, ECU, hardware sensors or pedals on the desk. No cables connected to a car. No crash victims, no violence, no fantasy, no ancient clothing, no talismans, no magic, no logos of manufacturers, no watermark. Leave clean generous margins, all apparatus fully in frame. This visual is a proposed software simulation, not proof of a built or certified product. Output wide 16:9.
```

## diagram：初始 prompt

```text
Use case: scientific-educational. Asset type: standalone 16:9 paid concept module and data-flow illustration, readable professional modern systems engineering explainer, clean white/light grey background, restrained teal and amber, dark charcoal sans-serif Traditional Chinese labels. Raster illustration with realistic rendered display/module details, NOT fantasy. Six numbered modules organized clearly in two horizontal rows: top row flow left to right 01 -> 02 -> 03 -> 04; bottom row 05 beneath 04, and 06 beneath 02-03. Exact labels: "01 模擬輸入" with three stylized waveform traces and a keyboard symbol, "02 訊號整理" with synchronized waveform window, "03 風險判讀" with software module and an amber question mark, "04 獨立狀態機" with five small neutral connected state dots, "05 虛擬車輛" with a car visibly inside a computer display, "06 測試紀錄" with an empty report grid, NOT results. Draw clean directional arrows 01→02→03→04→05. Thin grey audit lines from 03,04,05 converge into 06. No arrow directly from risk model to vehicle, no cloud and no real ECU. Header exact "ReLock｜模擬系統拆解". Footer exact "僅電腦模擬・非真車控制接線圖". No other text, no invented numbers, no percentages, no certification, no mythical glow, no pedestrians or crash. Large enough labels, unambiguous arrows, generous module spacing, no overlaps, full composition inside 16:9 frame. Goal explain data flow and separate perception from control; illustrate conceptual software modules rather than claim hardware architecture.
```

## scene：初始 prompt

```text
Use case: photorealistic-natural. Asset type: private paid concept usage and validation scenario, 16:9 landscape editorial engineering visualization. Bright contemporary research studio, over-the-shoulder natural view of an adult engineer in simple modern casual clothing operating a keyboard at an ordinary desk, face not identifiable, no branding. Two desktop monitors: primary clearly shows a simple unbranded virtual silver car in a simulated grid and three visually separated scenario cards using abstract waveform icons (teal, amber, grey), no collision victims; secondary shows an empty test matrix and neutral event timeline, not fabricated measurements. An open plain notebook contains only simple untitled boxes and arrows. Morning daylight, pale walls, realistic skin and fabric texture, careful hand anatomy, believable monitor perspective, warm neutral mood, technical and approachable. The only legible screen text is "SIMULATION ONLY"; other interface details are abstract blocks without pseudo text or numerical results. No physical car, hardware controller, sensor equipment, OBD/CAN equipment, wires to any vehicle, no road test, no accident, no injury, no fantasy or ancient style, no industrial robot, no watermarks. This is a visualization of a proposed computer-only test workflow, not a documentary of an existing tested prototype. Wide 16:9 with uncluttered margins.
```

## 機制圖自我修正

第 1 版：紀錄支線重複、缺少虛擬車輛紀錄線與鍵盤獨立輸入，判定不通過。

第 2 版：已拆出鍵盤，但灰線與鍵盤線重疊且 04→05 遺失，判定不通過。

第 3 版：改成 01→02→03→04→05 單列；鍵盤自上方直接輸入 04；03／04／05 各自向下指向 06，無回饋控制箭頭。逐條目視確認通過。

### 第 2 版修正 prompt

```text
Edit this engineering infographic. Preserve its high-quality 16:9 white background, six numbered modules, large Traditional Chinese headings, monitor renders, main title and footer. Correct only the confusing signal routing and generic state icon:
1. Main teal pipeline remains 01→02→03→04→05 (01/02/03/04 top row; 05 lower right;06 lower center).
2. Audit grey lines must be exactly three distinct one-way paths: 03→06, 04→06, 05→06. The current drawing wrongly duplicates a branch from03 and omits05. Replace all current grey audit lines with three clearly separated thin grey arrows arriving at different sides of06. Do not merge wires or cross the main teal arrows. 06 has NO outgoing arrows.
3. Move the keyboard out of the 01 monitor panel into the unused lower-left white space with exact label "鍵盤請求". A separate amber line routes from keyboard to 04 only, never through02 or03. Route along unused outer margin so it does not overlap other modules or arrows. Keep module01 as three simulated waveforms.
4. Inside04 replace the abstract five-node arrow graph with a simple vertical stack of five compact rounded rectangles containing exactly "正常", "事件評估", "限制", "條件慢移", "重新授權". No arrows between these five labels, since this is a module icon, not a verified transition diagram. Keep the heading04獨立狀態機.
5. Remove the three extra small text labels beside the01 waveforms; retain original main headings. No new labels except keyboard and five states above, no performance numbers, no tiny pseudo-text.
Keep all other typography and modules unchanged. Legibility and unambiguous directional arrows matter more than decorative detail. Do not draw a wireframe real car controller or certification logo.
```

### 第 3 版修正 prompt

```text
Re-layout this exact six-module ReLock infographic to eliminate wire crossings and restore the required arrow from04 to05. Keep modern white/teal/grey style, Traditional Chinese headings and monitor illustrations, but use this SIMPLER topology. Wide16:9.
Top title exact "ReLock｜模擬系統拆解".
ONE central horizontal row of FIVE equally sized panels, left to right: "01 模擬輸入", "02 訊號整理", "03 風險判讀", "04 獨立狀態機", "05 虛擬車輛".
Four prominent teal one-way arrows connect the panels horizontally: 01→02→03→04→05. The teal arrow04→05 MUST be present.
Small standalone keyboard ABOVE panel04 with exact label "鍵盤請求", with one AMBER arrow STRAIGHT DOWN from keyboard into top of04. Keyboard has no other wires and does not touch the main pipeline.
Panel04 interior five stacked state labels exactly "正常", "事件評估", "限制", "條件慢移", "重新授權"; no internal arrows.
Place "06 測試紀錄" as a single wide low panel BELOW panels03,04,05. Draw EXACTLY THREE thin GREY arrows, all STRAIGHT DOWN: from bottom center03 into06, bottom center04 into06, bottom center05 into06. No curves, no merged lines, no crossovers, no arrows from06. Panel06 contains small empty report grid, not results. Leave lower-left below01/02 empty.
Panel01 and02 waveform monitors;03 a software panel with a question mark;05 a car on a monitor. No extra little text or hardware. Keep generous whitespace, clean sans-serif labels, all content in frame.
Footer exact "僅電腦模擬・非真車控制接線圖".
Routing correctness is essential. Total arrows: FOUR teal horizontal, ONE amber vertical downward above04, THREE grey vertical downward into06. No other arrows. No percentages or performance claims. This is a module diagram not a physical circuit.
```
