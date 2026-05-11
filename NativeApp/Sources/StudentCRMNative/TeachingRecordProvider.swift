import Foundation

struct TeachingRecordDiagnostics {
    let source: String
    let queries: [String]
    let matchedItems: [String]
    let fallbackPaths: [String]
    let notes: [String]

    static let empty = TeachingRecordDiagnostics(
        source: "",
        queries: [],
        matchedItems: [],
        fallbackPaths: [],
        notes: []
    )
}

struct TeachingRecordFetchResult {
    let lessonRecords: [LessonRecord]
    let message: String
    let diagnostics: TeachingRecordDiagnostics

    static let empty = TeachingRecordFetchResult(
        lessonRecords: [],
        message: "",
        diagnostics: .empty
    )
}

protocol TeachingRecordProvider {
    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult
}

struct LocalCacheTeachingRecordProvider: TeachingRecordProvider {
    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        let cachePath = URL(fileURLWithPath: projectRootPath).appendingPathComponent("StudentCRM/cache/teaching_records.json").path
        guard FileManager.default.fileExists(atPath: cachePath),
              let data = try? Data(contentsOf: URL(fileURLWithPath: cachePath)),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let records = json["records"] as? [[String: Any]] else {
            return .empty
        }

        let candidateNames = Set(([student.name] + student.aliases).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) })

        let matched = records.filter { record in
            guard let name = record["student_name"] as? String else { return false }
            return candidateNames.contains(name)
        }

        guard !matched.isEmpty else { return .empty }

        let lessonRecords = matched.map { record in
            let id = record["card_id"] as? String ?? UUID().uuidString
            let date = record["date"] as? String ?? ""
            let title = record["title"] as? String ?? "未命名卡片"

            return LessonRecord(
                id: id,
                date: date,
                title: title,
                preview: "點擊展開以試圖抓取完整內容 (來自快取)",
                path: "Heptabase Cache",
                content: "這筆紀錄來自本地快取。由於 Heptabase MCP 目前連線異常，暫時無法自動載入內文。"
            )
        }.sorted { $0.date > $1.date }

        return TeachingRecordFetchResult(
            lessonRecords: lessonRecords,
            message: "目前資料來源：本地快取 (\(lessonRecords.count) 筆)",
            diagnostics: TeachingRecordDiagnostics(
                source: "本地快取 (teaching_records.json)",
                queries: Array(candidateNames),
                matchedItems: lessonRecords.map { $0.title },
                fallbackPaths: [cachePath],
                notes: ["從本地快取成功讀取 \(lessonRecords.count) 筆紀錄"]
            )
        )
    }
}

struct CompositeTeachingRecordProvider: TeachingRecordProvider {
    private let providers: [TeachingRecordProvider]

    init(providers: [TeachingRecordProvider] = [
        LocalCacheTeachingRecordProvider(),
        HeptabaseLocalExportProvider(),
        LocalTeachingFileProvider(),
        HeptabaseMCPProvider()
    ]) {
        self.providers = providers
    }

    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        var messages: [String] = []

        for provider in providers {
            let result = provider.fetchLessonRecords(for: student, projectRootPath: projectRootPath)
            if !result.lessonRecords.isEmpty {
                let mergedMessage = deduplicatedMessages(
                    messages + [result.message]
                ).joined(separator: "\n")
                return TeachingRecordFetchResult(
                    lessonRecords: result.lessonRecords,
                    message: mergedMessage,
                    diagnostics: result.diagnostics
                )
            }
            if !result.message.isEmpty {
                messages.append(result.message)
            }
        }

        return TeachingRecordFetchResult(
            lessonRecords: [],
            message: deduplicatedMessages(messages).joined(separator: "\n"),
            diagnostics: TeachingRecordDiagnostics(
                source: "無可用資料來源",
                queries: [],
                matchedItems: [],
                fallbackPaths: [],
                notes: deduplicatedMessages(messages)
            )
        )
    }

    private func deduplicatedMessages(_ messages: [String]) -> [String] {
        var seen = Set<String>()
        return messages
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .filter { message in
                guard !seen.contains(message) else { return false }
                seen.insert(message)
                return true
            }
    }
}

struct HeptabaseMCPProvider: TeachingRecordProvider {
    private let endpoint: URL?
    private let bearerToken: String
    private let titleSuffix = "數位管理教學"
    private let bridge = HeptabaseMCPBridge()

