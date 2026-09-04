// Ambient type for the bundled dialogue clip assets (INT-demo ElevenLabs dev
// lane). Metro turns `import clip from "./<hash>.wav"` into a registered asset
// id (a number), and `Image.resolveAssetSource` / expo-audio both take that
// number. Expo ships no wav module declaration, so it is declared here; the app
// tsconfig include globs pick this up for the generated index.
declare module "*.wav" {
  const assetId: number;
  export default assetId;
}
