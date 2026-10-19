// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "tune-button"
include(":app")
