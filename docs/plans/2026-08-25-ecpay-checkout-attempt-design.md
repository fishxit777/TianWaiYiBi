# 綠界結帳嘗試序號設計

**Status:** Implementing after production duplicate-order reproduction on 2026-08-25.

## Problem

現行程式把天外一筆內部訂單編號直接當成綠界 `MerchantTradeNo`。綠界規定該值永久不可重複，因此同一付款連結只要被再次提交，就會回覆 `10300028`；人工取消整筆內部訂單再重建只能暫時繞過問題，並不是可靠的正式結帳設計。

## Decision

每次產生綠界轉送頁時，由伺服器建立新的 20 碼英數 `MerchantTradeNo`。內部訂單編號放入 `CustomField1`，並與所有付款參數一起納入綠界 CheckMacValue。正式回呼先驗證 MerchantID、StoreID 與 CheckMacValue，通過後才把 `CustomField1` 還原成內部訂單編號；舊版沒有自訂欄位的回呼仍以 `MerchantTradeNo` 相容處理。

綠界官方付款與回呼規格均列出 `CustomField1`，付款結果通知範例亦把該欄位納入回傳與檢查碼：https://developers.ecpay.com.tw/2864/ 、https://developers.ecpay.com.tw/2878/

管理後台付款連結改成同分頁開啟，第一次點擊後立即鎖定連結並顯示轉送狀態，避免雙擊建立平行分頁。重新返回後台時重新載入狀態。金額、付款方式、正式環境、Email 與公開銷售閘門均不變。

## Alternatives

1. 繼續取消整筆內部訂單：操作成本高，容易留下多筆取消單，拒絕採用。
2. 新增完整 gateway-attempt 資料表：可提供更細稽核，但目前單一管理驗收與低交易量不需要新增 migration；若正式交易量上升再實作。
3. 採用本設計：改動小、保留內部訂單與權益關係、解決綠界唯一序號限制，並維持簽章驗證。

## Security and tests

- 交易序號固定 20 碼英數、含微秒時間與密碼學亂數，不包含客戶或內部訂單資訊。
- `CustomField1` 未通過 CheckMacValue 不得映射或開通。
- 伺服器仍逐筆核對金額、正式特店、StoreID、信用卡付款方式、模擬付款旗標與重送事件。
- 測試必須證明：同一內部訂單連續開啟產生不同交易序號；兩者均安全映射回同一訂單；竄改映射欄位會被拒絕；既有回呼仍相容；公開 NT$199 與一般結帳閘門不變。
