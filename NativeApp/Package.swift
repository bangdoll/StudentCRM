// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "StudentCRMNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "StudentCRMNative",
            targets: ["StudentCRMNative"]
        )
    ],
    targets: [
        .executableTarget(
            name: "StudentCRMNative",
            resources: [
                .process("Assets.xcassets")
            ],
            linkerSettings: [
                .linkedLibrary("sqlite3")
            ]
        )
    ]
)
