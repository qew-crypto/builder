from dataclasses import dataclass
from pathlib import Path

@dataclass
class BuildPlan:
    label: str
    commands: str
    working_dir: str = "."

SKIP={".git",".gradle","build","target","node_modules"}

def candidates(root: Path, name: str):
    return sorted((p for p in root.rglob(name) if not any(x in SKIP for x in p.relative_to(root).parts[:-1])), key=lambda p: len(p.parts))

def gradle_is_android(folder: Path) -> bool:
    text=""
    for name in ("build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts"):
        p=folder/name
        if p.exists():
            try: text += p.read_text(errors="ignore")[:200000]
            except OSError: pass
    return any(x in text for x in ("com.android.application","com.android.library","android {"))

def detect_build(root: Path) -> BuildPlan:
    # Explicit build/build.sh has the highest priority.
    for name in ("build.sh","build"):
        found=candidates(root,name)
        if found:
            p=found[0]; rel=p.parent.relative_to(root).as_posix() or "."
            return BuildPlan(f"скрипт {p.name}", f"chmod +x {p.name}\nbash {p.name}", rel)
    wrappers=candidates(root,"gradlew")
    if wrappers:
        p=wrappers[0]; folder=p.parent; rel=folder.relative_to(root).as_posix() or "."
        if gradle_is_android(folder): return BuildPlan("Android Gradle", "chmod +x gradlew\n./gradlew --no-daemon assembleDebug",rel)
        return BuildPlan("Gradle JAR", "chmod +x gradlew\n./gradlew --no-daemon build",rel)
    mvnw=candidates(root,"mvnw")
    if mvnw:
        p=mvnw[0]; rel=p.parent.relative_to(root).as_posix() or "."
        return BuildPlan("Maven Wrapper","chmod +x mvnw\n./mvnw -B package",rel)
    for gradle_name in ("build.gradle.kts","build.gradle"):
        found=candidates(root,gradle_name)
        if found:
            folder=found[0].parent; rel=folder.relative_to(root).as_posix() or "."
            cmd="gradle --no-daemon assembleDebug" if gradle_is_android(folder) else "gradle --no-daemon build"
            return BuildPlan("Android Gradle без wrapper" if gradle_is_android(folder) else "Gradle без wrapper",cmd,rel)
    pom=candidates(root,"pom.xml")
    if pom:
        rel=pom[0].parent.relative_to(root).as_posix() or "."
        return BuildPlan("Maven","mvn -B package",rel)
    raise ValueError("Не найден build, build.sh, gradlew, build.gradle(.kts), mvnw или pom.xml. Используйте ручной режим.")

def workflow(plan: BuildPlan) -> str:
    script="\n".join("          "+line for line in plan.commands.splitlines())
    work=plan.working_dir.replace("'","''")
    return f'''name: Telegram build
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - uses: gradle/actions/setup-gradle@v4
        with:
          gradle-version: '8.12.1'
      - name: Build ({plan.label})
        shell: bash
        working-directory: '{work}'
        run: |
{script}
      - uses: actions/upload-artifact@v4
        with:
          name: build-result
          path: |
            **/*.jar
            **/*.apk
            !**/*-sources.jar
            !**/*-javadoc.jar
            !**/.gradle/**
          if-no-files-found: error
          retention-days: 3
'''
