#!/usr/bin/env bash
# 用本机已缓存的 Gradle 8.13 直接构建（无需 wrapper jar）
export JAVA_HOME="D:/Dev/jdk-17"
cd "$(dirname "$0")/android" || exit 1
GRADLE="$HOME/.gradle/wrapper/dists/gradle-8.13-bin/5xuhj0ry160q40clulazy9h7d/gradle-8.13/bin/gradle.bat"
"$GRADLE" --no-daemon "$@"
