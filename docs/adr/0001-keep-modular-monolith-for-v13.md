# ADR 0001：V13 初版維持 Flask 模組化單體

- 狀態：Accepted
- 日期：2026-08-22

## 情境

專案已有 Flask、SQLite、官網、LINE webhook、mock payment 與管理後台，且目前目標是本機可驗收的第一版。品牌與管理能力的缺口高於擴展性缺口。

## 決策

維持單一 Flask application factory，依 public、line、payments、admin blueprint 分模組；資料仍使用 SQLite。LINE 與金流透過明確函式邊界隔離，未來才替換正式 provider 或資料庫。

## 理由

- 可直接沿用現有測試、資料與安全層。
- 開發、啟動與除錯路徑最短，適合單人與本機 MVP。
- 不引入 Node、容器、訊息佇列或多個部署單元，降低維護與失敗面。
- 現階段沒有流量、可用性或組織證據支持微服務。

## 後果

正面：交付快、測試集中、資料一致性簡單、營運成本低。

負面：正式高併發、非同步 webhook、水平擴展與進階分析需要後續改造。當真實流量、營收或團隊分工證明瓶頸存在時，再評估 PostgreSQL、背景工作與服務拆分。
