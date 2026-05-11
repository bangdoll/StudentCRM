import SwiftUI

@main
struct StudentCRMNativeApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup("StudentCRM 原生版") {
            RootSplitView()
                .environmentObject(store)
                .task {
                    await store.bootstrap()
                    await NotificationManager.shared.requestAuthorization()
                }
        }
        .defaultSize(width: 1320, height: 900)
    }
}
