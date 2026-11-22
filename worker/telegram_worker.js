export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("ClipNgan Hub Worker OK", { status: 200 });
    }

    const update = await request.json();

    // 1. Xử lý khi bấm nút Inline Keyboard trên Telegram
    if (update.callback_query) {
      const cb = update.callback_query;
      const chatId = String(cb.message.chat.id);
      const data = cb.data || "";

      await answerCallback(env, cb.id);
      if (chatId !== String(env.ADMIN_CHAT_ID)) {
        await sendMsg(env, chatId, "⛔ Chỉ Admin mới dùng được nút điều khiển này.");
        return new Response("OK", { status: 200 });
      }

      if (data === "run_trong_sinh") {
        await triggerWorkflow(env, chatId, "trong_sinh", "");
      } else if (data === "run_doi_thuong") {
        await triggerWorkflow(env, chatId, "doi_thuong", "");
      } else if (data === "status_story") {
        await sendStoryStatus(env, chatId);
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

    // Tự động lưu/cập nhật người dùng vào D1
    const user = await upsertUser(env, chatId, username, fullName, isAdmin);
    if (user && user.status === "banned" && !isAdmin) {
      await sendMsg(env, chatId, "🚫 Tài khoản của bạn đã bị tạm khóa.");
      return new Response("OK", { status: 200 });
    }

    // Menu chính
    if (text === "/start" || text === "/menu") {
      if (isAdmin) {
        await sendAdminMenu(env, chatId);
      } else {
        await sendMsg(
          env,
          chatId,
          `Xin chào ${fullName}! 👋\n` +
            `• Trạng thái: *${user?.role?.toUpperCase() || "FREE"}*\n` +
            `• Lượt còn lại: *${user?.credits ?? 5}*\n\n` +
            `🎧 Nghe Audio Đi Ngủ trên YouTube:\nhttps://youtube.com/@truonghoang-om2cf`
        );
      }
      return new Response("OK", { status: 200 });
    }

    if (!isAdmin) {
      await sendMsg(env, chatId, "👋 Nhắn /menu để xem thông tin tài khoản của bạn nhé!");
      return new Response("OK", { status: 200 });
    }

    // Lệnh Admin: Dựng video kèm chủ đề
    if (text.startsWith("/tao")) {
      const topic = text.replace(/^\/tao\s*/, "").trim();
      await triggerWorkflow(env, chatId, "trong_sinh", topic);
    } else if (text.startsWith("/doithuong")) {
      const topic = text.replace(/^\/doithuong\s*/, "").trim();
      await triggerWorkflow(env, chatId, "doi_thuong", topic);
    } else if (text === "/users") {
      await sendUsersList(env, chatId);
    } else if (text.startsWith("/vip ")) {
      const parts = text.split(/\s+/);
      const targetId = parts[1];
      const addCredits = parseInt(parts[2] || "50", 10);
      await env.DB.prepare(
        "UPDATE users SET role = 'vip', credits = credits + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?"
      ).bind(addCredits, targetId).run();
      await sendMsg(env, chatId, `✅ Đã nâng VIP & cộng +${addCredits} lượt cho ID \`${targetId}\`.`);
    } else if (text.startsWith("/ban ")) {
      const targetId = text.split(/\s+/)[1];
      await env.DB.prepare("UPDATE users SET status = 'banned' WHERE user_id = ?").bind(targetId).run();
      await sendMsg(env, chatId, `🚫 Đã khóa người dùng \`${targetId}\`.`);
    } else if (text.startsWith("/unban ")) {
      const targetId = text.split(/\s+/)[1];
      await env.DB.prepare("UPDATE users SET status = 'active' WHERE user_id = ?").bind(targetId).run();
      await sendMsg(env, chatId, `🔓 Đã mở khóa người dùng \`${targetId}\`.`);
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

async function upsertUser(env, userId, username, fullName, isAdmin) {
  if (!env.DB) return null;
  const role = isAdmin ? "admin" : "free";
  const credits = isAdmin ? 999999 : 5;
  await env.DB.prepare(
    `INSERT INTO users (user_id, username, full_name, role, credits, status)
     VALUES (?, ?, ?, ?, ?, 'active')
     ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, full_name = excluded.full_name, updated_at = CURRENT_TIMESTAMP`
  ).bind(userId, username, fullName, role, credits).run();
  return await env.DB.prepare("SELECT * FROM users WHERE user_id = ?").bind(userId).first();
}

async function sendAdminMenu(env, chatId) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: "🎛️ *TRUNG TÂM ĐIỀU KHIỂN AUDIO ĐI NGỦ*\nChọn nhanh thao tác bên dưới (hoặc gõ `/tao <ý tưởng>`):",
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: [
          [
            { text: "🔥 Dựng Tập Trọng Sinh", callback_data: "run_trong_sinh" },
            { text: "🏠 Dựng Tập Đời Thường", callback_data: "run_doi_thuong" },
          ],
          [
            { text: "📊 Tiến độ Bộ Truyện", callback_data: "status_story" },
            { text: "👥 Quản lý Người dùng", callback_data: "admin_users" },
          ],
          [{ text: "📦 4 Dự Án & Kênh", callback_data: "menu_projects" }],
        ],
      },
    }),
  });
}

