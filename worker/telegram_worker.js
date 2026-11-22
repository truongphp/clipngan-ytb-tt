export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/sync-series" && request.method === "POST") {
      const secret = request.headers.get("X-Sync-Secret") || "";
      if (secret !== env.TELEGRAM_BOT_TOKEN) {
        return new Response("Forbidden", { status: 403 });
      }
      const body = await request.json();
      await env.DB.prepare(
        `INSERT INTO series_list (slug, name, book_number, current_episode, status, full_youtube_url, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
         ON CONFLICT(slug) DO UPDATE SET
           name = excluded.name,
           book_number = excluded.book_number,
           current_episode = excluded.current_episode,
           status = excluded.status,
           full_youtube_url = CASE WHEN excluded.full_youtube_url != '' THEN excluded.full_youtube_url ELSE series_list.full_youtube_url END,
           updated_at = CURRENT_TIMESTAMP`
      )
        .bind(
          body.slug,
          body.name || body.slug,
          body.book_number || 1,
          body.current_episode || 0,
          body.status || "active",
          body.full_youtube_url || ""
        )
        .run();
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (request.method !== "POST") {
      return new Response("ClipNgan Hub v3 OK", { status: 200 });
    }

    const update = await request.json();

    if (update.callback_query) {
      const cb = update.callback_query;
      const chatId = String(cb.message.chat.id);
      const data = cb.data || "";

      await answerCallback(env, cb.id);
      if (chatId !== String(env.ADMIN_CHAT_ID)) {
        await sendMsg(env, chatId, "⛔ Chỉ Admin mới dùng được nút này.");
        return new Response("OK", { status: 200 });
      }

      if (data.startsWith("run_series:")) {
        const slug = data.replace("run_series:", "");
        const row = await env.DB.prepare("SELECT name FROM series_list WHERE slug = ?").bind(slug).first();
        await triggerWorkflow(env, chatId, slug, row?.name || slug, "", false);
      } else if (data === "new_topic_guide") {
        await sendMsg(
          env,
          chatId,
          "🆕 *TẠO CHỦ ĐỀ MỚI:*\nNhắn theo cú pháp:\n`/moi Tên chủ đề bạn muốn làm`\n\n*Ví dụ:*\n`/moi Cô dâu hào môn báo thù`\n\n👉 Hệ thống sẽ tự tạo nút chủ đề mới trong `/menu` và dựng ngay Tập 1!"
        );
      } else if (data === "history_full") {
        await sendFullHistory(env, chatId);
      } else if (data === "admin_users") {
        await sendUsersList(env, chatId);
      } else if (data === "menu_projects") {
        await sendMsg(
          env,
          chatId,
          "📦 *Hệ thống dự án của bạn:*\n" +
            "• 🎬 *Audio Đi Ngủ* (`clipngan-ytb-tt`)\n" +
            "• 🎨 *Tone màu* (`tonelab-studio-vantruong`)\n" +
            "• 👑 *Locket Gold* (`Locketfilter`)\n" +
            "• 🔐 *Locket Cá Nhân* (`Thayoro`)\n\n" +
            "👉 YouTube: https://youtube.com/@truonghoang-om2cf\n" +
            "👉 TikTok: https://www.tiktok.com/@scvpro11"
        );
      }
      return new Response("OK", { status: 200 });
    }

    const msg = update.message;
    if (!msg || !msg.text) return new Response("OK", { status: 200 });

    const chatId = String(msg.chat.id);
    const username = msg.from?.username || "";
    const fullName = [msg.from?.first_name, msg.from?.last_name].filter(Boolean).join(" ") || "User";
    const text = msg.text.trim();
    const isAdmin = chatId === String(env.ADMIN_CHAT_ID);

    const user = await upsertUser(env, chatId, username, fullName, isAdmin);
    if (user && user.status === "banned" && !isAdmin) {
      await sendMsg(env, chatId, "🚫 Tài khoản của bạn đã bị tạm khóa.");
      return new Response("OK", { status: 200 });
    }

    if (text === "/start" || text === "/menu") {
      if (isAdmin) {
        await sendAdminMenu(env, chatId);
      } else {
        await sendMsg(
          env,
          chatId,
          `Xin chào ${fullName}! 👋\n• Trạng thái: *${user?.role?.toUpperCase() || "FREE"}*\n• Lượt còn lại: *${user?.credits ?? 5}*\n\n🎧 YouTube Audio Đi Ngủ:\nhttps://youtube.com/@truonghoang-om2cf`
        );
      }
      return new Response("OK", { status: 200 });
    }

    if (!isAdmin) {
      await sendMsg(env, chatId, "👋 Nhắn /menu để xem thông tin của bạn nhé!");
      return new Response("OK", { status: 200 });
    }

    if (text.startsWith("/moi ")) {
      const topicName = text.replace(/^\/moi\s+/, "").trim();
      const slug = slugify(topicName);
      await env.DB.prepare(
        `INSERT INTO series_list (slug, name, book_number, current_episode, status, full_youtube_url, updated_at)
         VALUES (?, ?, 1, 0, 'active', '', CURRENT_TIMESTAMP)
         ON CONFLICT(slug) DO UPDATE SET name = excluded.name, status = 'active', current_episode = 0, updated_at = CURRENT_TIMESTAMP`
      )
        .bind(slug, topicName)
        .run();
      await triggerWorkflow(env, chatId, slug, topicName, topicName, true);
    } else if (text.startsWith("/tao")) {
      const topic = text.replace(/^\/tao\s*/, "").trim();
      await triggerWorkflow(env, chatId, "trong_sinh", "Trọng Sinh Báo Thù", topic, false);
    } else if (text === "/users") {
      await sendUsersList(env, chatId);
    } else if (text.startsWith("/vip ")) {
      const [, targetId, addStr] = text.split(/\s+/);
      const addCredits = parseInt(addStr || "50", 10);
      await env.DB.prepare(
        "UPDATE users SET role = 'vip', credits = credits + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?"
      ).bind(addCredits, targetId).run();
      await sendMsg(env, chatId, `✅ Đã nâng VIP & cộng +${addCredits} lượt cho ID \`${targetId}\`.`);
    } else if (text.startsWith("/ban ")) {
      const targetId = text.split(/\s+/)[1];
      await env.DB.prepare("UPDATE users SET status = 'banned' WHERE user_id = ?").bind(targetId).run();
      await sendMsg(env, chatId, `🚫 Đã khóa ID \`${targetId}\`.`);
    } else if (text.startsWith("/unban ")) {
      const targetId = text.split(/\s+/)[1];
      await env.DB.prepare("UPDATE users SET status = 'active' WHERE user_id = ?").bind(targetId).run();
      await sendMsg(env, chatId, `🔓 Đã mở khóa ID \`${targetId}\`.`);
    } else if (text.startsWith("/broadcast ")) {
      const content = text.replace(/^\/broadcast\s*/, "").trim();
      const rows = await env.DB.prepare("SELECT user_id FROM users WHERE status = 'active'").all();
      let sent = 0;
      for (const r of rows.results || []) {
        if (r.user_id !== chatId) {
          await sendMsg(env, r.user_id, `📢 *Thông báo:*\n${content}`);
          sent++;
        }
      }
      await sendMsg(env, chatId, `✅ Đã gửi thông báo tới ${sent} người dùng.`);
    } else {
      await sendAdminMenu(env, chatId);
    }

    return new Response("OK", { status: 200 });
  },
};

