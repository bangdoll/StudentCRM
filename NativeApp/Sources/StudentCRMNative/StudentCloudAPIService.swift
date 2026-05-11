import Foundation

enum StudentCloudAPIError: Error, LocalizedError {
    case invalidEndpoint
    case invalidResponse
    case httpStatus(Int)

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "StudentCRM API endpoint 格式錯誤"
        case .invalidResponse:
            return "StudentCRM API 回應格式錯誤"
        case .httpStatus(let code):
            return "StudentCRM API HTTP \(code)"
        }
    }
}

struct StudentCloudAPIService {
    func fetchStudents(endpoint: String) async throws -> StudentCloudStudentsResult {
        let normalized = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let baseURL = URL(string: normalized.isEmpty ? "http://127.0.0.1:8888" : normalized) else {
            throw StudentCloudAPIError.invalidEndpoint
        }

        let url = baseURL.appendingPathComponent("api/students")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw StudentCloudAPIError.invalidResponse
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw StudentCloudAPIError.httpStatus(httpResponse.statusCode)
        }

        let decoder = JSONDecoder()
        let payload = try decoder.decode(StudentCloudAPIResponse.self, from: data)
        return StudentCloudStudentsResult(
            students: payload.students.map(\.record),
            syncSummary: payload.sync.summary
        )
    }

    func fetchAppleCEOProgram(endpoint: String) async throws -> StudentCloudAppleCEOResult {
        let normalized = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let baseURL = URL(string: normalized.isEmpty ? "http://127.0.0.1:8888" : normalized) else {
            throw StudentCloudAPIError.invalidEndpoint
        }

        let url = baseURL.appendingPathComponent("api/program/apple-ceo")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw StudentCloudAPIError.invalidResponse
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw StudentCloudAPIError.httpStatus(httpResponse.statusCode)
        }

        let payload = try JSONDecoder().decode(StudentCloudAppleCEOResponse.self, from: data)
        return payload.result
    }

    func previewAppleCEOAttendance(endpoint: String, date: String, venue: String, attendees: [String], note: String) async throws -> AttendancePreviewResult {
        let normalized = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let baseURL = URL(string: normalized.isEmpty ? "http://127.0.0.1:8888" : normalized) else {
            throw StudentCloudAPIError.invalidEndpoint
        }

        let url = baseURL.appendingPathComponent("api/program/apple-ceo/preview/attendance")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(StudentCloudAttendancePreviewRequest(
            date: date,
            venue: venue,
            attendees: attendees,
            note: note
        ))

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw StudentCloudAPIError.invalidResponse
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw StudentCloudAPIError.httpStatus(httpResponse.statusCode)
        }

        return try JSONDecoder().decode(StudentCloudAttendancePreviewResponse.self, from: data).result
    }
}

struct StudentCloudStudentsResult {
    let students: [StudentRecord]
    let syncSummary: String
}

struct StudentCloudAppleCEOResult {
    let program: ProgramInfo
    let venue: VenueInfo
    let attendanceRecords: [AttendanceRecord]
    let venueLedger: [VenueLedgerRecord]
    let roundGroups: [StudentRoundGroup]
    let syncSummary: String
}

private struct StudentCloudAttendancePreviewRequest: Encodable {
    let date: String
    let venue: String
    let attendees: [String]
    let note: String
}

private struct StudentCloudAPIResponse: Decodable {
    let count: Int
    let students: [StudentCloudStudentRecord]
    let sync: StudentCloudSyncStatus
}

private struct StudentCloudStudentRecord: Decodable {
    let id: String
    let name: String
    let aliases: [String]?
    let file: String?
    let lessonsCount: Int?
    let latestDate: String?
    let nextLesson: String?
    let tags: [String]?

    var record: StudentRecord {
        StudentRecord(
            id: id,
            name: name,
            aliases: aliases ?? [],
            file: file ?? "",
            lessonsCount: lessonsCount ?? 0,
            latestDate: latestDate ?? "",
            nextLesson: nextLesson ?? "",
            tags: tags ?? []
        )
    }

    enum CodingKeys: String, CodingKey {
        case id, name, aliases, file, tags
        case lessonsCount = "lessons_count"
        case latestDate = "latest_date"
        case nextLesson = "next_lesson"
    }
}

private struct StudentCloudSyncStatus: Decodable {
    let engine: String
    let source: String
    let cachePath: String
    let lastError: String
    let checkedAt: String

    var summary: String {
        if lastError.isEmpty {
            return "API 引擎：\(engine)，來源：\(source)"
        }
        return "API 引擎：\(engine)，fallback：\(lastError)"
    }

