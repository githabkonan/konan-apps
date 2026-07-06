/**
 * en-data.js — THE FLEX 完全英語化辞書+置換エンジン
 * konan指示(2026-07-06): 言語は ja/en の2本に絞り、en は混在ゼロの完全翻訳にする。
 * 仕組み: ①データ配列の深掘り置換(_ja$バックアップ付き・可逆) ②DOMテキストの exact-match 置換
 *        ③MutationObserver で後から出るUIも翻訳。全て EN_STRINGS の完全一致ベース=安全。
 */
(function(){
"use strict";

window.EN_STRINGS = {
// ===== items: 高額 =====
"スーパーカー TYPE-SF":"Supercar TYPE-SF",
"プライベートジェット G-class":"Private Jet G-class",
"都心超高層ペントハウス":"Downtown Sky Penthouse",
"ラグジュアリーウォッチ DAYSTAR":"Luxury Watch DAYSTAR",
"宇宙ステーション滞在3泊":"3 Nights on a Space Station",
"国内最高峰サーキット貸切":"Private Racing Circuit Day",
"現代アート巨匠の原画":"Original Modern Art Masterpiece",
"銀座超一流寿司 1ヶ月毎日":"Ginza Elite Sushi, Every Day for a Month",
"和牛A5 食べ放題":"All-You-Can-Eat A5 Wagyu",
"回転寿司 100皿":"100 Plates of Conveyor Sushi",
"行列ラーメン 毎日食べる権":"Daily Pass: Famous Ramen Line-Skip",
"国内高級温泉旅館":"Luxury Hot Spring Ryokan",
"ハワイ1週間 ファーストクラス":"Hawaii, 1 Week First Class",
"ヨーロッパ周遊 2週間":"2-Week Europe Grand Tour",
"世界一周クルーズ":"Around-the-World Cruise",
"最新iPhone 全色":"Latest iPhone, Every Color",
"ゲームルーム フル構築":"Full Gaming Room Build",
"カラオケ 1ヶ月貸切":"Karaoke Box, 1 Month Private",
"海外アーティスト VIP席":"VIP Seats: World-Famous Artist",
"高級エステ 月1回コース":"Luxury Spa, Monthly Course",
"パーソナルトレーナー 1年":"Personal Trainer, 1 Year",
"高級クラブで散財の夜":"Big Night at an Exclusive Club",
"美人秘書サービス 1ヶ月":"Executive Secretary Service, 1 Month",
"慈善団体に1億円寄付":"¥100M Charity Donation",
"世界最高峰グランクリュ 100本":"100 Bottles of Grand Cru",
"ミネラルウォーター":"Mineral Water",
"お茶（ペットボトル）":"Bottled Green Tea",
"ポテトチップス":"Potato Chips",
"ジュース":"Juice",
"アイスクリーム":"Ice Cream",
"缶ビール":"Canned Beer",
"コーヒー":"Coffee",
"エナジードリンク":"Energy Drink",
"タバコ1箱":"Pack of Cigarettes",
"宝くじ":"Lottery Ticket",
"専属シェフ（1年契約）":"Private Chef (1-Year Contract)",
"執事（住み込み）":"Live-in Butler",
"ライオン（合法ペット）":"Pet Lion (Fully Legal)",
"ティラノサウルス全身骨格":"Complete T-Rex Skeleton",
"私設動物園":"Private Zoo",
"自家用潜水艦":"Personal Submarine",
"100m級スーパーヨット":"100m Superyacht",
"タワーマンション全室買い":"Buy Every Unit in the Tower",
"プライベート無人島":"Private Island",
"自家用ロケット":"Personal Rocket",
"プライベート宇宙ステーション":"Private Space Station",
"火星の土地（1区画）":"Plot of Land on Mars",
"不老不死の薬":"Elixir of Immortality",
// ===== 乞食/あげる/その他キャラ =====
"¥10万":"¥100K","¥100万":"¥1M","¥1000万":"¥10M","¥1億":"¥100M","¥5億":"¥500M",
"通りすがりのサラリーマン":"Passing Salaryman",
"通りすがりのOL":"Passing Office Lady",
"近所の小学生":"Neighborhood Kid",
"謎のスーツの男":"Mysterious Man in a Suit",
"超富豪 — 専属ボディガード付き":"Billionaire — With Bodyguards",
"謎の人物 — スーツケース持参":"Mystery Person — Carrying a Suitcase",
"謎のサンタクロース":"Mysterious Santa Claus",
"路上の老人":"Old Man on the Street",
"ホームレス":"Homeless Man",
"シングルマザー":"Single Mother",
"小さな子供":"Small Child",
"失業中の男":"Unemployed Man",
"年金暮らしの老婆":"Old Woman on a Pension",
"学費に困る学生":"Student Struggling with Tuition",
// ===== 投資/事業 =====
"株式投資":"Stocks",
"不動産投資":"Real Estate",
"仮想通貨":"Crypto",
"国債・債券":"Bonds",
"スタートアップ":"Startups",
"金(ゴールド)":"Gold",
"中リスク・中リターン":"Medium risk, medium return",
"低リスク・安定収入":"Low risk, steady income",
"超高リスク・超高リターン":"Extreme risk, extreme return",
"超低リスク・安定":"Ultra low risk, stable",
"全損か10倍か":"Total loss or 10x",
"インフレヘッジ":"Inflation hedge",
"インターン":"Intern","営業マン":"Sales Rep","エンジニア":"Engineer","マネージャー":"Manager",
// ===== 労働(22職) =====
"コンビニバイト":"Convenience Store Clerk",
"建設作業員":"Construction Worker",
"工場ライン":"Factory Line Worker",
"営業職":"Salesperson",
"医師":"Doctor",
"弁護士":"Lawyer",
"投資銀行家":"Investment Banker",
"起業家":"Entrepreneur",
"カリスマ経営者":"Star CEO",
"農業":"Farmer",
"漁業":"Fisherman",
"引越し作業員":"Mover",
"配達員(バイク)":"Delivery Rider",
"プログラマー":"Programmer",
"ホスト":"Host Club Star",
"ゲーム配信者":"Game Streamer",
"ニート":"NEET",
"ヒモ":"Kept Man",
"土と汗の生活":"A life of soil and sweat",
"海で体を張る":"Risk it all at sea",
"重い荷物を運ぶ":"Haul heavy boxes",
"24時間営業の最前線":"Front line of 24/7 retail",
"風を切って走る":"Ride like the wind",
"コードが金になる":"Code turns into money",
"命を救い、金を得る":"Save lives, make money",
"女性を沼にはめる夜":"Nights of dangerous charm",
"寝転びながら億を稼ぐ夢":"Dream of millions from the couch",
"パジャマでポテチを食べる。たまに天から金が降る":"Eat chips in pajamas. Sometimes money falls from the sky",
"愛で生計を立てる":"Make a living off love",
"全てを支配する":"Rule everything",
// ===== 労働アクションボタン =====
"収穫する！":"Harvest!","釣る！":"Fish!","運ぶ！":"Carry!","巡回する！":"Patrol!",
"レジを打つ！":"Ring it up!","配達！":"Deliver!","稼働させる！":"Run the line!","走れ！":"Run!",
"営業トーク！":"Pitch!","コードを書く！":"Write code!","診察する！":"Examine!","弁護する！":"Defend!",
"取引する！":"Trade!","魅了する！":"Charm!","接客する！":"Serve!","配信する！":"Stream!",
"投稿する！":"Post!","賭ける！":"Bet!","...（何もしない）":"...(do nothing)","甘える！":"Sweet-talk!",
"転売する！":"Flip it!","口八丁！":"Talk fast!","決断する！":"Decide!","2つ揃い！":"Two of a kind!",
// ===== 実績/称号 =====
"¥100万散財達成！":"Spent ¥1M!","¥500万散財達成！":"Spent ¥5M!","¥1000万散財達成！":"Spent ¥10M!",
"¥5000万散財達成！":"Spent ¥50M!","¥1億散財達成！":"Spent ¥100M!","¥5億散財達成！":"Spent ¥500M!",
"¥10億散財達成！":"Spent ¥1B!","¥100億散財達成！":"Spent ¥10B!","¥1000億散財達成！":"Spent ¥100B!",
"一般人":"Nobody","成金":"New Rich","富豪":"Tycoon","大富豪":"Big Tycoon","億万長者":"Billionaire","伝説の散財王":"Legendary Big Spender",
"称号":"Title",
// ===== イベント =====
"宝くじ 当選！":"Lottery Win!",
"保有株が急騰！":"Your Stock Soared!",
"謎の電話":"Mysterious Phone Call",
"コンテスト優勝！":"Contest Winner!",
"臨時ボーナス":"Surprise Bonus",
"インフルエンサー案件":"Influencer Deal",
"遺産相続！":"Inheritance!",
"競馬で大当たり！":"Big Win at the Races!",
"落とし物を拾った":"Found Something",
"仮想通貨が暴騰！":"Crypto Mooned!",
"レース優勝ボーナス入金":"Race victory bonus received",
"島で金鉱を発見！":"Gold found on your island!",
"希少価値が急上昇した":"Its rarity value skyrocketed",
"CM撮影オファーが届いた":"A commercial offer arrived",
"オークションで評価額が急騰した":"Auction value skyrocketed",
"博物館から高額レンタル依頼が来た":"A museum wants to rent it",
"レアワインの価格が暴騰した":"Rare wine prices exploded",
"宝くじが当選した！":"You won the lottery!",
"中身は石ころだった...💀":"It was full of rocks... 💀",
"現金が入っていた！":"It was full of cash!",
"ゴールドバーが入っていた！":"It was full of gold bars!",
"ダイヤモンドで満載だった！！":"It was packed with diamonds!!",
"草レースで優勝！賞金が入金された":"Won an amateur race! Prize money received",
"接触事故。修理費が発生":"Minor crash. Repair costs incurred",
"快晴のパリに到着。最高の気分だ":"Landed in sunny Paris. Feeling amazing",
"地価上昇で評価額が急増した":"Land value surged",
"嵐で修理費が発生した":"Storm damage. Repair costs incurred",
"クジラの群れと遭遇。一生の記憶だ":"Met a pod of whales. Unforgettable",
"宇宙で新鉱物を発見。特許収入が入る":"Discovered a new mineral in space. Patent income!",
"不動産価値が30%上昇した":"Property value rose 30%",
// ===== 乞食の訴え =====
"お腹がすいた...助けて...":"I'm starving... please help...",
"今日も食べるものがない...":"Nothing to eat again today...",
"子供にミルクを買えなくて...":"I can't afford milk for my baby...",
"お母さんが帰ってこない...":"Mommy hasn't come home...",
"家族を養えない...":"I can't feed my family...",
"薬を買うお金が...":"I can't afford my medicine...",
"もう学校を辞めるしか...":"I'll have to drop out of school...",
// ===== スロット/カジノ =====
"ダイヤ":"Diamond","セブン":"Seven","マネー":"Money","チェリー":"Cherry","スター":"Star","ジョーカー":"Joker","スロット":"Slots",
"クラシックパチンコ":"Classic Pachinko","ルーレット":"Roulette","バカラ":"Baccarat",
// ===== ストーリー(購入後フレーバー) =====
"最高級の霜降りが口の中で溶けた。これが本物の幸せだ。":"The finest marbled beef melted in my mouth. This is real happiness.",
"全部食えなかった。でも全部注文した。それが大事だ。":"Couldn't eat it all. Ordered it all anyway. That's what matters.",
"並ばなくていい特別席。毎日でも飽きない。":"A special seat, no line. I could do this every day.",
"露天風呂から山を眺めた。全部忘れた。":"Watched the mountains from an open-air bath. Forgot everything.",
"砂浜でコーヒーを飲んだ。日常と切り離された時間だった。":"Drank coffee on the beach. A world away from daily life.",
"パリ→ローマ→バルセロナ。全部ファーストクラス。":"Paris → Rome → Barcelona. First class all the way.",
"80日間の航海。陸に戻りたくなくなった。":"80 days at sea. Didn't want to go back to land.",
"全色買った。使うのは1台だけど所有する喜びがある。":"Bought every color. I use one, but owning them all feels great.",
"8Kモニター3枚。椅子は120万。快適すぎて外に出れない。":"Three 8K monitors. A ¥1.2M chair. Too comfortable to ever leave.",
"毎晩プロのバックバンドと歌う。最高すぎる。":"Singing with a pro backing band every night. Unreal.",
"ステージ前列。終わった後に楽屋に呼ばれた。":"Front row. Got invited backstage afterwards.",
"全身ケア。別の人間になった気がした。":"Full-body treatment. I feel like a new person.",
"専属トレーナーが毎日来る。体が変わり始めた。":"My trainer comes every day. My body is changing.",
"ドンペリを噴射した。翌朝の残高が笑えた。":"Sprayed Dom Pérignon everywhere. My balance the next morning was hilarious.",
"スケジュール管理から買い物代行まで。人生が変わった。":"From scheduling to shopping, all handled. Life-changing.",
"1億円の小切手を手渡した。スタッフが泣いていた。これが本物の満足感だ。":"Handed over a ¥100M check. The staff cried. This is real satisfaction.",
"喉が潤った。生きてる感じがする。":"So refreshing. I feel alive.",
"ホッとする一杯。日本人の血が騒ぐ。":"A soothing sip. Speaks to the soul.",
"一袋では止まらない。麻薬と何が違うんだ？":"Can't stop at one bag. How is this legal?",
"甘い。脳が喜んでいる。":"Sweet. My brain is celebrating.",
"冷たくて甘い完璧な存在。":"Cold, sweet, perfect.",
"プシュッ。今日も一日お疲れさん。":"Psshht. Cheers to another day.",
"カフェイン中毒の朝。これがないと始まらない。":"Caffeine-addict morning. Can't start without it.",
"翼を授ける。寿命と引き換えに。":"It gives you wings. In exchange for your lifespan.",
"やめられない。やめる気もない。":"Can't quit. Don't want to.",
"夢を買う。ほぼ確実に外れるが、買わなければ始まらない。":"Buying a dream. It almost never hits, but you can't win without one.",
"毎日3食、ミシュランレベル。冷蔵庫を開けることはもう二度とない。":"Michelin-level meals, three times a day. I'll never open a fridge again.",
"「お帰りなさいませ」朝起きてから寝るまで全部やってくれる。":"\"Welcome home, sir.\" Everything handled, morning to night.",
"広大な敷地と特別許可が必要。来客は逃げる。":"Requires a huge estate and special permits. Guests run away.",
"リビングに飾る本物の化石。来た人全員が固まる。":"A real fossil in the living room. Every guest freezes.",
"自宅敷地内にミニ動物園。キリン、シマウマ、ライオンまで揃える。":"A mini zoo at home. Giraffes, zebras, even lions.",
"海底パーティ。深海魚と乾杯。":"Party on the seafloor. Cheers with the deep-sea fish.",
"ヘリポート付き。海上の城。クルー30人。":"Helipad included. A castle at sea. Crew of 30.",
"全室を所有。完全プライバシー。":"Every unit is mine. Total privacy.",
"カリブ海に浮かぶ自分だけの島。":"My own island in the Caribbean.",
"打ち上げ可能。打ち上げ場の確保は別途。":"Launch-ready. Launch site sold separately.",
"地球を見下ろしながらコーヒーを飲む生活。":"Morning coffee, looking down at Earth.",
"火星の所有権書類。発送はSpaceXに依頼。":"Deed to Martian land. Delivery via SpaceX.",
"一滴で永遠の命。退屈との戦いが始まる。":"One drop, eternal life. Now the battle with boredom begins.",
// ===== 購入演出desc(HTML入り) =====
"新しいフェラーリが届いた。<strong>走り出す前に、まず近所を一周した。</strong>":"The new Ferrari arrived. <strong>Before hitting the highway, I cruised the neighborhood once.</strong>",
"深夜のパリへ。翌朝には<strong>東京に戻れる。</strong>それが当たり前になった。":"Midnight flight to Paris, <strong>back in Tokyo by morning.</strong> That's normal now.",
"ヨットのデッキで夕日を見ている。<strong>これが自由というものか。</strong>":"Watching the sunset from the yacht deck. <strong>So this is freedom.</strong>",
"無人島で星空を見上げた。<strong>静寂だけが友達だった。</strong>":"Stargazing on my island. <strong>Silence was my only company.</strong>",
"地球を上から見下ろした。<strong>国境線がなかった。</strong>":"Looked down at Earth. <strong>There were no borders.</strong>",
"六本木の夜景を独占している。<strong>東京が小さく見える。</strong>":"The Roppongi skyline, all mine. <strong>Tokyo looks small from here.</strong>",
"新しいフェラーリが届いた。":"The new Ferrari arrived.",
"走り出す前に、まず近所を一周した。":"Before hitting the highway, I cruised the neighborhood once.",
// ===== 共通UI =====
"ホーム":"Home","購入する":"Buy","購入済み":"Owned","残高不足":"Not enough money",
"残高":"Balance","散財":"Spent","アイテム":"Items","やり直す":"Restart",
"買い物":"Shop","売却":"Sell","乞食":"Beg","あげる":"Give","カジノ":"Casino",
"デイリー":"Daily","投資":"Invest","事業":"Biz","労働":"Work",
"散財シミュレーターRPG":"Money Spending Simulator RPG",
"散財シミュレーター":"Money Spending Simulator",
"お金をあげる":"Give Money","老人":"Old Man",
"「お腹がすいた...」":"\"I'm starving...\"",
"ノーマルで始める":"Start Normal","ハードで始める":"Start Hard","NEW GAME（最初から）":"NEW GAME (fresh start)",
"今朝、目覚めると銀行口座に10億円が振り込まれていた。さあ、全部使いやがれ。":"This morning, ¥1,000,000,000 appeared in your bank account. Now go spend every last yen.",
};

// ===== ラウンド2: ハードコードUI(実測 untranslated_r2 由来) =====
Object.assign(window.EN_STRINGS, {
"今朝、目覚めると銀行口座に":"This morning,","10億円":"¥1,000,000,000","が振り込まれていた。さあ、":"appeared in your bank account. Now,","全部使い切れ。":"spend it all.",
"保有FlexCoin:":"Your FlexCoins:","この世界で最も高価な通貨。":"The most expensive currency in this world.",
"1 FlexCoin = ¥1兆":"1 FlexCoin = ¥1 trillion","で密かに取引される、":"Secretly traded by",
"本物の超富裕層だけが扱う禁断の決済手段。":"the true ultra-rich. Forbidden money.",
"最強・買い切り":"Ultimate / One-time","「神の領域」 — この世の理を超える権利。":"\"God Tier\" — the right to break the rules of this world.",
"🎰 ギャンブルの神様":"🎰 God of Gambling","（全カジノ・FXで最高結果が出続ける）":"(Best results in every casino & FX trade)",
"伝説のハンドスピナー":"Legendary Fidget Spinner","（アスリート御用達）":"(Trusted by athletes)",
"＋ PREMIUM 全特典を内包":"+ Includes all PREMIUM perks","⚜ LEGENDARY を購入 — ¥1,000":"⚜ Buy LEGENDARY — ¥1,000",
"買い切り・永久":"One-time / Forever","限定プレミアムバッジ":"Exclusive PREMIUM badge",
"デイリー報酬 ×2倍":"Daily rewards ×2","⚡ オート労働":"⚡ Auto-work","（放置で自動タップ）":"(auto-taps while idle)",
"🛋 ニート強化":"🛋 NEET Boost","（確率100% / 収入×300倍）":"(100% success / income ×300)",
"★ PREMIUM バッジ表示":"★ PREMIUM badge display","💎 PREMIUM を購入 — ¥500":"💎 Buy PREMIUM — ¥500",
"💱 FlexCoin 換金（1🪙=¥1兆）":"💱 Convert FlexCoin (1🪙=¥1T)","¥1兆":"¥1T","¥10兆":"¥10T","¥100兆":"¥100T",
"💴 全コイン換金 ALL → ¥兆単位":"💴 Convert ALL coins → trillions","🪙 FLEXCOIN パック":"🪙 FLEXCOIN PACKS",
"💖 開発者を支援（特典なし）":"💖 Support the dev (no perks)","↺ 以前の購入を復元する":"↺ Restore Purchases",
"支払いは App Store / Google Play で安全に処理されます。":"Payments are processed securely by the App Store / Google Play.",
"購入は":"Purchases are subject to the","利用規約":"Terms of Use","と":"and","プライバシーポリシー":"Privacy Policy","に同意したものとみなします。":".",
"資産を売却":"Sell Assets","🙇 ストリートで稼ぐ":"🙇 Hustle on the Street",
"通行人がたまに何かを置いていく…":"Passersby sometimes leave something…","何かが置かれた！タップして受け取れ":"Something was left! Tap to grab it",
"👀 何か置かれた！タップで受取":"👀 Something's there! Tap to collect","受取回数":"Pickups","総額":"Total","最高":"Best","履歴":"History",
"💗 お金をあげる":"💗 Give Money","困っている人を助けて心を満たそう":"Help people in need, fill your heart",
"助けた人":"People helped","寄付総額":"Total given","カルマ":"Karma","あげた履歴":"Giving history",
"「お腹がすいた...」":"\"I'm starving...\"","「今日も食べるものがない...」":"\"Nothing to eat again today...\"",
"🎰 スロット":"🎰 Slots","★ 一番人気":"★ Most popular","🎡 ルーレット":"🎡 Roulette","🎴 バカラ":"🎴 Baccarat",
"🪙 クラシックパチンコ":"🪙 Classic Pachinko","3つ揃えろ":"Match 3 to win","勝率":"Win rate","最大勝利":"Biggest win","ゲーム数":"Games",
"今日受け取らなければ消える":"Disappears if not claimed today","本日受取済み ✓":"Claimed today ✓",
"ランキング":"Ranking","散財の神":"God of Spending","億万長者X":"Billionaire X","成り上がり":"Upstart","金の亡者":"Money Fiend","浪費家":"Big Spender",
"投資ポートフォリオ":"Portfolio","投資元本":"Principal","損益":"P/L","利益率":"Return","まだ投資していません":"No investments yet","💎 投資銘柄":"💎 Investments","¥1万":"¥10K",
"含み損益":"Unrealized P/L","数量":"Amount","レバレッジ":"Leverage","証拠金:":"Margin:","· レバ:":"· Lev:","· 想定ポジ:":"· Position:",
"📈 ロング (買い)":"📈 Long (Buy)","📉 ショート (売り)":"📉 Short (Sell)","保有ポジション":"Open Positions","決済":"Close","累計損益":"Total P/L","取引回数":"Trades",
"ビジネス":"Business","レベル":"Level","社員数":"Employees","予想収入/3分":"Est. income / 3min","社員ポジション":"Positions",
"●在籍":"●Hired","解雇":"Fire","雇用する ¥400,000":"Hire ¥400,000","Lv3 必要":"Needs Lv3","Lv4 必要":"Needs Lv4","Lv6 必要":"Needs Lv6",
"キャリアレベル":"Career Level","職種一覧":"Jobs","肉体労働":"Physical Labor","農業 ◀":"Farmer ◀","ブルーカラー":"Blue Collar","ホワイトカラー":"White Collar","エンタメ":"Entertainment","特殊":"Special","経営者":"Executive",
"NEW GAME":"NEW GAME","挑戦数":"Attempts","正答率":"Accuracy","連続日数":"Streak",
// 乞食の訴え(「」付きレンダリング版)
"「お腹がすいた...助けて...」":"\"I'm starving... please help...\"",
"「今日も食べるものがない...」":"\"Nothing to eat again today...\"",
"「子供にミルクを買えなくて...」":"\"I can't afford milk for my baby...\"",
"「お母さんが帰ってこない...」":"\"Mommy hasn't come home...\"",
"「家族を養えない...」":"\"I can't feed my family...\"",
"「薬を買うお金が...」":"\"I can't afford my medicine...\"",
"「もう学校を辞めるしか...」":"\"I'll have to drop out of school...\"",
// 購入演出モーダル(strong分割フラグメント)
"タップで閉じる":"Tap to close",
"深夜のパリへ。翌朝には":"Midnight flight to Paris,","東京に戻れる。":"back in Tokyo by morning.","それが当たり前になった。":"That's normal now.",
"ヨットのデッキで夕日を見ている。":"Watching the sunset from the yacht deck.","これが自由というものか。":"So this is freedom.",
"無人島で星空を見上げた。":"Stargazing on my island.","静寂だけが友達だった。":"Silence was my only company.",
"地球を上から見下ろした。":"Looked down at Earth.","国境線がなかった。":"There were no borders.",
"六本木の夜景を独占している。":"The Roppongi skyline, all mine.","東京が小さく見える。":"Tokyo looks small from here.",
// 称号(絵文字付き実レンダリング版)+称号アップ演出
"🪙 一般人":"🪙 Nobody","💰 成金":"💰 New Rich","🏦 富豪":"🏦 Tycoon","🏰 大富豪":"🏰 Big Tycoon",
"👑 億万長者":"👑 Billionaire","🐉 伝説の散財王":"🐉 Legendary Big Spender",
"散財して称号が上がった":"Your spending raised your title!",
// ミッション/実績トースト(🏆付き実レンダリング版)
"🎯 ミッション達成！":"🎯 Mission Complete!",
"🏆 ¥100万散財達成！":"🏆 Spent ¥1M!","🏆 ¥500万散財達成！":"🏆 Spent ¥5M!","🏆 ¥1000万散財達成！":"🏆 Spent ¥10M!",
"🏆 ¥5000万散財達成！":"🏆 Spent ¥50M!","🏆 ¥1億散財達成！":"🏆 Spent ¥100M!","🏆 ¥5億散財達成！":"🏆 Spent ¥500M!",
"🏆 ¥10億散財達成！":"🏆 Spent ¥1B!","🏆 ¥100億散財達成！":"🏆 Spent ¥10B!","🏆 ¥1000億散財達成！":"🏆 Spent ¥100B!",
});

// 動的数値入りパターン(exact不可の分)
window.EN_PATTERNS = [
  [/^称号(\s|　)*/, "Title "],
  [/^月給 ¥([\d,]+) \| 1タスク ¥([\d,]+)$/, "Salary ¥$1 | Per task ¥$2"],
  [/^¥([\d,]+)\/3分$/, "¥$1 / 3min"],
  [/^¥([\d,]+) \/ タップ$/, "¥$1 / tap"],
  [/^エントリー: ([\d.]+) → 現在: ([\d.]+)$/, "Entry: $1 → Now: $2"],
  [/^💰 ¥([\d,]+) 受取$/, "💰 Collect ¥$1"],
  [/^雇用する ¥([\d,]+)$/, "Hire ¥$1"],
  [/^Lv(\d+) 必要$/, "Needs Lv$1"],
  [/^¥([\d,]+) を購入$/, "Bought for ¥$1"],
  [/^\+¥([\d,]+) ボーナス！$/, "+¥$1 Bonus!"],
];

// ===== エンジン =====
var _dataDone=false;
function isEn(){ return (typeof currentLang!=='undefined') && currentLang==='en'; }

var JA_RUN=/[぀-ヿ一-鿿][぀-ヿ一-鿿ー・]*/g;
function trStr(v){
  if(typeof v!=='string') return null;
  var en=window.EN_STRINGS[v];
  if(en && en!==v) return en; // 同一文字列は置換しない(Observer無限ループ防止)
  if(window.EN_PATTERNS){
    for(var i=0;i<window.EN_PATTERNS.length;i++){
      var p=window.EN_PATTERNS[i];
      if(p[0].test(v)){
        var out=v.replace(p[0],p[1]);
        // 残った日本語ランを辞書で個別置換(称号名など)
        out=out.replace(JA_RUN,function(m){var e=window.EN_STRINGS[m];return (e&&e!==m)?e:m;});
        if(out!==v) return out;
      }
    }
  }
  return null;
}

// ① データ配列の深掘り置換(可逆: _ja$key に元値保存)
function walkData(o, depth){
  if(!o || depth>4) return;
  if(Array.isArray(o)){ for(var i=0;i<o.length;i++) walkData(o[i], depth+1); return; }
  if(typeof o!=='object') return;
  for(var k in o){
    if(k.indexOf('_ja$')===0) continue;
    var v=o[k];
    if(typeof v==='string'){
      var en=trStr(v);
      if(en){ o['_ja$'+k]=v; o[k]=en; }
    } else if(typeof v==='object'){ walkData(v, depth+1); }
  }
}
function restoreData(o, depth){
  if(!o || depth>4) return;
  if(Array.isArray(o)){ for(var i=0;i<o.length;i++) restoreData(o[i], depth+1); return; }
  if(typeof o!=='object') return;
  for(var k in o){
    if(k.indexOf('_ja$')===0){ o[k.slice(4)]=o[k]; delete o[k]; }
    else if(typeof o[k]==='object') restoreData(o[k], depth+1);
  }
}
var DATA_GLOBALS=['ITEMS','SCENES','GACHA','DAILY','BEG','BADGES_DEF','RANKS','INVEST_TYPES',
  'EMP_TYPES_NORMAL','EMP_TYPES_HARD','BIZ_LEVELS','JOBS','ALL_JOBS','PERIODIC_EVENTS',
  'SPEND_MISSIONS','BEG_ITEMS','BEG_ITEMS_HARD','GIVE_PEOPLE','SLOT_SYMBOLS'];
function applyDataEN(){
  DATA_GLOBALS.forEach(function(n){ try{ if(window[n]) walkData(window[n],0); }catch(e){} });
  _dataDone=true;
}
function restoreDataJA(){
  DATA_GLOBALS.forEach(function(n){ try{ if(window[n]) restoreData(window[n],0); }catch(e){} });
  _dataDone=false;
}

// ② DOMテキストの exact-match 置換(表示中のハードコードHTMLを翻訳)
function translateDom(root){
  try{
    var w=document.createTreeWalker(root||document.body, NodeFilter.SHOW_TEXT);
    var n;
    while(n=w.nextNode()){
      var t=n.textContent; var trimmed=t.trim();
      if(!trimmed) continue;
      var en=trStr(trimmed);
      if(en) n.textContent=t.replace(trimmed,en);
    }
  }catch(e){}
}

// ③ MutationObserver: 後からレンダリングされるUIも翻訳
var _obs=null;
function startObserver(){
  if(_obs) return;
  _obs=new MutationObserver(function(muts){
    if(!isEn()) return;
    muts.forEach(function(m){
      m.addedNodes && m.addedNodes.forEach(function(nd){
        if(nd.nodeType===1) translateDom(nd);
        else if(nd.nodeType===3){
          var t=nd.textContent.trim(); var en=trStr(t);
          if(en) nd.textContent=nd.textContent.replace(t,en);
        }
      });
      if(m.type==='characterData'){
        var t=m.target.textContent.trim(); var en=trStr(t);
        if(en) m.target.textContent=m.target.textContent.replace(t,en);
      }
    });
  });
  _obs.observe(document.body,{childList:true,subtree:true,characterData:true});
}
function stopObserver(){ if(_obs){ _obs.disconnect(); _obs=null; } }

// setLang をラップ(ja/en 完全対応)
document.addEventListener('DOMContentLoaded', function(){
  if(typeof window.setLang==='function'){
    var orig=window.setLang;
    window.setLang=function(code){
      // 言語は ja/en のみサポート(konan決定 2026-07-06)
      if(code!=='ja' && code!=='en') code='en';
      if(code==='en'){ applyDataEN(); } else { restoreDataJA(); stopObserver(); }
      orig(code);
      if(code==='en'){ translateDom(); startObserver(); }
      // 現在タブを再描画してデータ置換を反映
      try{ if(typeof renderShop==='function') renderShop(); }catch(e){}
      try{ if(typeof renderMarket==='function') renderMarket(); }catch(e){}
      try{ if(typeof renderWorkTab==='function') renderWorkTab(); }catch(e){}
      try{ if(typeof updateRank==='function') updateRank(); }catch(e){}
      try{ if(typeof updateUI==='function') updateUI(); }catch(e){}
    };
    // 起動時にenが保存されていた場合も適用
    if(localStorage.getItem('flex-lang')==='en'){
      setTimeout(function(){ try{ window.setLang('en'); }catch(e){} }, 400);
    }
  }
});
})();
