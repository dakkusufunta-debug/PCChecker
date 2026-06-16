# 中継サーバー構築手順（価格キャッシュ配信）

配布版のexeは、ユーザーPCから楽天API（IP許可制）を直接叩けず、秘密鍵（`.env`）も
同梱できない。そこで **固定IPの中継サーバー（収集層）** が日次で楽天APIを叩いて
価格キャッシュJSONを生成し、**CDN（配信層）** 経由で全ユーザーへ配信する。
exe側は鍵不要・IP制限の影響なしでそのJSONを参照する。

```
[収集層] 固定IP VPS              [配信層] Cloudflare           [クライアント] exe
  cron 日次バッチ                  Pages / R2                   rakuten_client.py
  build_price_cache.py     push    price_cache.json     GET     REMOTE_CACHE_URL
  .env（鍵はここだけ）      ───▶    （静的・IP制限なし）  ◀───    で参照・12hローカルキャッシュ
```

---

## 1. 収集層：国内VPS（固定IP）

さくらのVPS / ConoHa など、固定IPが標準付与される最小プラン（月数百円）でよい。

```bash
# VPS上(Ubuntu等)
sudo apt update && sudo apt install -y python3 python3-pip git
git clone https://github.com/dakkusufunta-debug/PCChecker.git
cd PCChecker
pip3 install -r requirements.txt   # 収集に必要なのは標準ライブラリのみだが念のため

# 楽天APIキーを配置（このサーバーにのみ置く）
cp .env.example .env
nano .env   # RAKUTEN_APPLICATION_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID を記入
```

> **楽天IP許可リスト**: 楽天デベロッパーのアプリ設定で、許可IPに **このVPSのグローバルIP** を登録する。
> （旧来の自宅eo光IP `119.230.160.212` は変動するため、固定IPのVPSに移すのが今回の主目的。）
> キーは年1回の延長が必要な点も忘れずに。

### バッチ実行

```bash
python3 scripts/build_price_cache.py /var/www/pcchecker-cache/price_cache.json
```

- `pc_analyzer` がトップレベルで import する Windows 専用モジュール（`wmi`/`winreg`）は、
  バッチが自動でスタブ化するため Linux でもそのまま動く。
- 全60パーツ＋6 BTOキーワードを楽天APIで取得（レート制限1.1秒/回で約1〜2分）。
- 出力は単一JSON。価格・BTOヒット件数が標準出力に表示される。

### cron 登録（毎日 早朝5時 JST に再生成）

```cron
# crontab -e
0 5 * * * cd /home/USER/PCChecker && /usr/bin/python3 scripts/build_price_cache.py /var/www/pcchecker-cache/price_cache.json >> /var/log/pcchecker-cache.log 2>&1
```

---

## 更新停止の通知（健全性アラート）

自宅PCなど固定IPではない環境で日次バッチを動かす場合、eo光などのグローバルIPが
変動すると楽天デベロッパーのIP許可リストと不一致になり、APIが拒否されて価格更新が
ほぼ全滅することがある。`scripts/build_price_cache.py` は生成後にヒット件数を確認し、
以下のいずれかなら異常として終了コードを非0にする。

- バッチ実行中に例外が発生した
- 価格ヒット数が総数の50%未満
- BTOヒットが0件

異常時に通知を受けるには、実行環境に `PCCHECKER_ALERT_WEBHOOK` を設定する。

```powershell
# Windows タスクスケジューラで使うユーザー環境変数として設定する例
[Environment]::SetEnvironmentVariable(
  "PCCHECKER_ALERT_WEBHOOK",
  "https://discord.com/api/webhooks/....",
  "User"
)
```

```bash
# Linux / cron で使う例
export PCCHECKER_ALERT_WEBHOOK="https://discord.com/api/webhooks/...."
python3 scripts/build_price_cache.py /var/www/pcchecker-cache/price_cache.json
```

Discord Webhook が最も手軽。Discord の「サーバー設定」→「連携サービス」→
「ウェブフック」で作成し、発行された Webhook URL を `PCCHECKER_ALERT_WEBHOOK` に設定する。
送信形式は `{"content": "..."}` の単純なJSONなので、Discord互換の受信先や汎用Webhookにも
流用できる。

通知例:

```text
[PCChecker] 価格キャッシュ更新の異常を検知しました
理由: 価格ヒット数がしきい値未満: 0/60 (50% 未満) / BTOヒット数がしきい値未満: 0件 (最低 1件)
価格ヒット: 0/60
BTOヒット: 0/6
generated_at: 2026-06-16T05:00:00+09:00
対処ヒント: 楽天IP許可リストの再確認(eo光IP変動の可能性)を行ってください。
```

この通知が届いたら、現在のグローバルIPを確認し、楽天デベロッパーのアプリ設定で
IP許可リストを更新する。APIキーの期限切れでも同様にヒット数が大きく落ちるため、
アプリ設定画面でキーの有効期限も確認する。

しきい値は必要に応じて環境変数で調整できる。

