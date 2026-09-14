# V35 單張3D完整介紹流程圖提示詞

模式：內建imagegen；新增圖，不覆寫V34三張圖。目的：產品概念全流程介紹，而不是再製作驗收工作台圖。

## 第二輪修正（採用）

第一輪未通過流程／範圍驗收：補充資料回線接到事件出現區，而非資料評估；另含未核准的影像資料卡及多餘看板。第二輪只修正這三處，保留原構圖、五步與兩分支。

```text
Edit ONLY the provided ReLock 3D introduction poster, retaining the entire 2:3 portrait composition, five numbered sections, matching silver car, cockpit, 3D style, all main arrows, central decision and BOTH outcomes, exception research box and footer. Keep the text readable and preserve every accurate existing Chinese label.
Make these tightly scoped correctness cleanups:
1. LEFT amber return line labelled "補充資料": it currently incorrectly rises to step02. Shorten this return to end at STEP03 "03 釐清資料與事件" ONLY. From the left outcome panel it goes left into the left margin, UP to step03 vertical center, then turns RIGHT with a single arrowhead entering the LEFT EDGE of step03. It must NOT reach step02 or step01. No arrow pointing to step02 on left. Keep the RIGHT teal "新事件" return to step02 unchanged.
2. In STEP03, replace the left floating card currently marked "影像資料" with a conceptual vehicle-motion/status card labelled exactly "車輛狀態". Remove the camera icon and road photograph from that card; replace with a clean small silver-car silhouette and three simple horizontal status lines. Do not imply camera/vision or human recognition capability. Keep the other signal and record cards and large amber question mark.
3. Remove the two large roadside text billboards flanking the TOP HEADER / first car (top left and top right) entirely, filling them naturally with the existing sky/roadscape. Preserve title, subtitle and top-right "3D 概念流程・尚未實作" pill; do not add slogans.
No other changes. In particular preserve the written five steps, conditionals, limitation that restricting a request is not stopping the physical vehicle, and that the concept is unimplemented/unverified. Preserve one complete image at high resolution, portrait 2048x3072, no cropping.
```

輸出來源：`exec-cd64b1d2-0b7a-492a-b25c-9c69e8b6f733.png`。內建 imagegen 實際輸出1024×1536；本機只以Lanczos等比轉成2048×3072 WebP供統一交付，並非新增原生細節或工程解析度。原始PNG保留於本機忽略目錄`_local/qa-v35/source/relock-introduction-round2.png`，網站素材為`private_assets/brand/concepts/v35-14-introduction.webp`（637,468 bytes）。未使用程式重畫或改寫圖中文字。


## 第一輪

```text
Use case: infographic-diagram.
Create ONE finished detailed 3D illustrated product-concept flow infographic in Traditional Chinese, portrait 2048 x 3072. This is a single continuous poster, not separate images. Premium modern industrial 3D visualization, daylight, white and pale silver background, graphite typography, restrained teal main arrows and amber uncertainty branches. Consistent unbranded silver sedan, contemporary road/interior/control-interface illustrations. Clear bold Traditional Chinese sans-serif labels. NOT ancient, no fantasy, no xianxia, no parchment. Critically this introduces what the proposed idea DOES and WHY, NOT a test bench: do NOT draw desktop computers, a laboratory, keyboard demo, or test worksheet as the main illustrations.

Title exact: "ReLock｜二次移動鎖"
Subtitle exact: "一次事件之後，下一次移動如何被重新檢視？"
Small top badge exact: "3D 概念流程・尚未實作"

Composition: ample 90px outer margins. Five full-width numbered illustrated steps stacked vertically in the upper 65% of the poster. Each step has a substantial polished realistic 3D illustration on one side, large title and ONE short explanatory sentence on the other. Link steps by four clear downward teal arrows. All text and arrowheads contained within the image. Readable hierarchy, no dense illegible dashboard text. The car is physically realistic, not a toy; interface overlays are clearly conceptual, not installed hardware specifications.

Step 01 title exact "01 正常行駛"
Copy exact "駕駛提出行駛請求，車輛處於一般行駛狀態。"
Illustration: silver sedan on a calm daylight road, normal driving, no performance numbers.

Step 02 title exact "02 出現疑似事件"
Copy exact "碰撞或異常接觸出現，需要重新釐清狀況。"
Illustration: same sedan near a simple roadside obstacle, gentle amber contact ripple at front bumper, no injury, no people struck, no dramatic wreck or explosion.

Step 03 title exact "03 釐清資料與事件"
Copy exact "檢查資料是否完整、一致；無法確認就標示未知。"
Illustration: semi-transparent conceptual vehicle overlay and three floating signal cards, clearly a concept, not a wiring schematic. Include a large amber question mark, no numerical accuracy, no claim of identifying a human.

Step 04 title exact "04 駕駛再次要求移動"
Copy exact "再次前進或後退是請求，不代表已獲准執行。"
Illustration: modern car cockpit, simple pedal symbol and forward/back request arrows entering a request card. It must not depict physically disabled brakes or automatic acceleration.

Step 05 title exact "05 獨立檢查授權條件"
Copy exact "事件狀態、資料品質與解除條件須一併檢視。"
Illustration: three checklist cards entering a separate 3D control gate, not a padlock attached to a wheel. Small line exact "判讀結果不能自行解除限制".
Below this step place a centered diamond containing exact "條件是否成立？". One short downward arrow connects step05 to the diamond.

From the diamond branch into TWO equally prominent large result panels on the next row:
LEFT amber arrow labeled "不足或未知" leading to panel with exact large title "維持限制與提示" and exact copy "等待補充資料，不因再次踩踏就直接放行。". Illustration: amber dashboard status card and a held-request symbol, NOT a guarantee the physical car is stopped.
RIGHT teal arrow labeled "成立" leading to panel with exact large title "重新授權後持續觀察" and exact copy "依條件研究是否接受移動；新事件須再評估。". Illustration: teal authorization card and same silver car with observation markers, NOT an all-clear safety guarantee.
A single thin teal return arrow from the RIGHT panel runs up the far right margin to step02, labeled exact "新事件". A single thin amber return arrow from the LEFT panel runs up the far left margin to step03, labeled exact "補充資料". No crossing arrows. No arrow directly from03 or04 to the car/results. Do not merge the two result branches.

Below the two outcomes, a separate dashed amber callout, NOT connected as a default branch:
Large exact "例外研究：條件慢移"
Copy exact "不是預設放行；條件與終止方式仍待獨立驗證。"
Include a small simple car-with-caution 3D icon, no recommended speeds or distances.

At bottom, a wide slim neutral strip with a record icon and exact "各分支保留事件、請求、授權與狀態紀錄".
Footer must be clearly legible, exact "概念流程示意，非真車控制指引。原型與安全效果尚未驗證。"
Additional small boundary exact "限制請求不等於車輛已停止；解除条件仍須研究。" BUT use Traditional Chinese "條件", rendering the final line exactly as "限制請求不等於車輛已停止；解除條件仍須研究。"

Constraints: all quoted Chinese text exact, use only listed text, no extra lorem ipsum. No logos other than the ReLock word title, no brand name on car, no figures/percentages, no CAD dimensions, no claims of safety certification, automatic braking, guaranteed protection, emergency rescue or universal detection. The result must look like a highly legible, detailed, modern 3D product introduction infographic; actual car/context scenes dominate instead of abstract boxes or testing equipment.
```
