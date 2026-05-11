import SwiftUI
import Foundation

struct StudentsOverviewView: View {
    @EnvironmentObject private var store: AppStore
    @State private var selectedStudent: StudentRecord?
    @State private var isHeptabaseSettingsPresented = false

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("學員總覽")
                        .font(.largeTitle.bold())
                    Text("真正的 macOS 原生版，資料已改由 SQLite 管理。")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Heptabase 雲端設定") {
                    isHeptabaseSettingsPresented = true
                }
                .buttonStyle(.bordered)
                Button("連線 Heptabase") {
                    Task { await store.connectHeptabaseMCP() }
                }
                .buttonStyle(.bordered)
                Button("重新匯入 JSON") {
                    Task { await store.reloadFromJSON() }
                }
                .buttonStyle(.borderedProminent)
                Button("同步 API") {
                    Task { await store.reloadStudentsFromAPI() }
                }
                .buttonStyle(.bordered)
            }

            HStack(spacing: 16) {
                StatCard(title: "全部學員", value: "\(store.oneOnOneSummary.totalStudents)", note: store.importStatus)
                StatCard(title: "待上課學員", value: "\(store.oneOnOneSummary.pendingLessonsCount) 位", note: store.oneOnOneSummary.pendingLessonNames.isEmpty ? "今明兩天尚無預約" : store.oneOnOneSummary.pendingLessonNames.joined(separator: "、"))
                StatCard(title: "尚未排課", value: "\(store.oneOnOneSummary.noNextLessonCount) 位", note: store.oneOnOneSummary.noNextLessonNames.isEmpty ? "所有學員皆已排課" : store.oneOnOneSummary.noNextLessonNames.joined(separator: "、"))
                StatCard(title: "Heptabase", value: store.heptabaseConnectionStatus, note: store.heptabaseStatusDetail)
            }

            HStack(spacing: 16) {
                StatCard(title: "穩定留存", value: "\(store.oneOnOneSummary.stableCount) 位", note: "狀態為 🟢 的學員")
                StatCard(title: "冰凍期", value: "\(store.oneOnOneSummary.freezingCount) 位", note: "狀態為 🧊 的學員")
                StatCard(title: "高流失風險", value: "\(store.oneOnOneSummary.riskCount) 位", note: "狀態為 🔴 的學員")
                StatCard(title: "資料來源", value: store.sourceDirectory.isEmpty ? "尚未解析" : "正式資料", note: store.studentAPISyncStatus == "API 尚未同步" ? store.sourceDirectory : store.studentAPISyncStatus)
            }

            ScrollView {
                LazyVGrid(
                    columns: [
                        GridItem(.adaptive(minimum: 320, maximum: 400), spacing: 20)
                    ],
                    spacing: 20
                ) {
                    ForEach(store.students) { student in
                        StudentCardView(
                            student: student,
                            prediction: store.studentPredictions[student.id],
                            lastLessonDateProp: store.lastLessons[student.id] ?? "TBD",
                            onSelect: { selectedStudent = student }
                        )
                    }
                }
                .padding(.top, 8)
            }
        }
        .padding(24)
        .sheet(item: $selectedStudent) { student in
            StudentTeachingRecordSheet(
                student: student,
                projectRootPath: inferredProjectRootPath
            )
        }
        .sheet(isPresented: $isHeptabaseSettingsPresented) {
            HeptabaseSettingsSheet()
                .environmentObject(store)
        }
    }

    private var inferredProjectRootPath: String {
        guard !store.sourceDirectory.isEmpty else { return FileManager.default.currentDirectoryPath }
        let url = URL(fileURLWithPath: store.sourceDirectory)
        return url.deletingLastPathComponent().deletingLastPathComponent().path
    }
}

