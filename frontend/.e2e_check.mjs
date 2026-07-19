// End-to-end UI check: load the app, run a search, screenshot the results.
import { chromium } from "playwright";

const SCRATCH = "/private/tmp/claude-501/-Users-yashjagirdar-Documents-Code-MSE-436-Final-Project/5a68b29f-104d-4145-bb58-a470fbdd5950/scratchpad";

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

page.on("console", (msg) => {
  if (msg.type() === "error") console.log("CONSOLE ERROR:", msg.text());
});
page.on("pageerror", (err) => console.log("PAGE ERROR:", err.message));

await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
await page.screenshot({ path: `${SCRATCH}/ui_initial.png` });
console.log("initial state captured");

await page.getByRole("button", { name: /search/i }).click();
await page.waitForSelector("h3", { timeout: 30000 });
await page.waitForTimeout(500);
await page.screenshot({ path: `${SCRATCH}/ui_results.png`, fullPage: false });

const cards = await page.locator("h3").count();
const badge = await page.locator("span[title='Fit score out of 100']").first().textContent();
console.log(`results rendered: ${cards} player cards, top fit score ${badge}`);

// Switch position to exercise the weight sliders re-render
await page.selectOption("select", "Goalkeeper");
await page.waitForTimeout(300);
await page.screenshot({ path: `${SCRATCH}/ui_goalkeeper_controls.png` });
console.log("position switch OK");

await browser.close();
