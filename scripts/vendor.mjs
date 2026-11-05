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
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const vendorPath = "src/easy_kitchen/static/easy_kitchen/vendor";

// Keep only runtime assets and license notices. Preserve the icon font URLs.
const assets = [
  ["bootstrap", "dist/css/bootstrap.min.css", "bootstrap/css/bootstrap.min.css"],
  ["bootstrap", "dist/js/bootstrap.bundle.min.js", "bootstrap/js/bootstrap.bundle.min.js"],
  ["bootstrap", "LICENSE", "bootstrap/LICENSE"],
  ["@popperjs/core", "LICENSE.md", "bootstrap/POPPER-LICENSE.md"],
  [
    "bootstrap-icons",
    "font/bootstrap-icons.min.css",
    "bootstrap-icons/font/bootstrap-icons.min.css",
  ],
  [
    "bootstrap-icons",
    "font/fonts/bootstrap-icons.woff2",
    "bootstrap-icons/font/fonts/bootstrap-icons.woff2",
  ],
  [
    "bootstrap-icons",
    "font/fonts/bootstrap-icons.woff",
    "bootstrap-icons/font/fonts/bootstrap-icons.woff",
  ],
  ["bootstrap-icons", "LICENSE", "bootstrap-icons/LICENSE"],
  ["htmx.org", "dist/htmx.min.js", "htmx/htmx.min.js"],
  ["htmx.org", "LICENSE", "htmx/LICENSE"],
  ["sortablejs", "Sortable.min.js", "sortablejs/Sortable.min.js"],
  ["sortablejs", "LICENSE", "sortablejs/LICENSE"],
];

async function validateVersions(root, modules) {
  const lock = JSON.parse(await readFile(join(root, "package-lock.json"), "utf8"));
  for (const name of new Set(assets.map(([name]) => name))) {
    const installed = JSON.parse(await readFile(join(modules, name, "package.json"), "utf8"));
    if (installed.version !== lock.packages?.[`node_modules/${name}`]?.version) {
      throw new Error(`${name} does not match package-lock.json. Run npm ci first.`);
    }
  }
}

async function prepareVendor(root, modules, stage) {
  await validateVersions(root, modules);
  await mkdir(stage);
  for (const [name, source, target] of assets) {
    const destination = join(stage, target);
    await mkdir(dirname(destination), { recursive: true });
    if (/\.(css|js)$/.test(target)) {
      const content = await readFile(join(modules, name, source), "utf8");
      // No maps or source trees are shipped, so remove dangling debugger URLs.
      await writeFile(
        destination,
        content.replace(
          /\/\*# sourceMappingURL=[^\r\n]*?\*\/|\/\/# sourceMappingURL=[^\r\n]*/g,
          "",
        ),
      );
    } else {
      await copyFile(join(modules, name, source), destination);
    }
  }
}

async function listFiles(directory, prefix = "") {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const name = prefix + entry.name;
    if (entry.isDirectory()) {
      files.push(...(await listFiles(join(directory, entry.name), name + "/")));
    } else if (entry.isFile()) {
      files.push(name);
    } else {
      throw new Error(`Unsupported vendor entry: ${name}`);
    }
  }
  return files.sort();
}

async function compareVendor(stage, destination) {
  const expected = await listFiles(stage);
  let actual;
  try {
    actual = await listFiles(destination);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    actual = [];
  }
  const differences = [];
  for (const name of expected) {
    if (!actual.includes(name)) {
      differences.push(`Missing: ${name}`);
    } else if (
      !(await readFile(join(stage, name))).equals(await readFile(join(destination, name)))
    ) {
      differences.push(`Changed: ${name}`);
    }
  }
  for (const name of actual) {
    if (!expected.includes(name)) differences.push(`Unexpected: ${name}`);
  }
  if (differences.length) {
    throw new Error(
      `Vendor files are out of date:\n${differences.join("\n")}\nRun npm ci and npm run vendor:build, then commit the vendor files.`,
    );
  }
}

export async function replaceVendor(stage, destination, backup, move = rename) {
  let hadPrevious = false;
  try {
    await move(destination, backup);
    hadPrevious = true;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  try {
    await move(stage, destination);
  } catch (error) {
    if (hadPrevious) {
      try {
        await move(backup, destination);
      } catch (rollbackError) {
        throw new AggregateError(
          [error, rollbackError],
          `Vendor replacement and rollback failed. Previous files remain at ${backup}.`,
          { cause: rollbackError },
        );
      }
    }
    throw error;
  }
}

export async function buildVendor({
  root = projectRoot,
  modules = join(root, "node_modules"),
  check = false,
} = {}) {
  const destination = join(root, vendorPath);
  await mkdir(dirname(destination), { recursive: true });
  // A sibling staging directory keeps all renames on the same filesystem.
  const workspace = await mkdtemp(join(dirname(destination), ".vendor-stage-"));
  const stage = join(workspace, "prepared");
  const backup = join(workspace, "previous");
  let preserveBackup = false;
  try {
    await prepareVendor(root, modules, stage);
    if (check) {
      await compareVendor(stage, destination);
    } else {
      try {
        await replaceVendor(stage, destination, backup);
      } catch (error) {
        // If rollback itself failed, retain the recovery copy for the user.
        preserveBackup = (await readdir(workspace)).includes("previous");
        throw error;
      }
    }
  } finally {
    if (!preserveBackup) await rm(workspace, { recursive: true, force: true });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.length > 1 || (args.length === 1 && args[0] !== "--check")) {
      throw new Error("Usage: node scripts/vendor.mjs [--check]");
    }
    await buildVendor({ check: args.includes("--check") });
    console.log(
      args.includes("--check") ? "Vendor files match the lockfile." : "Vendor files updated.",
    );
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
