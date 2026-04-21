# HireStack AI — Mobile Apps

Native mobile clients for HireStack AI.

- **`android/`** — Kotlin + Jetpack Compose + Hilt (this folder)
- **`ios/`** — Swift + SwiftUI (added after Android v1 ships)

Both apps reuse the production Railway backend
(`https://hirestack-ai-production.up.railway.app/api/*`)
and Supabase auth (`https://dkfmcnfhvbqwsgpkgoag.supabase.co`).

## Tier roadmap

| Tier | Scope | Status |
|------|-------|--------|
| 0 | Skeleton + theme + nav + networking + Supabase auth client | ✅ shipped |
| 1 | Login + signup + session restore + logout | ✅ shipped |
| 2 | Dashboard + Job Board + Application detail | ✅ shipped |
| 3 | Resume profiles + ATS Scanner + Document Library | not started |
| 4 | Pipeline + Candidates + Interview | not started |
| 5 | Career Analytics + Learning + Salary Coach | not started |
| 6 | Nexus + Variants + Evidence Mapper + Knowledge | not started |
| 7 | Polish + signed APK | not started |

## Build (after toolchain installed)

```bash
cd mobile/android
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

Toolchain prerequisites: JDK 17, Android SDK platform 34.
