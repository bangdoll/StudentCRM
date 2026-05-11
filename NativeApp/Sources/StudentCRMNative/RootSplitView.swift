import SwiftUI

struct RootSplitView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        NavigationSplitView {
            List(SidebarSection.allCases, selection: $store.selectedSection) { section in
                Label(section.title, systemImage: icon(for: section))
                    .tag(section)
            }
            .navigationTitle("StudentCRM")
            .listStyle(.sidebar)
        } detail: {
            switch store.selectedSection ?? .dashboard {
            case .dashboard:
                StudentsOverviewView()
            case .appleCEO:
                AppleCEOProgramView()
            }
        }
    }

    private func icon(for section: SidebarSection) -> String {
        switch section {
        case .dashboard: return "person.3.fill"
        case .appleCEO: return "apple.logo"
        }
    }
}