```bash
PCCHECKER_PRICE_MIN_HIT_RATIO=0.5  # 価格ヒット率の下限
PCCHECKER_BTO_MIN_HITS=1           # BTOヒット数の下限
```

`PCCHECKER_ALERT_WEBHOOK` が未設定の場合、通知は送らず標準エラーに警告だけを出す。
通知先の一時障害でもバッチ本体は通知失敗では落とさないが、生成結果が異常なら
タスクスケジューラやcronで検知できるよう終了コードは非0になる。

---

## 2. 配信層：Cloudflare Pages / R2

固定IPは**不要**（楽天を叩くのは収集層だけ）。静的JSONを配るだけなので高速・安価・DDoS耐性が高い。

### 方式A: Cloudflare Pages（手軽）
1. `pcchecker-cache` などの Pages プロジェクトを作成。
2. 収集層で生成した `price_cache.json` を含むディレクトリを `wrangler pages deploy` で公開。
   ```bash
   npx wrangler pages deploy /var/www/pcchecker-cache --project-name=pcchecker-cache
   ```
3. 公開URL（例 `https://pcchecker-cache.pages.dev/price_cache.json`）を控える。
   cron の最後に wrangler deploy を足せば、生成→公開まで日次自動化できる。

### 方式B: Cloudflare R2（オブジェクトストレージ）
1. R2 バケットを作成し、カスタムドメイン or `r2.dev` 公開を有効化。
2. cron 末尾で `wrangler r2 object put <bucket>/price_cache.json --file=...` を実行。

> どちらでも、配信物に秘密鍵は一切含まれない（鍵はVPSの`.env`のみ）。

---

## 3. クライアント（exe）側の設定

`rakuten_client.py` の `REMOTE_CACHE_URL` を、上で控えた公開URLに差し替える。
（検証時は環境変数 `PCCHECKER_CACHE_URL` で上書き可能。）

```python
# rakuten_client.py
REMOTE_CACHE_URL = os.environ.get(
    "PCCHECKER_CACHE_URL",
    "https://pcchecker-cache.pages.dev/price_cache.json",  # ← 本番URLに差し替え
)
```

### 配布版の挙動
- ローカルに `.env` が無い → `is_configured()` が False → `search_part`/`search_bto` は
  リモートキャッシュ（CDN）を参照。
- exe は取得したJSONを `%LOCALAPPDATA%\PCChecker\remote_cache.json` に12時間キャッシュ。
- CDN取得に失敗しても、古いローカルキャッシュ→それも無ければハードコード価格へ
  自動フォールバックするため、**診断機能は常に動く**。
- `app.js` は無改修（`/api/price`・`/api/bto` の応答形式は従来と同一）。

---

## 動作確認（ローカルで中継サーバーをエミュレート）

```powershell
# 生成したJSONをローカルHTTPで配信
cd /var/www/pcchecker-cache  # or 任意のフォルダ
python -m http.server 9000

# exe/アプリ側を「鍵なし＝配布版」状態にして、ローカルURLを向ける
$env:PCCHECKER_CACHE_URL = "http://localhost:9000/price_cache.json"
# （.env を退避するか、別フォルダで起動して is_configured() を False にする）
python main.py
```

`/api/price` がリモートキャッシュ由来の価格＋アフィリンクを返せば成功。

---

## 4. フィードバック受信（Cloudflare Worker）

リリース後の不具合報告・要望を集約する。アプリ内フォーム → ローカル `/api/feedback`
（main.py）→ 外部 Worker へ転送される。Worker 実装は `relay/feedback-worker.js`。

### デプロイ
```bash
# KV 名前空間を作成
npx wrangler kv namespace create FEEDBACK_KV   # 表示された id を控える

# wrangler.toml（relay/ に置く）
#   name = "pcchecker-feedback"
#   main = "feedback-worker.js"
#   compatibility_date = "2026-01-01"
#   kv_namespaces = [{ binding = "FEEDBACK_KV", id = "<KV_ID>" }]

# Discord通知を使うなら(任意)
npx wrangler secret put DISCORD_WEBHOOK_URL

cd relay && npx wrangler deploy
```

### クライアント側の設定
発行された `https://pcchecker-feedback.<account>.workers.dev` を
`feedback_client.py` の `FEEDBACK_URL`（または環境変数 `PCCHECKER_FEEDBACK_URL`）に設定する。

### 挙動
- 受信フィードバックは KV に保存（`fb:<時刻>:<uuid>` キー）、設定時は Discord にも通知。
- 添付診断データはオプトイン。ハードウェア構成と診断スコアのみで個人情報は含まない。
- Worker 側でもカテゴリ・空コメント・サイズ上限を二重に検証する。
- 送信先未設定／通信失敗時、アプリは「送信に失敗しました」を表示し、診断機能自体は通常どおり動作する。

### ローカル動作確認
```powershell
# 簡易スタブで成功(204)を返す例
$env:PCCHECKER_FEEDBACK_URL = "http://localhost:9100/"
python -m http.server 9100   # 204ではなく200だが ok:True になる
# 別ターミナルでアプリを起動し、フィードバックフォームから送信
```