function slugify(str) {
  return (
    str
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/gi, "d")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 28) || "chu_de_moi"
  );
}

async function upsertUser(env, userId, username, fullName, isAdmin) {
  if (!env.DB) return null;
  await env.DB.prepare(
    `INSERT INTO users (user_id, username, full_name, role, credits, status)
     VALUES (?, ?, ?, ?, ?, 'active')
     ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, full_name = excluded.full_name, updated_at = CURRENT_TIMESTAMP`
  )
    .bind(userId, username, fullName, isAdmin ? "admin" : "free", isAdmin ? 999999 : 5)
    .run();
  return await env.DB.prepare("SELECT * FROM users WHERE user_id = ?").bind(userId).first();
}

async function sendAdminMenu(env, chatId) {
  const activeRows = await env.DB.prepare(
    "SELECT slug, name, current_episode FROM series_list WHERE status = 'active' ORDER BY updated_at DESC LIMIT 8"
  ).all();

  const keyboard = [];
  for (const s of activeRows.results || []) {
    keyboard.push([
      { text: `🔥 ${s.name} (${s.current_episode}/5)`, callback_data: `run_series:${s.slug}` },
    ]);
  }
  keyboard.push([
    { text: "🆕 Tạo Chủ Đề Mới", callback_data: "new_topic_guide" },
    { text: "📚 Lịch Sử Full Bộ", callback_data: "history_full" },
  ]);
  keyboard.push([
    { text: "👥 Quản lý Người dùng", callback_data: "admin_users" },
    { text: "📦 4 Dự Án & Kênh", callback_data: "menu_projects" },
  ]);

  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: "🎛️ *AUDIO ĐI NGỦ — STUDIO v3*\nBấm vào tên bộ truyện bên dưới để dựng tập tiếp theo:",
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: keyboard },
    }),
  });
}

