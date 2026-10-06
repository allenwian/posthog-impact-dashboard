import { readFileSync } from "node:fs";
import { initializeApp } from "firebase-admin/app";
import { getStorage } from "firebase-admin/storage";
import { onRequest } from "firebase-functions/v2/https";

initializeApp();

// Snapshot bundled at deploy time; served until the daily refresh (functions-py) has published one.
const bundled = readFileSync(new URL("./impact.json", import.meta.url), "utf8");
const BUCKET = "weave-impact-ia26-data"; // written daily by the refresh_impact function (functions-py)
const CACHE_MS = 10 * 60 * 1000;
let cached = { body: bundled, at: 0 };

async function latest() {
  if (Date.now() - cached.at < CACHE_MS) return cached.body;
  try {
    const [buf] = await getStorage().bucket(BUCKET).file("impact/latest.json").download();
    cached = { body: buf.toString("utf8"), at: Date.now() };
  } catch (err) {
    // Not published yet or transient storage error: keep serving the last good copy.
    console.warn("serving cached impact data", err.message);
    cached = { ...cached, at: Date.now() };
  }
  return cached.body;
}

export const impact = onRequest(
  { region: "us-central1", memory: "256MiB", maxInstances: 5, minInstances: 0 },
  async (req, res) => {
    if (req.method !== "GET") {
      res.status(405).send("Method Not Allowed");
      return;
    }
    // Firebase Hosting's CDN caches for an hour, so visitors almost never wait on the function.
    res.set("Cache-Control", "public, max-age=300, s-maxage=3600");
    res.type("application/json").send(await latest());
  },
);
