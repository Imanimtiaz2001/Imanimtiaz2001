// Capture the running real app. Images are documentation, not generated mockups.
import { chromium } from "../frontend/node_modules/playwright/index.mjs";
import { mkdir } from "node:fs/promises";
const browser = await chromium.launch({ args: ["--no-sandbox"] });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 960 },
  });
  await page.goto("http://127.0.0.1:8033");
  await page.getByText("Ready to listen", { exact: true }).waitFor();
  await mkdir(new URL("../docs/images", import.meta.url), { recursive: true });
  await page.screenshot({
    path: new URL("../docs/images/desktop.png", import.meta.url).pathname,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Knowledge & settings" }).click();
  await page
    .getByLabel("Note file")
    .setInputFiles(new URL("../evals/notes.md", import.meta.url).pathname);
  await page.getByRole("button", { name: /My notes/ }).waitFor();
  await page.waitForFunction(() =>
    document
      .querySelector(".mode-switch button.active")
      ?.textContent?.includes("My notes"),
  );
  await page.getByLabel("Close settings").click();
  await page
    .getByLabel("Your question")
    .fill("What happens to microphone recordings?");
  await page.getByLabel("Send question").click();
  await page
    .getByText("Grounded in your notes", { exact: true })
    .waitFor({ timeout: 180000 });
  await page.locator(".sources summary").first().click();
  await page.screenshot({
    path: new URL("../docs/images/conversation.png", import.meta.url).pathname,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Open history").click();
  await page.getByRole("button", { name: "New conversation" }).click();
  await page.screenshot({
    path: new URL("../docs/images/mobile.png", import.meta.url).pathname,
    fullPage: true,
  });
  console.log("Captured real local-provider UI on desktop and mobile.");
} finally {
  await browser.close();
}
