import fs from "node:fs";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
const payload = JSON.parse(process.argv[2] || "{}");
const badge = (payload.badge || "PHẦN 1").toUpperCase();
const line1 = (payload.line1 || "SỰ THẬT CHẤN ĐỘNG").toUpperCase();
const line2 = (payload.line2 || "KHÔNG AI NGỜ TỚI").toUpperCase();
const outputPath = payload.output || "build_output/thumb.png";
const fontCandidates = [
"/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
];
const fontPath = fontCandidates.find((p) => fs.existsSync(p));
if (!fontPath) {
throw new Error("Không tìm thấy font NotoSans-Bold.ttf hoặc DejaVuSans-Bold.ttf");
}
const fontData = fs.readFileSync(fontPath);
const tree = {
type: "div",
props: {
style: {
width: "1280px",
height: "720px",
display: "flex",
flexDirection: "column",
justifyContent: "space-between",
padding: "64px 76px",
backgroundImage: "linear-gradient(135deg, #090D16 0%, #1E1B4B 55%, #450A0A 100%)",
color: "#FFFFFF",
fontFamily: "Noto Sans",
borderTop: "14px solid #EF4444",
},
children: [
{
type: "div",
props: {
style: {
display: "flex",
alignItems: "center",
gap: "18px",
},
children: [
{
type: "div",
props: {
style: {
backgroundColor: "#DC2626",
color: "#FFFFFF",
fontSize: "34px",
fontWeight: 700,
padding: "12px 30px",
borderRadius: "14px",
letterSpacing: "2px",
},
children: badge,
},
},
{
type: "div",
props: {
style: {
color: "#CBD5E1",
fontSize: "28px",
fontWeight: 700,
},
children: "AUDIO DRAMA FULL",
},
},
],
},
},
{
type: "div",
props: {
style: {
display: "flex",
flexDirection: "column",
gap: "18px",
},
children: [
{
type: "div",
props: {
style: {
fontSize: "88px",
fontWeight: 700,
lineHeight: 1.12,
color: "#FACC15",
textShadow: "0 6px 24px rgba(0,0,0,0.7)",
},
children: line1,
},
},
{
type: "div",
props: {
style: {
fontSize: "78px",
fontWeight: 700,
lineHeight: 1.15,
color: "#FFFFFF",
textShadow: "0 6px 24px rgba(0,0,0,0.7)",
},
children: line2,
},
},
],
},
},
{
type: "div",
props: {
style: {
display: "flex",
justifyContent: "space-between",
alignItems: "center",
borderTop: "2px solid rgba(255,255,255,0.18)",
paddingTop: "22px",
fontSize: "26px",
color: "#94A3B8",
},
children: [
{ type: "div", props: { children: "🎧 NGHE TRỌN TẬP KHÔNG CẮT" } },
{ type: "div", props: { style: { color: "#F87171" }, children: "TẬP MỚI MỖI NGÀY" } },
],
},
},
],
},
};
const svg = await satori(tree, {
width: 1280,
height: 720,
fonts: [
{
name: "Noto Sans",
data: fontData,
weight: 700,
style: "normal",
},
],
});
const resvg = new Resvg(svg, { fitTo: { mode: "width", value: 1280 } });
fs.writeFileSync(outputPath, resvg.render().asPng());
console.log("Satori rendered:", outputPath);
