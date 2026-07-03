/**
 * PCカスタムサポート フィードバック受信用 Cloudflare Worker
 *
 * アプリ内フィードバック(POST /api/feedback)の転送先。
 * 受け取ったフィードバックを ①Cloudflare KV に保存し、②(設定時)Discord
 * Webhook へ通知する。秘密情報は一切扱わない。
 *
 * デプロイ(wrangler):
 *   1. KV 名前空間を作成: wrangler kv namespace create FEEDBACK_KV
 *   2. wrangler.toml に binding と(任意で)DISCORD_WEBHOOK_URL を設定
 *   3. wrangler deploy
 *   4. 発行された https://<name>.<account>.workers.dev を
 *      feedback_client.py の FEEDBACK_URL(または環境変数 PCCUSTOMSUPPORT_FEEDBACK_URL)に設定
 *
 * wrangler.toml 例:
 *   name = "pccustomsupport-feedback"
 *   main = "feedback-worker.js"
 *   compatibility_date = "2026-01-01"
 *   kv_namespaces = [{ binding = "FEEDBACK_KV", id = "<KV_ID>" }]
 *   [vars]
 *   # DISCORD_WEBHOOK_URL は secret 推奨: wrangler secret put DISCORD_WEBHOOK_URL
 */

const MAX_BODY_BYTES = 128 * 1024; // 過大なペイロードを拒否
const ALLOWED_CATEGORIES = ["bug", "request", "other"];

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // サイズ上限チェック
    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) {
      return new Response("Payload too large", { status: 413 });
    }

    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // 最小限のバリデーション(クライアント側でも検証済みだが二重に守る)
    const category = String(data.category || "");
    const comment = String(data.comment || "").trim();
    if (!ALLOWED_CATEGORIES.includes(category) || !comment) {
      return new Response("Invalid feedback", { status: 422 });
    }

    const record = {
      category,
      comment: comment.slice(0, 2000),
      app_version: data.app_version || null,
      platform: data.platform || null,
      submitted_at: data.submitted_at || new Date().toISOString(),
      diagnostics: data.diagnostics ?? null,
      // 集計・スパム対策の補助情報(個人特定はしない)
      received_at: new Date().toISOString(),
      country: request.headers.get("CF-IPCountry") || null,
    };

    // ① KV に保存(キーは時刻 + ランダムで衝突回避)
    if (env.FEEDBACK_KV) {
      const key = `fb:${Date.now()}:${crypto.randomUUID()}`;
      try {
        await env.FEEDBACK_KV.put(key, JSON.stringify(record));
      } catch (e) {
        // 保存失敗は致命的ではない(通知側で拾えるため)。500で再送を促す。
        return new Response("Storage error", { status: 500 });
      }
    }

    // ② Discord 通知(設定時のみ)
    if (env.DISCORD_WEBHOOK_URL) {
      const label = { bug: "🐞 不具合", request: "✨ 要望", other: "💬 その他" }[category];
      const lines = [
        `**${label}** (v${record.app_version || "?"} / ${record.platform || "?"})`,
        record.comment,
      ];
      if (record.diagnostics?.specs) {
        const s = record.diagnostics.specs;
        lines.push(
          `> CPU: ${s.cpu_name || "?"} / GPU: ${s.gpu_name || "?"} / RAM: ${s.ram_total_gb || "?"}GB / OS: ${s.os_name || "?"}`
        );
      }
      try {
        await fetch(env.DISCORD_WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: lines.join("\n").slice(0, 1900) }),
        });
      } catch {
        // 通知失敗は無視(KV には保存済み)
      }
    }

    return new Response(null, { status: 204 });
  },
};
