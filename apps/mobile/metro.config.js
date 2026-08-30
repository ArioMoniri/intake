// Metro configuration (INT-263).
//
// expo-router turns EVERY file under the app directory into a route: its
// `require.context` matches `.*\.[tj]sx?$`, with no exception for test files.
// `src/app/scroll-containers.test.ts` has to live beside the routes it walks —
// the issue's acceptance is that the sweep enumerates the filesystem rather
// than a hand-kept list — so without this block Metro would bundle it as a
// screen at `/scroll-containers.test`, importing `node:fs` into the app.
//
// The block is on the file map, so the file is invisible to the route context,
// to typed-routes generation and to the bundle alike, while vitest (which does
// not go through Metro) still runs it.
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

const existing = config.resolver.blockList;
const testFilesUnderApp = /[\\/]src[\\/]app[\\/].*\.test\.[jt]sx?$/;

config.resolver.blockList = [
  ...(Array.isArray(existing) ? existing : existing ? [existing] : []),
  testFilesUnderApp,
];

module.exports = config;
