/
Dấu đầu dòng Cloudflare Worker (gói Free 0đ): Nhận lệnh từ Telegram Bot và kích hoạt GitHub Actions.
Dấu đầu dòng Biến môi trường cần đặt trong Cloudflare Worker Settings -> Variables and Secrets:
Dấu đầu dòng TELEGRAM_BOT_TOKEN : Token bot từ @BotFather
Dấu đầu dòng ALLOWED_CHAT_ID    : 6018196217
Dấu đầu dòng GITHUB_TOKEN       : GitHub Personal Access Token (quyền repo / actions:write)
Dấu đầu dòng GITHUB_REPO        : truongphp/clipngan-ytb-tt
*/
export default {
async fetch(request, env) {
if (request.method !== "POST") {
return new Response("ClipNgan Telegram Worker OK", { status: 200 });
}
const update = await request.json();
const message = update.message;
if (!message || !message.text) {
return new Response("OK", { status: 200 });
}
const chatId = String(message.chat.id);
if (env.ALLOWED_CHAT_ID && chatId !== String(env.ALLOWED_CHAT_ID)) {
return new Response("Unauthorized", { status: 200 });
}
const text = message.text.trim();
if (!text.startsWith("/tao") && !text.startsWith("/trongsinh") && !text.startsWith("/doithuong")) {
await replyTelegram(
env,
chatId,
"Lệnh hỗ trợ:\n• /tao — Dựng tập tiếp theo (Trọng sinh)\n• /doithuong — Dựng 1 tập Chuyện đời thường\n• /tao <chủ đề> — Dựng theo ý tưởng riêng"
);
return new Response("OK", { status: 200 });
}
let seriesType = "trong_sinh";
let customTopic = "";
if (text.startsWith("/doithuong")) {
seriesType = "doi_thuong";
customTopic = text.replace(/^/doithuong\s*/, "").trim();
} else if (text.startsWith("/trongsinh")) {
seriesType = "trong_sinh";
customTopic = text.replace(/^/trongsinh\s*/, "").trim();
} else {
customTopic = text.replace(/^/tao\s*/, "").trim();
}
const ghResp = await fetch(
https://api.github.com/repos/${env.GITHUB_REPO}/dispatches,
{
method: "POST",
headers: {
Authorization: Bearer ${env.GITHUB_TOKEN},
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
}
);
if (ghResp.ok) {
await replyTelegram(
env,
chatId,
🚀 Đã kích hoạt GitHub Actions dựng tập mới (${seriesType})! Khoảng 3–5 phút nữa clip sẽ gửi về đây.
);
} else {
const errText = await ghResp.text();
await replyTelegram(env, chatId, ❌ Không gọi được GitHub Actions: ${ghResp.status} ${errText});
}
return new Response("OK", { status: 200 });
},
};
async function replyTelegram(env, chatId, text) {
await fetch(https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage, {
method: "POST",
headers: { "Content-Type": "application/json" },
body: JSON.stringify({ chat_id: chatId, text }),
});
}
