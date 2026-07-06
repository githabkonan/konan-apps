/**
 * iap-native.js — THE FLEX(散財シミュレーションRPG) ネイティブIAPアダプタ
 * ============================================================
 * @capgo/native-purchases を使い、index.html の purchaseIAP() が期待する
 * window.IAP_NATIVE.purchase(productId) / restore() を実装する。
 * (甲4で審査通過済みの iap-bridge.js パターンを多商品向けに移植)
 *
 * 商品構成(IAP_CONFIG 参照):
 *   非消耗型: flex_premium_lifetime / flex_legendary_lifetime
 *   消耗型  : flex_coin_* (5種) / flex_donate_* (4種)
 *
 * 復元(Guideline 3.1.1 必須):
 *   restorePurchases() → getPurchases({onlyCurrentEntitlements:true}) で
 *   実際に所有している productIdentifier だけを付与する(誤付与しない)。
 * ============================================================
 */
(function () {
  "use strict";

  function isNativeApp() {
    return (
      typeof window.Capacitor !== "undefined" &&
      typeof window.Capacitor.isNativePlatform === "function" &&
      window.Capacitor.isNativePlatform()
    );
  }

  function getNP() {
    if (
      typeof window.Capacitor !== "undefined" &&
      window.Capacitor.Plugins &&
      window.Capacitor.Plugins.NativePurchases
    ) {
      return window.Capacitor.Plugins.NativePurchases;
    }
    return null;
  }

  // 非消耗型のproductId → fulfillIAP用キー
  var NON_CONSUMABLES = {
    flex_premium_lifetime: "premium",
    flex_legendary_lifetime: "legendary",
  };

  window.IAP_NATIVE = {
    isAvailable: function () {
      return isNativeApp() && getNP() !== null;
    },

    /**
     * @param {string} productId 例: "flex_coin_550"
     * @returns {Promise<{success:boolean, cancelled?:boolean}>}
     */
    purchase: async function (productId) {
      var np = getNP();
      if (!np) return { success: false };

      // 存在確認(ASC設定ミスを早期検出)
      var products;
      try {
        var r = await np.getProducts({
          productIdentifiers: [productId],
          productType: "inapp",
        });
        products = (r && r.products) || [];
      } catch (e) {
        console.error("[iap-native] getProducts failed:", e);
        return { success: false };
      }
      if (products.length === 0) {
        console.error("[iap-native] product not found in ASC:", productId);
        return { success: false };
      }

      try {
        var tx = await np.purchaseProduct({
          productIdentifier: productId,
          productType: "inapp",
          quantity: 1,
        });
        console.log("[iap-native] purchase complete:", tx && tx.transactionId);
        return { success: true };
      } catch (e) {
        if (e && (e.userCancelled === true || e.code === "PURCHASE_CANCELLED")) {
          return { success: false, cancelled: true };
        }
        console.error("[iap-native] purchaseProduct failed:", e);
        return { success: false };
      }
    },

    /**
     * 非消耗型(premium/legendary)の復元。
     * @returns {Promise<string[]>} 復元されたfulfillキーの配列(例 ["premium"])
     */
    restore: async function () {
      var np = getNP();
      if (!np) throw new Error("課金プラグインが利用できません");

      await np.restorePurchases();

      var owned = [];
      try {
        var r = await np.getPurchases({ onlyCurrentEntitlements: true });
        var list = (r && r.purchases) || [];
        for (var i = 0; i < list.length; i++) {
          var pid = list[i] && list[i].productIdentifier;
          if (pid && NON_CONSUMABLES[pid] && owned.indexOf(NON_CONSUMABLES[pid]) < 0) {
            owned.push(NON_CONSUMABLES[pid]);
          }
        }
      } catch (e) {
        console.error("[iap-native] getPurchases failed:", e);
        // getPurchases失敗時は誤付与を避けるため何も復元しない
      }
      return owned;
    },
  };

  if (isNativeApp()) {
    document.addEventListener("DOMContentLoaded", function () {
      console.log("[iap-native] initialized. available:", window.IAP_NATIVE.isAvailable());
    });
  }
})();