private struct HeptabaseSettingsSheet: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var endpoint: String = ""
    @State private var bearerToken: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Heptabase 雲端連線設定")
                        .font(.title2.bold())
                    Text("StudentCRM 採用官方 MCP Endpoint 雲端抓取。\n跨設備通用，不依賴本地桌面版 App。")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("關閉") { dismiss() }
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("官方 MCP Endpoint")
                    .font(.headline)
                TextField("https://api.heptabase.com/mcp", text: $endpoint)
                    .textFieldStyle(.roundedBorder)
                    .textSelection(.enabled)
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("官方 Bearer Token")
                    .font(.headline)
                SecureField("貼上 Heptabase MCP Bearer Token", text: $bearerToken)
                    .textFieldStyle(.roundedBorder)
                Text(tokenStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("目前狀態")
                    .font(.headline)
                Text(store.heptabaseConnectionStatus)
                    .font(.body.bold())
                if !store.latestActionMessage.isEmpty {
                    Text(store.latestActionMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(14)
            .background(Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 14))

            HStack {
                Button("清除 Token") {
                    bearerToken = ""
                    store.heptabaseBearerToken = ""
                    store.clearHeptabaseToken()
                }
                .buttonStyle(.bordered)

                Spacer()

                Button("儲存") {
                    store.heptabaseEndpoint = endpoint
                    store.heptabaseBearerToken = bearerToken
                    store.saveHeptabaseSettings()
                }
                .buttonStyle(.bordered)

                Button("儲存並測試") {
                    store.heptabaseEndpoint = endpoint
                    store.heptabaseBearerToken = bearerToken
                    store.saveHeptabaseSettings()
                    Task { await store.connectHeptabaseMCP() }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 720)
        .task {
            endpoint = store.heptabaseEndpoint
            bearerToken = store.heptabaseBearerToken
        }
    }

    private var tokenStatus: String {
        let trimmed = bearerToken.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "目前尚未設定 Token"
        }
        let suffix = String(trimmed.suffix(min(6, trimmed.count)))
        return "目前已貼入 Token，尾碼：\(suffix)"
    }
}

private struct PredictionBadge: View {
    let prediction: StudentPrediction

    var body: some View {
        Text("\(prediction.badge) \(prediction.status)")
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(backgroundColor)
            .overlay {
                Capsule()
                    .stroke(borderColor, lineWidth: 1)
            }
            .clipShape(Capsule())
            .help(prediction.reason)
    }

    private var backgroundColor: Color {
        switch prediction.style {
        case .full:
            return Color.green.opacity(0.15)
        case .short:
            return Color.orange.opacity(0.15)
        case .placeholder:
            return Color.gray.opacity(0.14)
        case .missing:
            return Color.red.opacity(0.14)
        }
    }

    private var borderColor: Color {
        switch prediction.style {
        case .full:
            return Color.green.opacity(0.45)
        case .short:
            return Color.orange.opacity(0.45)
        case .placeholder:
            return Color.gray.opacity(0.35)
        case .missing:
            return Color.red.opacity(0.45)
        }
    }
}

private struct StudentCardView: View {
    let student: StudentRecord
    let prediction: StudentPrediction?
    let lastLessonDateProp: String
    let onSelect: () -> Void

