/**
 * INT-620: the iOS 27 SDK requires the UIScene lifecycle. Without it a Release
 * build crashes at launch (EXC_BREAKPOINT in
 * _UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption), measured on
 * 18 Nov 2026 on an iOS 27.2 simulator.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const plugin = require("../plugins/withSceneLifecycle.js") as {
  patchAppDelegate: (s: string) => string;
  sceneManifest: () => Record<string, unknown>;
  SCENE_DELEGATE_SWIFT: string;
};

const MOBILE = join(__dirname, "..");

const GENERATED_APP_DELEGATE = `  ) -> Bool {
    let delegate = ReactNativeDelegate()
    let factory = ExpoReactNativeFactory(delegate: delegate)
    delegate.dependencyProvider = RCTAppDependencyProvider()

    reactNativeDelegate = delegate
    reactNativeFactory = factory

#if os(iOS) || os(tvOS)
    window = UIWindow(frame: UIScreen.main.bounds)
    factory.startReactNative(
      withModuleName: "main",
      in: window,
      launchOptions: launchOptions)
#endif

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
`;

describe("INT-620: UIScene lifecycle", () => {
  it("app.json registers the plugin", () => {
    const app = JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8"));
    expect(app.expo.plugins).toContain("./plugins/withSceneLifecycle");
  });

  it("removes the AppDelegate's own window, so React Native starts exactly once", () => {
    const out = plugin.patchAppDelegate(GENERATED_APP_DELEGATE);
    expect(out).not.toContain("UIWindow(frame:");
    expect(out).not.toContain("startReactNative");
    expect(out).toContain("reactNativeFactory = factory");
  });

  it("is idempotent", () => {
    const once = plugin.patchAppDelegate(GENERATED_APP_DELEGATE);
    expect(plugin.patchAppDelegate(once)).toBe(once);
  });

  it("near-miss: an AppDelegate without the expected block makes the build fail loudly", () => {
    expect(() => plugin.patchAppDelegate("class AppDelegate {}")).toThrow(/INT-620/);
  });

  it("declares one scene configuration that names the SceneDelegate", () => {
    const m = plugin.sceneManifest() as {
      UIApplicationSupportsMultipleScenes: boolean;
      UISceneConfigurations: { UIWindowSceneSessionRoleApplication: Record<string, string>[] };
    };
    expect(m.UIApplicationSupportsMultipleScenes).toBe(false);
    const roles = m.UISceneConfigurations.UIWindowSceneSessionRoleApplication;
    expect(roles).toHaveLength(1);
    expect(roles[0].UISceneDelegateClassName).toBe("$(PRODUCT_MODULE_NAME).SceneDelegate");
  });

  it("the SceneDelegate starts React Native in the scene's window and forwards links", () => {
    const s = plugin.SCENE_DELEGATE_SWIFT;
    expect(s).toContain("UIWindow(windowScene: windowScene)");
    expect(s).toContain('startReactNative(withModuleName: "main", in: window');
    expect(s).toContain("openURLContexts");
    expect(s).toContain("continue userActivity");
  });
});