async function triggerWorkflow(env, chatId, seriesType, customTopic) {
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
        custom_topic: customTopic,
        privacy_status: "unlisted",
      },
    }),
  });
  if (ghResp.ok) {
    await sendMsg(env, chatId, `🚀 Đã kích hoạt dựng tập mới (*${seriesType}*)! Đợi ~4–5 phút nhận hàng nhé.`);
  } else {
    const err = await ghResp.text();
    await sendMsg(env, chatId, `❌ Lỗi gọi GitHub Actions: ${ghResp.status}\n${err}`);
  }
}

async function sendStoryStatus(env, chatId) {
  const resp = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/contents/data/story_memory.json`,
    {
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github.raw+json",
        "User-Agent": "clipngan-worker",
      },
    }
  );
  if (!resp.ok) {
    await sendMsg(env, chatId, "❌ Không đọc được `data/story_memory.json`.");
    return;
  }
  const mem = await resp.json();
  const ts = mem.series?.trong_sinh || {};
  const dt = mem.series?.doi_thuong || {};
  await sendMsg(
    env,
    chatId,
    `📊 *TIẾN ĐỘ CỐT TRUYỆN HIỆN TẠI*\n\n` +
      `🔥 *Trọng sinh:* Bộ ${ts.book_number || 1} — Đã ra *${ts.current_episode || 0}* tập\n` +
      `🏠 *Đời thường:* Bộ ${dt.book_number || 1} — Đã ra *${dt.current_episode || 0}* tập`
  );
}

async function sendUsersList(env, chatId) {
  if (!env.DB) {
    await sendMsg(env, chatId, "⚠️ Chưa gắn D1 Binding tên `DB` cho Worker.");
    return;
  }
  const total = await env.DB.prepare("SELECT COUNT(*) as c FROM users").first();
  const rows = await env.DB.prepare(
    "SELECT user_id, username, full_name, role, credits, status FROM users ORDER BY updated_at DESC LIMIT 12"
  ).all();
  const listText = (rows.results || [])
    .map(
      (u) =>
        `• \`${u.user_id}\` | ${u.full_name} (@${u.username || "none"}) | *${u.role}* | ${u.credits} lượt | ${u.status}`
    )
    .join("\n");
  await sendMsg(
    env,
    chatId,
    `👥 *Tổng người dùng:* ${total?.c || 0}\n\n${listText || "Chưa có ai"}\n\n` +
      `*Lệnh nhanh:*\n` +
      `• \`/vip <id> <số_lượt>\`\n` +
      `• \`/ban <id>\` hoặc \`/unban <id>\`\n` +
      `• \`/broadcast <nội_dung>\``
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