    @State private var isBreathing = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                Text(student.name)
                    .font(.title2.bold())
                Spacer()
                if let prediction {
                    PredictionBadge(prediction: prediction)
                }
            }

            // Progress Section
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("本輪進度：\(student.lessonsCount % 8) / 8")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.secondary.opacity(0.15))
                            .frame(height: 6)

                        Capsule()
                            .fill(
                                LinearGradient(
                                    gradient: Gradient(colors: [Color.blue, Color.green]),
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: geo.size.width * CGFloat(Double(student.lessonsCount % 8) / 8.0), height: 6)
                    }
                }
                .frame(height: 6)
            }

            // Timeline Section
            VStack(alignment: .leading, spacing: 8) {
                Label("最後上課：\(lastLessonDate)", systemImage: "clock.arrow.circlepath")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                HStack {
                    Image(systemName: "calendar")
                    Text("下次上課：\(student.nextLesson.isEmpty ? "未安排" : student.nextLesson)")
                }
                .font(.headline)
                .foregroundStyle(isToday ? .green : (isNearTerm ? .blue : .primary))
            }

            HStack {
                Label("累計總堂數：\(student.lessonsCount)", systemImage: "number")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Action & Tags
            HStack {
                ForEach(student.tags.prefix(2), id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(isToday ? Color.green.opacity(0.1) : Color.blue.opacity(0.1))
                        .clipShape(Capsule())
                }
                Spacer()
                Button(action: onSelect) {
                    Text("查看紀錄")
                        .font(.caption.bold())
                        .foregroundStyle(isToday ? .green : .blue)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(20)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(
                    isToday ? Color.green.opacity(isBreathing ? 0.8 : 0.3) :
                    (isNearTerm ? Color.blue.opacity(isBreathing ? 0.6 : 0.2) : Color.gray.opacity(0.15)),
                    lineWidth: (isToday || isNearTerm) ? 2 : 1
                )
        )
        .shadow(color: Color.black.opacity(0.05), radius: 10, x: 0, y: 5)
        .onAppear {
            if isToday || isNearTerm {
                withAnimation(Animation.easeInOut(duration: 2.0).repeatForever(autoreverses: true)) {
                    isBreathing = true
                }
            }
        }
    }

    private var lastLessonDate: String {
        lastLessonDateProp
    }

    private var isToday: Bool {
        student.nextLesson.contains(formatDate(Date()))
    }

    private var isNearTerm: Bool {
        let tomorrow = formatDate(Calendar.current.date(byAdding: .day, value: 1, to: Date())!)
        let today = formatDate(Date())
        return student.nextLesson.contains(tomorrow) && !student.nextLesson.contains(today)
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}

private struct StatCard: View {
    let title: String
    let value: String
    let note: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title.bold())
            Text(note)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private struct StudentTeachingRecordSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var selectedTab: RecordTab = .studentFile
    @State private var recordBundle = StudentTeachingRecordBundle.empty
    @State private var isLoading = true
    @State private var loadErrorMessage = ""
    @State private var isDiagnosticsExpanded = true

    let student: StudentRecord
    let projectRootPath: String

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(student.name)
                        .font(.title.bold())
                    Text("完整教學紀錄")
                        .foregroundStyle(.secondary)
                    HStack(spacing: 12) {
                        Label("累計堂數 \(student.lessonsCount)", systemImage: "number.circle")
                        Label(student.nextLesson.isEmpty ? "未安排下次上課" : student.nextLesson, systemImage: "calendar")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                }
                Spacer()
                Button("關閉") { dismiss() }
            }

            Picker("內容區", selection: $selectedTab) {
                ForEach(RecordTab.allCases) { tab in
                    Text(tab.title).tag(tab)
                }
            }
            .pickerStyle(.segmented)

            Group {
                switch selectedTab {
                case .studentFile:
                    VStack(alignment: .leading, spacing: 10) {
                        Text("學員主檔")
                            .font(.headline)
                        Text(recordBundle.studentFilePath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        StudentProfileOverviewView(
                            student: student,
                            content: recordBundle.studentDocument
                        )
                    }
                case .lessonRecords:
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("完整教學紀錄")
                                .font(.headline)
                            Text("共 \(recordBundle.lessonRecords.count) 筆")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            if !sanitizedLoadErrorMessage.isEmpty {
                                Text(sanitizedLoadErrorMessage)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 10)
                                    .background(Color(nsColor: .controlBackgroundColor))
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                            }

                            if recordBundle.diagnostics.hasContent {
                                DisclosureGroup(
                                    isExpanded: $isDiagnosticsExpanded,
                                    content: {
                                        TeachingRecordDiagnosticsView(
                                            diagnostics: recordBundle.diagnostics
                                        )
                                        .padding(.top, 10)
                                    },
                                    label: {
                                        VStack(alignment: .leading, spacing: 6) {
                                            Text("\(student.name) 查詢診斷")
                                                .font(.headline)
                                            Text(recordBundle.diagnostics.source.isEmpty ? "尚未取得診斷來源" : recordBundle.diagnostics.source)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                )
                                .padding(14)
                                .background(Color(nsColor: .controlBackgroundColor))
                                .clipShape(RoundedRectangle(cornerRadius: 14))
                            }

                            if isLoading {
                                ProgressView("正在透過 Heptabase 抓取教學紀錄…")
                                    .padding(.top, 8)
                            } else if recordBundle.lessonRecords.isEmpty {
                                Text("目前找不到這位學員的 lesson 紀錄。")
                                    .foregroundStyle(.secondary)
                            } else {
                                ForEach(recordBundle.lessonRecords) { lesson in
                                    DisclosureGroup {
                                        VStack(alignment: .leading, spacing: 10) {
                                            Text(lesson.path)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                            MarkdownContentView(
                                                content: lesson.content,
                                                emptyMessage: "這筆 lesson 沒有內容。"
                                            )
                                        }
                                        .padding(.top, 10)
                                    } label: {
                                        VStack(alignment: .leading, spacing: 6) {
                                            HStack {
                                                Text(lesson.date)
                                                    .font(.headline)
                                                Spacer()
                                                Text(lesson.title)
                                                    .foregroundStyle(.secondary)
                                            }
                                            if !lesson.preview.isEmpty {
                                                Text(lesson.preview)
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                                    .lineLimit(2)
                                            }
                                        }
                                    }
                                    .padding(14)
                                    .background(Color(nsColor: .windowBackgroundColor))
                                    .clipShape(RoundedRectangle(cornerRadius: 14))
                                }
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .padding(24)
        .frame(minWidth: 1100, minHeight: 820)
        .task(id: student.id) {
            await loadBundle()
        }
    }

    private var sanitizedLoadErrorMessage: String {
        let normalized = loadErrorMessage.lowercased()
        if normalized.contains("executable not found in $path") || normalized.contains("\"npx\"") {
            return "Heptabase CLI 在目前環境不可用，已改用本地教學檔案補齊。"
        }
        return loadErrorMessage
    }

    private func loadBundle() async {
        isLoading = true
        loadErrorMessage = ""

        let bundle = await Task.detached(priority: .userInitiated) {
            Self.loadBundle(for: student, projectRootPath: projectRootPath)
        }.value

        recordBundle = bundle
        loadErrorMessage = bundle.loadErrorMessage
        isLoading = false
    }

    nonisolated private static func loadBundle(for student: StudentRecord, projectRootPath: String) -> StudentTeachingRecordBundle {
        let studentFilePath = URL(fileURLWithPath: projectRootPath)
            .appendingPathComponent(student.file.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
            .path

        let studentDocument = (try? String(contentsOfFile: studentFilePath, encoding: .utf8)) ?? ""
        let fetchResult = CompositeTeachingRecordProvider().fetchLessonRecords(
            for: student,
            projectRootPath: projectRootPath
        )
        return StudentTeachingRecordBundle(
            studentFilePath: studentFilePath,
            studentDocument: studentDocument,
            lessonRecords: fetchResult.lessonRecords,
            loadErrorMessage: fetchResult.message,
            diagnostics: fetchResult.diagnostics
        )
    }
}

private enum RecordTab: String, CaseIterable, Identifiable {
    case studentFile
    case lessonRecords

    var id: String { rawValue }

    var title: String {
        switch self {
        case .studentFile:
            return "學員主檔"
        case .lessonRecords:
            return "教學紀錄"
        }
    }
}

private struct StudentTeachingRecordBundle {
    let studentFilePath: String
    let studentDocument: String
    let lessonRecords: [LessonRecord]
    let loadErrorMessage: String
    let diagnostics: TeachingRecordDiagnostics

    static let empty = StudentTeachingRecordBundle(
        studentFilePath: "",
        studentDocument: "",
        lessonRecords: [],
        loadErrorMessage: "",
        diagnostics: .empty
    )
}

private extension TeachingRecordDiagnostics {
    var hasContent: Bool {
        !source.isEmpty ||
        !queries.isEmpty ||
        !matchedItems.isEmpty ||
        !fallbackPaths.isEmpty ||
        !notes.isEmpty
    }
}

private struct TeachingRecordDiagnosticsView: View {
    let diagnostics: TeachingRecordDiagnostics

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            diagnosticsSection("採用來源", items: diagnostics.source.isEmpty ? [] : [diagnostics.source])
            diagnosticsSection("查詢字串", items: diagnostics.queries)
            diagnosticsSection("命中項目", items: diagnostics.matchedItems)
            diagnosticsSection("Fallback 路徑", items: diagnostics.fallbackPaths)
            diagnosticsSection("備註", items: diagnostics.notes)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func diagnosticsSection(_ title: String, items: [String]) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                ForEach(items, id: \.self) { item in
                    Text(item)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }
}

private struct StudentProfileOverviewView: View {
    let student: StudentRecord
    let content: String
    @State private var selectedSection: StudentProfileSection = .summary

    private var parsed: StudentProfileDocument {
        StudentProfileParser.parse(content: content, student: student)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(availableSections) { section in
                    Button {
                        selectedSection = section
                    } label: {
                        HStack {
                            Image(systemName: section.icon)
                            Text(section.title)
                            Spacer()
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(selectedSection == section ? Color.accentColor.opacity(0.18) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(width: 180, alignment: .topLeading)

            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 16) {
                    switch selectedSection {
                    case .summary:
                        LazyVGrid(
                            columns: [
                                GridItem(.flexible(minimum: 220), spacing: 12),
                                GridItem(.flexible(minimum: 220), spacing: 12)
                            ],
                            alignment: .leading,
                            spacing: 12
                        ) {
                            SummaryFieldCard(title: "姓名", value: parsed.displayName)
                            SummaryFieldCard(title: "常用代號", value: parsed.aliasLabel)
                            SummaryFieldCard(title: "累積堂數", value: "\(parsed.lessonCount)")
                            SummaryFieldCard(title: "下次上課", value: parsed.nextLessonLabel)
                            SummaryFieldCard(title: "首次上課", value: parsed.firstLessonDate)
                            SummaryFieldCard(title: "最後上課", value: parsed.lastLessonDate)
                        }
                    case .hardware:
                        profileSectionCard(title: "硬體設備") {
                            ForEach(parsed.hardwareItems, id: \.self) { item in
                                Label(item, systemImage: "desktopcomputer")
                                    .labelStyle(.titleOnly)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.vertical, 4)
                            }
                        }
                    case .notes:
                        profileSectionCard(title: "重點摘要") {
                            ForEach(parsed.keyNotes, id: \.self) { note in
                                HStack(alignment: .top, spacing: 8) {
                                    Text("•")
                                    Text(note)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        }
                    case .fullDocument:
                        profileSectionCard(title: "完整主檔") {
                            MarkdownContentView(
                                content: content,
                                emptyMessage: "找不到學員主檔內容。"
                            )
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(16)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var availableSections: [StudentProfileSection] {
        var sections: [StudentProfileSection] = [.summary]
        if !parsed.hardwareItems.isEmpty { sections.append(.hardware) }
        if !parsed.keyNotes.isEmpty { sections.append(.notes) }
        sections.append(.fullDocument)
        return sections
    }

    @ViewBuilder
    private func profileSectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            content()
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private enum StudentProfileSection: String, CaseIterable, Identifiable {
    case summary
    case hardware
    case notes
    case fullDocument

    var id: String { rawValue }

    var title: String {
        switch self {
        case .summary: return "摘要"
        case .hardware: return "硬體設備"
        case .notes: return "重點摘要"
        case .fullDocument: return "完整主檔"
        }
    }

    var icon: String {
        switch self {
        case .summary: return "rectangle.grid.2x2"
        case .hardware: return "desktopcomputer"
        case .notes: return "text.alignleft"
        case .fullDocument: return "doc.text"
        }
    }
}

private struct SummaryFieldCard: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value.isEmpty ? "未提供" : value)
                .font(.headline)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

private struct StudentProfileDocument {
    let displayName: String
    let aliasLabel: String
    let lessonCount: Int
    let nextLessonLabel: String
    let firstLessonDate: String
    let lastLessonDate: String
    let hardwareItems: [String]
    let keyNotes: [String]
}

private enum StudentProfileParser {
    static func parse(content: String, student: StudentRecord) -> StudentProfileDocument {
        let frontmatter = parseFrontmatter(from: content)
        let body = stripFrontmatter(from: content)
        let bulletLines = parseBulletLines(from: body)

        let displayName = frontmatter["name"] ?? student.name
        let aliases = parseList(from: frontmatter["aliases"])
        let hardwareItems = parseList(from: frontmatter["hardware"]).ifEmpty(
            fallback: bulletLines.filter { $0.contains("設備") || $0.contains("iPhone") || $0.contains("MacBook") || $0.contains("iPad") }
        )

        let keyNotes = bulletLines
            .filter {
                !$0.contains("姓名") &&
                !$0.contains("常用代號") &&
                !$0.contains("上課地點") &&
                !$0.contains("設備")
            }
            .prefix(6)
            .map { $0 }

        return StudentProfileDocument(
            displayName: displayName,
            aliasLabel: aliases.isEmpty ? student.aliases.joined(separator: "、") : aliases.joined(separator: "、"),
            lessonCount: lessonCount(from: frontmatter["lessons_count"], fallback: student.lessonsCount),
            nextLessonLabel: student.nextLesson.isEmpty ? "未安排" : student.nextLesson,
            firstLessonDate: frontmatter["first_lesson_date"] ?? "未提供",
            lastLessonDate: frontmatter["last_lesson_date"] ?? "未提供",
            hardwareItems: hardwareItems,
            keyNotes: keyNotes
        )
    }

    private static func parseFrontmatter(from content: String) -> [String: String] {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        guard normalized.hasPrefix("---\n") else { return [:] }
        let parts = normalized.components(separatedBy: "\n---\n")
        guard let first = parts.first else { return [:] }
        let lines = first.components(separatedBy: "\n").dropFirst()
        var result: [String: String] = [:]
        for line in lines {
            guard let separator = line.firstIndex(of: ":") else { continue }
            let key = String(line[..<separator]).trimmingCharacters(in: .whitespacesAndNewlines)
            let value = String(line[line.index(after: separator)...]).trimmingCharacters(in: .whitespacesAndNewlines)
            if !key.isEmpty {
                result[key] = value
            }
        }
        return result
    }

    private static func stripFrontmatter(from content: String) -> String {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        guard normalized.hasPrefix("---\n") else { return normalized }
        let parts = normalized.components(separatedBy: "\n---\n")
        guard parts.count >= 2 else { return normalized }
        return parts.dropFirst().joined(separator: "\n---\n")
    }

    private static func parseBulletLines(from content: String) -> [String] {
        content
            .components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.hasPrefix("* ") || $0.hasPrefix("- ") }
            .map { String($0.dropFirst(2)).replacingOccurrences(of: "**", with: "") }
    }

    private static func parseList(from raw: String?) -> [String] {
        guard var raw else { return [] }
        raw = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return [] }

        if raw.hasPrefix("[") && raw.hasSuffix("]") {
            raw.removeFirst()
            raw.removeLast()
        }

        return raw
            .components(separatedBy: "\",")
            .map {
                $0.replacingOccurrences(of: "\"", with: "")
                    .trimmingCharacters(in: CharacterSet(charactersIn: " []"))
            }
            .filter { !$0.isEmpty }
    }

    private static func lessonCount(from raw: String?, fallback: Int) -> Int {
        guard let raw, let count = Int(raw.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            return fallback
        }
        return count
    }
}

private struct MarkdownContentView: View {
    let content: String
    let emptyMessage: String

    var body: some View {
        if renderedLines.isEmpty {
            Text(cleanedContent.isEmpty ? emptyMessage : cleanedContent)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(renderedLines) { line in
                    lineView(line)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func lineView(_ line: MarkdownLine) -> some View {
        switch line.kind {
        case .heading1:
            Text(line.text)
                .font(.title2.bold())
                .padding(.top, 4)
                .textSelection(.enabled)
        case .heading2:
            Text(line.text)
                .font(.title3.bold())
                .padding(.top, 2)
                .textSelection(.enabled)
        case .heading3:
            Text(line.text)
                .font(.headline)
                .textSelection(.enabled)
        case .bullet:
            HStack(alignment: .top, spacing: 8) {
                Text("•")
                    .padding(.leading, CGFloat(line.indentLevel) * 18)
                Text(formattedInlineText(line.text))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        case .blockquote:
            Text(line.text)
                .foregroundStyle(.secondary)
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.35))
                        .frame(width: 3)
                }
                .textSelection(.enabled)
        case .paragraph:
            Text(formattedInlineText(line.text))
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        case .rule:
            Divider()
                .padding(.vertical, 4)
        case .spacer:
            Spacer()
                .frame(height: 4)
        }
    }

    private var cleanedContent: String {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        guard normalized.hasPrefix("---\n") else { return normalized.trimmingCharacters(in: .whitespacesAndNewlines) }

        let pieces = normalized.components(separatedBy: "\n---\n")
        guard pieces.count >= 2 else { return normalized.trimmingCharacters(in: .whitespacesAndNewlines) }
        return pieces.dropFirst().joined(separator: "\n---\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var renderedLines: [MarkdownLine] {
        cleanedContent
            .components(separatedBy: "\n")
            .map { rawLine in
                let leadingSpaces = rawLine.prefix { $0 == " " }.count
                let trimmed = rawLine.trimmingCharacters(in: .whitespaces)

                if trimmed.isEmpty {
                    return MarkdownLine(kind: .spacer, text: "")
                }
                if trimmed == "---" || trimmed == "***" {
                    return MarkdownLine(kind: .rule, text: "")
                }
                if trimmed.hasPrefix("### ") {
                    return MarkdownLine(kind: .heading3, text: String(trimmed.dropFirst(4)))
                }
                if trimmed.hasPrefix("## ") {
                    return MarkdownLine(kind: .heading2, text: String(trimmed.dropFirst(3)))
                }
                if trimmed.hasPrefix("# ") {
                    return MarkdownLine(kind: .heading1, text: String(trimmed.dropFirst(2)))
                }
                if trimmed.hasPrefix(">") {
                    let quoteText = String(trimmed.drop { $0 == ">" || $0 == " " })
                    return MarkdownLine(kind: .blockquote, text: quoteText)
                }

                let bulletPrefixes = ["* ", "- ", "*   ", "-   "]
                if let prefix = bulletPrefixes.first(where: { trimmed.hasPrefix($0) }) {
                    let text = String(trimmed.dropFirst(prefix.count))
                    return MarkdownLine(
                        kind: .bullet,
                        text: text,
                        indentLevel: max(0, leadingSpaces / 4)
                    )
                }

                return MarkdownLine(kind: .paragraph, text: trimmed)
            }
    }

    private func formattedInlineText(_ text: String) -> AttributedString {
        var attributed = AttributedString(text.replacingOccurrences(of: "**", with: ""))
        if let range = attributed.range(of: "：") {
            attributed[attributed.startIndex..<range.upperBound].font = .body.bold()
        }
        return attributed
    }
}

private extension Array {
    func ifEmpty(fallback: [Element]) -> [Element] {
        isEmpty ? fallback : self
    }
}

private struct MarkdownLine: Identifiable {
    enum Kind {
        case heading1
        case heading2
        case heading3
        case bullet
        case blockquote
        case paragraph
        case rule
        case spacer
    }

    let id = UUID()
    let kind: Kind
    let text: String
    let indentLevel: Int

    init(kind: Kind, text: String, indentLevel: Int = 0) {
        self.kind = kind
        self.text = text
        self.indentLevel = indentLevel
    }
}