    enum CodingKeys: String, CodingKey {
        case engine, source
        case cachePath = "cache_path"
        case lastError = "last_error"
        case checkedAt = "checked_at"
    }
}

private struct StudentCloudAppleCEOResponse: Decodable {
    let program: StudentCloudProgramInfo
    let venue: StudentCloudVenueInfo
    let attendanceRecords: [StudentCloudAttendanceRecord]
    let venueLedger: [StudentCloudVenueLedgerRecord]
    let studentRounds: [StudentCloudRoundGroup]
    let sync: StudentCloudProgramSyncStatus

    var result: StudentCloudAppleCEOResult {
        StudentCloudAppleCEOResult(
            program: program.record,
            venue: venue.record,
            attendanceRecords: attendanceRecords.enumerated().map { index, item in item.record(index: index) },
            venueLedger: venueLedger.enumerated().map { index, item in item.record(index: index) },
            roundGroups: studentRounds.map(\.group),
            syncSummary: "API 引擎：\(sync.engine)，來源：\(sync.source)"
        )
    }

    enum CodingKeys: String, CodingKey {
        case program, venue, sync
        case attendanceRecords = "attendance_records"
        case venueLedger = "venue_ledger"
        case studentRounds = "student_rounds"
    }
}

private struct StudentCloudProgramInfo: Decodable {
    let id: String
    let name: String
    let url: String
    let description: String
    let schedule: String
    let capacity: String
    let roundSize: Int
    let pricePerStudent: Int
    let validityRule: String
    let leaveRule: String
    let joinRule: String

    var record: ProgramInfo {
        ProgramInfo(
            id: id,
            name: name,
            url: url,
            description: description,
            schedule: schedule,
            capacity: capacity,
            roundSize: roundSize,
            pricePerStudent: pricePerStudent,
            validityRule: validityRule,
            leaveRule: leaveRule,
            joinRule: joinRule
        )
    }

    enum CodingKeys: String, CodingKey {
        case id, name, url, description, schedule, capacity
        case roundSize = "round_size"
        case pricePerStudent = "price_per_student"
        case validityRule = "validity_rule"
        case leaveRule = "leave_rule"
        case joinRule = "join_rule"
    }
}

private struct StudentCloudVenueInfo: Decodable {
    let name: String
    let address: String
    let parking: String
    let metro: String
    let costPerPerson: Int

    var record: VenueInfo {
        VenueInfo(
            name: name,
            address: address,
            parking: parking,
            metro: metro,
            costPerPerson: costPerPerson
        )
    }

    enum CodingKeys: String, CodingKey {
        case name, address, parking, metro
        case costPerPerson = "cost_per_person"
    }
}

private struct StudentCloudAttendanceRecord: Decodable {
    let id: String?
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendeeDetails: [AttendeeDetail]
    let note: String

    func record(index: Int) -> AttendanceRecord {
        AttendanceRecord(
            id: id ?? "attendance-\(date)-\(index)",
            date: date,
            venue: venue,
            attendeeCount: attendeeCount,
            attendeeDetails: attendeeDetails,
            note: note
        )
    }

    enum CodingKeys: String, CodingKey {
        case id, date, venue, note
        case attendeeCount = "attendee_count"
        case attendees
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id)
        date = try container.decode(String.self, forKey: .date)
        venue = try container.decode(String.self, forKey: .venue)
        attendeeCount = try container.decode(Int.self, forKey: .attendeeCount)
        note = try container.decodeIfPresent(String.self, forKey: .note) ?? ""
        if let details = try? container.decode([AttendeeDetail].self, forKey: .attendees) {
            attendeeDetails = details
        } else if let names = try? container.decode([String].self, forKey: .attendees) {
            attendeeDetails = names.map { AttendeeDetail(name: $0, cumulative: "") }
        } else {
            attendeeDetails = []
        }
    }
}

private struct StudentCloudVenueLedgerRecord: Decodable {
    let id: String?
    let date: String
    let type: String
    let amount: Int
    let headcount: Int?
    let note: String
    let balanceAfter: Int

    func record(index: Int) -> VenueLedgerRecord {
        VenueLedgerRecord(
            id: id ?? "ledger-\(date)-\(index)",
            date: date,
            type: type,
            amount: amount,
            headcount: headcount,
            note: note,
            balanceAfter: balanceAfter
        )
    }

    enum CodingKeys: String, CodingKey {
        case id, date, type, amount, headcount, note
        case balanceAfter = "balance_after"
    }
}

private struct StudentCloudRoundGroup: Decodable {
    let studentName: String
    let rounds: [StudentCloudRound]

    var group: StudentRoundGroup {
        let records = rounds.enumerated().map { index, round in
            round.record(studentName: studentName, sortOrder: index)
        }
        return StudentRoundGroup(
            id: studentName,
            studentName: studentName,
            latestRound: records.first,
            historyRounds: Array(records.dropFirst())
        )
    }

