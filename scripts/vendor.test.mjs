import assert from "node:assert/strict";
import {
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { buildVendor, replaceVendor } from "./vendor.mjs";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const modules = join(projectRoot, "node_modules");

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "easy-kitchen-vendor-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await copyFile(join(projectRoot, "package-lock.json"), join(root, "package-lock.json"));
  const destination = join(root, "src/easy_kitchen/static/easy_kitchen/vendor");
  return { root, modules, destination };
}

test("builds reproducibly with usable font URLs, licenses and no dangling source maps", async (t) => {
  const options = await fixture(t);
  await buildVendor(options);
  await buildVendor({ ...options, check: true });
  await buildVendor(options);
  await buildVendor({ ...options, check: true });
  const css = await readFile(
    join(options.destination, "bootstrap-icons/font/bootstrap-icons.min.css"),
    "utf8",
  );
  const fontURLs = [...css.matchAll(/url\(["']?([^"')]+)["']?\)/g)].map((match) => match[1]);
  assert.equal(fontURLs.length, 2);
  for (const url of fontURLs) {
    assert.ok(
      (await readFile(join(options.destination, "bootstrap-icons/font", url.split("?")[0])))
        .length > 0,
    );
  }
  for (const path of [
    "bootstrap/LICENSE",
    "bootstrap/POPPER-LICENSE.md",
    "bootstrap-icons/LICENSE",
    "htmx/LICENSE",
    "sortablejs/LICENSE",
  ]) {
    assert.ok((await readFile(join(options.destination, path), "utf8")).length > 100);
  }
  for (const path of [
    "bootstrap/css/bootstrap.min.css",
    "bootstrap/js/bootstrap.bundle.min.js",
    "htmx/htmx.min.js",
    "sortablejs/Sortable.min.js",
  ]) {
    assert.doesNotMatch(
      await readFile(join(options.destination, path), "utf8"),
      /sourceMappingURL=/,
    );
  }
  assert.deepEqual(await readdir(dirname(options.destination)), ["vendor"]);
});

for (const kind of ["Changed", "Missing", "Unexpected"]) {
  test(`check rejects ${kind.toLowerCase()} files without modifying the vendor directory`, async (t) => {
    const options = await fixture(t);
    await buildVendor(options);
    const name = kind === "Unexpected" ? "extra.txt" : "htmx/htmx.min.js";
    const target = join(options.destination, name);
    if (kind === "Missing") await rm(target);
    else await writeFile(target, "local change");
    await assert.rejects(buildVendor({ ...options, check: true }), new RegExp(`${kind}: ${name}`));
    if (kind === "Missing") await assert.rejects(readFile(target), { code: "ENOENT" });
    else assert.equal(await readFile(target, "utf8"), "local change");
    assert.deepEqual(await readdir(dirname(options.destination)), ["vendor"]);
  });
}

test("a failed preparation leaves the previous vendor files intact", async (t) => {
  const options = await fixture(t);
  await mkdir(options.destination, { recursive: true });
  await writeFile(join(options.destination, "old.txt"), "previous assets");
  const incompleteModules = join(options.root, "incomplete-modules");
  for (const name of ["bootstrap", "@popperjs/core", "bootstrap-icons", "htmx.org", "sortablejs"]) {
    await mkdir(join(incompleteModules, name), { recursive: true });
    await copyFile(
      join(modules, name, "package.json"),
      join(incompleteModules, name, "package.json"),
    );
  }
  await mkdir(join(incompleteModules, "bootstrap/dist/css"), { recursive: true });
  await copyFile(
    join(modules, "bootstrap/dist/css/bootstrap.min.css"),
    join(incompleteModules, "bootstrap/dist/css/bootstrap.min.css"),
  );
  // The first asset is copied successfully; the next asset is deliberately missing.
  await assert.rejects(buildVendor({ ...options, modules: incompleteModules }), { code: "ENOENT" });
  assert.equal(await readFile(join(options.destination, "old.txt"), "utf8"), "previous assets");
  assert.deepEqual(await readdir(dirname(options.destination)), ["vendor"]);
});

test("a lockfile mismatch stops replacement", async (t) => {
  const options = await fixture(t);
  const lockfile = join(options.root, "package-lock.json");
  const lock = JSON.parse(await readFile(lockfile, "utf8"));
  lock.packages["node_modules/bootstrap"].version = "0.0.0";
  await writeFile(lockfile, JSON.stringify(lock));
  await assert.rejects(buildVendor(options), /bootstrap does not match package-lock.json/);
});

test("a failed final rename restores the previous vendor directory", async (t) => {
  const { root } = await fixture(t);
  const stage = join(root, "stage");
  const destination = join(root, "vendor");
  const backup = join(root, "backup");
  await mkdir(stage);
  await mkdir(destination);
  await writeFile(join(stage, "new.txt"), "prepared assets");
  await writeFile(join(destination, "old.txt"), "previous assets");
  const move = async (source, target) => {
    if (source === stage) throw Object.assign(new Error("rename failed"), { code: "EACCES" });
    return rename(source, target);
  };
  await assert.rejects(replaceVendor(stage, destination, backup, move), /rename failed/);
  assert.equal(await readFile(join(destination, "old.txt"), "utf8"), "previous assets");
  await assert.rejects(readFile(join(destination, "new.txt")), { code: "ENOENT" });
  assert.deepEqual((await readdir(root)).sort(), ["package-lock.json", "stage", "vendor"]);
});

test("a failed rollback retains the previous files at the reported recovery path", async (t) => {
  const { root } = await fixture(t);
  const stage = join(root, "stage");
  const destination = join(root, "vendor");
  const backup = join(root, "backup");
  await mkdir(stage);
  await mkdir(destination);
  await writeFile(join(destination, "old.txt"), "previous assets");
  const move = async (source, target) => {
    if (source !== destination) throw new Error("rename blocked");
    return rename(source, target);
  };
  await assert.rejects(replaceVendor(stage, destination, backup, move), (error) => {
    assert.ok(error instanceof AggregateError);
    assert.ok(error.message.includes(backup));
    return true;
  });
  assert.equal(await readFile(join(backup, "old.txt"), "utf8"), "previous assets");
});
