import Foundation

struct ResolvedSourceDirectory {
    let path: String
    let studentsURL: URL
    let appleCEOURL: URL
}

enum ImportError: Error, LocalizedError {
    case sourceNotFound

    var errorDescription: String? {
        switch self {
        case .sourceNotFound:
            return "找不到 OpenClaw/Data 正式資料目錄"
        }
    }
}

struct JSONImportService {
    func resolveSourceDirectory() throws -> ResolvedSourceDirectory {
        let fm = FileManager.default
        let cwd = URL(fileURLWithPath: fm.currentDirectoryPath)
        let candidates = [
            cwd.appendingPathComponent("../../OpenClaw/Data").standardizedFileURL,
            cwd.appendingPathComponent("../OpenClaw/Data").standardizedFileURL,
            cwd.appendingPathComponent("OpenClaw/Data").standardizedFileURL,
            URL(fileURLWithPath: "/Users/aios/Projects/00.AI-Notes_Local/OpenClaw/Data")
        ]

        for candidate in candidates {
            let students = candidate.appendingPathComponent("students.json")
            let appleCEO = candidate.appendingPathComponent("apple_ceo_class.json")
            if fm.fileExists(atPath: students.path), fm.fileExists(atPath: appleCEO.path) {
                return ResolvedSourceDirectory(
                    path: candidate.path,
                    studentsURL: students,
                    appleCEOURL: appleCEO
                )
            }
        }
        throw ImportError.sourceNotFound
    }

    func importAll(into db: DatabaseManager, sourceDirectory: ResolvedSourceDirectory) throws {
        let decoder = JSONDecoder()
        let students = try decoder.decode([StudentsJSONRecord].self, from: Data(contentsOf: sourceDirectory.studentsURL))
        let apple = try decoder.decode(AppleCEOJSONRoot.self, from: Data(contentsOf: sourceDirectory.appleCEOURL))

        try db.resetImportedData()

        for student in students {
            let inferredMetadata = inferStudentMetadata(for: student, sourceDirectory: sourceDirectory)
            try db.insertStudent(
                StudentRecord(
                    id: student.id,
                    name: student.name,
                    aliases: student.aliases ?? [],
                    file: student.file ?? "",
                    lessonsCount: student.lessonsCount ?? inferredMetadata.lessonsCount ?? 0,
                    latestDate: student.latestDate ?? "",
                    nextLesson: student.nextLesson ?? inferredMetadata.nextLesson ?? "",
                    tags: student.tags ?? []
                )
            )
        }

        try insertMeta(scope: "program", values: [
            "id": apple.program.id,
            "name": apple.program.name,
            "url": apple.program.url,
            "description": apple.program.description,
            "schedule": apple.program.schedule,
            "capacity": apple.program.capacity,
            "round_size": String(apple.program.roundSize),
            "price_per_student": String(apple.program.pricePerStudent),
            "validity_rule": apple.program.validityRule,
            "leave_rule": apple.program.leaveRule,
            "join_rule": apple.program.joinRule,
        ], db: db)

        try insertMeta(scope: "venue", values: [
            "name": apple.venue.name,
            "address": apple.venue.address,
            "parking": apple.venue.parking,
            "metro": apple.venue.metro,
            "cost_per_person": String(apple.venue.costPerPerson),
        ], db: db)

        for record in apple.attendanceRecords {
            try db.insertAttendance(
                AttendanceRecord(
                    id: "attendance-\(record.date)",
                    date: record.date,
                    venue: record.venue,
                    attendeeCount: record.attendeeCount,
                    attendeeDetails: record.attendeeDetails,
                    note: record.note
                )
            )
        }

        for (index, record) in apple.venueLedger.enumerated() {
            try db.insertVenueLedger(
                VenueLedgerRecord(
                    id: "ledger-\(record.date)-\(index)",
                    date: record.date,
                    type: record.type,
                    amount: record.amount,
                    headcount: record.headcount,
                    note: record.note,
                    balanceAfter: record.balanceAfter
                )
            )
        }

        for student in apple.studentRounds {
            for (index, round) in student.rounds.enumerated() {
                let sessions = round.sessions
                let attendedCount = sessions.filter { !$0.isEmpty }.count
                let expiry = expiryDate(from: sessions.first)
                let isExpired = expiry.map { Date() > $0 } ?? false
                let expiryString = expiry.map(Self.dateFormatter.string(from:))
                try db.insertRound(
                    StudentRoundRecord(
                        id: "round-\(student.studentName)-\(index)",
                        studentName: student.studentName,
                        label: round.label,
                        paymentStatus: round.paymentStatus,
                        sessions: sessions,
                        attendedCount: attendedCount,
                        expiryDate: expiryString,
                        isExpired: isExpired,
                        isActive: round.label.contains("進行中"),
                        sortOrder: index
                    ),
                    sortOrder: index
                )
            }
        }
    }

