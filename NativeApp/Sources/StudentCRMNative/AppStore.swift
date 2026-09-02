import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    private enum HeptabaseDefaultsKey {
        static let endpoint = "HeptabaseMCPEndpoint"
        static let bearerToken = "HeptabaseMCPBearerToken"
        static let refreshToken = "HeptabaseMCPRefreshToken"
        static let expiresAt = "HeptabaseMCPAccessTokenExpiresAt"
        static let scope = "HeptabaseMCPScope"
    }

    @Published var selectedSection: SidebarSection? = .dashboard
    @Published var students: [StudentRecord] = []
    @Published var studentPredictions: [String: StudentPrediction] = [:]
    @Published var aliasMappings: [AliasMapping] = []
    @Published var program: ProgramInfo?
    @Published var venue: VenueInfo?
    @Published var attendanceRecords: [AttendanceRecord] = []
    @Published var venueLedger: [VenueLedgerRecord] = []
    @Published var roundGroups: [StudentRoundGroup] = []
    @Published var summary: AppleCEOSummary = .empty
    @Published var oneOnOneSummary: OneOnOneSummary = .empty
    @Published var lastLessons: [String: String] = [:]
    @Published var importStatus: String = "尚未匯入"
    @Published var sourceDirectory: String = ""
    @Published var latestActionMessage: String = ""
    @Published var heptabaseConnectionStatus: String = "Heptabase 未連線"
    @Published var heptabaseStatusDetail: String = "可使用 OAuth bridge 或手動 Bearer Token"
    @Published var heptabaseEndpoint: String = "https://api.heptabase.com/mcp"
    @Published var heptabaseBearerToken: String = ""
    @Published var studentAPIEndpoint: String = "http://127.0.0.1:8888"
    @Published var studentAPISyncStatus: String = "API 尚未同步"
    @Published var attendancePreviewResult: AttendancePreviewResult?
    @Published var attendancePreviewStatus: String = "尚未產生預覽"

    private let database = DatabaseManager()
    private let importer = JSONImportService()
    private let cloudAPI = StudentCloudAPIService()
    private let notificationManager = NotificationManager.shared
    private let aliasScope = "apple_alias"

    func bootstrap() async {
        do {
            loadHeptabaseSettings()
            try database.prepare()
            let resolved = try importer.resolveSourceDirectory()
            sourceDirectory = resolved.path
            try importer.importAll(into: database, sourceDirectory: resolved)
            try reload()
            await notificationManager.refreshAppleCEONotifications(roundGroups: roundGroups)
            importStatus = "已從正式資料匯入"
        } catch {
            importStatus = "匯入失敗：\(error.localizedDescription)"
        }
    }

    func loadHeptabaseSettings() {
        let defaults = UserDefaults.standard
        heptabaseEndpoint = defaults.string(forKey: HeptabaseDefaultsKey.endpoint) ?? "https://api.heptabase.com/mcp"
        heptabaseBearerToken = defaults.string(forKey: HeptabaseDefaultsKey.bearerToken) ?? ""
        refreshHeptabaseConnectionStatus()
    }

    func saveHeptabaseSettings() {
        let defaults = UserDefaults.standard
        let endpoint = heptabaseEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let token = heptabaseBearerToken.trimmingCharacters(in: .whitespacesAndNewlines)

        defaults.set(endpoint.isEmpty ? "https://api.heptabase.com/mcp" : endpoint, forKey: HeptabaseDefaultsKey.endpoint)
        defaults.set(token, forKey: HeptabaseDefaultsKey.bearerToken)

        heptabaseEndpoint = endpoint.isEmpty ? "https://api.heptabase.com/mcp" : endpoint
        heptabaseBearerToken = token
        refreshHeptabaseConnectionStatus()
        latestActionMessage = token.isEmpty ? "已儲存 Heptabase endpoint，尚未設定 Bearer Token" : "已儲存 Heptabase MCP 設定"
        heptabaseStatusDetail = latestActionMessage
    }

    func clearHeptabaseToken() {
        UserDefaults.standard.removeObject(forKey: HeptabaseDefaultsKey.bearerToken)
        heptabaseBearerToken = ""
        refreshHeptabaseConnectionStatus()
        latestActionMessage = "已清除 Heptabase Bearer Token"
        heptabaseStatusDetail = latestActionMessage
    }

    func reloadFromJSON() async {
        do {
            let resolved = try importer.resolveSourceDirectory()
            sourceDirectory = resolved.path
            try importer.importAll(into: database, sourceDirectory: resolved)
            try reload()
            await notificationManager.refreshAppleCEONotifications(roundGroups: roundGroups)
            importStatus = "重新匯入完成"
        } catch {
            importStatus = "重新匯入失敗：\(error.localizedDescription)"
        }
    }

    func reloadStudentsFromAPI() async {
        do {
            let result = try await cloudAPI.fetchStudents(endpoint: studentAPIEndpoint)
            try database.replaceStudents(result.students)
            try reload()
            importStatus = "API 同步完成"
            studentAPISyncStatus = result.syncSummary
            latestActionMessage = "已從 StudentCRM API 同步 \(result.students.count) 位學員"
        } catch {
            importStatus = "API 同步失敗"
            studentAPISyncStatus = error.localizedDescription
            latestActionMessage = "StudentCRM API 同步失敗：\(error.localizedDescription)"
        }
    }

    func reloadAppleCEOProgramFromAPI() async {
        do {
            let result = try await cloudAPI.fetchAppleCEOProgram(endpoint: studentAPIEndpoint)
            try database.replaceAppleCEOProgram(
                program: result.program,
                venue: result.venue,
                attendanceRecords: result.attendanceRecords,
                venueLedger: result.venueLedger,
                roundGroups: result.roundGroups
            )
            try reload()
            studentAPISyncStatus = result.syncSummary
            latestActionMessage = "已從 StudentCRM API 同步蘋果總裁班班務"
        } catch {
            studentAPISyncStatus = error.localizedDescription
            latestActionMessage = "蘋果總裁班 API 同步失敗：\(error.localizedDescription)"
        }
    }

    func previewAppleCEOAttendanceFromAPI(date: Date, venue: String, attendeesText: String, note: String) async -> Bool {
        let attendees = attendeesText
            .components(separatedBy: CharacterSet(charactersIn: "、,，\n"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        guard !attendees.isEmpty else {
            attendancePreviewResult = nil
            attendancePreviewStatus = "預覽失敗：至少要有一位出席者"
            latestActionMessage = attendancePreviewStatus
            return false
        }

        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        let dateString = formatter.string(from: date)

        do {
            attendancePreviewStatus = "正在產生 API 預覽..."
            let result = try await cloudAPI.previewAppleCEOAttendance(
                endpoint: studentAPIEndpoint,
                date: dateString,
                venue: venue,
                attendees: attendees,
                note: note
            )
            attendancePreviewResult = result
            attendancePreviewStatus = "預覽完成：命中 \(result.summary.matchedCount) 位，警告 \(result.summary.warningCount) 則"
            latestActionMessage = "已產生蘋果總裁班上課紀錄預覽，未寫入資料"
            return true
        } catch {
            attendancePreviewResult = nil
            attendancePreviewStatus = "預覽失敗：\(error.localizedDescription)"
            latestActionMessage = attendancePreviewStatus
            return false
        }
    }

    func connectHeptabaseMCP() async {
        let token = heptabaseBearerToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let endpointText = heptabaseEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        heptabaseConnectionStatus = "Heptabase 連線中"
        heptabaseStatusDetail = token.isEmpty ? "正在啟動 OAuth bridge…" : "正在驗證 Bearer Token…"

        if !token.isEmpty {
            guard let endpoint = URL(string: endpointText.isEmpty ? "https://api.heptabase.com/mcp" : endpointText) else {
                heptabaseConnectionStatus = "Heptabase 端點無效"
                latestActionMessage = "Heptabase MCP endpoint 格式錯誤"
                heptabaseStatusDetail = latestActionMessage
                return
            }

            do {
                let tools = try await Task.detached(priority: .userInitiated) {
                    let client = HeptabaseMCPClient(endpoint: endpoint, bearerToken: token)
                    return try client.listToolNames()
                }.value
                let summary = tools.isEmpty ? "Heptabase MCP 已連線" : "Heptabase MCP 已連線：\(tools.joined(separator: "、"))"
                heptabaseConnectionStatus = summary
                latestActionMessage = "Heptabase Bearer Token 驗證成功"
                heptabaseStatusDetail = latestActionMessage
            } catch {
                heptabaseConnectionStatus = "Heptabase Token 驗證失敗"
                latestActionMessage = "Heptabase Bearer Token 驗證失敗：\(error.localizedDescription)"
                heptabaseStatusDetail = latestActionMessage
            }
            return
        }

        do {
            guard let endpoint = URL(string: endpointText.isEmpty ? "https://api.heptabase.com/mcp" : endpointText) else {
                heptabaseConnectionStatus = "Heptabase 端點無效"
                latestActionMessage = "Heptabase MCP endpoint 格式錯誤"
                heptabaseStatusDetail = latestActionMessage
                return
            }

            let result = try await Task.detached(priority: .userInitiated) {
                try await HeptabaseOAuthManager(endpoint: endpoint).connect()
            }.value
            persistHeptabaseOAuthResult(result)
            heptabaseBearerToken = result.accessToken
            heptabaseConnectionStatus = "Heptabase MCP 已連線"
            latestActionMessage = "Heptabase 原生 OAuth 驗證成功"
            let expiry = result.expiresAt.map(Self.heptabaseDateTimeFormatter.string(from:)) ?? "未知"
            heptabaseStatusDetail = "access token 已取得，效期至 \(expiry)"
        } catch {
            heptabaseConnectionStatus = "Heptabase 連線失敗"
            latestActionMessage = "Heptabase 原生 OAuth 失敗：\(error.localizedDescription)"
            heptabaseStatusDetail = latestActionMessage
        }
    }

    private func refreshHeptabaseConnectionStatus() {
        if !heptabaseBearerToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            heptabaseConnectionStatus = "Heptabase Token 已設定"
            heptabaseStatusDetail = "已設定 Bearer Token，按「連線 Heptabase」驗證"
        } else {
            heptabaseConnectionStatus = "Heptabase 未連線"
            heptabaseStatusDetail = "尚未設定 Token，可直接啟動原生 OAuth"
        }
    }

    private func persistHeptabaseOAuthResult(_ result: HeptabaseOAuthConnectResult) {
        let defaults = UserDefaults.standard
        defaults.set(result.accessToken, forKey: HeptabaseDefaultsKey.bearerToken)
        defaults.set(result.refreshToken, forKey: HeptabaseDefaultsKey.refreshToken)
        defaults.set(result.scope, forKey: HeptabaseDefaultsKey.scope)
        if let expiresAt = result.expiresAt {
            defaults.set(expiresAt, forKey: HeptabaseDefaultsKey.expiresAt)
        } else {
            defaults.removeObject(forKey: HeptabaseDefaultsKey.expiresAt)
        }
    }

    private static let heptabaseDateTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return formatter
    }()

    func addAttendance(date: Date, venue: String, attendeesText: String, note: String) async -> Bool {
        await upsertAttendance(
            recordID: nil,
            date: date,
            venue: venue,
            attendeesText: attendeesText,
            note: note
        )
    }

    func updateAttendance(record: AttendanceRecord, date: Date, venue: String, attendeesText: String, note: String) async -> Bool {
        await upsertAttendance(
            recordID: record.id,
            date: date,
            venue: venue,
            attendeesText: attendeesText,
            note: note
        )
    }

    private func upsertAttendance(recordID: String?, date: Date, venue: String, attendeesText: String, note: String) async -> Bool {
        let rawAttendees = attendeesText
            .components(separatedBy: CharacterSet(charactersIn: "、,\n"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        guard !rawAttendees.isEmpty else {
            latestActionMessage = "新增失敗：至少要有一位出席者"
            return false
        }

        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        let dateString = formatter.string(from: date)

        do {
            // 1. 先將出席日期分配進學員的輪數紀錄中
            try autoAssignAttendanceToLatestRounds(dateString: dateString, attendees: rawAttendees)

            // 2. 重新讀取，確保 roundGroups 已更新為最新的累積次數
            try reload()

            // 3. 根據更新後的資料產生帶有「累積次數 (x/8)」的詳細出席列表
            let attendeeDetails = rawAttendees.map { attendee -> AttendeeDetail in
                let cumulative = fetchAttendeeCumulative(for: attendee)
                return AttendeeDetail(name: attendee, cumulative: cumulative)
            }

            // 4. 寫入出席紀錄表
            try database.insertAttendance(
                AttendanceRecord(
                    id: recordID ?? "attendance-\(dateString)-\(Int(Date().timeIntervalSince1970))",
                    date: dateString,
                    venue: venue,
                    attendeeCount: attendeeDetails.count,
                    attendeeDetails: attendeeDetails,
                    note: note
                )
            )

            // 5. 再次重新讀取，同步所有狀態
            try reload()
            try persistAppleCEOJSON()
            await notificationManager.refreshAppleCEONotifications(roundGroups: roundGroups)
            latestActionMessage = recordID == nil ? "已新增上課紀錄：\(dateString)" : "已更新上課紀錄：\(dateString)"
            return true
        } catch {
            latestActionMessage = "新增失敗：\(error.localizedDescription)"
            return false
        }
    }

    private func fetchAttendeeCumulative(for name: String) -> String {
        guard let canonical = canonicalAppleCEOStudentName(for: name),
              let group = roundGroups.first(where: { $0.studentName == canonical }),
              let latest = group.latestRound else {
            return ""
        }
        return "\(latest.attendedCount)/8"
    }

    func addVenueLedger(date: Date, type: String, headcountText: String, amountText: String, note: String) async -> Bool {
        await upsertVenueLedger(
            recordID: nil,
            date: date,
            type: type,
            headcountText: headcountText,
            amountText: amountText,
            note: note
        )
    }

    func updateVenueLedger(record: VenueLedgerRecord, date: Date, type: String, headcountText: String, amountText: String, note: String) async -> Bool {
        await upsertVenueLedger(
            recordID: record.id,
            date: date,
            type: type,
            headcountText: headcountText,
            amountText: amountText,
            note: note
        )
    }

    private func upsertVenueLedger(recordID: String?, date: Date, type: String, headcountText: String, amountText: String, note: String) async -> Bool {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        let dateString = formatter.string(from: date)

        let headcount = Int(headcountText.trimmingCharacters(in: .whitespacesAndNewlines))
        let rawAmount = Int(amountText.trimmingCharacters(in: .whitespacesAndNewlines))
        let costPerPerson = venue?.costPerPerson ?? 0

        let resolvedAmount: Int
        if let rawAmount {
            if type == "扣款" {
                resolvedAmount = rawAmount > 0 ? -rawAmount : rawAmount
            } else {
                resolvedAmount = rawAmount
            }
        } else if type == "扣款", let headcount {
            resolvedAmount = -(headcount * costPerPerson)
        } else {
            latestActionMessage = "新增失敗：請輸入金額，或在扣款時輸入人數"
            return false
        }

        let filtered = venueLedger.filter { $0.id != recordID }
        let previousBalance = filtered.first?.balanceAfter ?? 0
        let nextBalance = previousBalance + resolvedAmount

        do {
            try database.insertVenueLedger(
                VenueLedgerRecord(
                    id: recordID ?? "ledger-\(dateString)-\(Int(Date().timeIntervalSince1970))",
                    date: dateString,
                    type: type,
                    amount: resolvedAmount,
                    headcount: headcount,
                    note: note,
                    balanceAfter: nextBalance
                )
            )
            try reload()
            try persistAppleCEOJSON()
            latestActionMessage = recordID == nil ? "已新增場地費紀錄：\(dateString)" : "已更新場地費紀錄：\(dateString)"
            return true
        } catch {
            latestActionMessage = "新增失敗：\(error.localizedDescription)"
            return false
        }
    }

    func deleteAttendance(_ record: AttendanceRecord) async {
        do {
            try database.deleteAttendance(id: record.id)
            try reload()
            try persistAppleCEOJSON()
            latestActionMessage = "已刪除上課紀錄：\(record.date)"
        } catch {
            latestActionMessage = "刪除失敗：\(error.localizedDescription)"
        }
    }

    func deleteVenueLedger(_ record: VenueLedgerRecord) async {
        do {
            try database.deleteVenueLedger(id: record.id)
            try reload()
            try persistAppleCEOJSON()
            latestActionMessage = "已刪除場地費紀錄：\(record.date)"
        } catch {
            latestActionMessage = "刪除失敗：\(error.localizedDescription)"
        }
    }

    func addAlias(alias: String, canonicalName: String) async -> Bool {
        let normalizedAlias = alias.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedCanonical = canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !normalizedAlias.isEmpty, !normalizedCanonical.isEmpty else {
            latestActionMessage = "新增別名失敗：請填入別名與正式姓名"
            return false
        }

        guard roundGroups.contains(where: { $0.studentName == normalizedCanonical }) else {
            latestActionMessage = "新增別名失敗：找不到對應學員 \(normalizedCanonical)"
            return false
        }

        do {
            try database.insertMeta(scope: aliasScope, key: normalizedAlias, value: normalizedCanonical)
            try reload()
            latestActionMessage = "已新增別名：\(normalizedAlias) → \(normalizedCanonical)"
            return true
        } catch {
            latestActionMessage = "新增別名失敗：\(error.localizedDescription)"
            return false
        }
    }

    func deleteAlias(_ mapping: AliasMapping) async {
        do {
            try database.deleteMeta(scope: aliasScope, key: mapping.alias)
            try reload()
            latestActionMessage = "已刪除別名：\(mapping.alias)"
        } catch {
            latestActionMessage = "刪除別名失敗：\(error.localizedDescription)"
        }
    }

    private func autoAssignAttendanceToLatestRounds(dateString: String, attendees: [String]) throws {
        for attendee in attendees {
            guard let canonicalName = canonicalAppleCEOStudentName(for: attendee),
                  let group = roundGroups.first(where: { $0.studentName == canonicalName }),
                  let latest = group.latestRound else {
                continue
            }

            if latest.sessions.contains(dateString) {
                continue
            }

            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "zh_Hant_TW")
            formatter.dateFormat = "yyyy-MM-dd"

            if let nextEmptyIndex = latest.sessions.firstIndex(where: { $0.isEmpty }) {
                // 現有輪數尚有空位，填入日期
                var updatedSessions = latest.sessions
                updatedSessions[nextEmptyIndex] = dateString

                let expiryDate = calculateExpiryDate(for: updatedSessions)
                let updatedRound = StudentRoundRecord(
                    id: latest.id,
                    studentName: latest.studentName,
                    label: latest.label,
                    paymentStatus: latest.paymentStatus,
                    sessions: updatedSessions,
                    attendedCount: updatedSessions.filter { !$0.isEmpty }.count,
                    expiryDate: expiryDate,
                    isExpired: expiryDate.map { formatter.date(from: $0)! < Calendar.current.startOfDay(for: Date()) } ?? false,
                    isActive: latest.isActive,
                    sortOrder: latest.sortOrder
                )
                try database.updateRound(updatedRound)
            } else {
                // 現有輪數已滿，自動開啟新的一輪
                let newSessions = [dateString] + Array(repeating: "", count: 7)
                let expiryDate = calculateExpiryDate(for: newSessions)
                let newRound = StudentRoundRecord(
                    id: "round-\(latest.studentName)-\(Int(Date().timeIntervalSince1970))-\(Int.random(in: 1...999))",
                    studentName: latest.studentName,
                    label: "新一輪 (自動建立)",
                    paymentStatus: "未收",
                    sessions: newSessions,
                    attendedCount: 1,
                    expiryDate: expiryDate,
                    isExpired: false,
                    isActive: true,
                    sortOrder: latest.sortOrder
                )
                try database.insertRound(newRound, sortOrder: newRound.sortOrder)
            }
        }
    }

    private func calculateExpiryDate(for sessions: [String]) -> String? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"

        guard let first = sessions.first(where: { !$0.isEmpty }),
              let firstDate = formatter.date(from: first),
              let expiry = Calendar.current.date(byAdding: .month, value: 4, to: firstDate) else {
            return nil
        }
        return formatter.string(from: expiry)
    }

    private func canonicalAppleCEOStudentName(for rawName: String) -> String? {
        let trimmed = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        if roundGroups.contains(where: { $0.studentName == trimmed }) {
            return trimmed
        }

        if let mapping = aliasMappings.first(where: { $0.alias == trimmed }) {
            return mapping.canonicalName
        }

        if let matchedStudent = students.first(where: {
            $0.name == trimmed || $0.aliases.contains(trimmed)
        }), roundGroups.contains(where: { $0.studentName == matchedStudent.name }) {
            return matchedStudent.name
        }

        let builtInAliases: [String: String] = [
            "Roger": "Roger老師",
            "Roger老師 ": "Roger老師",
            "Roger 老師": "Roger老師",
            "邦寧大哥": "劉邦寧",
            "方醫師": "方柏敦",
        ]
        return builtInAliases[trimmed]
    }

    private func persistAppleCEOJSON() throws {
        guard let program, let venue else { return }
        let resolved = try importer.resolveSourceDirectory()
        try importer.exportAppleCEOJSON(
            sourceDirectory: resolved,
            program: program,
            venue: venue,
            summary: summary,
            attendanceRecords: attendanceRecords,
            venueLedger: venueLedger,
            roundGroups: roundGroups
        )
    }

    private func reload() throws {
        let rawStudents = try database.fetchStudents().filter { $0.name != "Apple CEO Class" && $0.name != "蘋果總裁班" }

        // De-duplicate students by normalized name, picking the one with the most lessons,
        // but merging tags and aliases to preserve dual-status info (e.g., Roger/Lucia)
        let grouped = Dictionary(grouping: rawStudents) { normalizeName($0.name) }
        var uniqueStudents = grouped.values.compactMap { (group: [StudentRecord]) -> StudentRecord? in
            guard let best = group.sorted(by: { $0.lessonsCount > $1.lessonsCount }).first else { return nil }

            // Merge tags and aliases from all duplicates in the group
            let allTags = Set(group.flatMap { $0.tags })
            let allAliases = Set(group.flatMap { $0.aliases })

            return StudentRecord(
                id: best.id,
                name: best.name,
                aliases: Array(allAliases).sorted(),
                file: best.file,
                lessonsCount: best.lessonsCount,
                latestDate: best.latestDate,
                nextLesson: best.nextLesson,
                tags: Array(allTags).sorted()
            )
        }

        let computedLastLessons = buildLastLessonDates(for: uniqueStudents)
        uniqueStudents.sort { lhs, rhs in
            let lOrder = sortPriority(lhs.nextLesson)
            let rOrder = sortPriority(rhs.nextLesson)

            // 1. 優先照下次上課日期排序 (越快上課的排越前面)
            if lOrder != rOrder { return lOrder < rOrder }
            if lOrder != 3 && lhs.nextLesson != rhs.nextLesson {
                return lhs.nextLesson < rhs.nextLesson
            }

            // 2. 如果都沒有下次上課 (安排中)，則依照「最近上課日期」由新到舊排序
            let lLast = computedLastLessons[lhs.id] ?? "TBD"
            let rLast = computedLastLessons[rhs.id] ?? "TBD"

            if lLast == "TBD" && rLast != "TBD" { return false }
            if rLast == "TBD" && lLast != "TBD" { return true }

            if lLast != rLast {
                return lLast > rLast
            }

            // 3. 最後照名稱排序
            return lhs.name < rhs.name
        }
        students = uniqueStudents

        program = try database.fetchProgram()
        venue = try database.fetchVenue()
        attendanceRecords = try database.fetchAttendance()
        venueLedger = try database.fetchVenueLedger()
        roundGroups = try database.fetchRoundGroups()
        let aliases = try database.fetchMetaValues(scope: aliasScope)
        aliasMappings = aliases.keys.sorted().map { key in
            AliasMapping(id: key, alias: key, canonicalName: aliases[key] ?? "")
        }
        summary = try database.fetchSummary()
        lastLessons = buildLastLessonDates(for: students)
        studentPredictions = buildStudentPredictions(for: students)
        oneOnOneSummary = buildOneOnOneSummary(for: students, predictions: studentPredictions)
    }

    private func buildOneOnOneSummary(for students: [StudentRecord], predictions: [String: StudentPrediction]) -> OneOnOneSummary {
        let today = formatDate(Date())
        let tomorrow = formatDate(Calendar.current.date(byAdding: .day, value: 1, to: Date())!)

        let pendingCount = students.filter { $0.nextLesson.contains(today) || $0.nextLesson.contains(tomorrow) }
        let noNextCount = students.filter { $0.nextLesson.isEmpty || $0.nextLesson == "安排中" }

        var stable = 0
        var risk = 0
        var freezing = 0

        for student in students {
            if let pred = predictions[student.id] {
                if pred.badge == "🟢" { stable += 1 }
                else if pred.badge == "🔴" { risk += 1 }
                else if pred.badge == "🧊" { freezing += 1 }
            }
        }

        return OneOnOneSummary(
            totalStudents: students.count,
            pendingLessonsCount: pendingCount.count,
            noNextLessonCount: noNextCount.count,
            stableCount: stable,
            riskCount: risk,
            freezingCount: freezing,
            pendingLessonNames: pendingCount.map(\.name),
            noNextLessonNames: noNextCount.map(\.name)
        )
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private func buildLastLessonDates(for students: [StudentRecord]) -> [String: String] {
        Dictionary(uniqueKeysWithValues: students.map { student in
            let date = student.latestDate.isEmpty ? "TBD" : student.latestDate
            return (student.id, date)
        })
    }

    private func buildStudentPredictions(for students: [StudentRecord]) -> [String: StudentPrediction] {
        Dictionary(uniqueKeysWithValues: students.map { student in
            (student.id, predictStudentStatus(for: student))
        })
    }

    private func predictStudentStatus(for student: StudentRecord) -> StudentPrediction {
        let lessonPaths = lessonPaths(for: student)
        guard !lessonPaths.isEmpty else {
            return StudentPrediction(
                badge: "⚪",
                status: "無預測資料",
                style: .placeholder,
                reason: "系統中尚未找到有效的上課排程或筆記紀錄。"
            )
        }

        let daysSinceLastLesson = latestLessonDate(from: lessonPaths).map {
            Calendar.current.dateComponents([.day], from: $0, to: Date()).day ?? -1
        } ?? -1

        let averageLength = averageLessonLength(from: Array(lessonPaths.suffix(3)))

        if daysSinceLastLesson >= 0, daysSinceLastLesson <= 14 {
            return StudentPrediction(
                badge: "🟢",
                status: "穩定留存",
                style: .full,
                reason: "距離上次上課 \(daysSinceLastLesson) 天，仍在穩定互動區間。"
            )
        }

        if averageLength < 200 {
            return StudentPrediction(
                badge: "🔴",
                status: "高流失風險",
                style: .missing,
                reason: "已超過兩週未上課，且近期筆記平均字數偏低，需優先關心。"
            )
        }

        return StudentPrediction(
            badge: "🧊",
            status: "冰凍期 (需關心)",
            style: .short,
            reason: "已超過兩週未上課，但近期筆記內容仍扎實，建議主動回訪。"
        )
    }

    private func lessonPaths(for student: StudentRecord) -> [String] {
        let projectRoot = URL(fileURLWithPath: sourceDirectory)
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        let lessonDirectories = [
            projectRoot.appendingPathComponent("StudentCRM/cache").path,
            projectRoot.appendingPathComponent("01.Docs/teaching").path
        ]

        let candidateNames = Set(([student.name] + student.aliases).map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        })

        let fm = FileManager.default
        var matched: [(path: String, date: String)] = []

        for directory in lessonDirectories where fm.fileExists(atPath: directory) {
            guard let files = try? fm.contentsOfDirectory(atPath: directory) else { continue }
            for file in files where file.hasPrefix("Lesson_") && file.hasSuffix(".md") {
                guard let parsed = parseLessonFilename(file),
                      candidateNames.contains(parsed.studentName) else { continue }
                let fullPath = URL(fileURLWithPath: directory).appendingPathComponent(file).path
                matched.append((fullPath, parsed.date))
            }
        }

        return matched
            .sorted { $0.date < $1.date }
            .map(\.path)
    }

    private func parseLessonFilename(_ file: String) -> (date: String, studentName: String)? {
        guard file.hasPrefix("Lesson_"), file.hasSuffix(".md") else { return nil }
        let body = String(file.dropFirst("Lesson_".count).dropLast(".md".count))
        let parts = body.split(separator: "_", maxSplits: 1).map(String.init)
        guard parts.count == 2, parts[0].count == 8 else { return nil }
        let digits = parts[0]
        let date = "\(digits.prefix(4))-\(digits.dropFirst(4).prefix(2))-\(digits.suffix(2))"
        return (date, parts[1])
    }

    private func latestLessonDate(from lessonPaths: [String]) -> Date? {
        lessonPaths
            .compactMap { path in
                let filename = URL(fileURLWithPath: path).lastPathComponent
                return parseLessonFilename(filename)?.date
            }
            .compactMap { Self.dateFormatter.date(from: $0) }
            .max()
    }

    private func averageLessonLength(from lessonPaths: [String]) -> Int {
        let contents = lessonPaths.compactMap { try? String(contentsOfFile: $0, encoding: .utf8) }
        guard !contents.isEmpty else { return 0 }
        let total = contents.reduce(0) { $0 + $1.count }
        return total / contents.count
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    private func normalizeName(_ name: String) -> String {
        return name
            .lowercased()
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "　", with: "")
            .replacingOccurrences(of: "-zoom", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func sortPriority(_ nextLesson: String) -> Int {
        if nextLesson.isEmpty || nextLesson == "待定" || nextLesson == "未安排" || nextLesson == "安排中" {
            return 3
        }
        let today = formatDate(Date())
        if nextLesson < today {
            return 2
        }
        return 1
    }
}