    init(
        endpoint: URL? = HeptabaseMCPConfiguration.resolveEndpoint(),
        bearerToken: String = HeptabaseMCPConfiguration.resolveBearerToken()
    ) {
        self.endpoint = endpoint
        self.bearerToken = bearerToken
    }

    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        guard let endpoint else {
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "Heptabase MCP 端點格式無效，已改用其他資料來源。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "Heptabase MCP",
                    queries: [],
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: ["MCP 端點格式無效"]
                )
            )
        }

        if bearerToken.isEmpty {
            if let bridgeResult = fetchViaBridge(for: student, projectRootPath: projectRootPath) {
                return bridgeResult
            }

            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "尚未設定 Heptabase MCP Bearer Token，已改用其他資料來源。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "Heptabase MCP",
                    queries: [],
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: ["缺少 Bearer Token"]
                )
            )
        }

        let candidateNames = Array(
            Set(([student.name] + student.aliases)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty })
        )
        let candidateDates = candidateLessonDates(for: student, projectRootPath: projectRootPath)

        let client = HeptabaseMCPClient(endpoint: endpoint, bearerToken: bearerToken)
        var matchedCards: [String: (title: String, type: String)] = [:]
        var candidateCards: [String: (title: String, type: String)] = [:]
        var diagnostics: [String] = []
        let executedQueries = buildHeptabaseQueries(candidateNames: candidateNames, candidateDates: candidateDates)

        if let toolNames = try? client.listToolNames() {
            diagnostics.append("MCP tools: \(toolNames.joined(separator: ", "))")
        }

        for query in executedQueries {
            guard let results = try? client.semanticSearchObjects(query: query) else {
                continue
            }

            for result in results {
                candidateCards[result.id] = (title: result.title, type: result.type)
            }
        }

        diagnostics.append("候選卡片數：\(candidateCards.count)")

        for (cardID, info) in candidateCards {
            let titleScore = scoreHeptabaseTitle(
                info.title,
                candidateNames: candidateNames,
                candidateDates: candidateDates
            )
            let title = info.title
            let type = info.type

            if titleScore >= 7 {
                matchedCards[cardID] = (title: title, type: type)
                continue
            }

            guard let content = try? client.getObjectMarkdown(objectID: cardID, objectType: "card") else {
                continue
            }

            let cleanedContent = cleanHeptabaseTransportContent(content)
            let contentScore = scoreHeptabaseContent(cleanedContent, candidateNames: candidateNames)
            if titleScore + contentScore >= 8 {
                matchedCards[cardID] = (title: title, type: type)
            }
        }

        guard !matchedCards.isEmpty else {
            let detail = diagnostics.isEmpty ? "" : "\n" + diagnostics.joined(separator: "\n")
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "Heptabase MCP 沒有找到符合這位學員的教學卡片。\(detail)",
                diagnostics: TeachingRecordDiagnostics(
                    source: "Heptabase MCP",
                    queries: executedQueries,
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: deduplicatedStrings(diagnostics + ["沒有命中教學卡片", "候選卡片：\(candidateCards.values.map { $0.title }.sorted(by: >).joined(separator: " | "))"])
                )
            )
        }

        var lessonRecords: [LessonRecord] = []

        for (cardID, info) in matchedCards {
            let title = info.title
            let type = info.type
            guard let content = try? client.getObjectMarkdown(objectID: cardID, objectType: type) else {
                continue
            }

            if type == "journal" {
                let localCandidateNames = Array(Set(([student.name] + student.aliases)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }))

                guard let extracted = extractFallbackLesson(
                    from: content,
                    fileURL: URL(fileURLWithPath: "heptabase://journal/\(cardID)"),
                    candidateNames: localCandidateNames,
                    isDedicatedFile: false
                ) else { continue }

                lessonRecords.append(
                    LessonRecord(
                        id: cardID,
                        date: extracted.date,
                        title: extracted.title,
                        preview: extracted.preview,
                        path: "Heptabase MCP Journal",
                        content: extracted.content
                    )
                )
            } else {
                let cleanedContent = cleanHeptabaseTransportContent(content)
                let preview = cleanedContent
                    .components(separatedBy: .newlines)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .first(where: { !$0.isEmpty && !$0.hasPrefix("#") }) ?? ""

                lessonRecords.append(
                    LessonRecord(
                        id: cardID,
                        date: extractDate(from: title),
                        title: title,
                        preview: preview,
                        path: "Heptabase MCP Card: \(cardID)",
                        content: cleanedContent
                    )
                )
            }
        }

        lessonRecords.sort { lhs, rhs in
            if lhs.date == rhs.date { return lhs.title > rhs.title }
            return lhs.date > rhs.date
        }

        return TeachingRecordFetchResult(
            lessonRecords: lessonRecords,
            message: lessonRecords.isEmpty
                ? "Heptabase MCP 有命中卡片，但無法讀取完整內容。"
                : "目前資料來源：Heptabase MCP",
            diagnostics: TeachingRecordDiagnostics(
                source: "Heptabase MCP bridge",
                queries: executedQueries,
                matchedItems: matchedCards.map { "\($0.value.title) [\($0.key)]" }.sorted(by: >),
                fallbackPaths: [],
                notes: deduplicatedStrings(diagnostics)
            )
        )
    }

    private func fetchViaBridge(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult? {
        guard bridge.isAvailable else {
            return nil
        }

        let candidateNames = Array(
            Set(([student.name] + student.aliases)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty })
        )
        let candidateDates = candidateLessonDates(for: student, projectRootPath: projectRootPath)
        var matchedCards: [String: (title: String, type: String)] = [:]
        var executedQueries: [String] = []

        if !candidateDates.isEmpty {
            for date in candidateDates {
                let dateClean = date.replacingOccurrences(of: "-", with: "")
                for candidate in candidateNames {
                    let query = "#\(dateClean) \(candidate) \(titleSuffix)"
                    executedQueries.append(query)
                    guard let results = try? bridge.search(query: query, projectRootPath: projectRootPath) else {
                        continue
                    }

                    for result in results {
                        let normalizedTitle = normalize(result.title)
                        if result.type == "card" {
                            guard normalizedTitle.contains(normalize(titleSuffix)),
                                  normalizedTitle.contains(dateClean),
                                  candidateNames.contains(where: { normalizedTitle.contains(normalize($0)) })
                            else { continue }
                        } else if result.type == "journal" {
                            guard normalizedTitle.contains(dateClean) else { continue }
                        }
                        matchedCards[result.id] = (title: result.title, type: result.type)
                    }
                }
            }
        }

        if matchedCards.isEmpty {
            for candidate in candidateNames {
                let queryVariants = [
                    candidate,
                    "\(candidate) \(titleSuffix)",
                    "\(candidate) 數位管理",
                    "\(candidate.replacingOccurrences(of: " ", with: ""))",
                    "\(candidate.replacingOccurrences(of: " ", with: ""))\(titleSuffix)"
                ]

                for query in queryVariants {
                    executedQueries.append(query)
                    guard let results = try? bridge.search(query: query, projectRootPath: projectRootPath) else {
                        continue
                    }

                    for result in results {
                        let normalizedTitle = normalize(result.title)
                        if result.type == "card" {
                            guard normalizedTitle.contains(normalize(titleSuffix)),
                                  candidateNames.contains(where: { normalizedTitle.contains(normalize($0)) })
                            else { continue }
                        }
                        matchedCards[result.id] = (title: result.title, type: result.type)
                    }
                }
            }
        }

        guard !matchedCards.isEmpty else {
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "Heptabase MCP OAuth 已啟用，但沒有找到符合這位學員的教學卡片。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "Heptabase MCP OAuth",
                    queries: deduplicatedStrings(executedQueries),
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: ["OAuth 已啟用，但沒有命中卡片"]
                )
            )
        }

        var lessonRecords: [LessonRecord] = []
        for (cardID, info) in matchedCards {
            guard let content = try? bridge.getObjectMarkdown(
                objectID: cardID,
                objectType: info.type,
                projectRootPath: projectRootPath
            ) else {
                continue
            }
            if info.type == "journal" {
                let localCandidateNames = Array(Set(([student.name] + student.aliases)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }))

                if let extracted = extractFallbackLesson(
                    from: content,
                    fileURL: URL(fileURLWithPath: "heptabase://journal/\(cardID)"),
                    candidateNames: localCandidateNames,
                    isDedicatedFile: false
                ) {
                    lessonRecords.append(
                        LessonRecord(
                            id: cardID,
                            date: extracted.date,
                            title: extracted.title,
                            preview: extracted.preview,
                            path: "Heptabase Journal (OAuth)",
                            content: extracted.content
                        )
                    )
                }
            } else {
                let cleanedContent = cleanHeptabaseTransportContent(content)
                lessonRecords.append(
                    LessonRecord(
                        id: cardID,
                        date: extractDate(from: info.title),
                        title: info.title,
                        preview: firstMeaningfulPreviewLine(from: cleanedContent),
                        path: "Heptabase Card (OAuth): \(cardID)",
                        content: cleanedContent
                    )
                )
            }
        }

        lessonRecords.sort { lhs, rhs in
            if lhs.date == rhs.date { return lhs.title > rhs.title }
            return lhs.date > rhs.date
        }

        return TeachingRecordFetchResult(
            lessonRecords: lessonRecords,
            message: lessonRecords.isEmpty
                ? "Heptabase MCP OAuth 已命中卡片，但讀取內容失敗。"
                : "目前資料來源：Heptabase MCP OAuth",
            diagnostics: TeachingRecordDiagnostics(
                source: "Heptabase MCP OAuth",
                queries: deduplicatedStrings(executedQueries),
                matchedItems: matchedCards.map { "\($0.value.title) [\($0.key)]" }.sorted(by: >),
                fallbackPaths: [],
                notes: []
            )
        )
    }

    private func candidateLessonDates(for student: StudentRecord, projectRootPath: String) -> [String] {
        let teachingDirectory = URL(fileURLWithPath: projectRootPath).appendingPathComponent("01.Docs/teaching")
        guard let enumerator = FileManager.default.enumerator(
            at: teachingDirectory,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        let candidateNames = ([student.name] + student.aliases)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var dates = Set<String>()

        for case let fileURL as URL in enumerator {
            guard fileURL.pathExtension == "md",
                  let content = try? String(contentsOf: fileURL, encoding: .utf8)
            else {
                continue
            }

            let normalizedContent = normalize(content)
            guard normalizedContent.contains(normalize(titleSuffix)),
                  candidateNames.contains(where: { normalizedContent.contains(normalize($0)) })
            else {
                continue
            }

            if let match = fileURL.lastPathComponent.range(
                of: #"Lesson_(\d{4})(\d{2})(\d{2})_"#,
                options: .regularExpression
            ) {
                let raw = String(fileURL.lastPathComponent[match])
                    .replacingOccurrences(of: "Lesson_", with: "")
                    .replacingOccurrences(of: "_", with: "")
                if raw.count >= 8 {
                    let value = String(raw.prefix(8))
                    let date = "\(value.prefix(4))-\(value.dropFirst(4).prefix(2))-\(value.dropFirst(6).prefix(2))"
                    dates.insert(date)
                }
            }
        }

        return dates.sorted(by: >)
    }

    private func buildHeptabaseQueries(candidateNames: [String], candidateDates: [String]) -> [String] {
        var queries: [String] = []

        for date in candidateDates {
            let dateClean = date.replacingOccurrences(of: "-", with: "")
            for candidate in candidateNames {
                queries.append(contentsOf: [
                    "#\(dateClean) \(candidate) \(titleSuffix)",
                    "#\(dateClean) \(candidate)",
                    "\(dateClean) \(candidate)",
                    "\(date) \(candidate)",
                    "\(candidate) 教學"
                ])
            }
        }

        for candidate in candidateNames {
            let compactName = candidate.replacingOccurrences(of: " ", with: "")
            queries.append(contentsOf: [
                candidate,
                "\(candidate) \(titleSuffix)",
                "\(candidate) 數位管理",
                "\(candidate) 教學",
                compactName,
                "\(compactName)\(titleSuffix)"
            ])
        }

        return deduplicatedStrings(queries)
    }

    private func scoreHeptabaseTitle(
        _ title: String,
        candidateNames: [String],
        candidateDates: [String]
    ) -> Int {
        let normalizedTitle = normalize(title)
        var score = 0

        if candidateNames.contains(where: { normalizedTitle.contains(normalize($0)) }) {
            score += 5
        }
        if normalizedTitle.contains(normalize(titleSuffix)) {
            score += 3
        } else if normalizedTitle.contains("教學") || normalizedTitle.contains("數位管理") {
            score += 2
        }

        if candidateDates.contains(where: { normalizedTitle.contains($0.replacingOccurrences(of: "-", with: "")) }) {
            score += 2
        }

        return score
    }

    private func scoreHeptabaseContent(_ content: String, candidateNames: [String]) -> Int {
        let normalizedContent = normalize(content)
        var score = 0

        if candidateNames.contains(where: { normalizedContent.contains(normalize($0)) }) {
            score += 4
        }
        if normalizedContent.contains(normalize(titleSuffix)) {
            score += 3
        } else if normalizedContent.contains("教學") || normalizedContent.contains("數位管理") {
            score += 2
        }

        return score
    }

    private func extractFallbackLesson(
        from content: String,
        fileURL: URL,
        candidateNames: [String],
        isDedicatedFile: Bool
    ) -> LocalLessonExtraction? {
        let normalizedSuffix = normalize(titleSuffix)
        let lines = content.components(separatedBy: .newlines)

        var targetLine: String?
        for line in lines {
            let normalizedLine = normalize(line)
            if normalizedLine.contains(normalizedSuffix) && candidateNames.contains(where: { normalizedLine.contains(normalize($0)) }) {
                targetLine = line
                break
            }
        }
        guard let matchedLine = targetLine else { return nil }

        if !isDedicatedFile && fileURL.lastPathComponent.hasPrefix("Lesson_") {
            return nil
        }

        if isDedicatedFile {
            let title = preferredTitle(from: lines, candidateNames: candidateNames)
            let snippet = extractDedicatedLessonSnippet(from: lines)
            let preview = firstMeaningfulPreviewLine(from: snippet)
            guard !snippet.isEmpty, !preview.isEmpty else { return nil }

            return LocalLessonExtraction(
                title: title,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: title),
                preview: preview,
                content: snippet
            )
        } else {
            let cleanLine = cleanFallbackLine(matchedLine)
            guard !cleanLine.isEmpty else { return nil }
            return LocalLessonExtraction(
                title: cleanLine,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: cleanLine),
                preview: cleanLine,
                content: "> " + matchedLine.trimmingCharacters(in: .whitespacesAndNewlines) + "\n\n*(摘錄自 " + fileURL.lastPathComponent + ")*"
            )
        }
    }

    private func preferredTitle(from lines: [String], candidateNames: [String]) -> String {
        for line in lines {
            let normalizedLine = normalize(line)
            guard normalizedLine.contains(normalize(titleSuffix)),
                  candidateNames.contains(where: { normalizedLine.contains(normalize($0)) })
            else {
                continue
            }

            let cleaned = cleanFallbackLine(line)
            if !cleaned.isEmpty {
                return cleaned
            }
        }

        for line in lines where line.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("#") {
            let cleaned = cleanFallbackLine(line)
            if !cleaned.isEmpty {
                return cleaned
            }
        }

        return "數位管理教學"
    }

    private func extractDedicatedLessonSnippet(from lines: [String]) -> String {
        if let summaryIndex = lines.firstIndex(where: { $0.contains("### 教學內容摘要") }) {
            let start = min(lines.count - 1, summaryIndex + 1)
            let body = Array(lines[start...])
            return cleanedSnippet(from: body)
        }

        return cleanedSnippet(from: lines)
    }

    private func cleanedSnippet(from lines: [String]) -> String {
        lines
            .map { cleanFallbackLine($0) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func firstMeaningfulPreviewLine(from snippet: String) -> String {
        snippet
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first(where: { line in
                !line.isEmpty &&
                !line.hasPrefix("#") &&
                !line.hasPrefix("{{") &&
                !line.contains("今日行程")
            }) ?? ""
    }

    private func cleanFallbackLine(_ line: String) -> String {
        let prefixes = [
            "*   教學內容：",
            "* 教學內容：",
            "- 教學內容：",
            "教學內容：",
            "{{DONE}}",
            "{{TODO}}",
            "#",
            "*",
            "-"
        ]

        var value = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for prefix in prefixes {
            while value.hasPrefix(prefix) {
                value = String(value.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return value
    }

    private func extractDateFromFilename(_ filename: String) -> String? {
        guard let match = filename.range(
            of: #"Lesson_(\d{4})(\d{2})(\d{2})_"#,
            options: .regularExpression
        ) else {
            return nil
        }

        let raw = String(filename[match])
            .replacingOccurrences(of: "Lesson_", with: "")
            .replacingOccurrences(of: "_", with: "")
        guard raw.count >= 8 else { return nil }

        let value = String(raw.prefix(8))
        return "\(value.prefix(4))-\(value.dropFirst(4).prefix(2))-\(value.dropFirst(6).prefix(2))"
    }
}

struct HeptabaseCLITeachingRecordProvider: TeachingRecordProvider {
    private static let bunPath = "/Users/aios/.bun/bin/bun"
    private static let cliPath = "/Users/aios/.bun/install/global/node_modules/heptabase-cli/heptabase-cli.ts"
    private static let titleSuffix = "數位管理教學"

    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        guard FileManager.default.fileExists(atPath: Self.bunPath),
              FileManager.default.fileExists(atPath: Self.cliPath) else {
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "找不到 heptabase-cli，無法抓取 Heptabase 教學卡。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "heptabase-cli",
                    queries: [],
                    matchedItems: [],
                    fallbackPaths: [],
                notes: ["找不到 heptabase-cli"]
                )
            )
        }

        let candidateNames = Array(
            Set(([student.name] + student.aliases)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty })
        )
        let candidateDates = candidateLessonDates(for: student, projectRootPath: projectRootPath)

        var lastErrorMessage = ""
        var matchedCards: [String: (title: String, type: String)] = [:]
        var executedQueries: [String] = []

        if !candidateDates.isEmpty {
            for date in candidateDates {
                let dateClean = date.replacingOccurrences(of: "-", with: "")
                for candidate in candidateNames {
                    let query = "#\(dateClean) \(candidate) \(Self.titleSuffix)"
                    executedQueries.append(query)
                    guard let output = runCLI(
                        [
                            "semantic-search-objects",
                            "--queries", query,
                            "--result-object-types", "card",
                            "--output", "json"
                        ],
                        timeout: 25,
                        lastErrorMessage: &lastErrorMessage
                    ) else {
                        continue
                    }

                    for result in parseSearchResults(output) {
                        let normalizedTitle = normalize(result.title)

                        if result.type == "card" {
                            guard titleLooksLikeTeachingCard(normalizedTitle),
                                  normalizedTitle.contains(dateClean),
                                  candidateNames.contains(where: { normalizedTitle.contains(normalize($0)) })
                            else { continue }
                        } else if result.type == "journal" {
                            guard normalizedTitle.contains(dateClean) else { continue }
                        }

                        matchedCards[result.id] = (title: result.title, type: result.type)
                    }
                }
            }
        }

        if matchedCards.isEmpty {
            for candidate in candidateNames {
                let queryVariants = [
                    candidate,
                    "\(candidate) \(Self.titleSuffix)",
                    "\(candidate) 數位管理",
                    "\(candidate.replacingOccurrences(of: " ", with: ""))",
                    "\(candidate.replacingOccurrences(of: " ", with: ""))\(Self.titleSuffix)"
                ]

                for query in queryVariants {
                    executedQueries.append(query)
                    guard let output = runCLI(
                        [
                            "semantic-search-objects",
                            "--queries", query,
                            "--result-object-types", "card,journal",
                            "--output", "json"
                        ],
                        timeout: 25,
                        lastErrorMessage: &lastErrorMessage
                    ) else {
                        continue
                    }

                    for result in parseSearchResults(output) {
                        let normalizedTitle = normalize(result.title)

                        if result.type == "card" {
                            guard titleLooksLikeTeachingCard(normalizedTitle),
                                  candidateNames.contains(where: { normalizedTitle.contains(normalize($0)) })
                            else { continue }
                        }

                        matchedCards[result.id] = (title: result.title, type: result.type)
                    }
                }
            }
        }

        guard !matchedCards.isEmpty else {
            let message = lastErrorMessage.isEmpty
                ? "Heptabase 沒有找到符合這位學員的「數位管理教學」卡片。"
                : lastErrorMessage
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: message,
                diagnostics: TeachingRecordDiagnostics(
                    source: "heptabase-cli",
                    queries: deduplicatedStrings(executedQueries),
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: [message]
                )
            )
        }

        var lessonRecords: [LessonRecord] = []

        for (cardID, info) in matchedCards {
            let title = info.title
            let type = info.type
            guard let content = runCLI(
                [
                    "get-object",
                    "--object-id", cardID,
                    "--object-type", type,
                    "--output", "markdown"
                ],
                timeout: 25,
                lastErrorMessage: &lastErrorMessage
            ) else {
                continue
            }

            if type == "journal" {
                // Determine candidate names correctly
                let localCandidateNames = Array(Set(([student.name] + student.aliases)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }))

                guard let extracted = extractFallbackLesson(
                    from: content,
                    fileURL: URL(fileURLWithPath: "heptabase://journal/\(cardID)"),
                    candidateNames: localCandidateNames, // Wait, candidateNames is already available in scope from fetchLessonRecords!
                    isDedicatedFile: false
                ) else { continue }

                lessonRecords.append(
                    LessonRecord(
                        id: cardID,
                        date: extracted.date,
                        title: extracted.title,
                        preview: extracted.preview,
                        path: "Heptabase Journal",
                        content: extracted.content
                    )
                )
            } else {
                let cleanedContent = cleanHeptabaseTransportContent(content)
                let preview = cleanedContent
                    .components(separatedBy: "\n")
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .first(where: { !$0.isEmpty && !$0.hasPrefix("#") }) ?? ""

                lessonRecords.append(
                    LessonRecord(
                        id: cardID,
                        date: extractDate(from: title),
                        title: title,
                        preview: preview,
                        path: "Heptabase Card: \(cardID)",
                        content: cleanedContent
                    )
                )
            }
        }

        lessonRecords.sort { lhs, rhs in
            if lhs.date == rhs.date { return lhs.title > rhs.title }
            return lhs.date > rhs.date
        }

        return TeachingRecordFetchResult(
            lessonRecords: lessonRecords,
            message: lastErrorMessage,
            diagnostics: TeachingRecordDiagnostics(
                source: "heptabase-cli",
                queries: deduplicatedStrings(executedQueries),
                matchedItems: matchedCards.map { "\($0.value.title) [\($0.key)]" }.sorted(by: >),
                fallbackPaths: [],
                notes: lastErrorMessage.isEmpty ? [] : [lastErrorMessage]
            )
        )
    }

    private func titleLooksLikeTeachingCard(_ normalizedTitle: String) -> Bool {
        normalizedTitle.contains(normalize(Self.titleSuffix))
    }

    private func candidateLessonDates(for student: StudentRecord, projectRootPath: String) -> [String] {
        let teachingDirectory = URL(fileURLWithPath: projectRootPath).appendingPathComponent("01.Docs/teaching")
        guard let enumerator = FileManager.default.enumerator(
            at: teachingDirectory,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        let candidateNames = ([student.name] + student.aliases)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var dates = Set<String>()

        for case let fileURL as URL in enumerator {
            guard fileURL.pathExtension == "md",
                  let content = try? String(contentsOf: fileURL, encoding: .utf8)
            else {
                continue
            }

            let normalizedContent = normalize(content)
            guard normalizedContent.contains(normalize(Self.titleSuffix)),
                  candidateNames.contains(where: { normalizedContent.contains(normalize($0)) })
            else {
                continue
            }

            if let match = fileURL.lastPathComponent.range(
                of: #"Lesson_(\d{4})(\d{2})(\d{2})_"#,
                options: .regularExpression
            ) {
                let raw = String(fileURL.lastPathComponent[match])
                    .replacingOccurrences(of: "Lesson_", with: "")
                    .replacingOccurrences(of: "_", with: "")
                if raw.count >= 8 {
                    let value = String(raw.prefix(8))
                    let date = "\(value.prefix(4))-\(value.dropFirst(4).prefix(2))-\(value.dropFirst(6).prefix(2))"
                    dates.insert(date)
                }
            }
        }

        return dates.sorted(by: >)
    }

    private func runCLI(_ args: [String], timeout: TimeInterval, lastErrorMessage: inout String) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: Self.bunPath)
        process.arguments = [Self.cliPath] + args

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        let group = DispatchGroup()
        group.enter()
        process.terminationHandler = { _ in group.leave() }

        do {
            try process.run()
        } catch {
            lastErrorMessage = normalizedCLIErrorMessage(error.localizedDescription)
            return nil
        }

        if group.wait(timeout: .now() + timeout) == .timedOut {
            process.terminate()
            lastErrorMessage = "heptabase-cli 查詢逾時，請確認 Heptabase 已登入。"
            return nil
        }

        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        let output = String(data: outputData, encoding: .utf8) ?? ""
        let errorText = String(data: errorData, encoding: .utf8) ?? ""

        if output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           errorText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            lastErrorMessage = "heptabase-cli 已執行，但沒有回傳任何資料。"
            return nil
        }

        guard process.terminationStatus == 0 else {
            let trimmedError = errorText.trimmingCharacters(in: .whitespacesAndNewlines)
            lastErrorMessage = trimmedError.isEmpty
                ? "heptabase-cli 查詢失敗。"
                : normalizedCLIErrorMessage(trimmedError)
            return nil
        }

        return output
    }

    private func normalizedCLIErrorMessage(_ message: String) -> String {
        let normalized = message.lowercased()
        if normalized.contains("executable not found in $path") ||
            normalized.contains("\"npx\"") ||
            normalized.contains("env: npx") {
            return "Heptabase CLI 在目前環境不可用，已改用本地教學檔案補齊。"
        }
        if normalized.contains("permission denied") {
            return "heptabase-cli 權限不足，已改用本地教學檔案補齊。"
        }
        return message
    }

    private func parseSearchResults(_ output: String) -> [(id: String, title: String, type: String)] {
        var results: [(id: String, title: String, type: String)] = []

        // Try extracting XML patterns first as the CLI returns XML
        let xmlPattern = #"<(card|journal) id="([^"]+)" title="([^"]+)"#
        if let regex = try? NSRegularExpression(pattern: xmlPattern) {
            let nsRange = NSRange(output.startIndex..<output.endIndex, in: output)
            for match in regex.matches(in: output, range: nsRange) {
                guard let typeRange = Range(match.range(at: 1), in: output),
                      let idRange = Range(match.range(at: 2), in: output),
                      let titleRange = Range(match.range(at: 3), in: output) else { continue }
                results.append((String(output[idRange]), String(output[titleRange]), String(output[typeRange])))
            }
        }

        if !results.isEmpty { return deduplicated(results) }

        // Fallback to JSON if any wrapper or future output changes to JSON
        let jsonPattern = #""(card|journal)".*?"id"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)""#
        if let regex = try? NSRegularExpression(pattern: jsonPattern, options: [.dotMatchesLineSeparators]) {
            let nsRange = NSRange(output.startIndex..<output.endIndex, in: output)
            for match in regex.matches(in: output, range: nsRange) {
                guard let typeRange = Range(match.range(at: 1), in: output),
                      let idRange = Range(match.range(at: 2), in: output),
                      let titleRange = Range(match.range(at: 3), in: output) else { continue }
                results.append((String(output[idRange]), String(output[titleRange]), String(output[typeRange])))
            }
        }

        return deduplicated(results)
    }

    private func deduplicated(_ results: [(id: String, title: String, type: String)]) -> [(id: String, title: String, type: String)] {
        var seen = Set<String>()
        return results.filter { item in
            guard !item.id.isEmpty, !item.title.isEmpty, !seen.contains(item.id) else {
                return false
            }
            seen.insert(item.id)
            return true
        }
    }

    private func collectSearchResults(from node: Any, into results: inout [(id: String, title: String)]) {
        if let dictionary = node as? [String: Any] {
            if let id = dictionary["id"] as? String,
               let title = dictionary["title"] as? String {
                results.append((id, title))
            }

            if let object = dictionary["object"] as? [String: Any],
               let id = object["id"] as? String,
               let title = object["title"] as? String {
                results.append((id, title))
            }

            for value in dictionary.values {
                collectSearchResults(from: value, into: &results)
            }
        } else if let array = node as? [Any] {
            for item in array {
                collectSearchResults(from: item, into: &results)
            }
        }
    }

    private func deduplicated(_ results: [(id: String, title: String)]) -> [(id: String, title: String)] {
        var seen = Set<String>()
        return results.filter { item in
            guard !item.id.isEmpty, !item.title.isEmpty, !seen.contains(item.id) else {
                return false
            }
            seen.insert(item.id)
            return true
        }
    }

}

