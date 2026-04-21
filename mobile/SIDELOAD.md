# Android sideload guide

The HireStack AI Android app is **debug + sideload only** for now (no Google Play
listing yet). Two APKs are produced from the same codebase:

| APK | Size | Package | Use it for |
|-----|------|---------|------------|
| `app/build/outputs/apk/debug/app-debug.apk` | ~21 MB | `com.hirestack.ai.debug` | Day-to-day testing on your own device. |
| `app/build/outputs/apk/release/app-release.apk` | ~14 MB | `com.hirestack.ai`       | Sharing with friends / running side-by-side with the debug build. |

Both APKs talk to the production Railway backend
(`https://hirestack-ai-production.up.railway.app/api/`) and the Supabase auth
project — so you sign in with the **same email/password** you use on the web.

---

## 1. Build the APKs

From the repo root:

```bash
cd mobile/android
export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"   # macOS / Homebrew
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
export JAVA_HOME="/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home"

./gradlew assembleDebug          # debug APK only (~15 s after first build)
./gradlew assembleRelease        # release APK (~5 min first time, ~1 min after)
./gradlew assembleDebug assembleRelease   # both
```

Toolchain prerequisites: JDK 17 (Temurin), Android SDK platform 34 + build-tools 34.

> The release APK is signed with the **debug keystore** so anyone can build a
> working release APK without setting up their own keystore. Replace
> `signingConfig = signingConfigs.getByName("debug")` in `app/build.gradle.kts`
> with a real release keystore before submitting to Google Play.

## 2. Install over USB (`adb`)

1. Enable **Developer options** on the phone: Settings → About phone → tap
   *Build number* seven times.
2. Inside Developer options, enable **USB debugging**.
3. Plug the phone in, accept the *"Allow USB debugging?"* prompt on the device.
4. Verify the device is visible:

   ```bash
   adb devices
   ```

5. Install (use `-r` to upgrade in place):

   ```bash
   adb install -r mobile/android/app/build/outputs/apk/debug/app-debug.apk
   # or
   adb install -r mobile/android/app/build/outputs/apk/release/app-release.apk
   ```

## 3. Install without a computer

1. Copy the `.apk` to the phone (Drive, AirDrop via Nearby, USB transfer, or
   GitHub Actions artifact download).
2. Open the file from the **Files** app.
3. Android will ask you to allow installation from your file manager — grant the
   permission, then tap **Install**.
4. If Play Protect blocks it, tap **More details → Install anyway**. Both APKs
   are signed; Play Protect just hasn't seen our package signature before.

## 4. Sign in & first launch

1. Launch **HireStack AI** (or **HireStack AI (debug)** for the debug build).
2. Use the same Supabase credentials you use on the web app — accounts and data
   are shared across web, debug APK, and release APK.
3. The session is persisted in DataStore, so you stay logged in across restarts
   until you tap **Sign out** in the *More* tab.

## 5. Where each web feature lives in the app

| Web area | Mobile location |
|----------|-----------------|
| Dashboard | Bottom tab → **Dashboard** |
| Job board, application detail, add job | Bottom tab → **Jobs** |
| Resume profiles | More → **Resume profiles** |
| ATS Scanner | More → **ATS Scanner** |
| Document library | More → **Document library** |
| Recruiter pipeline | More → **Candidates** |
| Interview Coach | More → **Interview Coach** |
| Career analytics | More → **Career analytics** |
| Daily Learning | More → **Learning** |
| Salary Coach | More → **Salary Coach** |
| A/B Doc Lab | More → **Doc Variants** |
| Knowledge library | More → **Knowledge library** |

Generation flows that mutate AI state (running an A/B doc generation, generating
salary analyses or new learning challenges) are **read-only on mobile in v1** —
trigger them from the web app, then view the results on the phone.

## 6. Uninstall / reset

```bash
adb uninstall com.hirestack.ai.debug
adb uninstall com.hirestack.ai
```

Or long-press the app icon → *App info* → **Uninstall**. DataStore and the
Supabase session are wiped together with the install.

## 7. Troubleshooting

- **"App not installed" on a phone that already has another HireStack build** —
  uninstall the older build first; debug and release have different package
  IDs (`.debug` suffix), so both can co-exist, but two release APKs signed
  with different keystores cannot.
- **401 / "Not authenticated" right after sign-in** — pull down to refresh on
  the failing screen. The Supabase token is refreshed lazily on the next
  request.
- **Empty Candidates / "Create an organization"** — the recruiter pipeline
  requires you to belong to an org. Create one from the web app.
- **Build fails on first run with `Unresolved reference`** — make sure JDK 17 is
  active (`java -version`) and you're using the wrapper (`./gradlew`), not a
  global Gradle install.
