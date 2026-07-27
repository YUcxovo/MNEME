const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

async function main() {
  const source = path.resolve(process.argv[2] || "../../../../../materials/Mneme_demo.html");
  const output = path.resolve(process.argv[3] || "..");
  fs.mkdirSync(output, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 520, height: 940 }, deviceScaleFactor: 2 });
  await page.goto(`file://${source}`, { waitUntil: "load" });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));

  const captures = [
    ["prototype_digest.png", () => page.evaluate(() => showScreen("screen-digest"))],
    ["prototype_summary.png", () => page.evaluate(() => openPaper("self-rag"))],
    ["prototype_qa.png", () => page.evaluate(() => { openPaper("self-rag"); openQA(); })],
    ["prototype_graph.png", () => page.evaluate(() => openGraph())],
  ];

  for (const [name, activate] of captures) {
    await activate();
    await page.locator("#phone").screenshot({ path: path.join(output, name) });
  }

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