    enum CodingKeys: String, CodingKey {
        case rounds
        case studentName = "student_name"
    }
}

private struct StudentCloudRound: Decodable {
    let label: String
    let paymentStatus: String
    let sessions: [String]

    func record(studentName: String, sortOrder: Int) -> StudentRoundRecord {
        let actualSessions = sessions.filter { !$0.isEmpty }
        let expiry = Self.expiryDate(from: actualSessions.first)
        let today = Self.dateFormatter.string(from: Date())
        return StudentRoundRecord(
            id: "round-\(studentName)-\(sortOrder)",
            studentName: studentName,
            label: label,
            paymentStatus: paymentStatus,
            sessions: sessions,
            attendedCount: actualSessions.count,
            expiryDate: expiry,
            isExpired: expiry.map { $0 < today } ?? false,
            isActive: label.contains("進行中"),
            sortOrder: sortOrder
        )
    }

    enum CodingKeys: String, CodingKey {
        case label, sessions
        case paymentStatus = "payment_status"
    }

    private static func expiryDate(from firstSession: String?) -> String? {
        guard let firstSession,
              let date = dateFormatter.date(from: String(firstSession.prefix(10))),
              let expiry = Calendar.current.date(byAdding: .month, value: 4, to: date) else {
            return nil
        }
        return dateFormatter.string(from: expiry)
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

private struct StudentCloudProgramSyncStatus: Decodable {
    let engine: String
    let source: String
    let checkedAt: String

    enum CodingKeys: String, CodingKey {
        case engine, source
        case checkedAt = "checked_at"
    }
}

private struct StudentCloudAttendancePreviewResponse: Decodable {
    let status: String
    let requiresHumanConfirmation: Bool
    let willWrite: Bool
    let proposedRecord: StudentCloudAttendancePreviewRecord
    let affectedRounds: [StudentCloudAttendancePreviewRound]
    let warnings: [String]
    let summary: StudentCloudAttendancePreviewSummary

    var result: AttendancePreviewResult {
        AttendancePreviewResult(
            status: status,
            requiresHumanConfirmation: requiresHumanConfirmation,
            willWrite: willWrite,
            proposedRecord: proposedRecord.record,
            affectedRounds: affectedRounds.map(\.round),
            warnings: warnings,
            summary: summary.summary
        )
    }

    enum CodingKeys: String, CodingKey {
        case status, warnings, summary
        case requiresHumanConfirmation = "requires_human_confirmation"
        case willWrite = "will_write"
        case proposedRecord = "proposed_record"
        case affectedRounds = "affected_rounds"
    }
}

private struct StudentCloudAttendancePreviewRecord: Decodable {
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendees: [String]
    let note: String

    var record: AttendancePreviewRecord {
        AttendancePreviewRecord(
            date: date,
            venue: venue,
            attendeeCount: attendeeCount,
            attendees: attendees,
            note: note
        )
    }

    enum CodingKeys: String, CodingKey {
        case date, venue, attendees, note
        case attendeeCount = "attendee_count"
    }
}

private struct StudentCloudAttendancePreviewRound: Decodable {
    let studentName: String
    let action: String
    let before: StudentCloudAttendancePreviewRoundState
    let after: StudentCloudAttendancePreviewRoundState

    var round: AttendancePreviewRound {
        AttendancePreviewRound(
            studentName: studentName,
            action: action,
            before: before.state,
            after: after.state
        )
    }

    enum CodingKeys: String, CodingKey {
        case action, before, after
        case studentName = "student_name"
    }
}

private struct StudentCloudAttendancePreviewRoundState: Decodable {
    let label: String
    let sessions: [String]
    let attendedCount: Int
    let remainingCount: Int

    var state: AttendancePreviewRoundState {
        AttendancePreviewRoundState(
            label: label,
            sessions: sessions,
            attendedCount: attendedCount,
            remainingCount: remainingCount
        )
    }

    enum CodingKeys: String, CodingKey {
        case label, sessions
        case attendedCount = "attended_count"
        case remainingCount = "remaining_count"
    }
}

private struct StudentCloudAttendancePreviewSummary: Decodable {
    let attendeeCount: Int
    let matchedCount: Int
    let warningCount: Int

    var summary: AttendancePreviewSummary {
        AttendancePreviewSummary(
            attendeeCount: attendeeCount,
            matchedCount: matchedCount,
            warningCount: warningCount
        )
    }

    enum CodingKeys: String, CodingKey {
        case attendeeCount = "attendee_count"
        case matchedCount = "matched_count"
        case warningCount = "warning_count"
    }
}
