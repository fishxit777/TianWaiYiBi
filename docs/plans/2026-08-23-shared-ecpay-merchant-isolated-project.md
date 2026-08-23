# 共用綠界特店、隔離天外一筆付款資料

日期：2026-08-23

## 決策

天外一筆沿用既有合法綠界特店的 `MerchantID`、`HashKey`、`HashIV`，不另建第二個賣家帳號。這與 NestFM 的既有正式串接方式一致。共用範圍只限綠界簽章憑證；應用程式、部署、訂單、付款事件、客戶權益、LINE 與管理後台全部維持獨立。

## 隔離方式

- 綠界憑證只存入天外一筆自己的 Render 環境變數，不提交 Git、不顯示於前端或日誌。
- 天外一筆訂單固定使用 `TWYB` 前綴，避免與 NestFM 的 `NEST` 訂單混淆。
- 所有送往綠界的訂單加入 `StoreID=TWYB`；綠界 callback 必須同時通過 MerchantID、StoreID 與 CheckMacValue 驗證。
- `ReturnURL`、`OrderResultURL` 與 `ClientBackURL` 只指向天外一筆網域。
- callback 仍需核對本機訂單、成交金額、付款狀態及事件冪等，前端返回頁不能自行開通權益。

## 啟用閘門

設定憑證不等於立即開放正式收款。正式付款仍需 `PAYMENT_PROVIDER=ecpay`、`ECPAY_MODE=production`、`ECPAY_LIVE_CONFIRMED=true`、可用 HTTPS callback、SMTP 交付信與持久化資料庫同時就緒。任何一項缺少時，網站維持「正式付款尚未開放」，不建立扣款。

## 驗證

自動測試需覆蓋：付款轉送表單包含 `StoreID=TWYB`、合法 TWYB callback 可開通、相同 MerchantID 但其他 StoreID 的有效簽章 callback 必須被拒絕、錯誤金額或錯誤 CheckMacValue 不得授權內容。