async function sendFullHistory(env, chatId) {
  const rows = await env.DB.prepare(
    "SELECT name, book_number, current_episode, full_youtube_url FROM series_list WHERE status = 'completed' ORDER BY updated_at DESC LIMIT 12"
  ).all();

  const items = rows.results || [];
  if (!items.length) {
    await sendMsg(env, chatId, "📚 *Lịch Sử Full Bộ* hiện đang trống.\nKhi nào một bộ ra đủ 5 tập và gộp Full xong sẽ tự xuất hiện nút mở YouTube ở đây!");
    return;
  }

  const keyboard = items
    .filter((i) => i.full_youtube_url)
    .map((i) => [{ text: `🎬 ${i.name} (Full ${i.current_episode} tập)`, url: i.full_youtube_url }]);

  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: "📚 *LỊCH SỬ CÁC BỘ ĐÃ FULL TRỌN BỘ*\nBấm vào tên bộ để mở thẳng trên YouTube:",
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: keyboard },
    }),
  });
}

async function triggerWorkflow(env, chatId, seriesType, seriesName, customTopic, startNewBook) {
  const ghResp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "clipngan-worker",
    },
    body: JSON.stringify({
      event_type: "generate_episode",
      client_payload: {
        series_type: seriesType,
        series_name: seriesName,
        custom_topic: customTopic,
        start_new_book: startNewBook ? "true" : "false",
        privacy_status: "unlisted",
      },
    }),
  });
  if (ghResp.ok) {
    await sendMsg(env, chatId, `🚀 Đã kích hoạt dựng *${seriesName}*! Khoảng 3–5 phút nữa clip Studio v3 sẽ gửi về đây.`);
  } else {
    const err = await ghResp.text();
    await sendMsg(env, chatId, `❌ Lỗi GitHub Actions: ${ghResp.status}\n${err}`);
  }
}

async function sendUsersList(env, chatId) {
  const total = await env.DB.prepare("SELECT COUNT(*) as c FROM users").first();
  const rows = await env.DB.prepare(
    "SELECT user_id, username, full_name, role, credits, status FROM users ORDER BY updated_at DESC LIMIT 12"
  ).all();
  const listText = (rows.results || [])
    .map((u) => `• \`${u.user_id}\` | ${u.full_name} (@${u.username || "none"}) | *${u.role}* | ${u.credits} lượt | ${u.status}`)
    .join("\n");
  await sendMsg(
    env,
    chatId,
    `👥 *Tổng người dùng:* ${total?.c || 0}\n\n${listText || "Chưa có ai"}\n\n*Lệnh nhanh:*\n• \`/vip <id> <lượt>\`\n• \`/ban <id>\` | \`/unban <id>\`\n• \`/broadcast <nội_dung>\``
  );
}

async function sendMsg(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
  });
}

async function answerCallback(env, callbackId) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackId }),
  });
}
