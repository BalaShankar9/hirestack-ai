import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore, initializeFirestore, type Firestore } from "firebase/firestore";
import { connectStorageEmulator, getStorage } from "firebase/storage";
import { getAnalytics, isSupported } from "firebase/analytics";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

// Initialize Firebase (only once)
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

// Initialize services
export const auth = getAuth(app);
// New Firestore multi-database projects can use `default` (no parentheses).
// Allow overriding via env for older projects that still use `(default)`.
const firestoreDatabaseId = process.env.NEXT_PUBLIC_FIREBASE_DATABASE_ID || "default";
export const db: Firestore = (() => {
  try {
    // Avoid runtime errors when optional fields are `undefined` (Firestore doesn't allow them).
    // In dev/HMR this can re-run, so fallback to the existing instance when already initialized.
    return initializeFirestore(app, { ignoreUndefinedProperties: true }, firestoreDatabaseId);
  } catch {
    try {
      return getFirestore(app, firestoreDatabaseId);
    } catch {
      return getFirestore(app);
    }
  }
})();
export const storage = getStorage(app);
let storageEmulatorConnected = false;
if (
  typeof window !== "undefined" &&
  !storageEmulatorConnected &&
  process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST
) {
  const host = process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST;
  const port = Number(process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_PORT || "9199");
  try {
    connectStorageEmulator(storage, host, port);
    storageEmulatorConnected = true;
  } catch {
    // Ignore emulator connection errors in production builds.
  }
}

// Analytics (only in browser)
export const initAnalytics = async () => {
  if (typeof window !== "undefined" && (await isSupported())) {
    return getAnalytics(app);
  }
  return null;
};

export default app;