struct LocalTeachingFileProvider: TeachingRecordProvider {
    private let titleSuffix = "數位管理教學"

    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        let directories = [
            URL(fileURLWithPath: projectRootPath).appendingPathComponent("01.Docs/teaching"),
            URL(fileURLWithPath: projectRootPath).appendingPathComponent("01.Daily")
        ]

        var enumerators: [FileManager.DirectoryEnumerator] = []
        for directory in directories {
            if let enumerator = FileManager.default.enumerator(
                at: directory,
                includingPropertiesForKeys: nil
            ) {
                enumerators.append(enumerator)
            }
        }

        guard !enumerators.isEmpty else {
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "找不到本地 teaching 或 Daily 目錄。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "本地 teaching 與 Daily 檔案",
                    queries: [],
                    matchedItems: [],
                    fallbackPaths: [],
                    notes: ["找不到本地 teaching 或 Daily 目錄"]
                )
            )
        }

        let candidateNames = ([student.name] + student.aliases)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var records: [LessonRecord] = []
        var fallbackPaths: [String] = []

        for enumerator in enumerators {
            for case let fileURL as URL in enumerator {
            guard fileURL.pathExtension == "md",
                  let content = try? String(contentsOf: fileURL, encoding: .utf8)
            else {
                continue
            }

            let normalizedContent = normalize(content)
            guard normalizedContent.contains(normalize(titleSuffix)),
                  candidateNames.contains(where: { normalizedContent.contains(normalize($0)) })
            else {
                continue
            }

            let isDedicatedFile = fileLooksDedicatedToStudent(
                fileURL: fileURL,
                content: content,
                candidateNames: candidateNames
            )
            guard let extraction = extractFallbackLesson(
                from: content,
                fileURL: fileURL,
                candidateNames: candidateNames,
                isDedicatedFile: isDedicatedFile
            ) else {
                continue
            }

            records.append(
                LessonRecord(
                    id: fileURL.path,
                    date: extraction.date,
                    title: extraction.title,
                    preview: extraction.preview,
                    path: fileURL.path,
                    content: extraction.content
                )
            )
            fallbackPaths.append(fileURL.path)
            }
        }

        let deduped = deduplicated(records).sorted { lhs, rhs in
            if lhs.date == rhs.date { return lhs.title > rhs.title }
            return lhs.date > rhs.date
        }

        guard !deduped.isEmpty else {
            return TeachingRecordFetchResult(
                lessonRecords: [],
                message: "本地 teaching 與 Daily 檔案也沒有找到符合的數位管理教學紀錄。",
                diagnostics: TeachingRecordDiagnostics(
                    source: "本地 teaching 與 Daily 檔案",
                    queries: [],
                    matchedItems: [],
                    fallbackPaths: deduplicatedStrings(fallbackPaths),
                    notes: ["沒有找到符合的數位管理教學紀錄"]
                )
            )
        }

        return TeachingRecordFetchResult(
            lessonRecords: deduped,
            message: "Heptabase CLI 在目前環境沒有回傳可用資料，已改用本地教學與日記檔案補齊。",
            diagnostics: TeachingRecordDiagnostics(
                source: "本地 teaching 與 Daily 檔案",
                queries: [],
                matchedItems: deduped.map { "\($0.date)｜\($0.title)" },
                fallbackPaths: deduplicatedStrings(fallbackPaths),
                notes: ["已走本地教學檔案 fallback"]
            )
        )
    }

    private func fileLooksDedicatedToStudent(fileURL: URL, content: String, candidateNames: [String]) -> Bool {
        let normalizedFilename = normalize(fileURL.deletingPathExtension().lastPathComponent)
        if candidateNames.contains(where: { normalizedFilename.contains(normalize($0)) }) {
            return true
        }

        if let firstHeading = content
            .components(separatedBy: .newlines)
            .first(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("#") }) {
            let normalizedHeading = normalize(firstHeading)
            if candidateNames.contains(where: { normalizedHeading.contains(normalize($0)) }) {
                return true
            }
        }

        return false
    }

    private func extractFallbackLesson(
        from content: String,
        fileURL: URL,
        candidateNames: [String],
        isDedicatedFile: Bool
    ) -> LocalLessonExtraction? {
        let normalizedSuffix = normalize(titleSuffix)
        let lines = content.components(separatedBy: .newlines)

        var targetLine: String?
        for line in lines {
            let normalizedLine = normalize(line)
            if normalizedLine.contains(normalizedSuffix) && candidateNames.contains(where: { normalizedLine.contains(normalize($0)) }) {
                targetLine = line
                break
            }
        }
        guard let matchedLine = targetLine else { return nil }

        if !isDedicatedFile && fileURL.lastPathComponent.hasPrefix("Lesson_") {
            return nil
        }

        if isDedicatedFile {
            let title = preferredTitle(from: lines, candidateNames: candidateNames)
            let snippet = extractDedicatedLessonSnippet(from: lines)
            let preview = firstMeaningfulPreviewLine(from: snippet)
            guard !snippet.isEmpty, !preview.isEmpty else { return nil }

            return LocalLessonExtraction(
                title: title,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: title),
                preview: preview,
                content: snippet
            )
        } else {
            let cleanLine = cleanFallbackLine(matchedLine)
            guard !cleanLine.isEmpty else { return nil }
            return LocalLessonExtraction(
                title: cleanLine,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: cleanLine),
                preview: cleanLine,
                content: "> " + matchedLine.trimmingCharacters(in: .whitespacesAndNewlines) + "\n\n*(摘錄自 " + fileURL.lastPathComponent + ")*"
            )
        }
    }

    private func preferredTitle(from lines: [String], candidateNames: [String]) -> String {
        for line in lines {
            let normalizedLine = normalize(line)
            guard normalizedLine.contains(normalize(titleSuffix)),
                  candidateNames.contains(where: { normalizedLine.contains(normalize($0)) })
            else {
                continue
            }

            let cleaned = cleanFallbackLine(line)
            if !cleaned.isEmpty {
                return cleaned
            }
        }

        for line in lines where line.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("#") {
            let cleaned = cleanFallbackLine(line)
            if !cleaned.isEmpty {
                return cleaned
            }
        }

        return "數位管理教學"
    }

    private func extractDedicatedLessonSnippet(from lines: [String]) -> String {
        if let summaryIndex = lines.firstIndex(where: { $0.contains("### 教學內容摘要") }) {
            let start = min(lines.count - 1, summaryIndex + 1)
            let body = Array(lines[start...])
            return cleanedSnippet(from: body)
        }

        return cleanedSnippet(from: lines)
    }

    private func cleanedSnippet(from lines: [String]) -> String {
        lines
            .map { cleanFallbackLine($0) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func firstMeaningfulPreviewLine(from snippet: String) -> String {
        snippet
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first(where: { line in
                !line.isEmpty &&
                !line.hasPrefix("#") &&
                !line.hasPrefix("{{") &&
                !line.contains("今日行程")
            }) ?? ""
    }

    private func cleanFallbackLine(_ line: String) -> String {
        let prefixes = [
            "*   教學內容：",
            "* 教學內容：",
            "- 教學內容：",
            "教學內容：",
            "{{DONE}}",
            "{{TODO}}",
            "#",
            "*",
            "-"
        ]

        var value = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for prefix in prefixes {
            while value.hasPrefix(prefix) {
                value = String(value.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return value
    }

    private func extractDateFromFilename(_ filename: String) -> String? {
        guard let match = filename.range(
            of: #"Lesson_(\d{4})(\d{2})(\d{2})_"#,
            options: .regularExpression
        ) else {
            return nil
        }

        let raw = String(filename[match])
            .replacingOccurrences(of: "Lesson_", with: "")
            .replacingOccurrences(of: "_", with: "")
        guard raw.count >= 8 else { return nil }

        let value = String(raw.prefix(8))
        return "\(value.prefix(4))-\(value.dropFirst(4).prefix(2))-\(value.dropFirst(6).prefix(2))"
    }

    private func deduplicated(_ records: [LessonRecord]) -> [LessonRecord] {
        var seen = Set<String>()
        var output: [LessonRecord] = []

        for record in records {
            let key = "\(record.date)|\(record.title)|\(record.path)"
            if seen.insert(key).inserted {
                output.append(record)
            }
        }

        return output
    }
}

private struct LocalLessonExtraction {
    let title: String
    let date: String
    let preview: String
    let content: String
}

private enum HeptabaseMCPConfiguration {
    static func resolveEndpoint() -> URL? {
        let environment = ProcessInfo.processInfo.environment
        let defaults = UserDefaults.standard
        let rawValue = environment["HEPTABASE_MCP_ENDPOINT"]
            ?? defaults.string(forKey: "HeptabaseMCPEndpoint")
            ?? "https://api.heptabase.com/mcp"
        return URL(string: rawValue)
    }

    static func resolveBearerToken() -> String {
        let environment = ProcessInfo.processInfo.environment
        let defaults = UserDefaults.standard
        return environment["HEPTABASE_MCP_BEARER_TOKEN"]
            ?? environment["HEPTABASE_MCP_TOKEN"]
            ?? defaults.string(forKey: "HeptabaseMCPBearerToken")
            ?? ""
    }
}

struct HeptabaseMCPBridgeAuthResult {
    let message: String
    let tools: [String]
}

private struct HeptabaseMCPBridgeSearchEnvelope: Decodable {
    let ok: Bool
    let json: [MCPSearchResult]?
}

private struct HeptabaseMCPBridgeGetObjectEnvelope: Decodable {
    let ok: Bool
    let text: String?
}

private struct HeptabaseMCPBridgeAuthEnvelope: Decodable {
    let ok: Bool
    let message: String?
    let tools: [String]?
}

private struct HeptabaseMCPBridgeFailureEnvelope: Decodable {
    let ok: Bool?
    let error: String?
    let stderr: String?
}

struct HeptabaseMCPBridge {
    private let scriptRelativePath = "scripts/heptabase_mcp_bridge.mjs"
    private let timeout: TimeInterval = 45

    var isAvailable: Bool {
        FileManager.default.fileExists(atPath: resolvedScriptPath(projectRootPath: FileManager.default.currentDirectoryPath))
    }

    func authenticate(projectRootPath: String) throws -> HeptabaseMCPBridgeAuthResult {
        let envelope: HeptabaseMCPBridgeAuthEnvelope = try run(
            arguments: ["auth"],
            projectRootPath: projectRootPath
        )
        guard envelope.ok else {
            throw HeptabaseMCPBridgeError.invalidResponse
        }
        return HeptabaseMCPBridgeAuthResult(
            message: envelope.message ?? "Heptabase MCP 已完成授權。",
            tools: envelope.tools ?? []
        )
    }

    func search(query: String, projectRootPath: String) throws -> [MCPSearchResult] {
        let envelope: HeptabaseMCPBridgeSearchEnvelope = try run(
            arguments: ["search", query],
            projectRootPath: projectRootPath
        )
        guard envelope.ok else {
            throw HeptabaseMCPBridgeError.invalidResponse
        }
        return envelope.json ?? []
    }

    func getObjectMarkdown(objectID: String, objectType: String, projectRootPath: String) throws -> String {
        let envelope: HeptabaseMCPBridgeGetObjectEnvelope = try run(
            arguments: ["get-object", objectID, objectType],
            projectRootPath: projectRootPath
        )
        guard envelope.ok, let text = envelope.text else {
            throw HeptabaseMCPBridgeError.invalidResponse
        }
        return text
    }

    private func run<Response: Decodable>(
        arguments: [String],
        projectRootPath: String
    ) throws -> Response {
        let process = Process()
        let nodeBinary = resolvedNodeBinaryPath()
        if nodeBinary == "/usr/bin/env" {
            process.executableURL = URL(fileURLWithPath: nodeBinary)
            process.arguments = ["node", resolvedScriptPath(projectRootPath: projectRootPath)] + arguments
        } else {
            process.executableURL = URL(fileURLWithPath: nodeBinary)
            process.arguments = [resolvedScriptPath(projectRootPath: projectRootPath)] + arguments
        }
        process.currentDirectoryURL = URL(fileURLWithPath: projectRootPath)
        process.environment = bridgeEnvironment(nodeBinary: nodeBinary)

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        let group = DispatchGroup()
        group.enter()
        process.terminationHandler = { _ in group.leave() }

        if group.wait(timeout: .now() + timeout) == .timedOut {
            process.terminate()
            let output = String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let errorText = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let detail = bridgeFailureMessage(
                output: output,
                errorText: errorText,
                fallback: "Heptabase MCP bridge 連線逾時，請確認 OAuth 視窗是否被擋住。"
            )
            throw HeptabaseMCPBridgeError.commandFailed(detail)
        }

        let output = String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let errorText = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""

        guard process.terminationStatus == 0 else {
            throw HeptabaseMCPBridgeError.commandFailed(
                bridgeFailureMessage(
                    output: output,
                    errorText: errorText,
                    fallback: "Heptabase MCP bridge 執行失敗。"
                )
            )
        }

        guard let line = output
            .components(separatedBy: .newlines)
            .map({ $0.trimmingCharacters(in: .whitespacesAndNewlines) })
            .first(where: { !$0.isEmpty }),
              let data = line.data(using: .utf8) else {
            throw HeptabaseMCPBridgeError.invalidResponse
        }

        return try JSONDecoder().decode(Response.self, from: data)
    }

    private func resolvedScriptPath(projectRootPath: String) -> String {
        URL(fileURLWithPath: projectRootPath).appendingPathComponent(scriptRelativePath).path
    }

    private func bridgeEnvironment(nodeBinary: String) -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["NODE_BINARY"] = nodeBinary

        let nodeURL = URL(fileURLWithPath: nodeBinary)
        let binDirectory = nodeURL.deletingLastPathComponent().path
        let currentPath = environment["PATH"] ?? ""
        let pathParts = ([binDirectory] + currentPath.components(separatedBy: ":"))
            .filter { !$0.isEmpty }
        environment["PATH"] = deduplicatedStrings(pathParts).joined(separator: ":")

        if let npxBinary = resolvedSiblingBinary(named: "npx", from: nodeBinary) {
            environment["HEPTABASE_MCP_NPX_BINARY"] = npxBinary
        }

        return environment
    }

    private func resolvedNodeBinaryPath() -> String {
        let environment = ProcessInfo.processInfo.environment
        if let explicit = environment["NODE_BINARY"], FileManager.default.isExecutableFile(atPath: explicit) {
            return explicit
        }

        let candidates = [
            "/opt/homebrew/bin/node",
            "/usr/local/bin/node",
            "/opt/local/bin/node",
            "/Users/aios/.nvm/versions/node/current/bin/node"
        ] + fnmBinaryCandidates(named: "node")

        if let match = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) {
            return match
        }

        return "/usr/bin/env"
    }

    private func resolvedSiblingBinary(named name: String, from binaryPath: String) -> String? {
        let siblingPath = URL(fileURLWithPath: binaryPath)
            .deletingLastPathComponent()
            .appendingPathComponent(name)
            .path
        guard FileManager.default.isExecutableFile(atPath: siblingPath) else {
            return nil
        }
        return siblingPath
    }

    private func fnmBinaryCandidates(named name: String) -> [String] {
        let root = URL(fileURLWithPath: "/Users/aios/.local/state/fnm_multishells")
        guard let directories = try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        return directories
            .sorted { $0.lastPathComponent > $1.lastPathComponent }
            .map { $0.appendingPathComponent("bin/\(name)").path }
    }

    private func bridgeFailureMessage(output: String, errorText: String, fallback: String) -> String {
        let trimmedError = errorText.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedOutput = output.trimmingCharacters(in: .whitespacesAndNewlines)

        if let data = trimmedOutput.data(using: .utf8),
           let envelope = try? JSONDecoder().decode(HeptabaseMCPBridgeFailureEnvelope.self, from: data) {
            var lines: [String] = []
            if let error = envelope.error?.trimmingCharacters(in: .whitespacesAndNewlines), !error.isEmpty {
                lines.append(error)
            }
            if let stderr = envelope.stderr?.trimmingCharacters(in: .whitespacesAndNewlines), !stderr.isEmpty {
                lines.append("bridge stderr: \(stderr)")
            }
            if !lines.isEmpty {
                return deduplicatedStrings(lines).joined(separator: "\n")
            }
        }

        let combined = deduplicatedStrings([
            trimmedError,
            trimmedOutput.isEmpty ? "" : "bridge output: \(trimmedOutput)"
        ])

        if combined.isEmpty {
            return fallback
        }

        return ([fallback] + combined).joined(separator: "\n")
    }
}

private enum HeptabaseMCPBridgeError: LocalizedError {
    case commandFailed(String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .commandFailed(let message):
            return message.isEmpty ? "Heptabase MCP bridge 執行失敗。" : message
        case .invalidResponse:
            return "Heptabase MCP bridge 回傳格式無效。"
        }
    }
}

final class HeptabaseMCPClient {
    let endpoint: URL
    let bearerToken: String
    private var sessionID: String?
    private var protocolVersion = "2025-03-26"

    init(endpoint: URL, bearerToken: String) {
        self.endpoint = endpoint
        self.bearerToken = bearerToken
    }

    func listToolNames() throws -> [String] {
        try ensureInitialized()
        let response = try send(
            method: "tools/list",
            params: [:],
            responseType: MCPToolsListResponse.self
        )
        return response.result.tools.map(\.name)
    }

    func semanticSearchObjects(query: String) throws -> [MCPSearchResult] {
        try ensureInitialized()
        let response = try send(
            method: "tools/call",
            params: [
                "name": "semantic_search_objects",
                "arguments": [
                    "query": query
                ]
            ],
            responseType: MCPToolCallResponse.self
        )
        return response.result.searchResults
    }

    func getObjectMarkdown(objectID: String, objectType: String) throws -> String {
        try ensureInitialized()
        let response = try send(
            method: "tools/call",
            params: [
                "name": "get_object",
                "arguments": [
                    "objectId": objectID,
                    "objectType": objectType
                ]
            ],
            responseType: MCPToolCallResponse.self
        )

        let text = response.result.joinedText.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            throw HeptabaseMCPError.emptyResponse
        }
        return text
    }

    private func ensureInitialized() throws {
        guard sessionID == nil else { return }

        let response = try send(
            method: "initialize",
            params: [
                "protocolVersion": protocolVersion,
                "capabilities": [:],
                "clientInfo": [
                    "name": "StudentCRMNative",
                    "version": "1.0"
                ]
            ],
            responseType: MCPInitializeResponse.self,
            includeSessionID: false,
            includeProtocolVersionHeader: false
        )

        protocolVersion = response.result.protocolVersion

        try sendNotification(
            method: "notifications/initialized",
            params: [:]
        )
    }

    private func send<Response: Decodable>(
        method: String,
        params: [String: Any],
        responseType: Response.Type,
        includeSessionID: Bool = true,
        includeProtocolVersionHeader: Bool = true
    ) throws -> Response {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json, text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        if includeProtocolVersionHeader {
            request.setValue(protocolVersion, forHTTPHeaderField: "MCP-Protocol-Version")
        }
        if includeSessionID, let sessionID {
            request.setValue(sessionID, forHTTPHeaderField: "Mcp-Session-Id")
        }

        let payload: [String: Any] = [
            "jsonrpc": "2.0",
            "id": UUID().uuidString,
            "method": method,
            "params": params
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let capture = URLSessionSyncCapture()

        URLSession.shared.dataTask(with: request) { data, response, error in
            capture.store(data: data, response: response, error: error)
        }.resume()

        let result = capture.wait(timeout: .now() + 25)

        if let capturedError = result.error {
            throw capturedError
        }

        guard let httpResponse = result.response as? HTTPURLResponse else {
            throw HeptabaseMCPError.invalidHTTPResponse
        }

        if let responseSessionID = httpResponse.value(forHTTPHeaderField: "Mcp-Session-Id"),
           !responseSessionID.isEmpty {
            sessionID = responseSessionID
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw HeptabaseMCPError.httpStatus(httpResponse.statusCode)
        }

        guard let capturedData = result.data else {
            throw HeptabaseMCPError.emptyResponse
        }

        let decodedData = try extractMCPResponseData(
            from: capturedData,
            contentType: httpResponse.value(forHTTPHeaderField: "Content-Type") ?? ""
        )
        return try JSONDecoder().decode(responseType, from: decodedData)
    }

    private func extractMCPResponseData(from data: Data, contentType: String) throws -> Data {
        if contentType.contains("text/event-stream") {
            guard let text = String(data: data, encoding: .utf8) else {
                throw HeptabaseMCPError.emptyResponse
            }

            let eventPayloads = text
                .components(separatedBy: "\n\n")
                .flatMap { chunk -> [String] in
                    chunk
                        .components(separatedBy: .newlines)
                        .filter { $0.hasPrefix("data:") }
                        .map { line in
                            String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                        }
                }
                .filter { !$0.isEmpty }

            if let payload = eventPayloads.last, let eventData = payload.data(using: .utf8) {
                return eventData
            }
            throw HeptabaseMCPError.emptyResponse
        }

        return data
    }

    private func sendNotification(method: String, params: [String: Any]) throws {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json, text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue(protocolVersion, forHTTPHeaderField: "MCP-Protocol-Version")
        if let sessionID {
            request.setValue(sessionID, forHTTPHeaderField: "Mcp-Session-Id")
        }

        let payload: [String: Any] = [
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let capture = URLSessionSyncCapture()

        URLSession.shared.dataTask(with: request) { _, response, error in
            capture.store(data: nil, response: response, error: error)
        }.resume()

        let result = capture.wait(timeout: .now() + 25)

        if let capturedError = result.error {
            throw capturedError
        }

        guard let httpResponse = result.response as? HTTPURLResponse else {
            throw HeptabaseMCPError.invalidHTTPResponse
        }

        if let responseSessionID = httpResponse.value(forHTTPHeaderField: "Mcp-Session-Id"),
           !responseSessionID.isEmpty {
            sessionID = responseSessionID
        }

        guard httpResponse.statusCode == 202 || (200...299).contains(httpResponse.statusCode) else {
            throw HeptabaseMCPError.httpStatus(httpResponse.statusCode)
        }
    }
}

private final class URLSessionSyncCapture: @unchecked Sendable {
    private let semaphore = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var capturedData: Data?
    private var capturedResponse: URLResponse?
    private var capturedError: Error?

    func store(data: Data?, response: URLResponse?, error: Error?) {
        lock.lock()
        capturedData = data
        capturedResponse = response
        capturedError = error
        lock.unlock()
        semaphore.signal()
    }

    func wait(timeout: DispatchTime) -> (data: Data?, response: URLResponse?, error: Error?) {
        _ = semaphore.wait(timeout: timeout)
        lock.lock()
        defer { lock.unlock() }
        return (capturedData, capturedResponse, capturedError)
    }
}

private struct MCPInitializeResponse: Decodable {
    let result: MCPInitializeResult
}

private struct MCPInitializeResult: Decodable {
    let protocolVersion: String

    private enum CodingKeys: String, CodingKey {
        case protocolVersion
    }
}


private struct MCPToolsListResponse: Decodable {
    let result: MCPToolsListResult
}

private struct MCPToolsListResult: Decodable {
    let tools: [MCPToolDefinition]
}

private struct MCPToolDefinition: Decodable {
    let name: String
}

private struct MCPToolCallResponse: Decodable {
    let result: MCPToolCallResult
}

private struct MCPToolCallResult: Decodable {
    let content: [MCPContentItem]
    let isError: Bool?

    var joinedText: String {
        content
            .compactMap(\.text)
            .joined(separator: "\n")
    }

    var searchResults: [MCPSearchResult] {
        var collected: [MCPSearchResult] = []
        for item in content {
            if let text = item.text,
               let data = text.data(using: .utf8),
               let decoded = try? JSONDecoder().decode([MCPSearchResult].self, from: data) {
                collected.append(contentsOf: decoded)
            }

            if let data = item.data,
               let encoded = try? JSONSerialization.data(withJSONObject: data),
               let decoded = try? JSONDecoder().decode([MCPSearchResult].self, from: encoded) {
                collected.append(contentsOf: decoded)
            }
        }

        return collected
    }
}

private struct MCPContentItem: Decodable {
    let type: String?
    let text: String?
    let data: [String: AnyDecodable]?
}

struct MCPSearchResult: Decodable {
    let id: String
    let title: String
    var type: String = "card"
}

private enum HeptabaseMCPError: LocalizedError {
    case invalidHTTPResponse
    case httpStatus(Int)
    case emptyResponse

    var errorDescription: String? {
        switch self {
        case .invalidHTTPResponse:
            return "Heptabase MCP 沒有回傳可辨識的 HTTP 結果。"
        case .httpStatus(let code):
            return "Heptabase MCP HTTP 狀態異常：\(code)"
        case .emptyResponse:
            return "Heptabase MCP 沒有回傳內容。"
        }
    }
}

private struct AnyDecodable: Decodable {}

private func cleanHeptabaseTransportContent(_ content: String) -> String {
    var cleaned = content
    let patterns = [
        #"<card.*?>"#,
        #"</card>"#,
        #"<chunk.*?>"#,
        #"</chunk>"#,
        #"<whiteboard.*?>"#,
        #"</whiteboard>"#
    ]
    for pattern in patterns {
        cleaned = cleaned.replacingOccurrences(
            of: pattern,
            with: "",
            options: .regularExpression
        )
    }
    return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
}

func deduplicatedStrings(_ values: [String]) -> [String] {
    var seen = Set<String>()
    return values
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
        .filter { value in
            guard !seen.contains(value) else { return false }
            seen.insert(value)
            return true
        }
}

func extractDate(from title: String) -> String {
    let pattern = #"#?(\d{4})(\d{2})(\d{2})"#
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return "未標日期" }
    let nsRange = NSRange(title.startIndex..<title.endIndex, in: title)
    guard let match = regex.firstMatch(in: title, range: nsRange),
          let yearRange = Range(match.range(at: 1), in: title),
          let monthRange = Range(match.range(at: 2), in: title),
          let dayRange = Range(match.range(at: 3), in: title) else {
        return "未標日期"
    }
    return "\(title[yearRange])-\(title[monthRange])-\(title[dayRange])"
}

func normalize(_ text: String) -> String {
    text
        .lowercased()
        .replacingOccurrences(of: " ", with: "")
        .replacingOccurrences(of: "　", with: "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

private func parseHeptabaseSearchResults(_ xml: String) -> [MCPSearchResult] {
    // 簡易 XML 解析，提取 <card> 和 <journal> 中的 id 和 title
    var results: [MCPSearchResult] = []
    let cardPattern = #"<(card|journal)\s+id="([^"]+)"\s+title="([^"]+)"\s*/>"#
    guard let regex = try? NSRegularExpression(pattern: cardPattern, options: []) else { return [] }

    let nsRange = NSRange(xml.startIndex..<xml.endIndex, in: xml)
    let matches = regex.matches(in: xml, options: [], range: nsRange)

    for match in matches {
        if let typeRange = Range(match.range(at: 1), in: xml),
           let idRange = Range(match.range(at: 2), in: xml),
           let titleRange = Range(match.range(at: 3), in: xml) {
            results.append(
                MCPSearchResult(
                    id: String(xml[idRange]),
                    title: String(xml[titleRange]),
                    type: String(xml[typeRange])
                )
            )
        }
    }
    return results
}

private func extractFallbackLesson(
    from content: String,
    fileURL: URL,
    candidateNames: [String],
    isDedicatedFile: Bool
) -> LessonRecord? {
    let lines = content.components(separatedBy: .newlines)
    let fileName = fileURL.lastPathComponent
    let date = extractDate(from: fileName)

    // 尋找包含人名的行
    for (index, line) in lines.enumerated() {
        let normalizedLine = normalize(line)
        for name in candidateNames {
            if normalizedLine.contains(normalize(name)) {
                // 找到了教學紀錄點
                let title = line.trimmingCharacters(in: .whitespacesAndNewlines)
                let previewLines = lines[index...].prefix(5).joined(separator: "\n")
                return LessonRecord(
                    id: fileName + "_\(index)",
                    date: date,
                    title: title,
                    preview: firstMeaningfulPreviewLine(from: previewLines),
                    path: fileURL.path,
                    content: content
                )
            }
        }
    }

    return nil
}

private func firstMeaningfulPreviewLine(from content: String) -> String {
    let lines = content.components(separatedBy: .newlines)
    for line in lines {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && !trimmed.hasPrefix("#") && !trimmed.hasPrefix("-") {
            return trimmed
        }
    }
    return lines.first?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}

struct HeptabaseLocalExportProvider: TeachingRecordProvider {
    private let titleSuffix = "數位管理教學"

    func fetchLessonRecords(for student: StudentRecord, projectRootPath: String) -> TeachingRecordFetchResult {
        let backupRoot = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Documents/文件 - bangdoll’s MacBook Air - 1/Heptabase-auto-backup")

        guard let subDirs = try? FileManager.default.contentsOfDirectory(at: backupRoot, includingPropertiesForKeys: [.creationDateKey], options: .skipsHiddenFiles) else {
            return fallbackResult(message: "找不到 Heptabase 備份根目錄。")
        }

        let latestBackupDir = subDirs.filter { $0.hasDirectoryPath && $0.lastPathComponent.hasPrefix("Heptabase-Data-Backup-") }
            .sorted { d1, d2 in
                let date1 = (try? d1.resourceValues(forKeys: [.creationDateKey]))?.creationDate ?? Date.distantPast
                let date2 = (try? d2.resourceValues(forKeys: [.creationDateKey]))?.creationDate ?? Date.distantPast
                return date1 > date2
            }.first

        guard let targetDir = latestBackupDir else {
            return fallbackResult(message: "Heptabase 備份資料夾內沒有已解壓的備份子目錄。")
        }

        let targetDirs = [
            targetDir.appendingPathComponent("Card Library"),
            targetDir.appendingPathComponent("Journal")
        ]

        var enumerators: [FileManager.DirectoryEnumerator] = []
        for dir in targetDirs {
            if let enumerator = FileManager.default.enumerator(at: dir, includingPropertiesForKeys: nil) {
                enumerators.append(enumerator)
            }
        }

        guard !enumerators.isEmpty else {
            return fallbackResult(message: "最新的備份檔內沒有 Card Library 或 Journal。")
        }

        let candidateNames = ([student.name] + student.aliases)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var records: [LessonRecord] = []
        var fallbackPaths: [String] = []

        for enumerator in enumerators {
            for case let fileURL as URL in enumerator {
                guard fileURL.pathExtension == "md",
                      let content = try? String(contentsOf: fileURL, encoding: .utf8)
                else { continue }

                let normalizedContent = normalize(content)
                guard normalizedContent.contains(normalize(titleSuffix)),
                      candidateNames.contains(where: { normalizedContent.contains(normalize($0)) })
                else { continue }

                let isDedicatedFile = fileLooksDedicatedToStudent(fileURL: fileURL, content: content, candidateNames: candidateNames)
                guard let extraction = extractFallbackLesson(
                    from: content,
                    fileURL: fileURL,
                    candidateNames: candidateNames,
                    isDedicatedFile: isDedicatedFile
                ) else { continue }

                records.append(
                    LessonRecord(
                        id: fileURL.path,
                        date: extraction.date,
                        title: extraction.title,
                        preview: extraction.preview,
                        path: "備份: " + fileURL.lastPathComponent,
                        content: extraction.content
                    )
                )
                fallbackPaths.append(fileURL.path)
            }
        }

        let deduped = deduplicated(records).sorted { lhs, rhs in
            if lhs.date == rhs.date { return lhs.title > rhs.title }
            return lhs.date > rhs.date
        }

        guard !deduped.isEmpty else {
            return fallbackResult(message: "Heptabase 本地解壓檔中沒有符合的卡片。")
        }

        return TeachingRecordFetchResult(
            lessonRecords: deduped,
            message: "目前資料來源：Heptabase 本地解壓備份 (\(targetDir.lastPathComponent))",
            diagnostics: TeachingRecordDiagnostics(
                source: "Heptabase Local Backup",
                queries: [],
                matchedItems: deduped.map { "\($0.date)｜\($0.title)" },
                fallbackPaths: deduplicatedStrings(fallbackPaths),
                notes: ["從本地備份檔萃取成功"]
            )
        )
    }

    private func fallbackResult(message: String) -> TeachingRecordFetchResult {
        return TeachingRecordFetchResult(
            lessonRecords: [],
            message: message,
            diagnostics: TeachingRecordDiagnostics(
                source: "Heptabase Local Backup",
                queries: [],
                matchedItems: [],
                fallbackPaths: [],
                notes: [message]
            )
        )
    }

    private func fileLooksDedicatedToStudent(fileURL: URL, content: String, candidateNames: [String]) -> Bool {
        let normalizedFilename = normalize(fileURL.deletingPathExtension().lastPathComponent)
        if candidateNames.contains(where: { normalizedFilename.contains(normalize($0)) }) { return true }
        if let firstHeading = content.components(separatedBy: .newlines).first(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("#") }) {
            let normalizedHeading = normalize(firstHeading)
            if candidateNames.contains(where: { normalizedHeading.contains(normalize($0)) }) { return true }
        }
        return false
    }

    private func extractFallbackLesson(from content: String, fileURL: URL, candidateNames: [String], isDedicatedFile: Bool) -> LocalLessonExtraction? {
        let normalizedSuffix = normalize(titleSuffix)
        let lines = content.components(separatedBy: .newlines)

        var targetLine: String?
        for line in lines {
            let normalizedLine = normalize(line)
            if normalizedLine.contains(normalizedSuffix) && candidateNames.contains(where: { normalizedLine.contains(normalize($0)) }) {
                targetLine = line
                break
            }
        }
        guard let matchedLine = targetLine else { return nil }

        if isDedicatedFile {
            let title = preferredTitle(from: lines, candidateNames: candidateNames)
            let snippet = extractDedicatedLessonSnippet(from: lines)
            let preview = firstMeaningfulPreviewLine(from: snippet)
            guard !snippet.isEmpty, !preview.isEmpty else { return nil }
            return LocalLessonExtraction(
                title: title,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: title),
                preview: preview,
                content: snippet
            )
        } else {
            let cleanLine = cleanFallbackLine(matchedLine)
            guard !cleanLine.isEmpty else { return nil }
            return LocalLessonExtraction(
                title: cleanLine,
                date: extractDateFromFilename(fileURL.lastPathComponent) ?? extractDate(from: cleanLine),
                preview: cleanLine,
                content: "> " + matchedLine.trimmingCharacters(in: .whitespacesAndNewlines) + "\n\n*(摘錄自 \(fileURL.lastPathComponent))*"
            )
        }
    }

    private func preferredTitle(from lines: [String], candidateNames: [String]) -> String {
        for line in lines {
            let normalizedLine = normalize(line)
            if normalizedLine.contains(normalize(titleSuffix)), candidateNames.contains(where: { normalizedLine.contains(normalize($0)) }) {
                let cleaned = cleanFallbackLine(line)
                if !cleaned.isEmpty { return cleaned }
            }
        }
        for line in lines where line.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("#") {
            let cleaned = cleanFallbackLine(line)
            if !cleaned.isEmpty { return cleaned }
        }
        return "數位管理教學"
    }

    private func extractDedicatedLessonSnippet(from lines: [String]) -> String {
        if let summaryIndex = lines.firstIndex(where: { $0.contains("### 教學內容摘要") }) {
            let start = min(lines.count - 1, summaryIndex + 1)
            let body = Array(lines[start...])
            return cleanedSnippet(from: body)
        }
        return cleanedSnippet(from: lines)
    }

    private func cleanedSnippet(from lines: [String]) -> String {
        lines.map { cleanFallbackLine($0) }.filter { !$0.isEmpty }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func firstMeaningfulPreviewLine(from snippet: String) -> String {
        snippet.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
               .first(where: { !$0.isEmpty && !$0.hasPrefix("#") && !$0.hasPrefix("{{") && !$0.contains("今日行程") }) ?? ""
    }

    private func cleanFallbackLine(_ line: String) -> String {
        let prefixes = ["*   教學內容：", "* 教學內容：", "- 教學內容：", "教學內容：", "{{DONE}}", "{{TODO}}", "#", "*", "-"]
        var value = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for prefix in prefixes {
            while value.hasPrefix(prefix) { value = String(value.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines) }
        }
        return value
    }

    private func extractDateFromFilename(_ filename: String) -> String? {
        guard let match = filename.range(of: #"Lesson_(\d{4})(\d{2})(\d{2})_"#, options: .regularExpression) else { return nil }
        let raw = String(filename[match]).replacingOccurrences(of: "Lesson_", with: "").replacingOccurrences(of: "_", with: "")
        guard raw.count >= 8 else { return nil }
        let value = String(raw.prefix(8))
        return "\(value.prefix(4))-\(value.dropFirst(4).prefix(2))-\(value.dropFirst(6).prefix(2))"
    }

    private func deduplicated(_ records: [LessonRecord]) -> [LessonRecord] {
        var seen = Set<String>()
        var output: [LessonRecord] = []
        for record in records {
            let key = "\(record.date)|\(record.title)|\(record.path)"
            if seen.insert(key).inserted { output.append(record) }
        }
        return output
    }
}
