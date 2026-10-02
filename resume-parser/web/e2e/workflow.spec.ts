import { test, expect } from "@playwright/test";
import path from "node:path";

test("upload, evidence, JSON/CSV exports, history and deletion", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Good data starts/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "standard", exact: true }).click();
  await expect(page.getByText("standard.pdf", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Extract resume", exact: true })
    .click();
  await expect(
    page.getByText("Schema validated · review required"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Python", exact: true }).click();
  await expect(
    page.getByText("EXACT SOURCE QUOTE", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".source-line.highlight")).toContainText("Python");
  for (const format of ["JSON", "CSV"]) {
    const downloadPromise = page.waitForEvent("download");
    await page
      .locator(".export-bar")
      .getByRole("button", { name: format, exact: true })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(
      new RegExp(`resume-.*\\.${format.toLowerCase()}$`),
    );
  }
  await page.getByRole("button", { name: "Delete record" }).click();
  await page.getByRole("button", { name: "Delete now" }).click();
  await expect(
    page.getByRole("heading", {
      name: "A resume, with a little more clarity.",
    }),
  ).toBeVisible();
});

test("scanned and sidebar resumes parse through the UI", async ({ page }) => {
  for (const caseName of ["sidebar", "scanned"]) {
    await page.goto("/");
    await page.getByRole("button", { name: caseName, exact: true }).click();
    await expect(
      page.getByText(`${caseName}.pdf`, { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Extract resume", exact: true })
      .click();
    await expect(
      page.getByText("Schema validated · review required"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Institution Example University" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Delete record" }).click();
    await page.getByRole("button", { name: "Delete now" }).click();
  }
});

test("invalid file and mobile layout are usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Upload resume PDF").setInputFiles({
    name: "not-pdf.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hello"),
  });
  await expect(page.getByRole("alert")).toContainText("Choose a PDF file");
  await page
    .getByLabel("Upload resume PDF")
    .setInputFiles(path.resolve("../examples/sparse.pdf"));
  await page
    .getByRole("button", { name: "Extract resume", exact: true })
    .click();
  await expect(
    page.getByText("No employment entries found", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Recent documents" }).click();
  await expect(page.locator(".history")).toBeVisible();
  await page
    .locator(".history")
    .getByRole("button", { name: /Noor Ali/ })
    .first()
    .click();
  await expect(
    page.getByText("No employment entries found", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete record" }).click();
  await page.getByRole("button", { name: "Delete now" }).click();
});

test("interactive API docs use local assets without browser errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/docs");
  await expect(page.locator(".swagger-ui .info")).toBeVisible();
  await expect(page.locator(".swagger-ui")).toContainText("/api/resumes");
  expect(errors).toEqual([]);
});