    func exportAppleCEOJSON(
        sourceDirectory: ResolvedSourceDirectory,
        program: ProgramInfo,
        venue: VenueInfo,
        summary: AppleCEOSummary,
        attendanceRecords: [AttendanceRecord],
        venueLedger: [VenueLedgerRecord],
        roundGroups: [StudentRoundGroup]
    ) throws {
        let decoder = JSONDecoder()
        let existing = try decoder.decode(AppleCEOExportRoot.self, from: Data(contentsOf: sourceDirectory.appleCEOURL))

        let exportRoot = AppleCEOExportRoot(
            program: ProgramExportJSON(
                id: program.id,
                name: program.name,
                url: program.url,
                description: program.description,
                schedule: program.schedule,
                capacity: program.capacity,
                roundSize: program.roundSize,
                pricePerStudent: program.pricePerStudent,
                validityRule: program.validityRule,
                leaveRule: program.leaveRule,
                joinRule: program.joinRule
            ),
            venue: VenueExportJSON(
                name: venue.name,
                address: venue.address,
                parking: venue.parking,
                metro: venue.metro,
                costPerPerson: venue.costPerPerson
            ),
            activeParticipants: summary.activeStudents,
            attendanceRecords: attendanceRecords
                .sorted { $0.date < $1.date }
                .map {
                    AttendanceExportJSON(
                        date: $0.date,
                        venue: $0.venue,
                        attendeeCount: $0.attendeeCount,
                        attendees: $0.attendeeDetails,
                        note: $0.note
                    )
                },
            venueLedger: venueLedger
                .sorted { lhs, rhs in
                    if lhs.date == rhs.date { return lhs.id < rhs.id }
                    return lhs.date < rhs.date
                }
                .map {
                    VenueLedgerExportJSON(
                        date: $0.date,
                        type: $0.type,
                        amount: $0.amount,
                        headcount: $0.headcount,
                        note: $0.note,
                        balanceAfter: $0.balanceAfter
                    )
                },
            studentRounds: roundGroups
                .sorted { $0.studentName < $1.studentName }
                .map { group in
                    let rounds = ([group.latestRound].compactMap { $0 } + group.historyRounds)
                        .sorted { $0.sortOrder < $1.sortOrder }
                        .map {
                            RoundExportJSON(
                                label: $0.label,
                                paymentStatus: $0.paymentStatus,
                                sessions: $0.sessions
                            )
                        }
                    return StudentRoundsExportJSON(studentName: group.studentName, rounds: rounds)
                },
            legacyNote: existing.legacyNote
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(exportRoot)
        try data.write(to: sourceDirectory.appleCEOURL, options: .atomic)
    }

    private func insertMeta(scope: String, values: [String: String], db: DatabaseManager) throws {
        for (key, value) in values {
            try db.insertMeta(scope: scope, key: key, value: value)
        }
    }

    private func inferStudentMetadata(for student: StudentsJSONRecord, sourceDirectory: ResolvedSourceDirectory) -> StudentFileMetadata {
        guard let file = student.file, !file.isEmpty else { return StudentFileMetadata() }

        let projectRoot = URL(fileURLWithPath: sourceDirectory.path)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let studentFileURL = projectRoot.appendingPathComponent(file.trimmingCharacters(in: CharacterSet(charactersIn: "/")))

        guard let content = try? String(contentsOf: studentFileURL, encoding: .utf8) else {
            return StudentFileMetadata()
        }

        return parseFrontmatter(from: content)
    }

    private func parseFrontmatter(from content: String) -> StudentFileMetadata {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        guard normalized.hasPrefix("---\n") else { return StudentFileMetadata() }

        let parts = normalized.components(separatedBy: "\n---\n")
        guard parts.count >= 2 else { return StudentFileMetadata() }

        let frontmatter = parts[0]
        var lessonsCount: Int?
        var nextLesson: String?

        for rawLine in frontmatter.components(separatedBy: "\n") {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.hasPrefix("lessons_count:") {
                let value = line.replacingOccurrences(of: "lessons_count:", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
                lessonsCount = Int(value.replacingOccurrences(of: "\"", with: ""))
            } else if line.hasPrefix("next_lesson:") {
                let value = line.replacingOccurrences(of: "next_lesson:", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
                nextLesson = value.replacingOccurrences(of: "\"", with: "")
            }
        }

        return StudentFileMetadata(lessonsCount: lessonsCount, nextLesson: nextLesson)
    }

    private func expiryDate(from firstSession: String?) -> Date? {
        guard let firstSession, !firstSession.isEmpty,
              let date = Self.dateFormatter.date(from: firstSession) else { return nil }
        return Calendar.current.date(byAdding: .month, value: 4, to: date)
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "zh_Hant_TW")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

private struct StudentsJSONRecord: Decodable {
    let id: String
    let name: String
    let aliases: [String]?
    let file: String?
    let lessonsCount: Int?
    let tags: [String]?
    let nextLesson: String?
    let latestDate: String?

    enum CodingKeys: String, CodingKey {
        case id, name, aliases, file, tags
        case lessonsCount = "lessons_count"
        case nextLesson = "next_lesson"
        case latestDate = "latest_date"
    }
}

private struct StudentFileMetadata {
    var lessonsCount: Int?
    var nextLesson: String?
}

private struct AppleCEOJSONRoot: Decodable {
    let program: ProgramJSON
    let venue: VenueJSON
    let attendanceRecords: [AttendanceJSON]
    let venueLedger: [VenueLedgerJSON]
    let studentRounds: [StudentRoundsJSON]

    enum CodingKeys: String, CodingKey {
        case program, venue
        case attendanceRecords = "attendance_records"
        case venueLedger = "venue_ledger"
        case studentRounds = "student_rounds"
    }
}

private struct ProgramJSON: Decodable {
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

    enum CodingKeys: String, CodingKey {
        case id, name, url, description, schedule, capacity
        case roundSize = "round_size"
        case pricePerStudent = "price_per_student"
        case validityRule = "validity_rule"
        case leaveRule = "leave_rule"
        case joinRule = "join_rule"
    }
}

private struct VenueJSON: Decodable {
    let name: String
    let address: String
    let parking: String
    let metro: String
    let costPerPerson: Int

    enum CodingKeys: String, CodingKey {
        case name, address, parking, metro
        case costPerPerson = "cost_per_person"
    }
}

 private struct AttendanceJSON: Decodable {
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendeeDetails: [AttendeeDetail]
    let note: String

    enum CodingKeys: String, CodingKey {
        case date, venue, note
        case attendeeCount = "attendee_count"
        case attendees = "attendees"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        date = try container.decode(String.self, forKey: .date)
        venue = try container.decode(String.self, forKey: .venue)
        attendeeCount = try container.decode(Int.self, forKey: .attendeeCount)
        note = try container.decode(String.self, forKey: .note)

        if let details = try? container.decode([AttendeeDetail].self, forKey: .attendees) {
            attendeeDetails = details
        } else if let names = try? container.decode([String].self, forKey: .attendees) {
            attendeeDetails = names.map { AttendeeDetail(name: $0, cumulative: "") }
        } else {
            attendeeDetails = []
        }
    }
}

private struct VenueLedgerJSON: Decodable {
    let date: String
    let type: String
    let amount: Int
    let headcount: Int?
    let note: String
    let balanceAfter: Int

    enum CodingKeys: String, CodingKey {
        case date, type, amount, headcount, note
        case balanceAfter = "balance_after"
    }
}

private struct StudentRoundsJSON: Decodable {
    let studentName: String
    let rounds: [RoundJSON]

    enum CodingKeys: String, CodingKey {
        case rounds
        case studentName = "student_name"
    }
}

private struct RoundJSON: Decodable {
    let label: String
    let paymentStatus: String
    let sessions: [String]

    enum CodingKeys: String, CodingKey {
        case label, sessions
        case paymentStatus = "payment_status"
    }
}

private struct AppleCEOExportRoot: Codable {
    let program: ProgramExportJSON
    let venue: VenueExportJSON
    let activeParticipants: [String]
    let attendanceRecords: [AttendanceExportJSON]
    let venueLedger: [VenueLedgerExportJSON]
    let studentRounds: [StudentRoundsExportJSON]
    let legacyNote: String

    enum CodingKeys: String, CodingKey {
        case program, venue
        case activeParticipants = "active_participants"
        case attendanceRecords = "attendance_records"
        case venueLedger = "venue_ledger"
        case studentRounds = "student_rounds"
        case legacyNote = "legacy_note"
    }
}

private struct ProgramExportJSON: Codable {
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

    enum CodingKeys: String, CodingKey {
        case id, name, url, description, schedule, capacity
        case roundSize = "round_size"
        case pricePerStudent = "price_per_student"
        case validityRule = "validity_rule"
        case leaveRule = "leave_rule"
        case joinRule = "join_rule"
    }
}

private struct VenueExportJSON: Codable {
    let name: String
    let address: String
    let parking: String
    let metro: String
    let costPerPerson: Int

    enum CodingKeys: String, CodingKey {
        case name, address, parking, metro
        case costPerPerson = "cost_per_person"
    }
}

private struct AttendanceExportJSON: Codable {
    let date: String
    let venue: String
    let attendeeCount: Int
    let attendees: [AttendeeDetail]
    let note: String

    enum CodingKeys: String, CodingKey {
        case date, venue, attendees, note
        case attendeeCount = "attendee_count"
    }
}

private struct VenueLedgerExportJSON: Codable {
    let date: String
    let type: String
    let amount: Int
    let headcount: Int?
    let note: String
    let balanceAfter: Int

    enum CodingKeys: String, CodingKey {
        case date, type, amount, headcount, note
        case balanceAfter = "balance_after"
    }
}

private struct StudentRoundsExportJSON: Codable {
    let studentName: String
    let rounds: [RoundExportJSON]

    enum CodingKeys: String, CodingKey {
        case rounds
        case studentName = "student_name"
    }
}

private struct RoundExportJSON: Codable {
    let label: String
    let paymentStatus: String
    let sessions: [String]

    enum CodingKeys: String, CodingKey {
        case label, sessions
        case paymentStatus = "payment_status"
    }
}
